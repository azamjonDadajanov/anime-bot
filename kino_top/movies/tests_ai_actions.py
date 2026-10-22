"""``movies.ai_actions`` — account actions as signed confirmation cards.

The card is the contract: which fields a client may edit (the whitelist),
what the signed token carries, and what ``execute`` finally writes. The
model's own layer (``submit_action`` in ``movies.ai_assistant``) is covered
here too — the privacy promise (a fixed tool sentence, a card built
server-side, never a cached token) lives across those two modules.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from users.models import SubscriptionRequest, TelegramUser, UserSettings

from . import ai_actions, ai_assistant, llm
from .models import MediaTitle, TitleComment, TitleRating

PROVIDER = dict(
	AI_LLM_ENABLED=True,
	AI_LLM_API_KEY="test-key-4829",
	AI_LLM_MODEL="",
	AI_LLM_BASE_URL="",
	AI_LLM_JSON_MODE=False,
)

FAKE_PNG = b"\x89PNG\r\n\x1a\nfake-image-payload"


def make_title(title: str = "Qorong'i O'rmon") -> MediaTitle:
	return MediaTitle.objects.create(type=MediaTitle.MediaType.ANIME, title=title)


def make_user(username: str = "action-user", **fields):
	return get_user_model().objects.create_user(
		username=username, password="secret-4829", **fields
	)


def tool_call(name: str, arguments: dict, call_id: str = "call-1") -> llm.ChatResult:
	return llm.ChatResult(
		content="",
		tool_calls=(llm.ToolCall(id=call_id, name=name, arguments=json.dumps(arguments)),),
	)


def say(text: str) -> llm.ChatResult:
	return llm.ChatResult(content=text)


class CardBuildTests(TestCase):
	"""What the client receives before anything is written."""

	def setUp(self):
		self.user = make_user()
		self.title = make_title()

	def fields_of(self, card):
		return {field["key"]: field for field in card["fields"]}

	def test_the_comment_card_lists_the_title_and_the_editable_rows(self):
		card = ai_actions.build_action(
			self.user,
			"write_comment",
			{"title_id": self.title.pk, "body": "Ajoyib anime!", "score": 8},
		)

		self.assertEqual(card["action"], "write_comment")
		self.assertEqual(card["label"], "Izoh yozish")
		self.assertEqual(card["kind"], "confirm")
		self.assertEqual(card["source"], "site")
		self.assertTrue(card["token"])
		fields = self.fields_of(card)
		self.assertEqual(fields["title"]["type"], "static")
		self.assertEqual(fields["title"]["value"], self.title.title)
		self.assertEqual(fields["title"]["href"], f"/media/{self.title.slug}")
		self.assertEqual(fields["body"]["type"], "textarea")
		self.assertEqual(fields["body"]["value"], "Ajoyib anime!")
		self.assertTrue(fields["body"]["editable"])
		self.assertEqual(fields["body"]["max_length"], TitleComment.MAX_LENGTH)
		self.assertEqual(fields["score"]["min"], 1)
		self.assertEqual(fields["score"]["max"], 10)
		# The id rides only inside the signed token: the card itself offers no
		# way to retarget the comment at another title.
		self.assertNotIn("title_id", fields)

	def test_the_rating_card_requires_a_score_inside_the_range(self):
		card = ai_actions.build_action(
			self.user, "set_rating", {"title_id": self.title.pk, "score": 8}
		)

		score = self.fields_of(card)["score"]
		self.assertEqual(card["label"], "Yulduzcha qo'yish")
		self.assertTrue(score["required"])
		self.assertTrue(score["editable"])
		self.assertEqual((score["min"], score["max"]), (1, 10))

	def test_the_subscription_card_lists_the_plans_and_the_card_number(self):
		card = ai_actions.build_action(self.user, "subscription_request", {"plan": "monthly"})

		fields = self.fields_of(card)
		self.assertEqual(fields["plan"]["type"], "select")
		options = [option["value"] for option in fields["plan"]["options"]]
		self.assertIn("monthly", options)
		self.assertEqual(fields["card_number"]["type"], "static")
		self.assertTrue(fields["card_number"]["value"])
		self.assertEqual(fields["screenshot"]["type"], "file")
		self.assertTrue(fields["screenshot"]["required"])

	def test_the_name_card_pre_fills_the_current_names(self):
		self.user.first_name = "Ali"
		self.user.last_name = "Valiyev"
		self.user.save(update_fields=["first_name", "last_name"])

		card = ai_actions.build_action(self.user, "change_name", {})
		fields = self.fields_of(card)

		self.assertEqual(fields["first_name"]["value"], "Ali")
		self.assertEqual(fields["last_name"]["value"], "Valiyev")
		self.assertEqual(fields["first_name"]["max_length"], ai_actions.NAME_MAX_LENGTH)

	def test_the_theme_card_offers_exactly_the_three_options(self):
		card = ai_actions.build_action(self.user, "set_theme", {"theme": "dark"})

		theme = self.fields_of(card)["theme"]
		self.assertEqual(theme["type"], "select")
		self.assertEqual([option["value"] for option in theme["options"]], ["system", "light", "dark"])
		self.assertEqual(theme["value"], "dark")

	def test_the_motion_card_is_a_bool_toggle(self):
		card = ai_actions.build_action(self.user, "set_reduce_motion", {"enabled": False})

		enabled = self.fields_of(card)["enabled"]
		self.assertEqual(enabled["type"], "bool")
		self.assertIs(enabled["value"], False)
		self.assertTrue(enabled["editable"])

	def test_the_avatar_card_offers_text_and_an_optional_picture(self):
		card = ai_actions.build_action(self.user, "set_avatar", {"avatar": "🦊"})

		fields = self.fields_of(card)
		self.assertEqual(fields["avatar"]["type"], "text")
		self.assertEqual(fields["avatar"]["value"], "🦊")
		self.assertEqual(fields["avatar_file"]["type"], "file")
		self.assertFalse(fields["avatar_file"]["required"])

	def test_the_link_card_is_the_poll_kind(self):
		card = ai_actions.build_action(self.user, ai_actions.LINK_TELEGRAM, {})

		self.assertEqual(card["kind"], "link")
		self.assertFalse(card["link"]["linked"])

		TelegramUser.objects.create(telegram_id=111, auth_user=self.user, username="tester")
		linked = ai_actions.build_action(self.user, ai_actions.LINK_TELEGRAM, {})
		self.assertTrue(linked["link"]["linked"])
		self.assertEqual(linked["link"]["username"], "tester")

	def test_the_unlink_card_shows_the_connected_username(self):
		TelegramUser.objects.create(telegram_id=111, auth_user=self.user, username="tester")

		card = ai_actions.build_action(self.user, ai_actions.UNLINK_TELEGRAM, {})

		self.assertEqual(self.fields_of(card)["status"]["value"], "@tester")

	def test_the_whitelist_covers_exactly_the_confirmable_actions(self):
		self.assertEqual(
			set(ai_actions.EDITABLE_KEYS),
			set(ai_actions.ACTIONS) - {ai_actions.LINK_TELEGRAM, ai_actions.UNLINK_TELEGRAM},
		)

	def test_an_unknown_action_reports_the_known_ones(self):
		with self.assertRaises(ai_actions.ActionError) as caught:
			ai_actions.build_action(self.user, "delete_account", {})

		self.assertEqual(caught.exception.code, "unknown_action")
		self.assertIn("write_comment", caught.exception.detail)

	def test_a_non_dict_values_payload_is_treated_as_empty(self):
		with self.assertRaises(ai_actions.ActionError) as caught:
			ai_actions.build_action(self.user, "write_comment", "just some text")

		self.assertEqual(caught.exception.code, "invalid_values")


class TokenTests(TestCase):
	"""The signed proposal: who, what, and where it may run."""

	def setUp(self):
		self.user = make_user()
		self.other = make_user(username="other-user")

	def card(self, source: str = "bot"):
		return ai_actions.build_action(
			self.user, "set_theme", {"theme": "dark"}, source=source
		)

	def test_the_token_round_trips_the_values_and_the_source(self):
		payload = ai_actions.load_token(self.card()["token"])

		self.assertEqual(payload["u"], self.user.pk)
		self.assertEqual(payload["a"], "set_theme")
		self.assertEqual(payload["v"], {"theme": "dark"})
		self.assertEqual(payload["s"], "bot")

	def test_an_expired_token_is_refused(self):
		token = self.card()["token"]

		with mock.patch.object(ai_actions, "TOKEN_MAX_AGE", -1):
			with self.assertRaises(ai_actions.ActionError) as caught:
				ai_actions.load_token(token)

		self.assertEqual(caught.exception.code, "expired")

	def test_a_garbled_token_is_refused(self):
		with self.assertRaises(ai_actions.ActionError) as caught:
			ai_actions.load_token("not-a-real-token")

		self.assertEqual(caught.exception.code, "invalid_token")

	def test_another_users_token_cannot_execute(self):
		token = self.card()["token"]

		with self.assertRaises(ai_actions.ActionError) as caught:
			ai_actions.execute(self.other, token)

		self.assertEqual(caught.exception.code, "forbidden")

	def test_the_link_card_cannot_execute_through_confirm(self):
		card = ai_actions.build_action(self.user, ai_actions.LINK_TELEGRAM, {})

		with self.assertRaises(ai_actions.ActionError) as caught:
			ai_actions.execute(self.user, card["token"])

		self.assertEqual(caught.exception.code, "invalid_action")


class ExecuteTests(TestCase):
	"""What actually lands in the database after «Tasdiqlash»."""

	def setUp(self):
		self.user = make_user()
		self.title = make_title()

	def comment_card(self, body: str = "Ajoyib anime!"):
		return ai_actions.build_action(
			self.user,
			"write_comment",
			{"title_id": self.title.pk, "body": body, "score": 8},
		)

	def test_confirming_a_comment_writes_it_with_its_score(self):
		card = self.comment_card()

		result = ai_actions.execute(self.user, card["token"], source="site")

		comment = TitleComment.objects.get()
		self.assertEqual(comment.user_id, self.user.pk)
		self.assertEqual(comment.title_id, self.title.pk)
		self.assertEqual(comment.body, "Ajoyib anime!")
		self.assertEqual(comment.source, TitleComment.Source.SITE)
		self.assertEqual(TitleRating.objects.get().score, 8)
		self.assertEqual(result["message"], "Izoh va yulduzcha saqlandi.")

	def test_the_same_comment_twice_reports_a_duplicate(self):
		card = ai_actions.build_action(
			self.user,
			"write_comment",
			{"title_id": self.title.pk, "body": "Ajoyib anime!"},
		)

		ai_actions.execute(self.user, card["token"])
		result = ai_actions.execute(self.user, card["token"])

		self.assertEqual(TitleComment.objects.count(), 1)
		self.assertIn("allaqachon", result["message"])

	def test_client_edits_cannot_retarget_the_title(self):
		card = self.comment_card()
		other = make_title("Boshqa Anime")

		ai_actions.execute(
			self.user,
			card["token"],
			values={"title_id": other.pk, "body": "O'zgartirilgan izoh"},
		)

		comment = TitleComment.objects.get()
		self.assertEqual(comment.title_id, self.title.pk)
		self.assertEqual(comment.body, "O'zgartirilgan izoh")

	def test_a_score_outside_the_range_is_refused(self):
		card = ai_actions.build_action(
			self.user, "set_rating", {"title_id": self.title.pk, "score": 8}
		)

		with self.assertRaises(ai_actions.ActionError) as caught:
			ai_actions.execute(self.user, card["token"], values={"score": 11})

		self.assertEqual(caught.exception.code, "invalid_rating")
		self.assertFalse(TitleRating.objects.exists())

	def test_a_rating_update_replaces_the_saved_score(self):
		card = ai_actions.build_action(
			self.user, "set_rating", {"title_id": self.title.pk, "score": 8}
		)
		ai_actions.execute(self.user, card["token"])

		next_card = ai_actions.build_action(
			self.user, "set_rating", {"title_id": self.title.pk, "score": 8}
		)
		ai_actions.execute(self.user, next_card["token"], values={"score": 5})

		self.assertEqual(TitleRating.objects.get().score, 5)

	def test_change_name_writes_the_account(self):
		card = ai_actions.build_action(self.user, "change_name", {"first_name": "Ali"})

		result = ai_actions.execute(self.user, card["token"])

		self.user.refresh_from_db()
		self.assertEqual(self.user.first_name, "Ali")
		self.assertEqual(result["message"], "Ism-familiya yangilandi.")

	def test_change_name_needs_at_least_one_part(self):
		card = ai_actions.build_action(self.user, "change_name", {"first_name": "Ali"})

		with self.assertRaises(ai_actions.ActionError) as caught:
			ai_actions.execute(
				self.user, card["token"], values={"first_name": "", "last_name": ""}
			)

		self.assertEqual(caught.exception.code, "invalid_values")

	def test_the_theme_is_applied_to_user_settings(self):
		card = ai_actions.build_action(self.user, "set_theme", {"theme": "dark"})

		ai_actions.execute(self.user, card["token"], values={"theme": "light"})

		self.assertEqual(UserSettings.objects.get(user=self.user).theme, "light")

	def test_an_unknown_theme_is_refused(self):
		card = ai_actions.build_action(self.user, "set_theme", {"theme": "dark"})

		with self.assertRaises(ai_actions.ActionError) as caught:
			ai_actions.execute(self.user, card["token"], values={"theme": "neon"})

		self.assertEqual(caught.exception.code, "invalid_values")

	def test_reduce_motion_flips_the_preference(self):
		card = ai_actions.build_action(self.user, "set_reduce_motion", {"enabled": False})

		ai_actions.execute(self.user, card["token"], values={"enabled": True})

		self.assertTrue(UserSettings.objects.get(user=self.user).reduce_motion)

	def test_an_avatar_text_is_saved(self):
		card = ai_actions.build_action(self.user, "set_avatar", {"avatar": "🦊"})

		result = ai_actions.execute(self.user, card["token"])

		self.assertEqual(UserSettings.objects.get(user=self.user).avatar, "🦊")
		self.assertEqual(result["message"], "Profil rasmi yangilandi.")

	def test_a_too_long_avatar_text_is_refused(self):
		card = ai_actions.build_action(self.user, "set_avatar", {"avatar": "🦊"})

		with self.assertRaises(ai_actions.ActionError) as caught:
			ai_actions.execute(self.user, card["token"], values={"avatar": "x" * 65})

		self.assertEqual(caught.exception.code, "invalid_values")


class AvatarFileTests(TestCase):
	"""The uploaded picture path of «Profil rasmi»."""

	def setUp(self):
		self.media_root = tempfile.mkdtemp()
		self.override = override_settings(MEDIA_ROOT=self.media_root)
		self.override.enable()
		self.addCleanup(self.override.disable)
		self.addCleanup(shutil.rmtree, self.media_root, True)
		self.user = make_user()

	def test_a_picture_upload_is_saved(self):
		card = ai_actions.build_action(self.user, "set_avatar", {"avatar": "🦊"})

		result = ai_actions.execute(
			self.user,
			card["token"],
			files={
				"avatar_file": SimpleUploadedFile("avatar.png", FAKE_PNG, content_type="image/png")
			},
		)

		settings_object = UserSettings.objects.get(user=self.user)
		self.assertTrue(settings_object.avatar_file.name)
		self.assertEqual(result["data"]["avatar_file"], str(settings_object.avatar_file.name))

	def test_a_non_image_upload_is_refused(self):
		card = ai_actions.build_action(self.user, "set_avatar", {"avatar": "🦊"})

		with self.assertRaises(ai_actions.ActionError) as caught:
			ai_actions.execute(
				self.user,
				card["token"],
				files={
					"avatar_file": SimpleUploadedFile("note.txt", b"hello", content_type="text/plain")
				},
			)

		self.assertEqual(caught.exception.code, "invalid_values")

	def test_an_oversized_picture_is_refused(self):
		card = ai_actions.build_action(self.user, "set_avatar", {"avatar": "🦊"})

		with self.assertRaises(ai_actions.ActionError) as caught:
			ai_actions.execute(
				self.user,
				card["token"],
				files={
					"avatar_file": SimpleUploadedFile(
						"big.png",
						b"x" * (ai_actions.AVATAR_MAX_BYTES + 1),
						content_type="image/png",
					)
				},
			)

		self.assertEqual(caught.exception.code, "invalid_values")


class SubscriptionActionTests(TestCase):
	"""«Obunani uzaytirish»: the screenshot flow the admin gets notified of."""

	def setUp(self):
		self.user = make_user()
		self.card = ai_actions.build_action(
			self.user, "subscription_request", {"plan": "monthly"}
		)

	@mock.patch("users.telegram_notify.notify_admins_new_request")
	def test_a_screenshot_creates_the_request_and_notifies(self, notify):
		result = ai_actions.execute(
			self.user,
			self.card["token"],
			files={
				"screenshot": SimpleUploadedFile("shot.png", FAKE_PNG, content_type="image/png")
			},
		)

		request = SubscriptionRequest.objects.get()
		self.assertEqual(request.plan, "monthly")
		self.assertEqual(request.status, SubscriptionRequest.Status.PENDING)
		self.assertEqual(result["data"]["request_id"], request.pk)
		self.assertEqual(
			result["message"],
			"Ariza yuborildi — administratorlar to'lovni tekshirib, tasdiqlashadi.",
		)
		notify.assert_called_once()

	def test_without_a_screenshot_the_run_refuses(self):
		with self.assertRaises(ai_actions.ActionError) as caught:
			ai_actions.execute(self.user, self.card["token"])

		self.assertEqual(caught.exception.code, "needs_input")
		self.assertFalse(SubscriptionRequest.objects.exists())

	@mock.patch("users.telegram_notify.notify_admins_new_request")
	def test_a_second_pending_request_for_the_same_plan_is_refused(self, notify):
		shot = lambda: SimpleUploadedFile(  # noqa: E731 - one-shot upload factory
			"shot.png", FAKE_PNG, content_type="image/png"
		)
		ai_actions.execute(self.user, self.card["token"], files={"screenshot": shot()})

		with self.assertRaises(ai_actions.ActionError) as caught:
			ai_actions.execute(self.user, self.card["token"], files={"screenshot": shot()})

		self.assertEqual(caught.exception.code, "conflict")
		self.assertEqual(SubscriptionRequest.objects.count(), 1)


class UnlinkActionTests(TestCase):
	"""«Telegramni uzish» from the website side."""

	def setUp(self):
		self.user = make_user()

	def test_unlinking_detaches_the_profile(self):
		profile = TelegramUser.objects.create(
			telegram_id=111, auth_user=self.user, username="tester"
		)
		card = ai_actions.build_action(self.user, ai_actions.UNLINK_TELEGRAM, {})

		result = ai_actions.execute(self.user, card["token"])

		profile.refresh_from_db()
		self.assertIsNone(profile.auth_user_id)
		self.assertFalse(result["data"]["linked"])
		self.assertEqual(result["message"], "Telegram akkaunt uzildi.")

	def test_unlinking_twice_still_succeeds(self):
		card = ai_actions.build_action(self.user, ai_actions.UNLINK_TELEGRAM, {})

		result = ai_actions.execute(self.user, card["token"])

		self.assertFalse(result["data"]["linked"])
		self.assertIn("allaqachon", result["message"])


class SubmitActionToolTests(TestCase):
	"""The model's own layer: a fixed sentence, a server-built card.

	Whatever the model sends in ``qiymatlar`` must come back only as
	"tayyor" / a short error — a name, a plan or a photo can never be
	echoed into the conversation history, and a card is never cached for
	the next caller of the same question.
	"""

	def setUp(self):
		self.user = make_user()
		self.title = make_title()
		self.override = override_settings(**PROVIDER)
		self.override.enable()
		self.addCleanup(self.override.disable)
		ai_assistant.clear_cache()
		self.addCleanup(ai_assistant.clear_cache)
		llm.reset_cooldowns()
		llm.reset_signature_cache()
		self.addCleanup(llm.reset_cooldowns)
		self.addCleanup(llm.reset_signature_cache)

	def test_the_tool_is_offered_only_with_an_account(self):
		without = ai_assistant._ToolRunner()
		with_user = ai_assistant._ToolRunner(user=self.user, source="bot")

		self.assertNotIn(
			"submit_action", [tool["function"]["name"] for tool in without.schemas()]
		)
		self.assertIn(
			"submit_action", [tool["function"]["name"] for tool in with_user.schemas()]
		)

	def test_the_tool_result_is_fixed_and_never_echoes_the_values(self):
		runner = ai_assistant._ToolRunner(user=self.user, source="bot")

		output = runner.run(
			"submit_action",
			json.dumps(
				{
					"amal": "write_comment",
					"qiymatlar": {
						"title_id": self.title.pk,
						"body": "MAXFIY-IZOH-42",
						"score": 9,
					},
				}
			),
		)

		self.assertIn("Amal tayyorlandi", output)
		self.assertNotIn("MAXFIY-IZOH-42", output)
		# The card itself (shown to the user, built server-side) carries the
		# values and the signed token.
		self.assertIsNotNone(runner.action)
		self.assertEqual(runner.action["source"], "bot")
		self.assertEqual(runner.action["action"], "write_comment")
		body = next(f for f in runner.action["fields"] if f["key"] == "body")
		self.assertEqual(body["value"], "MAXFIY-IZOH-42")
		self.assertTrue(runner.action["token"])

	def test_invalid_values_report_a_short_error_instead_of_a_card(self):
		runner = ai_assistant._ToolRunner(user=self.user, source="bot")

		output = runner.run(
			"submit_action",
			json.dumps({"amal": "set_rating", "qiymatlar": {"title_id": self.title.pk, "score": 99}}),
		)

		self.assertTrue(output.startswith("Xatolik:"))
		self.assertIsNone(runner.action)

	def test_the_assistant_returns_the_card_next_to_its_answer(self):
		completions = mock.Mock(
			side_effect=[
				tool_call(
					"submit_action",
					{
						"amal": "write_comment",
						"qiymatlar": {"title_id": self.title.pk, "body": "Zo'r anime."},
					},
				),
				say("Izoh tayyor — tasdiqlang."),
			]
		)

		with mock.patch("movies.llm.chat_completion", completions):
			result = ai_assistant.answer("shu anime haqida izoh qoldir", user=self.user)

		self.assertEqual(result.answer, "Izoh tayyor — tasdiqlang.")
		self.assertEqual(result.tools, ("submit_action",))
		self.assertEqual(result.action["action"], "write_comment")

	def test_the_support_persona_never_gets_the_tool(self):
		completions = mock.Mock(
			side_effect=[
				tool_call(
					"submit_action",
					{"amal": "set_theme", "qiymatlar": {"theme": "dark"}},
				),
				say("Maslahat: sozlamalarni tekshiring."),
			]
		)

		with mock.patch("movies.llm.chat_completion", completions):
			result = ai_assistant.answer(
				"mavzuni tungi qil", support=True, user=self.user
			)

		offered = [
			tool["function"]["name"] for tool in completions.call_args_list[0].kwargs["tools"]
		]
		self.assertNotIn("submit_action", offered)
		second_messages = completions.call_args_list[1].args[0]
		tool_messages = [m for m in second_messages if m["role"] == "tool"]
		self.assertIn("mavjud emas", tool_messages[0]["content"])
		self.assertIsNone(result.action)

	def test_without_a_user_the_model_cannot_ask_for_an_action(self):
		completions = mock.Mock(
			side_effect=[
				tool_call("submit_action", {"amal": "set_theme", "qiymatlar": {"theme": "dark"}}),
				say("Buni men bajarolmayman."),
			]
		)

		with mock.patch("movies.llm.chat_completion", completions):
			result = ai_assistant.answer("mavzuni tungi qil")

		self.assertIsNone(result.action)

	def test_an_action_answer_is_never_cached(self):
		completions = mock.Mock(
			side_effect=[
				tool_call("submit_action", {"amal": "set_theme", "qiymatlar": {"theme": "dark"}}),
				say("Tasdiqlang."),
				tool_call("submit_action", {"amal": "set_theme", "qiymatlar": {"theme": "dark"}}),
				say("Tasdiqlang."),
			]
		)

		with mock.patch("movies.llm.chat_completion", completions):
			first = ai_assistant.answer("mavzuni tungi qil", user=self.user)
			second = ai_assistant.answer("mavzuni tungi qil", user=self.user)

		self.assertEqual(completions.call_count, 4)
		self.assertIsNotNone(first.action)
		self.assertIsNotNone(second.action)


class ActionApiTests(TestCase):
	"""The confirm endpoint the website's «Tasdiqlash» button calls."""

	def setUp(self):
		self.client = APIClient()
		self.url = "/api/catalog/ai-assistant/action/"
		self.user = make_user()
		self.title = make_title()

	def test_authentication_is_required(self):
		card = ai_actions.build_action(self.user, "set_theme", {"theme": "dark"})

		response = self.client.post(self.url, {"token": card["token"]}, format="multipart")

		self.assertIn(response.status_code, (401, 403))

	def test_confirming_runs_the_action_and_reports_the_message(self):
		self.client.force_authenticate(self.user)
		card = ai_actions.build_action(self.user, "set_theme", {"theme": "dark"})

		response = self.client.post(
			self.url,
			{"token": card["token"], "values": json.dumps({"theme": "light"})},
			format="multipart",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["status"], "done")
		self.assertEqual(response.data["action"], "set_theme")
		self.assertEqual(response.data["message"], "Mavzu yangilandi.")
		self.assertEqual(UserSettings.objects.get(user=self.user).theme, "light")

	def test_client_values_are_filtered_through_the_whitelist(self):
		self.client.force_authenticate(self.user)
		card = ai_actions.build_action(
			self.user,
			"write_comment",
			{"title_id": self.title.pk, "body": "Birinchi variant", "score": 7},
		)

		response = self.client.post(
			self.url,
			{
				"token": card["token"],
				"values": json.dumps({"body": "Ikkinchi variant", "title_id": 999999}),
			},
			format="multipart",
		)

		self.assertEqual(response.status_code, 200)
		comment = TitleComment.objects.get()
		self.assertEqual(comment.body, "Ikkinchi variant")
		self.assertEqual(comment.title_id, self.title.pk)

	def test_a_foreign_token_comes_back_as_a_400(self):
		card = ai_actions.build_action(self.user, "set_theme", {"theme": "dark"})
		other = make_user(username="api-other")
		self.client.force_authenticate(other)

		response = self.client.post(self.url, {"token": card["token"]}, format="multipart")

		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.data["code"], "forbidden")

	def test_a_garbled_token_comes_back_as_a_400(self):
		self.client.force_authenticate(self.user)

		response = self.client.post(self.url, {"token": "nope"}, format="multipart")

		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.data["code"], "invalid_token")

	@mock.patch("users.telegram_notify.notify_admins_new_request")
	def test_a_payment_screenshot_rides_along_as_multipart(self, notify):
		self.client.force_authenticate(self.user)
		card = ai_actions.build_action(
			self.user, "subscription_request", {"plan": "monthly"}
		)

		response = self.client.post(
			self.url,
			{
				"token": card["token"],
				"values": json.dumps({"plan": "yearly"}),
				"screenshot": SimpleUploadedFile("shot.png", FAKE_PNG, content_type="image/png"),
			},
			format="multipart",
		)

		self.assertEqual(response.status_code, 200)
		request = SubscriptionRequest.objects.get()
		self.assertEqual(request.plan, "yearly")
		notify.assert_called_once()

	def test_a_missing_screenshot_is_reported(self):
		self.client.force_authenticate(self.user)
		card = ai_actions.build_action(
			self.user, "subscription_request", {"plan": "monthly"}
		)

		response = self.client.post(
			self.url, {"token": card["token"]}, format="multipart"
		)

		self.assertEqual(response.status_code, 400)
		self.assertEqual(response.data["code"], "needs_input")
