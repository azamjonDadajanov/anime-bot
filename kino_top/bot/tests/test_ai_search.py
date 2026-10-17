"""``🤖 AI orqali qidirish``: semantic search behind the subscription gate.

Driven through the real dispatcher, so the mandatory-subscription gate, the FSM
state and the rendered list are exercised the way the user meets them. The
sentence encoder is replaced by a deterministic fake (``movies.tests.FakeEncoder``)
— the ranking order is not what is under test here, the flow and the copy are.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.test import override_settings
from django.utils import timezone
from movies import ai_reasoning, ai_search, embeddings, llm
from movies.models import Genre, MediaTitle, MediaView, TelegramChannel
from movies.tests import FakeEncoder
from users.models import FavoriteContent, Subscription, TelegramUser

from .. import callbacks as cb
from ..models import BotSettings
from ..texts import (
	AI_SEARCH_REQUIRED,
	AI_SEARCH_RESULTS,
	AI_SEARCH_THINKING,
	AI_SEARCH_UNAVAILABLE,
)
from ..utils import escape_html
from .base import DispatcherTestCase
from .fakes import USER, build_callback, build_command, build_message
from .helpers import bot_env, make_channel

SITE = "https://anichopar.uz"
QUERY = "menga sarguzasht va qo'rqinchli animelar ayt"


def make_ai_title(*, title: str, media_type: str = MediaTitle.MediaType.ANIME, genres=(), synopsis: str = ""):
	"""A catalogue title with the genres and synopsis the AI document needs."""
	media = MediaTitle.objects.create(type=media_type, title=title, synopsis=synopsis)
	if genres:
		media.genres.set([Genre.objects.get_or_create(name=name)[0] for name in genres])
	return media


class AISearchBotTests(DispatcherTestCase):
	def setUp(self) -> None:
		super().setUp()
		# The model is "installed" (stub files) and the encoder is faked, so the
		# flow runs without the real 470MB ONNX graph.
		self.model_dir = tempfile.mkdtemp(prefix="ai-bot-model-")
		self.addCleanup(shutil.rmtree, self.model_dir, ignore_errors=True)
		for name in embeddings.required_files():
			path = Path(self.model_dir) / name
			path.parent.mkdir(parents=True, exist_ok=True)
			path.write_bytes(b"stub")
		self.override = override_settings(
			AI_SEARCH_ENABLED=True,
			AI_SEARCH_MIN_SCORE=0.0,
			AI_SEARCH_TOP_K=5,
			AI_MODEL_DIR=self.model_dir,
		)
		self.override.enable()
		self.addCleanup(self.override.disable)
		patcher = mock.patch("movies.embeddings.load_encoder", return_value=FakeEncoder())
		patcher.start()
		self.addCleanup(patcher.stop)
		ai_search.invalidate_cache()
		self.addCleanup(ai_search.invalidate_cache)
		# The provider chain keeps in-process cooldowns; a leftover from another
		# test would silently skip the "provider" this one expects to be asked.
		llm.reset_cooldowns()
		llm.reset_signature_cache()
		self.addCleanup(llm.reset_cooldowns)

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

	# ------------------------------------------------------------------ the gate
	def test_the_search_screen_offers_the_ai_button(self) -> None:
		self.session.reset()
		self._press(cb.SEARCH)

		self.assertIn("🤖 AI orqali qidirish", self.button_texts())

	def test_a_visitor_without_a_subscription_is_refused(self) -> None:
		self.session.reset()
		self._press(cb.AI_SEARCH)

		self.assertIn(AI_SEARCH_REQUIRED.split("\n")[0].replace("</b>", ""), self.all_text())

	def test_an_expired_subscription_is_refused(self) -> None:
		self._subscribe(days=-2)
		self.session.reset()

		self._press(cb.AI_SEARCH)

		self.assertIn("faqat obunachilar uchun", self.all_text())

	def test_the_prompt_asks_for_the_user_s_own_words(self) -> None:
		self._subscribe()
		self.session.reset()

		self._press(cb.AI_SEARCH)

		self.assertIn("AI qidiruv", self.all_text())
		self.assertIn("sarguzasht va qo'rqinchli animelar", self.all_text())

	def test_the_mandatory_channel_gate_still_applies(self) -> None:
		"""The AI search is content: it stays behind the required channels."""
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

		self._press(cb.AI_SEARCH)

		self.assertIn("Majburiy obuna", self.all_text())

	# --------------------------------------------------------------- the results
	def test_a_subscriber_receives_links_with_one_line_summaries(self) -> None:
		title = make_ai_title(
			title="Qorong'i O'rmon",
			genres=["Qo'rqinchli", "Sarguzasht"],
			synopsis="Qo'rqinchli o'rmonda kechgan sarguzasht. Davomi bor.",
		)
		self._subscribe()
		self.session.reset()

		with bot_env(BOT_SITE_URL=SITE):
			self._press(cb.AI_SEARCH)
			self.session.reset()
			self._ask(QUERY)

		text = self.all_text()
		self.assertIn("AI topgan natijalar", text)
		self.assertIn(escape_html(QUERY), text)
		self.assertIn(f'href="{SITE}/media/{title.slug}"', text)
		# The list shape the request asks for: the link line, its metadata, then
		# the one-sentence summary underneath it.
		lines = [line for line in text.split("\n") if line.strip()]
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

	def test_a_new_title_is_indexed_without_any_command(self) -> None:
		"""Requirement: adding content must update the trained index by itself."""
		title = make_ai_title(title="Yangi Qo'rqinchli Anime", genres=["Qo'rqinchli"])
		self._subscribe()
		self.session.reset()

		self._press(cb.AI_SEARCH)
		self.session.reset()
		self._ask("qo'rqinchli anime")

		self.assertIn(escape_html(title.title), self.all_text())

	def test_an_edited_title_is_answered_from_the_new_text(self) -> None:
		title = make_ai_title(title="Eski Nom", genres=["Komediya"])
		self._subscribe()
		title.title = "Yangi Nom"
		title.save(update_fields=["title", "updated_at"])
		self.session.reset()

		self._press(cb.AI_SEARCH)
		self.session.reset()
		self._ask("yangi nom")

		self.assertIn("Yangi Nom", self.all_text())

	def test_the_answer_says_how_many_more_matched(self) -> None:
		"""The list is capped; the last line admits how many matches it left out."""
		for index in range(11):
			make_ai_title(title=f"Qo'rqinchli {index}", genres=["Qo'rqinchli"])
		self._subscribe()
		self.session.reset()

		self._press(cb.AI_SEARCH)
		self.session.reset()
		self._ask("qo'rqinchli anime")

		text = self.all_text()
		self.assertIn("Jami <b>11 ta</b> mos kontent topildi", text)
		self.assertIn("10 tasi", text)

	def test_the_thinking_placeholder_becomes_the_model_answer(self) -> None:
		"""The user sees progress immediately, then the model's own words."""
		title = make_ai_title(
			title="Qorong'i O'rmon",
			genres=["Qo'rqinchli"],
			synopsis="Qo'rqinchli o'rmon haqida hikoya.",
		)
		self._subscribe()
		self.session.reset()
		payload = json.dumps({
			"fikrlash": "So'rov qo'rqinchli kayfiyatni so'rayapti.",
			"tanlov": [1],
			"javob": f"«{title.title}» aynan sizga mos keladi.",
		})
		ai_reasoning.clear_cache()
		self.addCleanup(ai_reasoning.clear_cache)

		with mock.patch("movies.llm.chat", return_value=payload), override_settings(
			AI_LLM_API_KEY="test-key"
		):
			self._press(cb.AI_SEARCH)
			self.session.reset()
			self._ask(QUERY)

		self.assertIn(AI_SEARCH_THINKING, self.session.sent_texts())
		edits = "\n".join(method.text for method in self.session.methods("EditMessageText"))
		self.assertIn("AI javobi", edits)
		self.assertIn(escape_html(f"«{title.title}» aynan sizga mos keladi."), edits)
		self.assertIn(
			escape_html("Fikrlash: So'rov qo'rqinchli kayfiyatni so'rayapti."), edits
		)
		self.assertIn(title.title, self.button_texts())

	def test_a_broken_provider_still_answers_from_the_vectors(self) -> None:
		"""A reasoning outage must not cost the user their search results."""
		title = make_ai_title(title="Qorong'i O'rmon", genres=["Qo'rqinchli"])
		self._subscribe()
		self.session.reset()
		ai_reasoning.clear_cache()
		self.addCleanup(ai_reasoning.clear_cache)

		with mock.patch(
			"movies.llm.chat", side_effect=llm.LLMUnavailable("provider yiqildi")
		), override_settings(AI_LLM_API_KEY="test-key"):
			self._press(cb.AI_SEARCH)
			self.session.reset()
			self._ask(QUERY)

		self.assertIn(escape_html(title.title), self.all_text())
		self.assertNotIn("AI javobi", self.all_text())

	def test_an_unrelated_request_reports_nothing_found(self) -> None:
		make_ai_title(title="Kulgili Maktab", genres=["Komediya"], synopsis="Quvnoq maktab.")
		self._subscribe()
		self.session.reset()

		with override_settings(AI_SEARCH_MIN_SCORE=0.9):
			self._press(cb.AI_SEARCH)
			self.session.reset()
			self._ask("bugun ob-havo qanday")

		self.assertIn("bugun ob-havo qanday", self.all_text())
		self.assertIn("mos kontent topilmadi", self.all_text())
		self.assertIn("🔍 Oddiy qidiruv", self.button_texts())

	def test_a_digit_query_inside_the_ai_state_is_not_a_code_lookup(self) -> None:
		"""The AI prompt owns the messages typed while it is open."""
		title = make_ai_title(title="Kodli Anime", genres=["Sarguzasht"])
		MediaTitle.objects.filter(pk=title.pk).update(code="1997")
		self._subscribe()
		self.session.reset()

		self._press(cb.AI_SEARCH)
		self.session.reset()
		self._ask("1997")

		self.assertIn("1997", self.all_text())
		self.assertNotIn("🆔 Kod:", self.all_text())

	def test_a_missing_model_is_reported_with_the_plain_search(self) -> None:
		make_ai_title(title="Qorong'i O'rmon", genres=["Qo'rqinchli"])
		self._subscribe()
		self.session.reset()

		with mock.patch(
			"movies.embeddings.load_encoder",
			side_effect=embeddings.EmbeddingUnavailable("model yo'q"),
		):
			self._press(cb.AI_SEARCH)
			self.session.reset()
			self._ask(QUERY)

		self.assertIn(AI_SEARCH_UNAVAILABLE.split("\n")[0], self.all_text())
		# Falls back to the plain search screen, which still offers the AI button.
		self.assertIn("🎌 Anime", self.button_texts())
		self.assertIn("🤖 AI orqali qidirish", self.button_texts())

	def test_an_empty_query_keeps_the_prompt_open(self) -> None:
		self._subscribe()
		self.session.reset()

		self._press(cb.AI_SEARCH)
		self.session.reset()
		self._ask("   ")

		self.assertIn("Iltimos, matn yoki kod yuboring.", self.all_text())

	def test_a_conversational_question_is_answered_without_a_list(self) -> None:
		"""A "who are you" question gets the model's words, not the vector hits.

		The semantic search always has nearest neighbours to offer, so without
		the conversational branch such a question would be answered with an
		irrelevant row of titles instead of a reply.
		"""
		make_ai_title(title="Qorong'i O'rmon", genres=["Qo'rqinchli"])
		self._subscribe()
		self.session.reset()
		payload = json.dumps({
			"fikrlash": "Bu anime so'rovi emas, yordamchi haqida savol.",
			"tanlov": [],
			"javob": "Men AniVoyman, shu platformada ishlayman.",
		})
		ai_reasoning.clear_cache()
		self.addCleanup(ai_reasoning.clear_cache)

		with mock.patch("movies.llm.chat", return_value=payload), override_settings(
			AI_LLM_API_KEY="test-key"
		):
			self._press(cb.AI_SEARCH)
			self.session.reset()
			self._ask("sen kimsan")

		edits = "\n".join(method.text for method in self.session.methods("EditMessageText"))
		self.assertIn(escape_html("Men AniVoyman, shu platformada ishlayman."), edits)
		self.assertNotIn("topgan natijalar", self.all_text())
		self.assertNotIn("mos kontent topilmadi", self.all_text())
		# The prompt stays open for the next question.
		self.assertIn("🔍 Oddiy qidiruv", self.button_texts())

	# ------------------------------------------------- the favourites opt-in
	def test_the_prompt_offers_the_favourites_toggle_and_it_flips(self) -> None:
		"""The context is opt-in ("agar user ozi hohlasa"): the toggle button
		starts off and the press flips the label."""
		self._subscribe()
		self.session.reset()

		self._press(cb.AI_SEARCH)
		self.assertIn("🎯 Sevimlilar: ❌", self.button_texts())

		self.session.reset()
		self._press(cb.AI_FAV)
		self.assertIn("🎯 Sevimlilar: ✅", self.visible())

		self.session.reset()
		self._press(cb.AI_FAV)
		self.assertIn("🎯 Sevimlilar: ❌", self.button_texts())

	def test_the_toggle_is_off_by_default_and_sends_no_context(self) -> None:
		"""Without the opt-in the model must not see the user's taste."""
		make_ai_title(title="Qorong'i O'rmon", genres=["Qo'rqinchli"])
		self._subscribe()
		self.session.reset()
		router = json.dumps({"harakat": "qidiruv", "qidiruv": "qo'rqinchli"})
		search = json.dumps({"fikrlash": "x", "tanlov": [1], "javob": "Mana."})
		ai_reasoning.clear_cache()
		self.addCleanup(ai_reasoning.clear_cache)

		with mock.patch("movies.llm.chat", side_effect=[router, search]) as chat, override_settings(
			AI_LLM_API_KEY="test-key"
		):
			self._press(cb.AI_SEARCH)
			self.session.reset()
			self._ask(QUERY)

		for call in chat.call_args_list:
			self.assertNotIn("Sevimlilar:", call.args[0][1]["content"])

	def test_with_the_toggle_on_the_favourites_reach_the_model(self) -> None:
		"""Opted in, the prompt carries the user's favourites and history —
		so "men oxirgi ko'rganimga o'xshashini ayt" can be answered."""
		title = make_ai_title(title="Qorong'i O'rmon", genres=["Qo'rqinchli"])
		favorite = make_ai_title(title="Vagabond", genres=["Drama"])
		profile = TelegramUser.objects.get(telegram_id=USER.id)
		FavoriteContent.objects.create(user=profile, content=favorite)
		MediaView.objects.create(user=profile.auth_user, title=title)
		self._subscribe()
		self.session.reset()
		router = json.dumps({"harakat": "qidiruv", "qidiruv": "Vagabond o'xshash"})
		search = json.dumps({"fikrlash": "x", "tanlov": [1], "javob": "Mana."})
		ai_reasoning.clear_cache()
		self.addCleanup(ai_reasoning.clear_cache)

		with mock.patch("movies.llm.chat", side_effect=[router, search]) as chat, override_settings(
			AI_LLM_API_KEY="test-key"
		):
			self._press(cb.AI_SEARCH)
			self.session.reset()
			self._press(cb.AI_FAV)
			self.session.reset()
			self._ask("men oxirgi ko'rganimga o'xshashini ayt")

		router_prompt = chat.call_args_list[0].args[0][1]["content"]
		search_prompt = chat.call_args_list[1].args[0][1]["content"]
		self.assertIn("Vagabond", router_prompt)
		self.assertIn("Qorong'i O'rmon", router_prompt)
		self.assertIn("Vagabond", search_prompt)
