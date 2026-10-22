"""``AniVoy`` — the online AI assistant and its catalogue tools.

Two layers are under test:

* the tool runner in ``movies.ai_assistant`` (does a tool read the right rows,
  and does its answer reach the model as a ``tool`` message?);
* the subscription-gated API, driven end to end with the model's HTTP layer
  mocked — so the real tool code runs against the test database and only the
  provider is faked.

There is no offline model and no vector index: a request with no provider must
come back as "unavailable", never as a silent local answer.
"""

from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import FavoriteContent, Subscription, TelegramUser

from . import ai_assistant, llm
from .models import AIProvider, Genre, MediaPart, MediaTitle

PROVIDER = dict(
	AI_LLM_ENABLED=True,
	AI_LLM_API_KEY="test-key-4829",
	AI_LLM_MODEL="",
	AI_LLM_BASE_URL="",
	AI_LLM_JSON_MODE=False,
)
NO_PROVIDER = dict(PROVIDER, AI_LLM_API_KEY="")


def tool_call(name: str, arguments: dict, call_id: str = "call-1") -> llm.ChatResult:
	"""A provider answer that asks for one function."""
	return llm.ChatResult(
		content="",
		tool_calls=(llm.ToolCall(id=call_id, name=name, arguments=json.dumps(arguments)),),
	)


def say(text: str) -> llm.ChatResult:
	return llm.ChatResult(content=text)


class AssistantTestCase(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.url = "/api/catalog/ai-assistant/"
		self.override = override_settings(**PROVIDER)
		self.override.enable()
		self.addCleanup(self.override.disable)
		ai_assistant.clear_cache()
		self.addCleanup(ai_assistant.clear_cache)
		llm.reset_cooldowns()
		llm.reset_signature_cache()
		self.addCleanup(llm.reset_cooldowns)
		self.addCleanup(llm.reset_signature_cache)

	def make_title(
		self,
		title="Qorong'i O'rmon",
		*,
		media_type=MediaTitle.MediaType.ANIME,
		genres=(),
		synopsis="",
		year=2020,
		rating=8,
	):
		media = MediaTitle.objects.create(
			type=media_type,
			title=title,
			synopsis=synopsis,
			release_year=year,
			rating=rating,
		)
		if genres:
			media.genres.set([Genre.objects.get_or_create(name=name)[0] for name in genres])
		return media

	def make_subscriber(self, username="assistant-sub", *, days=30):
		user = get_user_model().objects.create_user(username=username, password="secret-4829")
		subscription, _ = Subscription.objects.get_or_create(user=user)
		subscription.plan = "monthly"
		subscription.started_at = timezone.now()
		subscription.expires_at = timezone.now() + timedelta(days=days)
		subscription.save(update_fields=["plan", "started_at", "expires_at", "updated_at"])
		user.refresh_from_db()
		return user

	# ------------------------------------------------------------------- tools
	def test_the_search_tool_returns_titles_and_filters(self):
		horror = self.make_title("Qorong'i O'rmon", genres=["Qo'rqinchli"], year=2020)
		self.make_title(
			"Kulgili Maktab",
			media_type=MediaTitle.MediaType.SERIES,
			genres=["Komediya"],
			year=2021,
		)
		runner = ai_assistant._ToolRunner()

		output = runner.run(
			"search_catalog", json.dumps({"janr": "qo'rqinchli", "tur": "anime", "yil": 2020})
		)

		self.assertIn(horror.title, output)
		self.assertIn(f"[id: {horror.pk}]", output)
		self.assertNotIn("Kulgili Maktab", output)
		self.assertEqual([title.pk for title in runner.titles()], [horror.pk])

	def test_the_details_tool_reports_parts_and_genres(self):
		title = self.make_title("Naruto", genres=["Sarguzasht"], synopsis="Ninja yo'li.")
		MediaPart.objects.create(content=title, season_number=1, number=1)
		MediaPart.objects.create(content=title, season_number=1, number=2)
		runner = ai_assistant._ToolRunner()

		details = runner.run("title_details", json.dumps({"id": title.pk}))
		parts = runner.run("list_parts", json.dumps({"nom": "Naruto"}))

		self.assertIn("Qismlar: 2", details)
		self.assertIn("Mavsumlar: 1", details)
		self.assertIn("Sarguzasht", details)
		self.assertIn("2 ta qism", parts)
		self.assertIn("1-mavsum 2-qism", parts)

	def test_the_genre_and_stats_tools_read_the_catalogue(self):
		self.make_title("Birinchi", genres=["Drama"])
		self.make_title("Ikkinchi", media_type=MediaTitle.MediaType.MANGA, genres=["Drama"])
		runner = ai_assistant._ToolRunner()

		genres = runner.run("list_genres", "{}")
		stats = runner.run("catalog_stats", "{}")

		self.assertIn("Drama (2)", genres)
		self.assertIn("Anime: 1 ta", stats)
		self.assertIn("Manga: 1 ta", stats)

	def test_a_popular_lookup_feeds_the_result_list(self):
		self.make_title("Past", rating=3)
		best = self.make_title("Yuqori", rating=10)
		runner = ai_assistant._ToolRunner()

		runner.run("popular_titles", json.dumps({"tur": "mashhur", "limit": 1}))

		self.assertEqual([title.pk for title in runner.titles()], [best.pk])

	def test_an_unknown_function_is_reported_to_the_model(self):
		runner = ai_assistant._ToolRunner()
		output = runner.run("delete_everything", "{}")
		self.assertIn("mavjud emas", output)

	# ------------------------------------------------------ the model + tools
	def test_the_assistant_runs_the_tool_and_answers_with_its_rows(self):
		title = self.make_title("Qorong'i O'rmon", genres=["Qo'rqinchli"])
		completions = mock.Mock(
			side_effect=[
				tool_call("search_catalog", {"janr": "Qo'rqinchli"}),
				say("«Qorong'i O'rmon» aynan sizga mos keladi."),
			]
		)

		with mock.patch("movies.llm.chat_completion", completions):
			result = ai_assistant.answer("menga qo'rqinchli anime ayt")

		self.assertTrue(result.used_llm)
		self.assertEqual(
			result.answer, "«Qorong'i O'rmon» aynan sizga mos keladi."
		)
		self.assertEqual([row.pk for row in result.titles], [title.pk])
		self.assertEqual(result.tools, ("search_catalog",))
		self.assertFalse(result.conversational)

		# The second call carries the tool's output as a `tool` message, which is
		# what makes the model's answer grounded in real catalogue rows.
		second_messages = completions.call_args_list[1].args[0]
		tool_messages = [message for message in second_messages if message["role"] == "tool"]
		self.assertEqual(len(tool_messages), 1)
		self.assertIn(title.title, tool_messages[0]["content"])
		self.assertEqual(tool_messages[0]["tool_call_id"], "call-1")
		# …and the tools were actually offered to the model.
		self.assertTrue(completions.call_args_list[0].kwargs["tools"])

	def test_a_conversational_question_carries_no_result_list(self):
		completions = mock.Mock(return_value=say("Men AniVoyman, shu platformada ishlayman."))

		with mock.patch("movies.llm.chat_completion", completions):
			result = ai_assistant.answer("sen kimsan")

		self.assertTrue(result.used_llm)
		self.assertTrue(result.conversational)
		self.assertEqual(result.titles, ())
		self.assertIn("AniVoyman", result.answer)
		self.assertEqual(completions.call_count, 1)

	def test_a_failed_tool_is_reported_instead_of_breaking_the_answer(self):
		runner = ai_assistant._ToolRunner()
		output = runner.run("search_catalog", "{not json")
		self.assertIn("Xatolik", output)

	def test_personal_taste_is_only_offered_after_opt_in(self):
		without = ai_assistant._ToolRunner()
		with_context = ai_assistant._ToolRunner(personal_context="Sevimlilar: Naruto (anime)")

		self.assertNotIn(
			"personal_taste",
			[tool["function"]["name"] for tool in without.schemas()],
		)
		self.assertIn(
			"personal_taste",
			[tool["function"]["name"] for tool in with_context.schemas()],
		)
		self.assertIn("Naruto", with_context.run("personal_taste", "{}"))

	def test_the_assistant_reports_an_outage_without_any_local_fallback(self):
		with override_settings(**NO_PROVIDER):
			result = ai_assistant.answer("qo'rqinchli anime")

		self.assertFalse(result.used_llm)
		self.assertEqual(result.titles, ())
		self.assertTrue(result.error)

	def test_the_same_question_is_cached_for_a_moment(self):
		completions = mock.Mock(return_value=say("Javob."))
		with mock.patch("movies.llm.chat_completion", completions):
			first = ai_assistant.answer("katalogda nima bor")
			second = ai_assistant.answer("katalogda nima bor")

		self.assertEqual(completions.call_count, 1)
		self.assertEqual(first.answer, second.answer)

	def test_the_result_payload_links_to_the_site(self):
		title = self.make_title("Qorong'i O'rmon", synopsis="Birinchi jumla. Davomi.")
		payload = ai_assistant.title_payload(title, site_url="https://anichopar.uz")

		self.assertEqual(payload["url"], f"https://anichopar.uz/media/{title.slug}")
		self.assertEqual(payload["summary"], "Birinchi jumla.")
		self.assertEqual(payload["genres"], [])


class AssistantApiTests(AssistantTestCase):
	def test_a_free_account_gets_the_subscription_upsell(self):
		user = get_user_model().objects.create_user(username="free", password="secret-4829")
		self.client.force_authenticate(user)

		response = self.client.post(self.url, {"query": "qo'rqinchli anime"}, format="json")

		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.data["code"], "subscription_required")

	def test_a_subscriber_gets_the_answer_and_the_titles(self):
		title = self.make_title(
			"Qorong'i O'rmon", genres=["Qo'rqinchli"], synopsis="Qo'rqinchli o'rmon."
		)
		self.client.force_authenticate(self.make_subscriber())
		completions = mock.Mock(
			side_effect=[
				tool_call("search_catalog", {"matn": "qo'rqinchli"}),
				say("Mana mos anime."),
			]
		)

		with override_settings(BOT_SITE_URL="https://anichopar.uz"), mock.patch(
			"movies.llm.chat_completion", completions
		):
			response = self.client.post(self.url, {"query": "qo'rqinchli anime"}, format="json")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["answer"], "Mana mos anime.")
		self.assertEqual(response.data["count"], 1)
		self.assertEqual(response.data["tools"], ["search_catalog"])
		item = response.data["results"][0]
		self.assertEqual(item["title"], title.title)
		self.assertEqual(item["url"], f"https://anichopar.uz/media/{title.slug}")
		self.assertNotIn("score", item)

	def test_the_api_says_unavailable_when_no_provider_is_configured(self):
		self.client.force_authenticate(self.make_subscriber())

		with override_settings(**NO_PROVIDER):
			response = self.client.post(self.url, {"query": "nima bor"}, format="json")

		self.assertEqual(response.status_code, 503)
		self.assertEqual(response.data["code"], "ai_unavailable")

	def test_the_user_gets_the_same_message_as_everybody_else(self):
		"""The reason is for the operator, not for the subscriber."""
		self.client.force_authenticate(self.make_subscriber())

		with override_settings(**NO_PROVIDER):
			response = self.client.post(self.url, {"query": "nima bor"}, format="json")

		self.assertEqual(response.data["detail"], ai_assistant.UNAVAILABLE_TEXT)
		self.assertNotIn("reason", response.data)

	def test_the_administrator_gets_the_reason(self):
		"""A dead model and a spent quota need different fixes."""
		admin = self.make_subscriber(username="root-ai")
		admin.is_staff = True
		admin.is_superuser = True
		admin.save(update_fields=["is_staff", "is_superuser"])
		admin.refresh_from_db()
		self.client.force_authenticate(admin)

		with override_settings(**NO_PROVIDER):
			response = self.client.post(self.url, {"query": "nima bor"}, format="json")

		self.assertEqual(response.status_code, 503)
		self.assertEqual(response.data["detail"], ai_assistant.UNAVAILABLE_TEXT)
		self.assertTrue(response.data["reason"])

	def test_the_taste_flag_registers_the_personal_tool(self):
		user = self.make_subscriber()
		profile = TelegramUser.objects.create(telegram_id=111222333, auth_user=user)
		favorite = self.make_title("Vagabond", genres=["Drama"])
		FavoriteContent.objects.create(user=profile, content=favorite)
		self.client.force_authenticate(user)
		completions = mock.Mock(return_value=say("Javob."))

		with mock.patch("movies.llm.chat_completion", completions):
			response = self.client.post(
				self.url, {"query": "sevimlilarimga o'xshashini top", "taste": True}, format="json"
			)

		self.assertEqual(response.status_code, 200)
		offered = [
			tool["function"]["name"] for tool in completions.call_args_list[0].kwargs["tools"]
		]
		self.assertIn("personal_taste", offered)

	def test_the_history_is_sent_as_chat_messages(self):
		self.client.force_authenticate(self.make_subscriber())
		completions = mock.Mock(return_value=say("Javob."))

		with mock.patch("movies.llm.chat_completion", completions):
			self.client.post(
				self.url,
				{
					"query": "nima aytgandingiz?",
					"history": [
						{"role": "user", "text": "qo'rqinchli anime ayt"},
						{"role": "ai", "text": "Mana bir nechta."},
					],
				},
				format="json",
			)

		messages = completions.call_args_list[0].args[0]
		self.assertEqual(messages[1], {"role": "user", "content": "qo'rqinchli anime ayt"})
		self.assertEqual(messages[2], {"role": "assistant", "content": "Mana bir nechta."})

	# ------------------------------------------------------- the action card
	def test_a_proposed_action_rides_back_with_the_answer(self):
		title = self.make_title("Qorong'i O'rmon")
		self.client.force_authenticate(self.make_subscriber())
		completions = mock.Mock(
			side_effect=[
				tool_call(
					"submit_action",
					{
						"amal": "write_comment",
						"qiymatlar": {"title_id": title.pk, "body": "Zor anime edi."},
					},
				),
				say("Izoh tayyor — tasdiqlang."),
			]
		)

		with mock.patch("movies.llm.chat_completion", completions):
			response = self.client.post(self.url, {"query": "izoh qoldir"}, format="json")

		self.assertEqual(response.status_code, 200)
		action = response.data["action"]
		self.assertEqual(action["action"], "write_comment")
		self.assertEqual(action["kind"], "confirm")
		self.assertEqual(action["source"], "site")
		self.assertTrue(action["token"])
		body = next(field for field in action["fields"] if field["key"] == "body")
		self.assertEqual(body["value"], "Zor anime edi.")

	def test_a_plain_answer_carries_no_action(self):
		self.client.force_authenticate(self.make_subscriber())
		completions = mock.Mock(return_value=say("Javob."))

		with mock.patch("movies.llm.chat_completion", completions):
			response = self.client.post(self.url, {"query": "salom"}, format="json")

		self.assertEqual(response.status_code, 200)
		self.assertIsNone(response.data["action"])

	def test_the_support_persona_never_offers_submit_action(self):
		self.client.force_authenticate(self.make_subscriber())
		completions = mock.Mock(return_value=say("Maslahat."))

		with mock.patch("movies.llm.chat_completion", completions):
			response = self.client.post(
				self.url, {"query": "izoh qoldir", "support": True}, format="json"
			)

		self.assertEqual(response.status_code, 200)
		offered = [
			tool["function"]["name"] for tool in completions.call_args_list[0].kwargs["tools"]
		]
		self.assertNotIn("submit_action", offered)


class _FakeResponse:
	"""The little bit of an HTTP response ``llm._attempt`` reads."""

	def __init__(self, body: dict):
		self.body = json.dumps(body).encode("utf-8")
		self.status = 200
		self.headers: dict = {}

	def read(self) -> bytes:
		return self.body

	def __enter__(self):
		return self

	def __exit__(self, *exc_info) -> bool:
		return False


class AssistantProviderPayloadTests(TestCase):
	"""The wire format: tools go out, ``tool_calls`` come back parsed.

	``urllib`` is the only thing faked here, so the real payload building and the
	real tool loop run — which is what makes this an integration check of the
	OpenAI-compatible tool calling, not a mock of our own code.
	"""

	def setUp(self):
		override = override_settings(
			AI_LLM_ENABLED=True,
			AI_LLM_PROVIDER="custom",
			AI_LLM_API_KEY="test-key-4829",
			AI_LLM_MODEL="test-model",
			AI_LLM_BASE_URL="https://provider.test/v1",
		)
		override.enable()
		self.addCleanup(override.disable)
		ai_assistant.clear_cache()
		self.addCleanup(ai_assistant.clear_cache)
		llm.reset_cooldowns()
		llm.reset_signature_cache()
		self.addCleanup(llm.reset_cooldowns)
		self.addCleanup(llm.reset_signature_cache)

	def test_the_request_carries_the_tools_and_the_answer_is_parsed(self):
		MediaTitle.objects.create(type=MediaTitle.MediaType.ANIME, title="Birinchi")
		payloads = []

		def fake_urlopen(request, timeout=None):
			payload = json.loads(request.data.decode("utf-8"))
			payloads.append(payload)
			# A provider that asks for a function until it has the result, then
			# answers — exactly how the loop is supposed to be driven.
			answered = any(
				message.get("role") == "tool" for message in payload["messages"]
			)
			if answered:
				return _FakeResponse(
					{"choices": [{"message": {"role": "assistant", "content": "Mana."}}]}
				)
			return _FakeResponse(
				{
					"choices": [
						{
							"message": {
								"role": "assistant",
								"content": "",
								"tool_calls": [
									{
										"id": "call-9",
										"type": "function",
										"function": {
											"name": "search_catalog",
											"arguments": json.dumps({"matn": "birinchi"}),
										},
									}
								],
							}
						}
					]
				}
			)

		with mock.patch("movies.llm.urllib.request.urlopen", fake_urlopen):
			first = llm.chat_completion(
				[{"role": "user", "content": "qidir"}], tools=ai_assistant.TOOL_SCHEMAS
			)
			self.assertEqual([call.name for call in first.tool_calls], ["search_catalog"])
			self.assertEqual(first.tool_calls[0].arguments, json.dumps({"matn": "birinchi"}))

			# …and the same request shape drives a full assistant answer: the tool
			# runs against the database and its rows come back as the result list.
			result = ai_assistant.answer("birinchi anime")

		self.assertEqual(payloads[0]["tool_choice"], "auto")
		self.assertEqual(
			[tool["function"]["name"] for tool in payloads[0]["tools"]][:6],
			[
				"search_catalog",
				"title_details",
				"list_parts",
				"list_genres",
				"popular_titles",
				"catalog_stats",
			],
		)
		self.assertEqual(result.answer, "Mana.")
		self.assertEqual([title.title for title in result.titles], ["Birinchi"])
		# The third request (the assistant's second) carries the tool's output as
		# a `tool` message, which is what makes the final answer grounded.
		tool_messages = [
			message for message in payloads[2]["messages"] if message["role"] == "tool"
		]
		self.assertEqual(tool_messages[0]["tool_call_id"], "call-9")
		self.assertIn("Birinchi", tool_messages[0]["content"])

	def test_provider_call_metadata_rides_back_with_the_tool_call(self):
		"""Gemini 3 rejects the follow-up unless its signature is echoed."""
		MediaTitle.objects.create(type=MediaTitle.MediaType.ANIME, title="Birinchi")
		payloads = []
		signature = {"google": {"thought_signature": "sig-4829"}}

		def fake_urlopen(request, timeout=None):
			payload = json.loads(request.data.decode("utf-8"))
			payloads.append(payload)
			answered = any(
				message.get("role") == "tool" for message in payload["messages"]
			)
			if answered:
				return _FakeResponse(
					{"choices": [{"message": {"role": "assistant", "content": "Mana."}}]}
				)
			return _FakeResponse(
				{
					"choices": [
						{
							"message": {
								"role": "assistant",
								"content": "",
								"tool_calls": [
									{
										"id": "call-9",
										"type": "function",
										"extra_content": signature,
										"function": {
											"name": "search_catalog",
											"arguments": json.dumps({"matn": "birinchi"}),
										},
									}
								],
							}
						}
					]
				}
			)

		with mock.patch("movies.llm.urllib.request.urlopen", fake_urlopen):
			result = ai_assistant.answer("birinchi anime")

		self.assertEqual(result.answer, "Mana.")
		assistant_message = next(
			message for message in payloads[1]["messages"] if message.get("tool_calls")
		)
		self.assertEqual(assistant_message["tool_calls"][0]["extra_content"], signature)

	def test_a_provider_without_metadata_keeps_the_classic_shape(self):
		payloads = []

		def fake_urlopen(request, timeout=None):
			payload = json.loads(request.data.decode("utf-8"))
			payloads.append(payload)
			answered = any(
				message.get("role") == "tool" for message in payload["messages"]
			)
			if answered:
				return _FakeResponse(
					{"choices": [{"message": {"role": "assistant", "content": "Mana."}}]}
				)
			return _FakeResponse(
				{
					"choices": [
						{
							"message": {
								"role": "assistant",
								"content": "",
								"tool_calls": [
									{
										"id": "call-1",
										"type": "function",
										"function": {"name": "catalog_stats", "arguments": "{}"},
									}
								],
							}
						}
					]
				}
			)

		with mock.patch("movies.llm.urllib.request.urlopen", fake_urlopen):
			ai_assistant.answer("katalog statistikasi")

		assistant_message = next(
			message for message in payloads[1]["messages"] if message.get("tool_calls")
		)
		self.assertNotIn("extra_content", assistant_message["tool_calls"][0])

	def test_the_personal_tool_is_absent_without_opt_in(self):
		payloads = []

		def fake_urlopen(request, timeout=None):
			payloads.append(json.loads(request.data.decode("utf-8")))
			return _FakeResponse({"choices": [{"message": {"content": "Salom."}}]})

		with mock.patch("movies.llm.urllib.request.urlopen", fake_urlopen):
			ai_assistant.answer("salom")

		offered = [tool["function"]["name"] for tool in payloads[0]["tools"]]
		self.assertNotIn("personal_taste", offered)

	def test_a_provider_without_functions_still_answers(self):
		"""A model that cannot call the catalogue is asked without it.

		The question still goes out - the user gets words instead of silence -
		and the model is told that the catalogue is out of reach, so it does
		not invent titles.
		"""
		MediaTitle.objects.create(type=MediaTitle.MediaType.ANIME, title="Yolg'an titul")
		AIProvider.objects.create(
			name="Matnli",
			kind=AIProvider.Kind.CUSTOM,
			api_key="test-key-4829",
			model="test-model",
			base_url="https://provider.test/v1",
			supports_tools=False,
		)
		payloads = []

		def fake_urlopen(request, timeout=None):
			payloads.append(json.loads(request.data.decode("utf-8")))
			return _FakeResponse({"choices": [{"message": {"content": "Salom."}}]})

		with mock.patch("movies.llm.urllib.request.urlopen", fake_urlopen):
			result = ai_assistant.answer("salom")

		self.assertTrue(result.used_llm)
		self.assertEqual(result.answer, "Salom.")
		# No functions were offered, and the model was warned about it.
		self.assertNotIn("tools", payloads[0])
		system = payloads[0]["messages"][0]["content"]
		self.assertIn(llm.TEXT_ONLY_NOTE.strip(), system)
		# Nothing was looked up, so nothing is claimed.
		self.assertEqual(result.titles, ())
		self.assertTrue(result.conversational)


class AssistantCommandTests(TestCase):
	"""``manage.py ai_status`` replaces the old index command."""

	def setUp(self):
		override = override_settings(AI_LLM_API_KEY="", AI_LLM_BASE_URL="", AI_LLM_MODEL="")
		override.enable()
		self.addCleanup(override.disable)
		llm.reset_cooldowns()
		llm.reset_signature_cache()
		self.addCleanup(llm.reset_cooldowns)

	def make_provider(self, name="Birinchi", **extra):
		fields = dict(
			kind=AIProvider.Kind.CUSTOM,
			api_key="test-key-4829",
			model="test-model",
			base_url="https://birinchi.test/v1",
			priority=1,
		)
		fields.update(extra)
		return AIProvider.objects.create(name=name, **fields)

	def test_the_status_command_lists_the_chain(self):
		self.make_provider()
		out = StringIO()

		call_command("ai_status", stdout=out)

		text = out.getvalue()
		self.assertIn("AI zanjiri (1 ta provayder)", text)
		self.assertIn("Birinchi", text)
		self.assertIn("1 ta provayder tayyor", text)

	def test_the_status_command_explains_an_empty_chain(self):
		out = StringIO()
		call_command("ai_status", stdout=out)
		self.assertIn("AI provayder yo'q", out.getvalue())

	def test_the_test_flag_runs_a_real_answer(self):
		self.make_provider()
		out = StringIO()

		with mock.patch("movies.llm.chat_completion", mock.Mock(return_value=say("5 ta."))) as chat:
			call_command("ai_status", "--test", stdout=out)

		self.assertIn("5 ta.", out.getvalue())
		self.assertGreaterEqual(chat.call_count, 1)
