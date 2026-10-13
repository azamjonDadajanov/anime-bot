from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from .models import MediaPart, MediaTitle, MediaView, TelegramChannel, TelegramMedia


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
