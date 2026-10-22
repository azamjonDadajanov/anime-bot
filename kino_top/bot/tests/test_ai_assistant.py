"""``🤖 AI yordamchi``: AniVoy behind the subscription gate, in the real bot.

Driven through the dispatcher, so the mandatory-channel gate, the FSM state and
the rendered answer are exercised the way the user meets them. The online model
is mocked at ``movies.llm.chat_completion`` only — the catalogue tools are the
real ones, reading the test database, which is what makes these tests describe
"the assistant looked this up" rather than "a payload was returned".
"""

from __future__ import annotations

import json
from datetime import timedelta
from unittest import mock

from django.test import override_settings
from django.utils import timezone
from movies import ai_assistant, llm
from movies.models import Genre, MediaTitle, TelegramChannel, TitleComment, TitleRating
from users.models import (
	FavoriteContent,
	Subscription,
	SubscriptionRequest,
	TelegramUser,
	UserSettings,
)

from .. import callbacks as cb
from ..models import BotSettings
from ..texts import (
	AI_ACTION_CANCELLED,
	AI_ACTION_DONE,
	AI_ACTION_EDIT_ASK,
	AI_ACTION_HEADER,
	AI_ACTION_INVALID,
	AI_ACTION_LINKED,
	AI_ASSISTANT_REQUIRED,
	AI_ASSISTANT_THINKING,
	AI_ASSISTANT_UNAVAILABLE,
	SUBREQ_SAVED,
)
from ..utils import escape_html
from .base import DispatcherTestCase
from .fakes import ADMIN, USER, build_callback, build_command, build_message, fake_photo
from .helpers import bot_env, make_channel

SITE = "https://anichopar.uz"
QUERY = "menga sarguzasht va qo'rqinchli animelar ayt"


def tool_call(name: str, arguments: dict, call_id: str = "call-1") -> llm.ChatResult:
	return llm.ChatResult(
		content="",
		tool_calls=(llm.ToolCall(id=call_id, name=name, arguments=json.dumps(arguments)),),
	)


def say(text: str) -> llm.ChatResult:
	return llm.ChatResult(content=text)


def make_title(*, title: str, genres=(), synopsis: str = "", media_type=MediaTitle.MediaType.ANIME):
	media = MediaTitle.objects.create(type=media_type, title=title, synopsis=synopsis)
	if genres:
		media.genres.set([Genre.objects.get_or_create(name=name)[0] for name in genres])
	return media


class AIAssistantBotTests(DispatcherTestCase):
	def setUp(self) -> None:
		super().setUp()
		# A fake key keeps ``llm.is_configured()`` true; every completion is
		# mocked per test, so no request ever leaves the process.
		self.override = override_settings(
			AI_LLM_ENABLED=True,
			AI_LLM_API_KEY="test-key-4829",
			AI_LLM_MODEL="",
			AI_LLM_BASE_URL="",
		)
		self.override.enable()
		self.addCleanup(self.override.disable)
		ai_assistant.clear_cache()
		self.addCleanup(ai_assistant.clear_cache)
		llm.reset_cooldowns()
		llm.reset_signature_cache()
		self.addCleanup(llm.reset_cooldowns)
		self.addCleanup(llm.reset_signature_cache)
		self.feed(build_command("start"))
		self.update_id = 700

	def _press(self, data: str) -> None:
		self.update_id += 1
		self.feed(build_callback(data, update_id=self.update_id))

	def _ask(self, text: str) -> None:
		self.update_id += 1
		self.feed(build_message(text, update_id=self.update_id))

	def _subscribe(self, *, plan: str = "monthly", days: int = 30) -> None:
		user = TelegramUser.objects.get(telegram_id=USER.id).auth_user
		subscription, _ = Subscription.objects.get_or_create(user=user)
		subscription.plan = plan
		subscription.started_at = timezone.now()
		subscription.expires_at = timezone.now() + timedelta(days=days)
		subscription.save(update_fields=["plan", "started_at", "expires_at", "updated_at"])

	# ------------------------------------------------------------- the button
	def test_the_search_screen_no_longer_offers_ai(self) -> None:
		"""The assistant left the search screen: it has its own main-menu button."""
		self.session.reset()
		self._press(cb.SEARCH)

		self.assertNotIn("AI yordamchi", self.button_texts())
		self.assertIn("🎌 Anime", self.button_texts())

	def test_a_free_user_does_not_see_the_assistant_button(self) -> None:
		self.session.reset()
		self._press(cb.MENU)

		self.assertNotIn("🤖 AI yordamchi", self.button_texts())
		self.assertIn("🔍 Qidirish", self.button_texts())

	def test_a_subscriber_sees_the_assistant_button(self) -> None:
		self._subscribe()
		self.session.reset()
		self._press(cb.MENU)

		self.assertIn("🤖 AI yordamchi", self.button_texts())

	def test_a_visitor_without_a_subscription_is_refused(self) -> None:
		self.session.reset()
		self._press(cb.AI_ASSISTANT)

		self.assertIn(AI_ASSISTANT_REQUIRED.split("\n")[0].replace("</b>", ""), self.all_text())

	def test_an_expired_subscription_is_refused(self) -> None:
		self._subscribe(days=-2)
		self.session.reset()

		self._press(cb.AI_ASSISTANT)

		self.assertIn("faqat obunachilar uchun", self.all_text())

	def test_the_prompt_offers_examples_and_the_favourites_toggle(self) -> None:
		self._subscribe()
		self.session.reset()

		self._press(cb.AI_ASSISTANT)

		self.assertIn("AI yordamchi", self.all_text())
		self.assertIn("sevimlilarimga o'xshash nima bor?", self.all_text())
		self.assertIn("🎯 Sevimlilar: ❌", self.button_texts())

	def test_the_mandatory_channel_gate_still_applies(self) -> None:
		settings = BotSettings.get_solo()
		settings.require_subscription = True
		settings.save(update_fields=["require_subscription", "updated_at"])
		make_channel(
			chat_id=-1005550009999,
			title="Majburiy kanal",
			purpose=TelegramChannel.Purpose.REQUIRED,
		)
		self.session.member_status = "left"
		self._subscribe()
		self.session.reset()

		self._press(cb.AI_ASSISTANT)

		self.assertIn("Majburiy obuna", self.all_text())

	# ------------------------------------------------------------ the answers
	def test_a_subscriber_receives_the_titles_the_tool_found(self) -> None:
		title = make_title(
			title="Qorong'i O'rmon",
			genres=["Qo'rqinchli", "Sarguzasht"],
			synopsis="Qo'rqinchli o'rmonda kechgan sarguzasht. Davomi bor.",
		)
		self._subscribe()
		self.session.reset()
		completions = mock.Mock(
			side_effect=[
				tool_call("search_catalog", {"janr": "Qo'rqinchli"}),
				say(f"«{title.title}» aynan sizga mos keladi."),
			]
		)

		with bot_env(BOT_SITE_URL=SITE), mock.patch(
			"movies.llm.chat_completion", completions
		):
			self._press(cb.AI_ASSISTANT)
			self.session.reset()
			self._ask(QUERY)

		self.assertIn(AI_ASSISTANT_THINKING, self.session.sent_texts())
		edits = "\n".join(method.text for method in self.session.methods("EditMessageText"))
		self.assertIn(f'href="{SITE}/media/{title.slug}"', edits)
		self.assertIn(escape_html(title.title), edits)
		self.assertIn("AniVoy javobi", edits)
		self.assertIn(escape_html(f"«{title.title}» aynan sizga mos keladi."), edits)
		# The list shape: the link line, its metadata, then the one-sentence
		# summary underneath it.
		lines = [line for line in edits.split("\n") if line.strip()]
		link_index = next(
			index for index, line in enumerate(lines) if f"/media/{title.slug}" in line
		)
		self.assertIn(" · ", lines[link_index + 1])
		self.assertEqual(
			lines[link_index + 2].strip(),
			escape_html("Qo'rqinchli o'rmonda kechgan sarguzasht."),
		)
		self.assertIn(title.title, self.button_texts())
		self.assertIn("🔎 Yana so'rash", self.button_texts())

	def test_a_conversational_question_is_answered_without_a_list(self) -> None:
		make_title(title="Qorong'i O'rmon", genres=["Qo'rqinchli"])
		self._subscribe()
		self.session.reset()

		with mock.patch(
			"movies.llm.chat_completion",
			mock.Mock(return_value=say("Men AniVoyman, shu platformada ishlayman.")),
		):
			self._press(cb.AI_ASSISTANT)
			self.session.reset()
			self._ask("sen kimsan")

		edits = "\n".join(method.text for method in self.session.methods("EditMessageText"))
		self.assertIn(escape_html("Men AniVoyman, shu platformada ishlayman."), edits)
		self.assertNotIn("topilganlar", edits)
		self.assertNotIn("mos kontent topilmadi", edits)
		self.assertIn("🎯 Sevimlilar", self.button_texts())

	def test_the_answer_is_sent_with_allowed_markdown_tags(self) -> None:
		"""The model writes markdown; Telegram gets only its own HTML tags."""
		self._subscribe()
		self.session.reset()
		answer = "**Naruto** — *sarguzasht* anime.\n- Uzumaki\n- Hokage\n\n`1999` yilda chiqqan."

		with mock.patch(
			"movies.llm.chat_completion", mock.Mock(return_value=say(answer))
		):
			self._press(cb.AI_ASSISTANT)
			self.session.reset()
			self._ask("naruto nima haqida")

		edits = "\n".join(method.text for method in self.session.methods("EditMessageText"))
		self.assertIn("<b>Naruto</b>", edits)
		self.assertIn("<i>sarguzasht</i>", edits)
		self.assertIn("• Uzumaki", edits)
		self.assertIn("<code>1999</code>", edits)
		# No raw markdown markers survive to the chat.
		self.assertNotIn("**", edits)
		self.assertNotIn("`", edits)

	def test_a_missing_model_is_reported_without_a_local_fallback(self) -> None:
		make_title(title="Qorong'i O'rmon", genres=["Qo'rqinchli"])
		self._subscribe()
		self.session.reset()

		with mock.patch(
			"movies.llm.chat_completion",
			side_effect=llm.LLMUnavailable("provider yiqildi"),
		):
			self._press(cb.AI_ASSISTANT)
			self.session.reset()
			self._ask(QUERY)

		self.assertIn(AI_ASSISTANT_UNAVAILABLE.split("\n")[0], self.all_text())
		# The main menu still works; there is no result list to fall back to.
		self.assertIn("🔍 Qidirish", self.button_texts())

	def test_the_administrator_sees_the_reason(self) -> None:
		"""The operator needs to know *why*: a dead model or a spent quota.

		Everybody else gets the same sentence — the reason is a technical
		detail that would only confuse a subscriber.
		"""
		self.session.reset()
		with bot_env(ADMIN_IDS=str(ADMIN.id)):
			# The administrator has to be a subscriber as well: the assistant
			# is behind the same gate for everybody.
			self.feed(build_command("start", user=ADMIN, update_id=690))
			user = TelegramUser.objects.get(telegram_id=ADMIN.id).auth_user
			subscription, _ = Subscription.objects.get_or_create(user=user)
			subscription.plan = "monthly"
			subscription.started_at = timezone.now()
			subscription.expires_at = timezone.now() + timedelta(days=30)
			subscription.save(
				update_fields=["plan", "started_at", "expires_at", "updated_at"]
			)

			with mock.patch(
				"movies.llm.chat_completion",
				side_effect=llm.LLMUnavailable("Gemini HTTP 404: model topilmadi"),
			):
				self.update_id += 1
				self.feed(
					build_callback(
						cb.AI_ASSISTANT, user=ADMIN, update_id=self.update_id
					)
				)
				self.session.reset()
				self.update_id += 1
				self.feed(build_message(QUERY, user=ADMIN, update_id=self.update_id))

		self.assertIn("Sabab:", self.all_text())
		self.assertIn("404", self.all_text())

	def test_an_empty_message_keeps_the_prompt_open(self) -> None:
		self._subscribe()
		self.session.reset()

		self._press(cb.AI_ASSISTANT)
		self.session.reset()
		self._ask("   ")

		self.assertIn("Iltimos, matn yoki kod yuboring.", self.all_text())

	def test_a_digit_question_inside_the_assistant_is_not_a_code_lookup(self) -> None:
		make_title(title="Kodli Anime", genres=["Sarguzasht"])
		self._subscribe()
		self.session.reset()

		with mock.patch(
			"movies.llm.chat_completion",
			mock.Mock(return_value=say("1997 yilda chiqqan anime bormi? Ha.")),
		):
			self._press(cb.AI_ASSISTANT)
			self.session.reset()
			self._ask("1997")

		self.assertIn("1997", self.all_text())
		self.assertNotIn("🆔 Kod:", self.all_text())

	# ------------------------------------------------- the favourites opt-in
	def test_the_toggle_flips_the_label(self) -> None:
		self._subscribe()
		self.session.reset()

		self._press(cb.AI_ASSISTANT)
		self.assertIn("🎯 Sevimlilar: ❌", self.button_texts())

		self.session.reset()
		self._press(cb.AI_PERSONAL)
		self.assertIn("🎯 Sevimlilar: ✅", self.visible())

		self.session.reset()
		self._press(cb.AI_PERSONAL)
		self.assertIn("🎯 Sevimlilar: ❌", self.button_texts())

	def test_the_toggle_off_means_the_model_cannot_read_the_favourites(self) -> None:
		self._subscribe()
		profile = TelegramUser.objects.get(telegram_id=USER.id)
		favorite = make_title(title="Vagabond", genres=["Drama"])
		FavoriteContent.objects.create(user=profile, content=favorite)
		self.session.reset()
		completions = mock.Mock(return_value=say("Javob."))

		with mock.patch("movies.llm.chat_completion", completions):
			self._press(cb.AI_ASSISTANT)
			self.session.reset()
			self._ask(QUERY)

		offered = [
			tool["function"]["name"] for tool in completions.call_args_list[0].kwargs["tools"]
		]
		self.assertNotIn("personal_taste", offered)

	def test_the_toggle_on_offers_the_personal_tool(self) -> None:
		self._subscribe()
		profile = TelegramUser.objects.get(telegram_id=USER.id)
		favorite = make_title(title="Vagabond", genres=["Drama"])
		FavoriteContent.objects.create(user=profile, content=favorite)
		self.session.reset()
		completions = mock.Mock(return_value=say("Javob."))

		with mock.patch("movies.llm.chat_completion", completions):
			self._press(cb.AI_ASSISTANT)
			self.session.reset()
			self._press(cb.AI_PERSONAL)
			self.session.reset()
			self._ask("sevimlilarimga o'xshashini top")

		offered = [
			tool["function"]["name"] for tool in completions.call_args_list[0].kwargs["tools"]
		]
		self.assertIn("personal_taste", offered)


class AIActionCardBotTests(DispatcherTestCase):
	"""The proposed amal: edit a field, confirm, or cancel — in the real bot.

	The card itself is built server-side by ``movies.ai_actions``; these
	tests drive what the user meets: the rendered values, the per-field
	buttons, the shared screenshot state of «Obuna», and the fact that
	«Bekor qilish» writes nothing at all.
	"""

	def setUp(self) -> None:
		super().setUp()
		self.override = override_settings(
			AI_LLM_ENABLED=True,
			AI_LLM_API_KEY="test-key-4829",
			AI_LLM_MODEL="",
			AI_LLM_BASE_URL="",
		)
		self.override.enable()
		self.addCleanup(self.override.disable)
		ai_assistant.clear_cache()
		self.addCleanup(ai_assistant.clear_cache)
		llm.reset_cooldowns()
		llm.reset_signature_cache()
		self.addCleanup(llm.reset_cooldowns)
		self.addCleanup(llm.reset_signature_cache)
		self.feed(build_command("start"))
		self.profile = TelegramUser.objects.get(telegram_id=USER.id)
		user = self.profile.auth_user
		subscription, _ = Subscription.objects.get_or_create(user=user)
		subscription.plan = "monthly"
		subscription.started_at = timezone.now()
		subscription.expires_at = timezone.now() + timedelta(days=30)
		subscription.save(update_fields=["plan", "started_at", "expires_at", "updated_at"])
		self.update_id = 700

	# ------------------------------------------------------------- plumbing
	def _press(self, data: str) -> None:
		self.update_id += 1
		self.feed(build_callback(data, update_id=self.update_id))

	def _ask(self, text: str) -> None:
		self.update_id += 1
		self.feed(build_message(text, update_id=self.update_id))

	def _propose(self, amal: str, qiymatlar: dict, words: str = "Amalni tasdiqlang.") -> None:
		"""One model turn that asks for an action, then writes its short answer."""
		completions = mock.Mock(
			side_effect=[
				tool_call("submit_action", {"amal": amal, "qiymatlar": qiymatlar}),
				say(words),
			]
		)
		with mock.patch("movies.llm.chat_completion", completions):
			self._press(cb.AI_ASSISTANT)
			self.session.reset()
			self._ask("shu amalni bajar")

	def _edits(self) -> str:
		return "\n".join(method.text for method in self.session.methods("EditMessageText"))

	def _last_edit(self) -> str:
		edits = self.session.methods("EditMessageText")
		return edits[-1].text if edits else ""

	def comment_title(self) -> MediaTitle:
		return make_title(title="Qorongi Ormon")

	# ------------------------------------------------------- the card itself
	def test_the_comment_card_shows_the_values_and_the_confirm_buttons(self) -> None:
		title = self.comment_title()

		self._propose(
			"write_comment",
			{"title_id": title.pk, "body": "Zor anime edi", "score": 9},
			words="Izoh tayyor.",
		)

		edits = self._edits()
		self.assertIn(AI_ACTION_HEADER.format(label="Izoh yozish"), edits)
		self.assertIn("<b>Kontent</b>: Qorongi Ormon", edits)
		self.assertIn("<b>Yulduzchalar</b>: 9/10", edits)
		self.assertIn("<b>Izoh matni</b>: Zor anime edi", edits)
		self.assertIn("Izoh tayyor.", edits)
		self.assertIn("✅ Tasdiqlash", self.button_texts())
		self.assertIn("❌ Bekor qilish", self.button_texts())

	def test_confirming_writes_the_comment_and_the_score(self) -> None:
		title = self.comment_title()
		self._propose(
			"write_comment",
			{"title_id": title.pk, "body": "Zor anime edi", "score": 9},
		)
		self.session.reset()

		self._press(cb.AI_ACTION_OK)

		comment = TitleComment.objects.get()
		self.assertEqual(comment.body, "Zor anime edi")
		self.assertEqual(comment.title_id, title.pk)
		self.assertEqual(comment.source, TitleComment.Source.BOT)
		self.assertEqual(TitleRating.objects.get().score, 9)
		text = self.all_text()
		self.assertIn(
			AI_ACTION_DONE.format(
				label="Izoh yozish", message="Izoh va yulduzcha saqlandi."
			),
			text,
		)
		# …and the assistant screen is back, ready for the next question.
		self.assertIn("🎯 Sevimlilar: ❌", self.button_texts())

	def test_cancelling_writes_nothing_and_keeps_the_assistant_open(self) -> None:
		title = self.comment_title()
		self._propose("write_comment", {"title_id": title.pk, "body": "Bekor qilinadigan"})
		self.session.reset()

		self._press(cb.AI_ACTION_NO)

		self.assertIn(AI_ACTION_CANCELLED, self.all_text())
		self.assertFalse(TitleComment.objects.exists())
		self.assertNotIn("✅ Tasdiqlash", self.button_texts())

		# The conversation continues as if the card never happened.
		self.session.reset()
		with mock.patch("movies.llm.chat_completion", mock.Mock(return_value=say("Tushunarli."))):
			self._ask("rahmat")
		self.assertIn("Tushunarli.", self.all_text())

	def test_the_score_steppers_stay_inside_the_range(self) -> None:
		title = self.comment_title()
		self._propose("set_rating", {"title_id": title.pk, "score": 9})
		self.session.reset()

		self._press(f"{cb.AI_ACTION_ADJ}:score:-1")
		self.assertIn("<b>Yulduzchalar</b>: 8/10", self._last_edit())

		self._press(f"{cb.AI_ACTION_ADJ}:score:+1")
		self._press(f"{cb.AI_ACTION_ADJ}:score:+1")
		self._press(f"{cb.AI_ACTION_ADJ}:score:+1")  # clamped at the maximum
		self.assertIn("<b>Yulduzchalar</b>: 10/10", self._last_edit())
		self.assertFalse(TitleRating.objects.exists())

		self._press(cb.AI_ACTION_OK)
		self.assertEqual(TitleRating.objects.get().score, 10)

	def test_the_text_editor_rewrites_the_body(self) -> None:
		title = self.comment_title()
		self._propose("write_comment", {"title_id": title.pk, "body": "Zor anime edi"})
		self.session.reset()

		self._press(f"{cb.AI_ACTION_EDIT}:body")
		self.assertIn(AI_ACTION_EDIT_ASK.format(label="Izoh matni"), self.all_text())
		self.assertIn("⬅️ Ortga", self.button_texts())

		self.session.reset()
		self._ask("Yangilangan izoh")
		self.assertIn("<b>Izoh matni</b>: Yangilangan izoh", self.texts())

		self.session.reset()
		self._press(cb.AI_ACTION_OK)
		self.assertEqual(TitleComment.objects.get().body, "Yangilangan izoh")

	def test_the_back_button_returns_to_the_card_unchanged(self) -> None:
		title = self.comment_title()
		self._propose("write_comment", {"title_id": title.pk, "body": "Zor anime edi"})
		self.session.reset()

		self._press(f"{cb.AI_ACTION_EDIT}:body")
		self.session.reset()
		self._press(cb.AI_ACTION_BACK)

		self.assertIn("<b>Izoh matni</b>: Zor anime edi", self._last_edit())
		self.assertIn("✅ Tasdiqlash", self.button_texts())
		self.assertEqual(self._assistant_state(), "UserAssistantStates:query")

	def test_an_empty_required_text_is_refused_and_the_editor_reopens(self) -> None:
		title = self.comment_title()
		self._propose("write_comment", {"title_id": title.pk, "body": "Zor anime edi"})
		self.session.reset()
		self._press(f"{cb.AI_ACTION_EDIT}:body")
		self.session.reset()

		self._ask("   ")

		self.assertIn(
			AI_ACTION_INVALID.format(detail="Qiymat bo'sh bo'lmasligi kerak."),
			self.all_text(),
		)
		# Still in the editor: the next message lands on the card, not on the
		# model (which is mocked here so a stray query cannot go online).
		self.session.reset()
		with mock.patch(
			"movies.llm.chat_completion", mock.Mock(return_value=say("MODEL_KERAK_EMAS"))
		) as chat:
			self._ask("Endi togri matn")
		self.assertIn("<b>Izoh matni</b>: Endi togri matn", self.texts())
		self.assertEqual(chat.call_count, 0)

	def test_the_theme_select_cycles_and_confirm_saves(self) -> None:
		self._propose("set_theme", {"theme": "light"})
		self.assertIn("<b>Mavzu</b>: Kunduzgi", self._last_edit())
		self.session.reset()

		self._press(f"{cb.AI_ACTION_CYCLE}:theme")
		self.assertIn("<b>Mavzu</b>: Tungi", self._last_edit())

		self._press(cb.AI_ACTION_OK)
		self.assertEqual(UserSettings.objects.get(user=self.profile.auth_user).theme, "dark")

	def test_the_bool_toggle_flips_and_confirm_saves(self) -> None:
		self._propose("set_reduce_motion", {"enabled": True})
		self.assertIn("<b>Harakatlarni kamaytirish</b>: yoqilgan", self._last_edit())
		self.assertIn("✅ Harakatlarni kamaytirish", self.button_texts())
		self.session.reset()

		self._press(f"{cb.AI_ACTION_TOGGLE}:enabled")
		self.assertIn("<b>Harakatlarni kamaytirish</b>: o&#x27;chirilgan", self._last_edit())
		self.assertIn("❌ Harakatlarni kamaytirish", self.button_texts())

		self._press(cb.AI_ACTION_OK)
		self.assertFalse(UserSettings.objects.get(user=self.profile.auth_user).reduce_motion)

	def test_the_subscription_card_confirm_opens_the_screenshot_state(self) -> None:
		self._propose("subscription_request", {"plan": "monthly"})

		edits = self._edits()
		self.assertIn(AI_ACTION_HEADER.format(label="Obunani uzaytirish"), edits)
		self.assertIn("Tarif", edits)
		self.assertIn("1 oylik", edits)
		self.assertIn("Karta raqami", edits)
		self.session.reset()

		self._press(cb.AI_ACTION_OK)

		self.assertIn("Obuna to'lovi", self.all_text())
		self.assertEqual(SubscriptionRequest.objects.count(), 0)

		self.session.reset()
		self.update_id += 1
		with mock.patch(
			"users.telegram_notify.notify_admins_new_request", return_value=True
		) as notify:
			self.feed(build_message("", update_id=self.update_id, photo=[fake_photo()]))

		self.assertIn(SUBREQ_SAVED, self.all_text())
		self.assertEqual(notify.call_count, 1)
		request = SubscriptionRequest.objects.get()
		self.assertEqual(request.plan, "monthly")
		self.assertEqual(request.status, SubscriptionRequest.Status.PENDING)

	def test_the_link_card_reports_the_connected_state(self) -> None:
		self._propose("link_telegram", {})

		self.assertIn(AI_ACTION_LINKED, self._edits())
		self.assertIn("✅ Ulangan", self.button_texts())
		self.assertNotIn("✅ Tasdiqlash", self.button_texts())
		self.session.reset()

		self._press(cb.AI_ACTION_CHECK)
		self.assertIn(AI_ACTION_LINKED, self._last_edit())

		self._press(cb.AI_ACTION_OK)
		answers = self.session.methods("AnswerCallbackQuery")
		self.assertIn("Ulash tugmalardan bajariladi.", answers[-1].text)

	def _assistant_state(self):
		from aiogram.fsm.storage.base import StorageKey

		from ..models import FSMState
		from ..storage import DjangoStorage

		key = StorageKey(bot_id=999, chat_id=USER.id, user_id=USER.id)
		row = FSMState.objects.filter(key=DjangoStorage().build_key(key)).first()
		return row.state if row is not None else None
