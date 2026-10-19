import io
import json
import urllib.error
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.db.models.query import QuerySet
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from . import llm
from .models import (
	AIProvider,
	MediaPart,
	MediaTitle,
	MediaView,
	TelegramChannel,
	TelegramMedia,
)


class CatalogMediaTests(TestCase):
	def setUp(self):
		self.client = APIClient()

	def test_swagger_ui_and_schema_include_all_api_routes(self):
		docs_response = self.client.get("/api/docs/")
		schema_response = self.client.get("/api/schema/?format=json")

		self.assertEqual(docs_response.status_code, 200)
		self.assertContains(docs_response, "SwaggerUIBundle")
		self.assertEqual(schema_response.status_code, 200)
		paths = schema_response.json()["paths"]
		self.assertIn("/api/auth/telegram/mini-app/", paths)
		self.assertIn("/api/auth/telegram/login/", paths)
		self.assertIn("/api/catalog/", paths)
		self.assertIn("/api/catalog/code/{code}/", paths)
		self.assertIn("/api/channels/", paths)
		self.assertIn("/api/telegram-media/", paths)

	def test_catalog_can_be_read_and_filtered_without_authentication(self):
		MediaTitle.objects.create(
			type=MediaTitle.MediaType.MANGA,
			title="Public Manga",
			slug="public-manga",
		)
		MediaTitle.objects.create(
			type=MediaTitle.MediaType.MOVIE,
			title="Public Movie",
			slug="public-movie",
		)

		response = self.client.get("/api/catalog/", {"type": "manga"})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.data), 1)
		self.assertEqual(response.data[0]["slug"], "public-manga")
		self.assertRegex(response.data[0]["code"], r"^[0-9]{4}$")

	def test_slug_detail_and_code_lookup_return_all_channel_file_ids(self):
		content = MediaTitle.objects.create(
			type=MediaTitle.MediaType.SERIES,
			title="Four Channel Series",
			slug="four-channel-series",
		)
		part = MediaPart.objects.create(content=content, number=1)
		channels = [
			TelegramChannel.objects.create(chat_id=-1000000000000 - index, title=f"Source {index}")
			for index in range(1, 5)
		]
		for index, channel in enumerate(channels, start=1):
			TelegramMedia.objects.create(
				part=part,
				channel=channel,
				file_id=f"channel-{index}-file-id",
				media_type=TelegramMedia.MediaType.VIDEO,
				order=index,
			)

		slug_response = self.client.get(f"/api/catalog/{content.slug}/")
		self.assertEqual(slug_response.status_code, 200)
		self.assertEqual(slug_response.data["code"], content.code)
		self.assertEqual(slug_response.data["parts"][0]["id"], part.pk)
		self.assertNotIn("telegram_media", slug_response.data["parts"][0])

		anonymous_response = self.client.get(f"/api/catalog/code/{content.code}/")
		self.assertIn(anonymous_response.status_code, (401, 403))

		user = get_user_model().objects.create_user(username="code-search-user", password="secret")
		self.client.force_authenticate(user)
		lookup_response = self.client.get(f"/api/catalog/code/{content.code}/")

		self.assertEqual(lookup_response.status_code, 200)
		self.assertEqual(lookup_response.data["slug"], content.slug)
		media = lookup_response.data["parts"][0]["telegram_media"]
		self.assertEqual(len(media), 4)
		self.assertEqual(
			[record["channel"]["title"] for record in media],
			[f"Source {index}" for index in range(1, 5)],
		)
		self.assertEqual(
			[record["file_id"] for record in media],
			[f"channel-{index}-file-id" for index in range(1, 5)],
		)

	def test_media_codes_are_unique_four_digit_numbers(self):
		first = MediaTitle.objects.create(
			type=MediaTitle.MediaType.ANIME,
			title="First Anime",
			slug="first-anime",
		)
		second = MediaTitle.objects.create(
			type=MediaTitle.MediaType.ANIME,
			title="Second Anime",
			slug="second-anime",
		)

		self.assertRegex(first.code, r"^[0-9]{4}$")
		self.assertRegex(second.code, r"^[0-9]{4}$")
		self.assertNotEqual(first.code, second.code)

	def test_admin_can_register_channels_and_assign_media_source(self):
		admin = get_user_model().objects.create_superuser(
			username="channel-admin",
			password="admin-password",
		)
		self.client.force_authenticate(admin)

		channel_response = self.client.post(
			"/api/channels/",
			{"chat_id": -1001234567890, "title": "Anime Source", "username": "anime_source"},
			format="json",
		)
		self.assertEqual(channel_response.status_code, 201)

		content = MediaTitle.objects.create(
			type=MediaTitle.MediaType.ANIME,
			title="Channel Anime",
			slug="channel-anime",
		)
		part = MediaPart.objects.create(content=content, number=1)
		media_response = self.client.post(
			"/api/telegram-media/",
			{
				"part": part.pk,
				"channel": channel_response.data["id"],
				"file_id": "channel-video-file-id",
				"media_type": "video",
				"order": 1,
			},
			format="json",
		)

		self.assertEqual(media_response.status_code, 201)
		self.assertEqual(media_response.data["channel"], channel_response.data["id"])

	def test_catalog_writes_require_admin_and_telegram_file_ids_are_private(self):
		anonymous_write = self.client.post(
			"/api/catalog/",
			{"type": "movie", "title": "Private Movie", "slug": "private-movie"},
			format="json",
		)
		private_media = self.client.get("/api/telegram-media/")

		self.assertIn(anonymous_write.status_code, (401, 403))
		self.assertIn(private_media.status_code, (401, 403))

		admin = get_user_model().objects.create_superuser(
			username="catalog-admin",
			password="admin-password",
		)
		self.client.force_authenticate(admin)
		admin_write = self.client.post(
			"/api/catalog/",
			{"type": "movie", "title": "Admin Movie", "slug": "admin-movie"},
			format="json",
		)

		self.assertEqual(admin_write.status_code, 201)

	def test_cover_image_bytes_are_stored_in_the_database(self):
		manga = MediaTitle.objects.create(
			type=MediaTitle.MediaType.MANGA,
			title="Cover Test",
			slug="cover-test",
			cover=b"image-bytes",
			cover_content_type="image/jpeg",
		)

		manga.refresh_from_db()
		self.assertEqual(manga.cover, b"image-bytes")
		self.assertEqual(manga.cover_content_type, "image/jpeg")

	def test_manga_pages_are_returned_in_order_by_telegram_file_id(self):
		manga = MediaTitle.objects.create(
			type=MediaTitle.MediaType.MANGA,
			title="Sample Manga",
			slug="sample-manga",
		)
		chapter = MediaPart.objects.create(content=manga, number=1)
		TelegramMedia.objects.create(
			part=chapter,
			file_id="page-two-file-id",
			media_type=TelegramMedia.MediaType.PHOTO,
			order=2,
		)
		TelegramMedia.objects.create(
			part=chapter,
			file_id="page-one-file-id",
			media_type=TelegramMedia.MediaType.PHOTO,
			order=1,
		)

		self.assertEqual(
			list(chapter.telegram_media.values_list("file_id", flat=True)),
			["page-one-file-id", "page-two-file-id"],
		)

	def test_movie_video_is_retrievable_by_telegram_file_id(self):
		movie = MediaTitle.objects.create(
			type=MediaTitle.MediaType.MOVIE,
			title="Sample Movie",
			slug="sample-movie",
		)
		film = MediaPart.objects.create(content=movie, number=1)
		video = TelegramMedia.objects.create(
			part=film,
			file_id="telegram-video-file-id",
			media_type=TelegramMedia.MediaType.VIDEO,
			order=1,
		)

		self.assertEqual(film.telegram_media.get(), video)
		self.assertEqual(video.file_id, "telegram-video-file-id")


class MediaViewApiTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.user = get_user_model().objects.create_user(
			username="viewer",
			password="viewer-secret-4829",
		)
		self.title = MediaTitle.objects.create(
			type=MediaTitle.MediaType.SERIES,
			title="Viewed Series",
			slug="viewed-series",
		)
		self.part = MediaPart.objects.create(content=self.title, number=1)

	def test_recording_a_view_creates_one_row_per_title(self):
		self.client.force_authenticate(self.user)

		first = self.client.post("/api/catalog/viewed-series/view/", {"part": self.part.pk}, format="json")
		second = self.client.post("/api/catalog/viewed-series/view/", {}, format="json")

		self.assertEqual(first.status_code, 200)
		self.assertEqual(second.status_code, 200)
		views = MediaView.objects.filter(user=self.user, title=self.title)
		self.assertEqual(views.count(), 1)
		view = views.get()
		self.assertEqual(view.count, 2)
		self.assertEqual(view.source, MediaView.Source.SITE)
		self.assertEqual(view.part, self.part)

	def test_recording_a_view_requires_authentication(self):
		response = self.client.post("/api/catalog/viewed-series/view/", {}, format="json")

		self.assertIn(response.status_code, (401, 403))
		self.assertFalse(MediaView.objects.exists())

	def test_recording_a_view_ignores_a_part_from_another_title(self):
		other = MediaTitle.objects.create(
			type=MediaTitle.MediaType.MOVIE,
			title="Other Movie",
			slug="other-movie",
		)
		foreign_part = MediaPart.objects.create(content=other, number=1)
		self.client.force_authenticate(self.user)

		response = self.client.post(
			"/api/catalog/viewed-series/view/",
			{"part": foreign_part.pk},
			format="json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertIsNone(MediaView.objects.get(user=self.user).part)


# --------------------------------------------------------------------------- #
# The reasoning chain: HTTP stubs for the failover tests
# --------------------------------------------------------------------------- #
ONE_URL = "https://birinchi.test/v1"
TWO_URL = "https://ikkinchi.test/v1"


def completion_body(text: str) -> dict:
	"""An OpenAI-shaped answer with ``text`` in it."""
	return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def provider_answer(text: str) -> dict:
	return {"status": 200, "body": completion_body(text)}


def provider_limit(*, retry_after=None) -> dict:
	"""A quota answer (429), optionally with the provider's own Retry-After."""
	headers = {"Retry-After": str(retry_after)} if retry_after else {}
	return {"status": 429, "body": {"error": "rate limit"}, "headers": headers}


class _FakeResponse:
	"""The little bit of an HTTP response ``_attempt`` reads."""

	def __init__(self, body: bytes):
		self.body = body
		self.status = 200
		self.headers: dict = {}

	def read(self) -> bytes:
		return self.body

	def __enter__(self):
		return self

	def __exit__(self, *exc_info) -> bool:
		return False


class ProviderStub:
	"""A stand-in for ``urllib.request.urlopen``: one canned answer per endpoint.

	Routing by URL is what makes the failover testable: the first provider can
	refuse while the second answers, and every call is recorded — so a test can
	assert *which* providers were asked, in which order, and that the request was
	never in flight to two of them at once (``max_concurrent``).
	"""

	def __init__(self, answers: dict):
		self.answers = dict(answers)
		self.calls = []
		self.max_concurrent = 0
		self._running = 0

	def __call__(self, request, timeout=None):
		url = request.full_url
		base = url.rsplit("/chat/completions", 1)[0]
		self.calls.append(base)
		self._running += 1
		self.max_concurrent = max(self.max_concurrent, self._running)
		try:
			answer = self.answers[base]
			body = json.dumps(answer["body"]).encode("utf-8")
			if answer["status"] != 200:
				raise urllib.error.HTTPError(
					url,
					answer["status"],
					"refused",
					answer.get("headers") or {},
					io.BytesIO(body),
				)
			return _FakeResponse(body)
		finally:
			self._running -= 1


class _FakeClock:
	"""A hand-driven clock: the chain's time budget is tested without sleeping."""

	def __init__(self, start: float = 1000.0):
		self.now = start

	def __call__(self) -> float:
		return self.now

	def advance(self, seconds: float) -> None:
		self.now += seconds


class AIProviderFailoverTests(TestCase):
	"""The provider chain: who is asked, in which order, and after which failure.

	``urllib`` is stubbed at the request level, so these tests run the real
	payload building, the real status handling and the real failover — not a
	mocked ``chat``.
	"""

	def setUp(self):
		super().setUp()
		# The suite must not read the developer's real key from .env: these
		# tests describe a chain made of database rows only.
		override = override_settings(AI_LLM_API_KEY="", AI_LLM_BASE_URL="", AI_LLM_MODEL="")
		override.enable()
		self.addCleanup(override.disable)
		# Both caches are process-wide; a leftover would make the next test lie.
		llm.reset_cooldowns()
		llm.reset_signature_cache()
		self.addCleanup(llm.reset_cooldowns)
		self.addCleanup(llm.reset_signature_cache)

	def make_provider(self, name, base_url, *, priority=100, **extra):
		fields = dict(
			kind=AIProvider.Kind.CUSTOM,
			api_key="test-key",
			model="test-model",
			base_url=base_url,
			priority=priority,
		)
		fields.update(extra)
		return AIProvider.objects.create(name=name, **fields)

	def ask(self, stub, prompt="salom", **kwargs):
		"""One ``llm.chat`` call against the stub, outside any real network."""
		with mock.patch("movies.llm.urllib.request.urlopen", stub):
			return llm.chat([{"role": "user", "content": prompt}], **kwargs)

	def test_the_chain_is_read_from_the_database_in_order(self):
		"""The single function the feature asks: who can answer, and in what order."""
		slow = self.make_provider("Sekin", ONE_URL, priority=1, avg_latency_ms=900)
		self.make_provider("Tez", TWO_URL, priority=2)

		self.assertEqual([c.label for c in llm.provider_chain()], ["Sekin", "Tez"])

		AIProvider.objects.filter(pk=slow.pk).update(priority=5, avg_latency_ms=900)
		AIProvider.objects.filter(name="Tez").update(priority=5, avg_latency_ms=120)

		chain = llm.provider_chain()
		# Same preference, so the provider that already proved faster goes first.
		self.assertEqual([c.label for c in chain], ["Tez", "Sekin"])
		self.assertEqual(chain[0].base_url, TWO_URL)
		self.assertEqual(chain[0].api_key, "test-key")
		# Every entry carries its own row, so the runtime state goes back to it.
		self.assertTrue(all(config.row_id for config in chain))

	def test_a_keyless_row_and_an_empty_table_fall_back_to_the_environment(self):
		"""A row without a key is skipped; with no rows at all .env still works."""
		self.make_provider("Kalitsiz", ONE_URL, api_key="")
		active = self.make_provider("Kalitli", TWO_URL)

		self.assertEqual([c.label for c in llm.provider_chain()], ["Kalitli"])

		active.is_active = False
		active.save(update_fields=["is_active", "updated_at"])
		with override_settings(
			AI_LLM_API_KEY="env-key",
			AI_LLM_PROVIDER="custom",
			AI_LLM_MODEL="env-model",
			AI_LLM_BASE_URL=ONE_URL,
		):
			chain = llm.provider_chain()

		self.assertEqual([c.label for c in chain], ["custom"])
		self.assertIsNone(chain[0].row_id)
		self.assertEqual(chain[0].base_url, ONE_URL)
		self.assertEqual(chain[0].model, "env-model")

	def test_a_limited_provider_hands_the_question_to_the_next_one(self):
		"""The whole point: 429 on the first provider is not a failed search."""
		first = self.make_provider("Birinchi", ONE_URL, priority=1)
		second = self.make_provider("Ikkinchi", TWO_URL, priority=2)
		stub = ProviderStub(
			{ONE_URL: provider_limit(), TWO_URL: provider_answer("Mana javob.")}
		)

		answer = self.ask(stub)

		self.assertEqual(answer, "Mana javob.")
		self.assertEqual(stub.calls, [ONE_URL, TWO_URL])
		# Neither all at once nor in parallel: the second was asked only after the
		# first refused.
		self.assertEqual(stub.max_concurrent, 1)
		first.refresh_from_db()
		second.refresh_from_db()
		self.assertGreater(first.cooldown_until, timezone.now())
		self.assertEqual(first.failure_count, 1)
		self.assertIn("429", first.last_error)
		self.assertEqual(second.success_count, 1)
		self.assertIsNone(second.cooldown_until)
		self.assertEqual(second.last_error, "")

	def test_the_next_request_does_not_ask_the_limited_provider_again(self):
		"""A cooldown is remembered, so the failure is paid for once, not per search."""
		self.make_provider("Birinchi", ONE_URL, priority=1)
		self.make_provider("Ikkinchi", TWO_URL, priority=2)
		stub = ProviderStub(
			{ONE_URL: provider_limit(), TWO_URL: provider_answer("Mana javob.")}
		)

		self.ask(stub, prompt="birinchi savol")
		stub.calls.clear()
		second = self.ask(stub, prompt="ikkinchi savol")

		self.assertEqual(second, "Mana javob.")
		self.assertEqual(stub.calls, [TWO_URL])

	def test_this_process_remembers_a_limit_even_if_the_row_write_fails(self):
		"""The in-process cooldown is the second line of defence, not a duplicate.

		A search during a database hiccup must still not re-ask a provider that
		just said "limit" — and must not wait for it either.
		"""
		first = self.make_provider("Birinchi", ONE_URL, priority=1)
		self.make_provider("Ikkinchi", TWO_URL, priority=2)
		stub = ProviderStub(
			{ONE_URL: provider_limit(), TWO_URL: provider_answer("Mana javob.")}
		)

		with mock.patch("movies.llm._record_failure"):
			self.ask(stub, prompt="birinchi savol")
		first.refresh_from_db()
		self.assertIsNone(first.cooldown_until)
		self.assertGreater(llm.cooldown_left(f"row:{first.pk}"), 0)

		stub.calls.clear()
		self.ask(stub, prompt="ikkinchi savol")

		self.assertEqual(stub.calls, [TWO_URL])

	def test_the_providers_own_retry_after_decides_the_wait(self):
		self.make_provider("Birinchi", ONE_URL, priority=1)
		self.make_provider("Ikkinchi", TWO_URL, priority=2)
		stub = ProviderStub(
			{
				ONE_URL: provider_limit(retry_after=120),
				TWO_URL: provider_answer("Mana javob."),
			}
		)

		self.ask(stub)

		first = AIProvider.objects.get(name="Birinchi")
		wait = (first.cooldown_until - timezone.now()).total_seconds()
		self.assertGreater(wait, 100)
		self.assertLessEqual(wait, 130)

	def test_when_every_provider_is_cooling_nothing_is_sent_at_all(self):
		"""An outage must not cost the user a wait: the vectors answer instantly."""
		self.make_provider(
			"Birinchi",
			ONE_URL,
			priority=1,
			cooldown_until=timezone.now() + timedelta(minutes=5),
		)
		self.make_provider(
			"Ikkinchi",
			TWO_URL,
			priority=2,
			cooldown_until=timezone.now() + timedelta(seconds=30),
		)
		with mock.patch("movies.llm.urllib.request.urlopen") as urlopen:
			with self.assertRaises(llm.LLMUnavailable) as raised:
				self.ask(None)

		self.assertEqual(urlopen.call_count, 0)
		self.assertEqual(llm.provider_chain(), [])
		# The message tells the two empty-chain cases apart, with the wait.
		self.assertIn("limitda", str(raised.exception))
		wait = llm.soonest_cooldown_seconds()
		self.assertIsNotNone(wait)
		self.assertLessEqual(wait, 31)
		# ...and nothing is hidden: the rows are still reported, as "kutishda".
		report = llm.configuration()
		self.assertEqual(len(report["providers"]), 2)
		self.assertEqual(report["usable"], 0)
		self.assertFalse(report["configured"])
		self.assertFalse(any(config["usable"] for config in report["providers"]))

	def test_a_broken_bookkeeping_write_never_breaks_the_answer(self):
		"""Counting the call is best effort; replying never is."""
		self.make_provider("Birinchi", ONE_URL, priority=1)
		self.make_provider("Ikkinchi", TWO_URL, priority=2)
		stub = ProviderStub(
			{ONE_URL: provider_limit(), TWO_URL: provider_answer("Mana javob.")}
		)

		with mock.patch.object(
			QuerySet, "update", side_effect=DatabaseError("baza yopildi")
		):
			answer = self.ask(stub)

		self.assertEqual(answer, "Mana javob.")

	def test_the_chain_budget_shrinks_after_a_slow_provider(self):
		"""Two dead providers cost the deadline, not two full timeouts."""
		self.make_provider("Birinchi", ONE_URL, priority=1)
		self.make_provider("Ikkinchi", TWO_URL, priority=2)
		clock = _FakeClock()
		asked = []

		def slow(config, messages, *, max_tokens, temperature, seconds, **kwargs):
			asked.append((config.label, seconds))
			clock.advance(3)
			raise llm.ProviderError(f"{config.label} juda sekin javob berdi")

		with mock.patch("movies.llm._monotonic", clock), mock.patch(
			"movies.llm._attempt", side_effect=slow
		), override_settings(AI_LLM_TIMEOUT=8, AI_LLM_DEADLINE=10):
			with self.assertRaises(llm.LLMUnavailable):
				self.ask(None)

		self.assertEqual(asked, [("Birinchi", 8), ("Ikkinchi", 7)])


class AIProviderAdminTests(TestCase):
	"""The operator's screen: the chain itself, and the two actions that fix it."""

	def setUp(self):
		self.client = Client()
		self.client.force_login(
			get_user_model().objects.create_superuser(
				username="root", password="root-secret-4829"
			)
		)
		# No environment provider: the chain under test is the rows below.
		override = override_settings(AI_LLM_API_KEY="", AI_LLM_BASE_URL="", AI_LLM_MODEL="")
		override.enable()
		self.addCleanup(override.disable)
		# The admin templates link their CSS through {% static %}, and production
		# storage is the hashed manifest one — which only exists after a
		# collectstatic. The pages are what is under test here, not the hashing.
		override = override_settings(
			STORAGES={
				"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
				"staticfiles": {
					"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
				},
			}
		)
		override.enable()
		self.addCleanup(override.disable)
		llm.reset_cooldowns()
		self.addCleanup(llm.reset_cooldowns)

	def make_provider(self, name="Birinchi", **extra):
		fields = dict(
			kind=AIProvider.Kind.CUSTOM,
			api_key="test-key-4829",
			model="test-model",
			base_url=ONE_URL,
			priority=1,
		)
		fields.update(extra)
		return AIProvider.objects.create(name=name, **fields)

	def act(self, action: str, *rows):
		return self.client.post(
			"/django-admin/movies/aiprovider/",
			{
				"action": action,
				"_selected_action": [row.pk for row in rows],
				"select_across": "0",
				"index": "0",
			},
			follow=True,
		)

	def test_the_chain_is_visible_and_editable(self):
		self.make_provider("Birinchi")
		response = self.client.get("/django-admin/movies/aiprovider/")
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Birinchi")
		# The key is never printed in full.
		self.assertContains(response, "test…4829")
		self.assertNotContains(response, "test-key-4829")

	def test_the_cooldown_reset_action_makes_a_provider_usable_again(self):
		"""The fix after a limit is cleared out of hours: one click, no SQL."""
		row = self.make_provider(cooldown_until=timezone.now() + timedelta(minutes=5))
		self.assertEqual(llm.provider_chain(), [])

		response = self.act("clear_cooldowns", row)

		self.assertEqual(response.status_code, 200)
		row.refresh_from_db()
		self.assertIsNone(row.cooldown_until)
		self.assertEqual([c.label for c in llm.provider_chain()], ["Birinchi"])

	def test_the_test_action_reports_what_the_provider_answered(self):
		row = self.make_provider()
		stub = ProviderStub({ONE_URL: provider_answer("Ha")})

		with mock.patch("movies.llm.urllib.request.urlopen", stub):
			response = self.act("test_selected", row)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Birinchi")
		self.assertEqual(len(stub.calls), 1)

	def test_a_provider_can_be_taken_out_of_the_chain_from_the_admin(self):
		row = self.make_provider()

		self.act("deactivate", row)

		row.refresh_from_db()
		self.assertFalse(row.is_active)
		self.assertEqual(llm.provider_chain(), [])


