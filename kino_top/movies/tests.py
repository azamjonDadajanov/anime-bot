import io
import json
import math
import re
import shutil
import tempfile
import urllib.error
import zlib
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.db.models.query import QuerySet
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import Subscription

from . import ai_reasoning, ai_search, embeddings, llm
from .models import (
	AIProvider,
	Genre,
	MediaPart,
	MediaTitle,
	MediaView,
	TelegramChannel,
	TelegramMedia,
	TitleEmbedding,
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
# AI search (semantic catalogue search)
# --------------------------------------------------------------------------- #
AI_QUERY = "sarguzasht va qo'rqinchli animelar"


class FakeEncoder:
	"""Deterministic stand-in for the ONNX sentence encoder.

	Words are hashed into fixed buckets, so two texts that share a word point in
	a similar direction. That is enough to test ranking, thresholds and index
	bookkeeping without downloading (and running) the real 470MB model, and it
	keeps the tests hermetic and instant.
	"""

	dim = 32

	def encode(self, texts, *, batch_size=16):
		vectors = []
		for text in texts:
			vector = [0.0] * self.dim
			for word in re.findall(r"[^\W\d_]+", str(text or "").lower()):
				vector[zlib.crc32(word.encode("utf-8")) % self.dim] += 1.0
			length = math.sqrt(sum(value * value for value in vector)) or 1.0
			vectors.append([value / length for value in vector])
		return vectors


class AISearchTestCase(TestCase):
	"""Shared fixture: fake encoder, throwaway model dir, AI search enabled.

	``AI_MODEL_DIR`` points at an empty temporary directory on purpose: the
	suite must never read (or download) the real model, and ``is_ready()`` is
	what tells the API whether a deployment can serve the feature.
	"""

	def setUp(self):
		self.model_dir = tempfile.mkdtemp(prefix="ai-model-")
		self.addCleanup(shutil.rmtree, self.model_dir, ignore_errors=True)
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
		self.client = APIClient()
		self.ai_url = "/api/catalog/ai-search/"

	# ------------------------------------------------------------------ helpers
	def write_model_files(self):
		"""Pretend the model was downloaded (``is_ready`` only stats the files)."""
		for name in embeddings.required_files():
			path = Path(self.model_dir) / name
			path.parent.mkdir(parents=True, exist_ok=True)
			path.write_bytes(b"stub")

	def make_title(
		self,
		title="Qorong'i O'rmon",
		*,
		media_type=MediaTitle.MediaType.ANIME,
		genres=(),
		synopsis="",
	):
		media = MediaTitle.objects.create(type=media_type, title=title, synopsis=synopsis)
		if genres:
			media.genres.set([Genre.objects.get_or_create(name=name)[0] for name in genres])
		return media

	def make_subscriber(self, username="ai-subscriber", *, plan="monthly", days=30):
		# New accounts already get their (free) Subscription row from the users
		# app, so this bumps that row instead of inserting a second one.
		user = get_user_model().objects.create_user(username=username, password="ai-secret-4829")
		subscription, _ = Subscription.objects.get_or_create(user=user)
		subscription.plan = plan
		subscription.started_at = timezone.now()
		subscription.expires_at = timezone.now() + timedelta(days=days)
		subscription.save(update_fields=["plan", "started_at", "expires_at", "updated_at"])
		# Creating the account cached its (free) subscription on the instance;
		# drop that cache so the returned user reflects the paid plan.
		user.refresh_from_db()
		return user

	def index_all(self):
		"""Install the (stub) model files and run the indexer over the catalogue."""
		self.write_model_files()
		call_command("index_anime_embeddings", stdout=StringIO())


class AISearchIndexTests(AISearchTestCase):
	"""The index follows the catalogue: create, edit, genre change, delete."""

	def test_indexing_stores_a_vector_and_the_document_digest(self):
		title = self.make_title()
		self.assertTrue(ai_search.index_title(title))
		row = TitleEmbedding.objects.get(title=title)
		expected = ai_search.document_hash(ai_search.title_document(title))
		self.assertEqual(row.document_hash, expected)
		self.assertEqual(row.model_name, embeddings.MODEL_NAME)
		self.assertEqual(row.dim, FakeEncoder.dim)
		self.assertEqual(len(row.to_vector()), FakeEncoder.dim)

	def test_an_unchanged_title_is_not_re_embedded(self):
		title = self.make_title()
		self.assertTrue(ai_search.index_title(title))
		self.assertFalse(ai_search.index_title(title))
		self.assertTrue(ai_search.index_title(title, force=True))

	def test_saving_a_title_indexes_it_once_the_transaction_commits(self):
		with self.captureOnCommitCallbacks(execute=True):
			title = self.make_title()
		self.assertTrue(TitleEmbedding.objects.filter(title=title).exists())

	def test_editing_a_title_replaces_the_stored_vector(self):
		with self.captureOnCommitCallbacks(execute=True):
			title = self.make_title(synopsis="Yolg'iz qahramon qorli o'rmonda yashaydi.")
		before = TitleEmbedding.objects.get(title=title).document_hash
		title.synopsis = "Quvnoq qahramon quyoshli sohilda suzadi."
		with self.captureOnCommitCallbacks(execute=True):
			title.save()
		after = TitleEmbedding.objects.get(title=title).document_hash
		self.assertNotEqual(before, after)
		self.assertEqual(after, ai_search.document_hash(ai_search.title_document(title)))

	def test_attaching_a_genre_re_embeds_the_title(self):
		with self.captureOnCommitCallbacks(execute=True):
			title = self.make_title(genres=["Komediya"])
		before = TitleEmbedding.objects.get(title=title).document_hash
		with self.captureOnCommitCallbacks(execute=True):
			title.genres.set([Genre.objects.create(name="Qo'rqinchli")])
		after = TitleEmbedding.objects.get(title=title).document_hash
		self.assertNotEqual(before, after)
		self.assertIn("Qo'rqinchli", ai_search.title_document(title))

	def test_renaming_a_genre_re_embeds_its_titles(self):
		genre = Genre.objects.create(name="Sarguzasht")
		with self.captureOnCommitCallbacks(execute=True):
			title = self.make_title(genres=[genre.name])
		before = TitleEmbedding.objects.get(title=title).document_hash
		genre.name = "Sarguzasht va sayohat"
		with self.captureOnCommitCallbacks(execute=True):
			genre.save()
		after = TitleEmbedding.objects.get(title=title).document_hash
		self.assertNotEqual(before, after)

	def test_deleting_a_title_removes_its_vector(self):
		with self.captureOnCommitCallbacks(execute=True):
			title = self.make_title()
		self.assertTrue(TitleEmbedding.objects.exists())
		title.delete()
		self.assertFalse(TitleEmbedding.objects.exists())

	def test_a_switched_off_ai_search_never_indexes(self):
		with override_settings(AI_SEARCH_ENABLED=False):
			with self.captureOnCommitCallbacks(execute=True):
				self.make_title()
		self.assertFalse(TitleEmbedding.objects.exists())

	def test_a_missing_model_does_not_break_a_catalogue_edit(self):
		# The encoder refuses to load: the signal must swallow that instead of
		# making an ordinary admin edit fail. The title simply stays unindexed
		# until `index_anime_embeddings` can run.
		with mock.patch(
			"movies.embeddings.load_encoder",
			side_effect=embeddings.EmbeddingUnavailable("model fayllari yo'q"),
		):
			with self.captureOnCommitCallbacks(execute=True):
				title = self.make_title()
		self.assertTrue(MediaTitle.objects.filter(pk=title.pk).exists())
		self.assertFalse(TitleEmbedding.objects.exists())


class AISearchCommandTests(AISearchTestCase):
	"""``manage.py index_anime_embeddings`` is the initial build and the repair."""

	def test_the_command_embeds_every_title(self):
		self.write_model_files()
		self.make_title("Birinchi anime")
		self.make_title("Birinchi manga", media_type=MediaTitle.MediaType.MANGA)
		out = StringIO()
		call_command("index_anime_embeddings", stdout=out)
		self.assertEqual(TitleEmbedding.objects.count(), 2)
		self.assertIn("2 yangilandi", out.getvalue())

	def test_the_command_is_idempotent(self):
		self.write_model_files()
		self.make_title()
		self.index_all()
		out = StringIO()
		call_command("index_anime_embeddings", stdout=out)
		self.assertIn("0 yangilandi", out.getvalue())
		self.assertIn("1 o'zgarmadi", out.getvalue())

	def test_force_re_embeds_untouched_titles(self):
		self.write_model_files()
		self.make_title()
		self.index_all()
		out = StringIO()
		call_command("index_anime_embeddings", "--force", stdout=out)
		self.assertIn("1 yangilandi", out.getvalue())

	def test_the_type_filter_limits_the_run(self):
		self.write_model_files()
		self.make_title("Faqat anime", media_type=MediaTitle.MediaType.ANIME)
		self.make_title("Faqat manga", media_type=MediaTitle.MediaType.MANGA)
		call_command("index_anime_embeddings", "--type", "anime", stdout=StringIO())
		self.assertEqual(TitleEmbedding.objects.count(), 1)

	def test_an_invalid_type_is_refused(self):
		self.write_model_files()
		with self.assertRaises(CommandError) as error:
			call_command("index_anime_embeddings", "--type", "radio", stdout=StringIO())
		self.assertIn("radio", str(error.exception))

	def test_a_dry_run_touches_nothing(self):
		self.write_model_files()
		self.make_title()
		out = StringIO()
		call_command("index_anime_embeddings", "--dry-run", stdout=out)
		self.assertIn("Indekslanishi kerak: 1", out.getvalue())
		self.assertFalse(TitleEmbedding.objects.exists())

	def test_status_reports_coverage_and_stale_rows(self):
		self.write_model_files()
		title = self.make_title("Eski nom")
		self.index_all()
		# A queryset update skips the signals on purpose: it is how a row can go
		# stale without the index noticing.
		MediaTitle.objects.filter(pk=title.pk).update(title="Yangi nom")
		out = StringIO()
		call_command("index_anime_embeddings", "--status", stdout=out)
		text = out.getvalue()
		self.assertIn("Indekslangan: 1/1", text)
		self.assertIn("Eskirgan: 1 ta", text)
		self.assertIn("Yangi nom", text)

	def test_the_command_explains_a_missing_model(self):
		self.make_title()
		with self.assertRaises(CommandError) as error:
			call_command("index_anime_embeddings", stdout=StringIO())
		self.assertIn("--download-model", str(error.exception))

	def test_the_command_respects_the_feature_switch(self):
		self.write_model_files()
		self.make_title()
		with override_settings(AI_SEARCH_ENABLED=False):
			with self.assertRaises(CommandError) as error:
				call_command("index_anime_embeddings", stdout=StringIO())
		self.assertIn("AI_SEARCH_ENABLED", str(error.exception))


class AISearchQueryTests(AISearchTestCase):
	"""Ranking and the one-line summary that clients display."""

	def test_the_matching_title_is_ranked_first(self):
		horror = self.make_title(
			"Qorong'i O'rmon",
			genres=["Qo'rqinchli", "Sarguzasht"],
			synopsis="Qo'rqinchli sarguzasht ertak.",
		)
		self.make_title("Kulgili Maktab", genres=["Komediya"], synopsis="Quvnoq maktab hayoti.")
		self.index_all()
		hits = ai_search.search("qo'rqinchli sarguzasht animelar")
		self.assertTrue(hits)
		self.assertEqual(hits[0].title.pk, horror.pk)
		self.assertGreater(hits[0].score, 0.0)

	def test_the_threshold_drops_unrelated_titles(self):
		self.make_title("Kulgili Maktab", genres=["Komediya"], synopsis="Quvnoq maktab hayoti.")
		self.index_all()
		self.assertEqual(ai_search.search("qor va muz haqida", threshold=0.9), [])

	def test_the_media_type_filter_is_applied(self):
		self.make_title("Qo'rqinchli Anime", genres=["Qo'rqinchli"])
		self.make_title(
			"Qo'rqinchli Manga",
			media_type=MediaTitle.MediaType.MANGA,
			genres=["Qo'rqinchli"],
		)
		self.index_all()
		hits = ai_search.search("qo'rqinchli", media_type=MediaTitle.MediaType.MANGA)
		self.assertTrue(hits)
		self.assertTrue(all(hit.title.type == MediaTitle.MediaType.MANGA for hit in hits))

	def test_the_limit_is_honoured(self):
		for index in range(4):
			self.make_title(f"Sarguzasht {index}", genres=["Sarguzasht"])
		self.index_all()
		self.assertEqual(len(ai_search.search("sarguzasht", limit=2)), 2)

	def test_the_outcome_counts_every_match_beyond_the_page(self):
		"""The list is a page of the matches; ``total`` is all of them."""
		for index in range(5):
			self.make_title(f"Qo'rqinchli {index}", genres=["Qo'rqinchli"])
		self.index_all()

		outcome = ai_search.search_outcome("qo'rqinchli", limit=2)

		self.assertEqual(len(outcome.hits), 2)
		self.assertEqual(outcome.total, 5)
		self.assertTrue(outcome.has_more)

	def test_a_large_enough_limit_leaves_nothing_behind(self):
		for index in range(3):
			self.make_title(f"Qo'rqinchli {index}", genres=["Qo'rqinchli"])
		self.index_all()

		outcome = ai_search.search_outcome("qo'rqinchli", limit=10)

		self.assertEqual(len(outcome.hits), 3)
		self.assertEqual(outcome.total, 3)
		self.assertFalse(outcome.has_more)

	def test_searching_an_empty_index_returns_nothing(self):
		self.write_model_files()
		self.assertEqual(ai_search.search("sarguzasht"), [])

	def test_searching_a_blank_query_returns_nothing(self):
		self.make_title()
		self.index_all()
		self.assertEqual(ai_search.search("   "), [])

	def test_the_summary_is_the_first_sentence_of_the_synopsis(self):
		title = self.make_title(synopsis="Birinchi jumla shu. Ikkinchi jumla boshqa.")
		self.assertEqual(ai_search.one_line_summary(title), "Birinchi jumla shu.")

	def test_a_long_sentence_is_truncated(self):
		title = self.make_title(synopsis="so'z " * 80)
		summary = ai_search.one_line_summary(title)
		self.assertLessEqual(len(summary), ai_search.SUMMARY_MAX_CHARS)
		self.assertTrue(summary.endswith("…"))

	def test_the_summary_falls_back_to_the_metadata(self):
		title = self.make_title("Janrsiz", genres=["Sarguzasht"])
		self.assertEqual(ai_search.one_line_summary(title), "Sarguzasht janridagi anime.")

	def test_a_free_account_cannot_use_the_ai_search(self):
		user = get_user_model().objects.create_user(username="free-user", password="free-secret-4829")
		self.assertFalse(ai_search.user_can_search(user))
		self.assertFalse(ai_search.user_can_search(None))

	def test_an_active_subscription_unlocks_the_ai_search(self):
		self.assertTrue(ai_search.user_can_search(self.make_subscriber()))


class AISearchReasoningTests(AISearchTestCase):
	"""The "fikrlash" step: what the chat model adds, and what happens without it.

	The model call itself is patched — the suite never talks to a provider, just
	like it never loads the 470MB encoder.
	"""

	def setUp(self):
		super().setUp()
		ai_reasoning.clear_cache()
		self.addCleanup(ai_reasoning.clear_cache)
		llm.reset_cooldowns()
		llm.reset_signature_cache()
		self.addCleanup(llm.reset_cooldowns)
		self.addCleanup(llm.reset_signature_cache)

	def catalogue(self):
		"""Two titles: the vector search has something to rank and reason about."""
		first = self.make_title(
			"Qorong'i O'rmon",
			genres=["Qo'rqinchli"],
			synopsis="Qo'rqinchli o'rmonda kechgan sarguzasht.",
		)
		second = self.make_title(
			"Kulgili Maktab",
			genres=["Komediya"],
			synopsis="Quvnoq maktab hayoti.",
		)
		self.index_all()
		return first, second

	def test_without_a_key_the_answer_comes_from_the_vectors_alone(self):
		"""No provider configured: the search still answers, without prose."""
		self.catalogue()

		answer = ai_reasoning.answer_search("qo'rqinchli o'rmon", limit=2)

		self.assertEqual(len(answer.hits), 2)
		self.assertFalse(answer.used_llm)
		self.assertEqual(answer.answer, "")
		self.assertIn("AI_LLM_API_KEY", answer.error)

	def test_the_model_answer_is_parsed_and_orders_the_picks(self):
		"""The model's ``tanlov`` decides the order the user sees.

		``[2, 1]`` reverses whatever the vector search decided, which is the point
		of the reasoning step — assert against the real vector order instead of
		guessing which title wins the cosine race.
		"""
		self.catalogue()
		payload = json.dumps({
			"fikrlash": "So'rov komediya so'rayapti.",
			"tanlov": [2, 1],
			"javob": "Sizga «Kulgili Maktab» mos keladi.",
		})
		with mock.patch("movies.llm.chat", return_value=payload) as chat, override_settings(
			AI_LLM_API_KEY="test-key"
		):
			answer = ai_reasoning.answer_search("quvnoq kontent", limit=2)
			vector_order = [
				hit.title.pk for hit in ai_search.search("quvnoq kontent", limit=2)
			]

		self.assertTrue(answer.used_llm)
		self.assertEqual(answer.thinking, "So'rov komediya so'rayapti.")
		self.assertEqual(len(vector_order), 2)
		self.assertEqual([hit.title.pk for hit in answer.hits], list(reversed(vector_order)))
		self.assertIn("Kulgili Maktab", answer.answer)
		# The user's own words and the candidates both reach the model.
		prompt = chat.call_args.args[0][1]["content"]
		self.assertIn("quvnoq kontent", prompt)
		self.assertIn("Qorong'i O'rmon", prompt)
		self.assertIn("1.", prompt)

	def test_a_model_failure_keeps_the_vector_order(self):
		self.catalogue()
		with mock.patch(
			"movies.llm.chat", side_effect=llm.LLMUnavailable("kvota tugadi")
		) as chat, override_settings(AI_LLM_API_KEY="test-key"):
			answer = ai_reasoning.answer_search("qo'rqinchli", limit=2)
			plain = ai_search.search("qo'rqinchli", limit=2)

		self.assertEqual(chat.call_count, 1)
		self.assertFalse(answer.used_llm)
		self.assertEqual(answer.error, "kvota tugadi")
		self.assertEqual(
			[hit.title.pk for hit in answer.hits], [hit.title.pk for hit in plain]
		)

	def test_only_the_candidates_can_be_picked(self):
		"""A hallucinated title or index is ignored, not rendered."""
		self.catalogue()
		payload = json.dumps({"fikrlash": "", "tanlov": [1, 99, "Sarguzasht 7"], "javob": "Mana."})
		with mock.patch("movies.llm.chat", return_value=payload), override_settings(
			AI_LLM_API_KEY="test-key"
		):
			answer = ai_reasoning.answer_search("qo'rqinchli", limit=2)
			best = ai_search.search("qo'rqinchli", limit=1)[0]

		self.assertEqual(answer.hits[0].title.pk, best.title.pk)
		self.assertEqual(len(answer.hits), 2)

	def test_an_identical_request_reuses_the_answer(self):
		"""The same question twice in a row must not pay for the model again."""
		self.catalogue()
		payload = json.dumps({"fikrlash": "x", "tanlov": [1], "javob": "Javob."})
		with mock.patch("movies.llm.chat", return_value=payload) as chat, override_settings(
			AI_LLM_API_KEY="test-key"
		):
			ai_reasoning.answer_search("qo'rqinchli", limit=2)
			calls_after_first = chat.call_count
			second = ai_reasoning.answer_search("qo'rqinchli", limit=2)

		# One route call plus one reasoning call produced the first answer; the
		# repeat is served entirely from the cache.
		self.assertEqual(calls_after_first, 2)
		self.assertEqual(chat.call_count, calls_after_first)
		self.assertEqual(second.answer, "Javob.")

	def test_a_provider_without_a_key_never_touches_the_network(self):
		"""No key means no HTTP request at all — not a request that fails later."""
		self.catalogue()
		with mock.patch("movies.llm.urllib.request.urlopen") as urlopen:
			answer = ai_reasoning.answer_search("qo'rqinchli", limit=2)

		self.assertFalse(answer.used_llm)
		self.assertEqual(urlopen.call_count, 0)

	def test_the_prompt_only_lists_configured_candidates(self):
		self.catalogue()
		with mock.patch("movies.llm.chat", return_value="{}") as chat, override_settings(
			AI_LLM_API_KEY="test-key"
		):
			ai_reasoning.answer_search("komediya", limit=1)
		prompt = chat.call_args.args[0][1]["content"]
		self.assertEqual(prompt.count("Nomi:"), 1)

	def test_a_conversational_answer_comes_without_a_result_list(self):
		"""A "who are you" question is answered in words, not with titles.

		The vector search always returns *some* nearest titles, but when the
		model judges the request a conversation rather than a catalogue lookup
		(empty ``tanlov``) those candidates must not be shown as if they were
		an answer.
		"""
		self.catalogue()
		payload = json.dumps({
			"fikrlash": "Bu anime so'rovi emas, yordamchi haqida savol.",
			"tanlov": [],
			"javob": "Men AniVoyman, shu platformada ishlayman.",
		})
		with mock.patch("movies.llm.chat", return_value=payload), override_settings(
			AI_LLM_API_KEY="test-key"
		):
			answer = ai_reasoning.answer_search("sen kimsan", limit=2)

		self.assertTrue(answer.used_llm)
		self.assertTrue(answer.conversational)
		self.assertEqual(answer.hits, [])
		self.assertEqual(answer.total, 0)
		self.assertFalse(answer.has_more)
		self.assertIn("AniVoy", answer.answer)

	def test_a_conversation_is_routed_and_answered_without_candidates(self):
		"""A "who are you" is answered by the router alone: no catalogue tokens."""
		self.catalogue()
		payload = json.dumps({
			"harakat": "suhbat",
			"javob": "Men AniVoyman, shu platformada ishlayman.",
		})
		with mock.patch("movies.llm.chat", return_value=payload) as chat, override_settings(
			AI_LLM_API_KEY="test-key"
		):
			answer = ai_reasoning.answer_search("sen kimsan", limit=2)

		self.assertTrue(answer.conversational)
		self.assertEqual(answer.hits, [])
		self.assertIn("AniVoy", answer.answer)
		# One call, and it never saw a candidate line.
		self.assertEqual(chat.call_count, 1)
		self.assertNotIn("Nomi:", chat.call_args.args[0][1]["content"])

	def test_a_search_is_routed_then_given_the_candidate_list(self):
		"""Search asks twice: once to classify (no list), once with the list."""
		self.catalogue()
		router = json.dumps({"harakat": "qidiruv", "qidiruv": "quvnoq komediya"})
		search = json.dumps({"fikrlash": "komediya", "tanlov": [1], "javob": "Mana."})
		with mock.patch("movies.llm.chat", side_effect=[router, search]) as chat, override_settings(
			AI_LLM_API_KEY="test-key"
		):
			answer = ai_reasoning.answer_search("kulgi kerak", limit=1)

		self.assertTrue(answer.used_llm)
		self.assertFalse(answer.conversational)
		self.assertEqual(chat.call_count, 2)
		# The first call is the classifier: no candidates there.
		self.assertNotIn("Nomi:", chat.call_args_list[0].args[0][1]["content"])
		# The second carries the candidates, and the model's cleaned-up query.
		second_prompt = chat.call_args_list[1].args[0][1]["content"]
		self.assertIn("Nomi:", second_prompt)
		self.assertIn("quvnoq komediya", second_prompt)

	def test_the_user_context_reaches_both_model_calls(self):
		"""The favourites block rides on the router *and* the reasoning call.

		Without it "men oxirgi ko'rganimga o'xshashini ayt" is an empty query:
		the router cannot clean it up and the model cannot judge similarity.
		"""
		self.catalogue()
		router = json.dumps({"harakat": "qidiruv", "qidiruv": "qo'rqinchli"})
		search = json.dumps({"fikrlash": "x", "tanlov": [1], "javob": "Mana."})
		context = "Sevimlilar: Vagabond (manga, Drama)"
		with mock.patch("movies.llm.chat", side_effect=[router, search]) as chat, override_settings(
			AI_LLM_API_KEY="test-key"
		):
			ai_reasoning.answer_search(
				"sevimlim mosini top", limit=1, context=context
			)

		router_prompt = chat.call_args_list[0].args[0][1]["content"]
		search_prompt = chat.call_args_list[1].args[0][1]["content"]
		self.assertIn("Vagabond", router_prompt)
		self.assertIn("Vagabond", search_prompt)

	def test_the_same_question_with_a_different_context_is_not_cached_together(self):
		"""Two users asking the same words but with different taste get their
		own answers — the context is part of the question."""
		self.catalogue()
		router = json.dumps({"harakat": "qidiruv", "qidiruv": "sarguzasht"})
		search = json.dumps({"fikrlash": "x", "tanlov": [1], "javob": "Javob."})
		with mock.patch("movies.llm.chat", side_effect=[router, search, router, search]) as chat, override_settings(
			AI_LLM_API_KEY="test-key"
		):
			ai_reasoning.answer_search(
				"o'xshashini ayt", limit=1, context="Sevimlilar: Naruto"
			)
			ai_reasoning.answer_search(
				"o'xshashini ayt", limit=1, context="Sevimlilar: Vagabond"
			)

		# Four calls, not two: the second context could not reuse the first's
		# cached route or explanation.
		self.assertEqual(chat.call_count, 4)


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


class AIProviderFailoverTests(AISearchTestCase):
	"""The provider chain: who is asked, in which order, and after which failure.

	``urllib`` is stubbed at the request level, so these tests run the real
	payload building, the real status handling and the real failover — not a
	mocked ``chat``.
	"""

	def setUp(self):
		super().setUp()
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

		def slow(config, messages, *, max_tokens, temperature, seconds):
			asked.append((config.label, seconds))
			clock.advance(3)
			raise llm.ProviderError(f"{config.label} juda sekin javob berdi")

		with mock.patch("movies.llm._monotonic", clock), mock.patch(
			"movies.llm._attempt", side_effect=slow
		), override_settings(AI_LLM_TIMEOUT=8, AI_LLM_DEADLINE=10):
			with self.assertRaises(llm.LLMUnavailable):
				self.ask(None)

		self.assertEqual(asked, [("Birinchi", 8), ("Ikkinchi", 7)])

	def test_the_api_explains_the_picks_when_the_first_provider_is_limited(self):
		"""End to end: the visitor sees the model's answer, not the 429 behind it."""
		self.make_title(
			"Qorong'i O'rmon",
			genres=["Qo'rqinchli"],
			synopsis="Qo'rqinchli o'rmon haqida hikoya.",
		)
		self.index_all()
		self.client.force_authenticate(self.make_subscriber())
		self.make_provider("Birinchi", ONE_URL, priority=1)
		self.make_provider("Ikkinchi", TWO_URL, priority=2)
		payload = json.dumps(
			{"fikrlash": "So'rov qo'rqinchli kayfiyatni so'rayapti.", "tanlov": [1], "javob": "Mana mos kino."}
		)
		stub = ProviderStub(
			{ONE_URL: provider_limit(), TWO_URL: provider_answer(payload)}
		)
		ai_reasoning.clear_cache()
		self.addCleanup(ai_reasoning.clear_cache)

		with mock.patch("movies.llm.urllib.request.urlopen", stub):
			response = self.client.post(
				self.ai_url, {"query": "qo'rqinchli"}, format="json"
			)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.data["reasoning"])
		self.assertEqual(response.data["answer"], "Mana mos kino.")
		self.assertEqual(response.data["count"], 1)
		self.assertEqual(stub.calls, [ONE_URL, TWO_URL, TWO_URL])

	def test_the_status_command_shows_the_chain_and_the_wait(self):
		"""The operator sees the failover order, and who is currently skipped."""
		self.write_model_files()
		self.make_title("Qorong'i O'rmon")
		self.index_all()
		self.make_provider("Birinchi", ONE_URL, priority=1)
		self.make_provider(
			"Ikkinchi",
			TWO_URL,
			priority=2,
			cooldown_until=timezone.now() + timedelta(seconds=90),
		)
		out = StringIO()

		call_command("index_anime_embeddings", "--status", stdout=out)

		text = out.getvalue()
		self.assertIn("Fikrlash zanjiri (2 ta provayder)", text)
		self.assertIn("Birinchi", text)
		self.assertIn("Ikkinchi", text)
		self.assertIn("kutishda (limit/xato)", text)
		self.assertIn("1 ta provayder tayyor", text)

	def test_the_chain_test_command_reports_which_provider_answered(self):
		self.write_model_files()
		self.make_provider("Birinchi", ONE_URL, priority=1, api_key="test-key")
		stub = ProviderStub({ONE_URL: provider_answer("Ha")})
		out = StringIO()

		with mock.patch("movies.llm.urllib.request.urlopen", stub):
			call_command("index_anime_embeddings", "--test-llm", stdout=out)

		self.assertIn("Ha", out.getvalue())
		self.assertIn("✓ javob berdi: Birinchi", out.getvalue())

	def test_the_chain_test_command_explains_an_empty_chain(self):
		with self.assertRaises(CommandError) as raised:
			call_command("index_anime_embeddings", "--test-llm", stdout=StringIO())
		self.assertIn("AI provayder yo'q", str(raised.exception))


class AIProviderAdminTests(TestCase):
	"""The operator's screen: the chain itself, and the two actions that fix it."""

	def setUp(self):
		self.client = Client()
		self.client.force_login(
			get_user_model().objects.create_superuser(
				username="root", password="root-secret-4829"
			)
		)
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


class AISearchApiTests(AISearchTestCase):
	"""``POST /api/catalog/ai-search/`` and its subscription gate."""

	def test_a_subscriber_receives_links_and_one_line_summaries(self):
		self.write_model_files()
		title = self.make_title(
			"Qorong'i O'rmon",
			genres=["Qo'rqinchli"],
			synopsis="Qo'rqinchli o'rmon haqida hikoya. Davomi bor.",
		)
		self.index_all()
		self.client.force_authenticate(self.make_subscriber())

		response = self.client.post(self.ai_url, {"query": AI_QUERY}, format="json")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["count"], 1)
		item = response.data["results"][0]
		self.assertEqual(item["title"], title.title)
		self.assertEqual(item["url"], f"/media/{title.slug}")
		self.assertEqual(item["summary"], "Qo'rqinchli o'rmon haqida hikoya.")
		self.assertIn("score", item)
		self.assertEqual(list(item["genres"]), ["Qo'rqinchli"])

	def test_a_configured_site_url_makes_the_links_absolute(self):
		self.write_model_files()
		title = self.make_title("Qorong'i O'rmon", genres=["Qo'rqinchli"])
		self.index_all()
		self.client.force_authenticate(self.make_subscriber())

		with override_settings(BOT_SITE_URL="https://anichopar.uz"):
			response = self.client.post(self.ai_url, {"query": AI_QUERY}, format="json")

		self.assertEqual(response.data["results"][0]["url"], f"https://anichopar.uz/media/{title.slug}")

	def test_the_response_carries_the_model_answer(self):
		self.write_model_files()
		title = self.make_title(
			"Qorong'i O'rmon",
			genres=["Qo'rqinchli"],
			synopsis="Qo'rqinchli o'rmon haqida hikoya.",
		)
		self.index_all()
		self.client.force_authenticate(self.make_subscriber())
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
			response = self.client.post(self.ai_url, {"query": AI_QUERY}, format="json")

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.data["reasoning"])
		self.assertEqual(
			response.data["thinking"], "So'rov qo'rqinchli kayfiyatni so'rayapti."
		)
		self.assertIn(title.title, response.data["answer"])

	def test_the_api_answers_even_when_the_model_is_down(self):
		"""A provider outage must not take the search down with it."""
		self.write_model_files()
		self.make_title("Qorong'i O'rmon", genres=["Qo'rqinchli"])
		self.index_all()
		self.client.force_authenticate(self.make_subscriber())
		ai_reasoning.clear_cache()
		self.addCleanup(ai_reasoning.clear_cache)

		with mock.patch(
			"movies.llm.chat", side_effect=llm.LLMUnavailable("provider yiqildi")
		), override_settings(AI_LLM_API_KEY="test-key"):
			response = self.client.post(self.ai_url, {"query": AI_QUERY}, format="json")

		self.assertEqual(response.status_code, 200)
		self.assertFalse(response.data["reasoning"])
		self.assertEqual(response.data["answer"], "")
		self.assertEqual(response.data["count"], 1)

	def test_the_response_reports_matches_beyond_the_returned_page(self):
		self.write_model_files()
		for index in range(5):
			self.make_title(f"Qo'rqinchli {index}", genres=["Qo'rqinchli"])
		self.index_all()
		self.client.force_authenticate(self.make_subscriber())

		response = self.client.post(
			self.ai_url, {"query": "qo'rqinchli", "limit": 2}, format="json"
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["count"], 2)
		self.assertEqual(response.data["total"], 5)
		self.assertTrue(response.data["has_more"])

	def test_the_type_filter_is_counted_in_the_total(self):
		"""A "manga only" request must not be padded with anime matches."""
		self.write_model_files()
		for index in range(3):
			self.make_title(f"Qo'rqinchli Anime {index}", genres=["Qo'rqinchli"])
		self.make_title(
			"Qo'rqinchli Manga",
			media_type=MediaTitle.MediaType.MANGA,
			genres=["Qo'rqinchli"],
		)
		self.index_all()
		self.client.force_authenticate(self.make_subscriber())

		response = self.client.post(
			self.ai_url, {"query": "qo'rqinchli", "type": "manga"}, format="json"
		)

		self.assertEqual(response.data["count"], 1)
		self.assertEqual(response.data["total"], 1)
		self.assertFalse(response.data["has_more"])

	def test_the_type_filter_can_be_passed_through(self):
		self.write_model_files()
		self.make_title("Qo'rqinchli Anime", genres=["Qo'rqinchli"])
		self.make_title("Qo'rqinchli Kino", media_type=MediaTitle.MediaType.MOVIE, genres=["Qo'rqinchli"])
		self.index_all()
		self.client.force_authenticate(self.make_subscriber())

		response = self.client.post(
			self.ai_url, {"query": "qo'rqinchli", "type": "movie"}, format="json"
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual({item["type"] for item in response.data["results"]}, {"movie"})

	def test_a_signed_in_visitor_without_a_subscription_is_refused(self):
		self.write_model_files()
		self.make_title("Qorong'i O'rmon", genres=["Qo'rqinchli"])
		self.index_all()
		self.client.force_authenticate(
			get_user_model().objects.create_user(username="no-plan", password="no-plan-4829")
		)

		response = self.client.post(self.ai_url, {"query": AI_QUERY}, format="json")

		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.data["code"], "subscription_required")

	def test_an_expired_subscription_is_refused(self):
		self.write_model_files()
		self.make_title("Qorong'i O'rmon", genres=["Qo'rqinchli"])
		self.index_all()
		self.client.force_authenticate(self.make_subscriber("expired-user", days=-5))

		response = self.client.post(self.ai_url, {"query": AI_QUERY}, format="json")

		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.data["code"], "subscription_required")

	def test_the_endpoint_requires_authentication(self):
		response = self.client.post(self.ai_url, {"query": AI_QUERY}, format="json")
		self.assertIn(response.status_code, (401, 403))

	def test_a_blank_query_is_rejected(self):
		self.write_model_files()
		self.client.force_authenticate(self.make_subscriber())
		response = self.client.post(self.ai_url, {"query": "   "}, format="json")
		self.assertEqual(response.status_code, 400)
		self.assertIn("query", response.data)

	def test_an_unbuilt_index_is_reported_instead_of_faked(self):
		self.write_model_files()
		self.client.force_authenticate(self.make_subscriber())
		response = self.client.post(self.ai_url, {"query": AI_QUERY}, format="json")
		self.assertEqual(response.status_code, 503)
		self.assertEqual(response.data["code"], "index_empty")

	def test_a_missing_model_is_reported(self):
		self.make_title("Qorong'i O'rmon")
		self.client.force_authenticate(self.make_subscriber())
		response = self.client.post(self.ai_url, {"query": AI_QUERY}, format="json")
		self.assertEqual(response.status_code, 503)
		self.assertEqual(response.data["code"], "ai_unavailable")

	def test_the_feature_can_be_switched_off(self):
		self.write_model_files()
		self.make_title("Qorong'i O'rmon", genres=["Qo'rqinchli"])
		self.index_all()
		self.client.force_authenticate(self.make_subscriber())
		with override_settings(AI_SEARCH_ENABLED=False):
			response = self.client.post(self.ai_url, {"query": AI_QUERY}, format="json")
		self.assertEqual(response.status_code, 503)
		self.assertEqual(response.data["code"], "ai_unavailable")

	def test_the_endpoint_is_documented_in_the_schema(self):
		schema = self.client.get("/api/schema/?format=json").json()
		self.assertIn("/api/catalog/ai-search/", schema["paths"])
