import base64
import importlib
import io
import json
import shutil
import tempfile
import urllib.error
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.db.models.query import QuerySet
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from django.utils.functional import empty
from PIL import Image
from rest_framework.test import APIClient

from . import llm
from .management.commands.fix_covers import Command as FixCoversCommand
from .models import (
	AIProvider,
	MediaPart,
	MediaTitle,
	MediaView,
	TelegramChannel,
	TelegramMedia,
)


def _sample_pdf(page_count: int = 2) -> bytes:
	"""A tiny multi-page PDF produced with Pillow (no fixture files)."""
	buffer = io.BytesIO()
	images = [
		Image.new("RGB", (120, 160), color) for color in ("white", "lightgrey")
	][:page_count]
	images[0].save(buffer, "PDF", save_all=True, append_images=images[1:])
	return buffer.getvalue()


def _sample_cover(color="orange") -> bytes:
	"""A tiny JPEG stand-in for a poster image."""
	buffer = io.BytesIO()
	Image.new("RGB", (40, 60), color).save(buffer, "JPEG", quality=70)
	return buffer.getvalue()


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

	def test_cover_image_is_stored_as_a_media_file_not_in_the_database(self):
		"""The poster lives under MEDIA_ROOT/covers/ so nginx can serve it."""
		with tempfile.TemporaryDirectory(prefix="kino-covers-") as media_root:
			with override_settings(MEDIA_ROOT=media_root):
				default_storage._wrapped = empty
				try:
					manga = MediaTitle.objects.create(
						type=MediaTitle.MediaType.MANGA,
						title="Cover Test",
						slug="cover-test",
						cover=ContentFile(_sample_cover(), name="cover.jpg"),
						cover_content_type="image/jpeg",
					)

					manga.refresh_from_db()
					self.assertTrue(manga.cover.name.startswith("covers/"))
					stored = Path(manga.cover.path)
					self.assertTrue(stored.exists())
					self.assertTrue(stored.read_bytes().startswith(b"\xff\xd8"))
					self.assertEqual(manga.cover_content_type, "image/jpeg")

					# The catalogue ships the URL, never the bytes: the
					# response stays small and the browser caches the image
					# itself (nginx sets the cache headers).
					response = self.client.get("/api/catalog/", {"type": "manga"})
					self.assertEqual(response.status_code, 200)
					payload = response.data[0]
					self.assertEqual(payload["cover"], manga.cover.url)
					self.assertTrue(payload["cover"].startswith("/media/covers/"))
					self.assertNotIn("base64", json.dumps(payload))
				finally:
					default_storage._wrapped = empty

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


class MangaPdfDownloadProtectionTests(TestCase):
	"""Chapters are readable, but no visitor ever receives a PDF file."""

	def setUp(self):
		self.media_root = tempfile.mkdtemp(prefix="kino-media-")
		self.override = override_settings(MEDIA_ROOT=self.media_root)
		self.override.enable()
		# FileSystemStorage caches MEDIA_ROOT on first use; force a fresh one.
		default_storage._wrapped = empty
		self.addCleanup(self._restore_media)

		self.client = APIClient()
		self.title = MediaTitle.objects.create(
			type=MediaTitle.MediaType.MANGA,
			title="Protected Manga",
			slug="protected-manga",
		)
		self.part = MediaPart.objects.create(content=self.title, number=1)
		self.part.pdf.save(
			"protected-manga-1.pdf", ContentFile(_sample_pdf()), save=True
		)

	def _restore_media(self):
		self.override.disable()
		default_storage._wrapped = empty
		shutil.rmtree(self.media_root, ignore_errors=True)

	def render_dir(self, part=None) -> Path:
		target = part or self.part
		return Path(self.media_root) / "manga" / "render" / str(target.pk)

	def public_dir(self, part=None) -> Path:
		"""What nginx serves as /media/manga/pages/<part_id>/."""
		target = part or self.part
		return Path(self.media_root) / "manga" / "pages" / str(target.pk)

	def test_pages_meta_renders_every_page_where_nginx_can_serve_them(self):
		response = self.client.get(f"/api/parts/{self.part.pk}/pages/")

		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertTrue(data["available"])
		self.assertEqual(data["count"], 2)
		self.assertTrue(data["etag"].startswith('"'))
		# The browser is pointed at nginx with a cache-busting version token;
		# Django only reports the location and never streams the bytes.
		self.assertEqual(data["base_url"], f"/media/manga/pages/{self.part.pk}/")
		self.assertRegex(data["version"], r"^[0-9a-f]{16}$")
		for number in (1, 2):
			page = self.public_dir() / f"page_{number}.jpg"
			self.assertTrue(page.exists(), f"page {number} was not rendered")
			self.assertTrue(page.read_bytes().startswith(b"\xff\xd8"))
		# The raw PDF and the rendering workspace stay unreachable.
		self.assertFalse((self.public_dir() / "source.pdf").exists())

	def test_a_page_is_a_jpeg_image_and_can_be_revalidated(self):
		response = self.client.get(f"/api/parts/{self.part.pk}/pages/1/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response["Content-Type"], "image/jpeg")
		body = b"".join(response.streaming_content)
		response.close()
		self.assertTrue(body.startswith(b"\xff\xd8"))
		self.assertNotIn(b"%PDF", body)

		cached = self.client.get(
			f"/api/parts/{self.part.pk}/pages/1/",
			HTTP_IF_NONE_MATCH=response["ETag"],
		)
		self.assertEqual(cached.status_code, 304)

	def test_pages_beyond_the_document_do_not_exist(self):
		response = self.client.get(f"/api/parts/{self.part.pk}/pages/3/")

		self.assertEqual(response.status_code, 404)

	def test_the_raw_pdf_endpoint_never_returns_the_file(self):
		download = self.client.get(f"/api/parts/{self.part.pk}/pdf/")

		self.assertEqual(download.status_code, 403)
		self.assertNotIn(b"%PDF", download.content)

		# Availability stays reportable (admin panel, upload feedback).
		meta = self.client.get(f"/api/parts/{self.part.pk}/pdf/", {"meta": 1})
		self.assertEqual(meta.status_code, 200)
		self.assertEqual(
			meta.json(), {"available": True, "source": "local", "size": self.part.pdf.size}
		)

	def test_telegram_only_chapters_render_without_exposing_the_bytes(self):
		part = MediaPart.objects.create(content=self.title, number=2)
		TelegramMedia.objects.create(
			part=part,
			file_id="tg-doc-file",
			media_type=TelegramMedia.MediaType.DOCUMENT,
			order=1,
		)

		with mock.patch(
			"movies.pdf_pages.fetch_file_bytes",
			return_value=(_sample_pdf(), "documents/chapter.pdf"),
		) as fetch:
			meta = self.client.get(f"/api/parts/{part.pk}/pages/")
			page = self.client.get(f"/api/parts/{part.pk}/pages/1/")

		self.assertEqual(meta.status_code, 200)
		self.assertEqual(meta.json()["count"], 2)
		self.assertEqual(page.status_code, 200)
		self.assertEqual(page["Content-Type"], "image/jpeg")
		page.close()
		# The Telegram download happens exactly once, then pages come from disk.
		fetch.assert_called_once_with("tg-doc-file")
		raw_pdf = self.client.get(f"/api/parts/{part.pk}/pdf/")
		self.assertEqual(raw_pdf.status_code, 403)

	def test_deleting_the_pdf_drops_every_rendered_page(self):
		meta = self.client.get(f"/api/parts/{self.part.pk}/pages/")
		self.assertTrue(meta.json()["available"])
		self.assertTrue(self.public_dir().exists())
		rendered = self.client.get(f"/api/parts/{self.part.pk}/pages/1/")
		b"".join(rendered.streaming_content)
		rendered.close()  # release the file handle so Windows can drop the cache
		self.assertTrue(self.render_dir().exists())

		denied = self.client.delete(f"/api/parts/{self.part.pk}/pdf/")
		self.assertIn(denied.status_code, (401, 403))

		staff = get_user_model().objects.create_user(
			username="editor", password="pass", is_staff=True
		)
		self.client.force_authenticate(staff)
		removed = self.client.delete(f"/api/parts/{self.part.pk}/pdf/")

		self.assertEqual(removed.status_code, 204)
		self.assertFalse(self.render_dir().exists())
		# nginx would otherwise keep serving the stale JPEGs forever.
		self.assertFalse(self.public_dir().exists())
		meta = self.client.get(f"/api/parts/{self.part.pk}/pdf/", {"meta": 1})
		self.assertEqual(meta.json()["available"], False)


class CoverAsMediaFileTests(TestCase):
	"""Covers: base64 in (the panel), bytes in (the bot), a /media URL out."""

	def setUp(self):
		self.media_root = tempfile.mkdtemp(prefix="kino-cover-media-")
		self.override = override_settings(MEDIA_ROOT=self.media_root)
		self.override.enable()
		default_storage._wrapped = empty
		self.addCleanup(self._restore_media)

		self.client = APIClient()
		self.admin = get_user_model().objects.create_superuser(
			username="cover-editor", password="cover-password"
		)

	def _restore_media(self):
		self.override.disable()
		default_storage._wrapped = empty
		shutil.rmtree(self.media_root, ignore_errors=True)

	def test_base64_cover_becomes_a_media_file_and_a_url(self):
		self.client.force_authenticate(self.admin)
		payload = base64.b64encode(_sample_cover()).decode("ascii")

		created = self.client.post(
			"/api/catalog/",
			{
				"type": "anime",
				"title": "Base64 Cover Anime",
				"slug": "base64-cover-anime",
				"cover": payload,
				"cover_content_type": "image/jpeg",
			},
			format="json",
		)

		self.assertEqual(created.status_code, 201, created.data)
		url = created.data["cover"]
		self.assertTrue(url.startswith("/media/covers/"), url)
		relative = url[len("/media/") :]
		self.assertTrue(default_storage.exists(relative))
		# No base64 blob left in the response body.
		self.assertNotIn(payload, json.dumps(created.data))

		# Echoing the URL back (what the panel does on an untouched form)
		# must not fail and must not replace the stored file.
		updated = self.client.patch(
			f"/api/catalog/{created.data['slug']}/",
			{"title": "Renamed Cover Anime", "cover": url},
			format="json",
		)

		self.assertEqual(updated.status_code, 200, updated.data)
		self.assertEqual(updated.data["cover"], url)
		title = MediaTitle.objects.get(slug="base64-cover-anime")
		self.assertEqual(title.cover.name, relative)
		self.assertTrue(title.cover.storage.exists(title.cover.name))

	def test_data_url_prefix_is_accepted_too(self):
		self.client.force_authenticate(self.admin)
		data_url = "data:image/jpeg;base64," + base64.b64encode(_sample_cover()).decode("ascii")

		created = self.client.post(
			"/api/catalog/",
			{"type": "movie", "title": "Data Url Movie", "slug": "data-url-movie", "cover": data_url},
			format="json",
		)

		self.assertEqual(created.status_code, 201, created.data)
		self.assertTrue(created.data["cover"].startswith("/media/covers/"))
		self.assertTrue(created.data["cover"].endswith(".jpg"))

	def test_invalid_base64_is_rejected(self):
		self.client.force_authenticate(self.admin)

		created = self.client.post(
			"/api/catalog/",
			{"type": "movie", "title": "Bad Cover", "slug": "bad-cover", "cover": "%%%not-base64%%%"},
			format="json",
		)

		self.assertEqual(created.status_code, 400)
		self.assertIn("cover", created.data)


class FixCoversCommandTests(TestCase):
	"""`manage.py fix_covers` repairs what the base64 era left behind."""

	def setUp(self):
		self.media_root = tempfile.mkdtemp(prefix="kino-fix-covers-")
		self.override = override_settings(MEDIA_ROOT=self.media_root)
		self.override.enable()
		default_storage._wrapped = empty
		self.addCleanup(self._restore_media)

	def _restore_media(self):
		self.override.disable()
		default_storage._wrapped = empty
		shutil.rmtree(self.media_root, ignore_errors=True)

	def _title(self, slug, *, cover=None, content_type="image/jpeg"):
		fields = {
			"type": MediaTitle.MediaType.MANGA,
			"title": slug,
			"slug": slug,
			"cover_content_type": content_type,
		}
		if cover is not None:
			fields["cover"] = cover
		return MediaTitle.objects.create(**fields)

	def _stored_bytes(self, title) -> bytes:
		return Path(title.cover.path).read_bytes()

	def _base64_cover(self) -> str:
		return base64.b64encode(_sample_cover()).decode("ascii")

	def _run(self, **kwargs) -> str:
		out = io.StringIO()
		call_command("fix_covers", stdout=out, **kwargs)
		return out.getvalue()

	def test_base64_file_is_decoded_into_the_image_it_stands_for(self):
		payload = self._base64_cover()
		title = self._title(
			"broken-cover",
			cover=ContentFile(payload.encode("ascii"), name="broken-cover.jpg"),
			content_type="image/png",
		)
		broken_path = Path(self.media_root, title.cover.name)
		self.assertTrue(broken_path.exists())

		report = self._run()

		self.assertIn("fixed=1", report)
		self.assertIn("fayl ->", report)
		title.refresh_from_db()
		# A fresh URL: the browser must not keep whatever it cached before.
		self.assertNotEqual(title.cover.name, "covers/broken-cover.jpg")
		self.assertTrue(title.cover.name.startswith("covers/"))
		self.assertTrue(self._stored_bytes(title).startswith(b"\xff\xd8"))
		self.assertEqual(title.cover_content_type, "image/jpeg")
		self.assertFalse(broken_path.exists())

	def test_second_run_changes_nothing(self):
		title = self._title(
			"idem-cover",
			cover=ContentFile(self._base64_cover().encode("ascii"), name="idem-cover.jpg"),
		)

		self._run()
		title.refresh_from_db()
		name, content = title.cover.name, self._stored_bytes(title)

		report = self._run()
		self.assertIn("ok=1", report)
		self.assertIn("fixed=0", report)
		self.assertEqual(title.cover.name, name)
		self.assertEqual(self._stored_bytes(title), content)

	def test_dry_run_reports_without_writing(self):
		payload = self._base64_cover()
		title = self._title(
			"dry-cover",
			cover=ContentFile(payload.encode("ascii"), name="dry-cover.jpg"),
		)

		report = self._run(dry_run=True)

		self.assertIn("[dry-run]", report)
		self.assertIn("fixed=1", report)
		title.refresh_from_db()
		self.assertEqual(title.cover.name, "covers/dry-cover.jpg")
		self.assertEqual(self._stored_bytes(title), payload.encode("ascii"))

	def test_valid_cover_is_left_untouched(self):
		title = self._title("good-cover", cover=ContentFile(_sample_cover(), name="good-cover.jpg"))

		report = self._run()

		self.assertIn("ok=1", report)
		self.assertIn("fixed=0", report)
		title.refresh_from_db()
		self.assertEqual(title.cover.name, "covers/good-cover.jpg")
		self.assertTrue(self._stored_bytes(title).startswith(b"\xff\xd8"))

	def test_lost_file_is_reported_and_strict_fails(self):
		title = self._title("gone-cover", cover=ContentFile(_sample_cover(), name="gone-cover.jpg"))
		Path(self.media_root, title.cover.name).unlink()

		report = self._run()
		self.assertIn("missing=1", report)

		with self.assertRaises(CommandError):
			self._run(strict=True)

	def test_title_without_any_cover_is_empty_not_an_error(self):
		self._title("no-cover")

		report = self._run(strict=True)

		self.assertIn("empty=1", report)
		self.assertIn("checked=1", report)

	def test_legacy_blob_restores_a_lost_file(self):
		title = self._title("lost-cover", cover=ContentFile(_sample_cover(), name="lost-cover.jpg"))
		Path(self.media_root, title.cover.name).unlink()
		payload = base64.b64encode(_sample_cover("green")).decode("ascii")

		with mock.patch.object(FixCoversCommand, "_column_exists", return_value=True), mock.patch.object(
			FixCoversCommand, "_legacy_blob", return_value=payload.encode("ascii")
		):
			report = self._run()

		self.assertIn("fixed=1", report)
		self.assertIn("cover_blob ->", report)
		title.refresh_from_db()
		self.assertTrue(self._stored_bytes(title).startswith(b"\xff\xd8"))
		self.assertNotEqual(self._stored_bytes(title), _sample_cover())

	def test_undecodable_bytes_are_reported_and_do_not_stop_the_run(self):
		self._title("bad-cover", cover=ContentFile(b"neither image nor base64...", name="bad-cover.jpg"))
		self._title("fine-cover", cover=ContentFile(_sample_cover(), name="fine-cover.jpg"))

		report = self._run()

		self.assertIn("failed=1", report)
		self.assertIn("ok=1", report)
		self.assertIn("bad-cover", report)
		self.assertIn("checked=2", report)

	def test_unmigrated_schema_is_reported_instead_of_written(self):
		payload = self._base64_cover()
		title = self._title(
			"old-schema",
			cover=ContentFile(payload.encode("ascii"), name="old-schema.jpg"),
		)

		with mock.patch.object(FixCoversCommand, "_cover_column_is_binary", return_value=True):
			report = self._run()

		self.assertIn("migratsiya", report)
		self.assertNotIn("checked=", report)
		title.refresh_from_db()
		self.assertEqual(title.cover.name, "covers/old-schema.jpg")
		self.assertEqual(self._stored_bytes(title), payload.encode("ascii"))


class CoverPayloadMigrationTests(SimpleTestCase):
	"""Migration 0019 decodes whatever shape the stored payload has."""

	def test_base64_text_raw_bytes_and_memoryviews_all_become_image_bytes(self):
		module = importlib.import_module("movies.migrations.0019_migrate_covers_to_files")
		image = _sample_cover()

		self.assertEqual(module._decode_payload(image), image)
		self.assertEqual(module._decode_payload(memoryview(image)), image)
		self.assertEqual(module._decode_payload(base64.b64encode(image)), image)
		text = "data:image/jpeg;base64,\n\t" + base64.b64encode(image).decode("ascii")
		self.assertEqual(module._decode_payload(text.encode("ascii")), image)
		# Anything that is not base64 is kept as it was.
		self.assertEqual(module._decode_payload(b"!!! not base64 !!!"), b"!!! not base64 !!!")



