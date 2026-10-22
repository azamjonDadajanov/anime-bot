"""«📢 E'lon qilish» from the website panel.

The operator first sees the exact message (GET), then chooses where it goes:
the public channel, every bot user, or both at once (POST). An ongoing title
announces only its newest episode by default, a finished one announces its
whole run. ``TransactionTestCase`` because the channel post bridges into the
async ORM, whose worker thread only sees committed rows.
"""

from __future__ import annotations

import shutil
import tempfile
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TransactionTestCase, override_settings
from movies.models import MediaPart, MediaTitle, TelegramChannel
from rest_framework.test import APIClient
from users.models import TelegramUser

from bot.models import BotSettings
from bot.tests.fakes import BOT_TOKEN, FakeSession, make_bot


def url(slug: str) -> str:
	return f"/api/admin/media/{slug}/announce/"


class AnnounceApiTestCase(TransactionTestCase):
	def setUp(self) -> None:
		super().setUp()
		self.staff = get_user_model().objects.create_user(
			username="announce-admin",
			email="announce@example.com",
			password="panel-secret-4829",
			is_staff=True,
		)
		self.client = APIClient()
		self.client.force_authenticate(self.staff)

		self.ongoing_channel = TelegramChannel.objects.create(
			chat_id=-1008880000001,
			title="Ongoing e'lonlari",
			username="ongoing_news",
			purpose=TelegramChannel.Purpose.PUBLIC,
		)
		self.completed_channel = TelegramChannel.objects.create(
			chat_id=-1008880000002,
			title="Tugallangan e'lonlari",
			username="done_news",
			purpose=TelegramChannel.Purpose.PUBLIC,
		)
		settings = BotSettings.get_solo()
		settings.publish_channel = self.ongoing_channel
		settings.ongoing_channel = self.ongoing_channel
		settings.completed_channel = self.completed_channel
		settings.save()

		self.title = MediaTitle.objects.create(
			type=MediaTitle.MediaType.ANIME,
			title="Announce Anime",
			slug="announce-anime",
			code="7788",
			status=MediaTitle.Status.ONGOING,
			rating=9,
			duration_minutes=24,
			quality_options=["1080", "720"],
		)
		for number in (1, 2, 3):
			MediaPart.objects.create(content=self.title, number=number)

		self.session = FakeSession()

		# Covers are files on disk; keep the test's uploads in a temp store.
		self.media_root = tempfile.mkdtemp()
		media_override = override_settings(MEDIA_ROOT=self.media_root)
		media_override.enable()
		self.addCleanup(media_override.disable)
		self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)

	def bot_patch(self):
		return mock.patch("aiogram.Bot", lambda token, **kwargs: make_bot(self.session))

	def attach_cover(self) -> None:
		self.title.cover.save(
			"cover.jpg", ContentFile(b"\xff\xd8\xff\xe0fake-jpeg"), save=True
		)


@override_settings(BOT_TOKEN=BOT_TOKEN, TELEGRAM_BOT_TOKEN=BOT_TOKEN)
class AnnouncePreviewTests(AnnounceApiTestCase):
	def test_preview_shows_the_exact_message_and_audience(self) -> None:
		TelegramUser.objects.create(telegram_id=9001, first_name="A")
		TelegramUser.objects.create(telegram_id=9002, first_name="B")

		response = self.client.get(url(self.title.slug))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["scope"], "last")
		self.assertEqual(response.data["recipients"], 2)
		self.assertEqual(response.data["channel_title"], "Ongoing e'lonlari")
		self.assertEqual(response.data["parts"], [3])
		self.assertEqual(response.data["total_parts"], 3)
		self.assertIn("Announce Anime", response.data["caption"])
		self.assertIn("Davomiyligi: 24 daqiqa", response.data["caption"])
		self.assertIn("Qism: 3/3", response.data["caption"])
		self.assertIn("Tomosha qilish", response.data["button_label"])

	def test_scope_all_lists_every_episode(self) -> None:
		response = self.client.get(url(self.title.slug), {"scope": "all"})

		self.assertEqual(response.data["scope"], "all")
		self.assertEqual(response.data["parts"], [1, 2, 3])
		self.assertIn("1–3-qismlar", response.data["caption"])

	def test_completed_title_uses_the_completed_channel(self) -> None:
		self.title.status = MediaTitle.Status.COMPLETED
		self.title.save(update_fields=["status"])

		response = self.client.get(url(self.title.slug))

		self.assertEqual(response.data["channel_title"], "Tugallangan e'lonlari")

	def test_non_staff_cannot_preview(self) -> None:
		viewer = get_user_model().objects.create_user(
			username="announce-viewer", password="viewer-4829"
		)
		client = APIClient()
		client.force_authenticate(viewer)

		self.assertEqual(client.get(url(self.title.slug)).status_code, 403)


@override_settings(BOT_TOKEN=BOT_TOKEN, TELEGRAM_BOT_TOKEN=BOT_TOKEN)
class AnnounceSendTests(AnnounceApiTestCase):
	def test_channel_target_posts_one_photo_with_the_start_button(self) -> None:
		self.attach_cover()
		with self.bot_patch():
			response = self.client.post(
				url(self.title.slug), {"targets": ["channel"], "scope": "last"}, format="json"
			)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["targets"], ["channel"])
		self.assertIsNotNone(response.data["channel_message_id"])
		photos = self.session.methods("SendPhoto")
		self.assertEqual(len(photos), 1)
		self.assertEqual(photos[0].chat_id, self.ongoing_channel.chat_id)
		self.assertIn("Qism: 3/3", photos[0].caption)
		self.assertEqual(
			photos[0].reply_markup.inline_keyboard[0][0].url,
			"https://t.me/test_bot?start=anime_7788",
		)

	def test_both_targets_are_accepted_in_one_request(self) -> None:
		self.attach_cover()
		TelegramUser.objects.create(telegram_id=9101, first_name="A")
		with self.bot_patch(), mock.patch(
			"adminpanel.announcements._start_users_announcement", return_value=True
		) as started:
			response = self.client.post(
				url(self.title.slug),
				{"targets": ["users", "channel"], "scope": "all"},
				format="json",
			)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["targets"], ["channel", "users"])
		self.assertTrue(response.data["users_started"])
		self.assertEqual(response.data["users_total"], 1)
		started.assert_called_once()
		self.assertEqual(len(self.session.methods("SendPhoto")), 1)

	def test_users_only_target_reports_the_audience(self) -> None:
		TelegramUser.objects.create(telegram_id=9201, first_name="A")
		with mock.patch(
			"adminpanel.announcements._start_users_announcement", return_value=True
		):
			response = self.client.post(
				url(self.title.slug), {"targets": ["users"], "scope": "all"}, format="json"
			)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["users_total"], 1)
		self.assertNotIn("channel_message_id", response.data)

	def test_a_missing_target_is_refused(self) -> None:
		response = self.client.post(url(self.title.slug), {"targets": []}, format="json")

		self.assertEqual(response.status_code, 400)
		self.assertIn("manzil", response.data["detail"])
		self.assertEqual(self.session.methods("SendPhoto"), [])

	def test_an_unknown_target_is_refused(self) -> None:
		response = self.client.post(
			url(self.title.slug), {"targets": ["telegram", "channel"]}, format="json"
		)

		self.assertEqual(response.status_code, 400)

	def test_without_a_channel_the_single_target_request_fails_with_a_reason(self) -> None:
		settings = BotSettings.get_solo()
		settings.publish_channel = None
		settings.ongoing_channel = None
		settings.save()

		with self.bot_patch():
			response = self.client.post(
				url(self.title.slug), {"targets": ["channel"]}, format="json"
			)

		self.assertEqual(response.status_code, 400)
		self.assertIn("E'lon kanali tanlanmagan", response.data["detail"])

	def test_without_a_token_the_request_explains_what_to_set(self) -> None:
		with override_settings(BOT_TOKEN="", TELEGRAM_BOT_TOKEN=""):
			response = self.client.post(
				url(self.title.slug), {"targets": ["channel"]}, format="json"
			)

		self.assertEqual(response.status_code, 400)
		self.assertIn("BOT_TOKEN", response.data["detail"])

	def test_a_title_without_episodes_cannot_be_announced(self) -> None:
		bare = MediaTitle.objects.create(
			type=MediaTitle.MediaType.ANIME,
			title="Bo'sh",
			slug="bossh-media",
			code="7799",
			status=MediaTitle.Status.COMPLETED,
		)

		response = self.client.post(
			url(bare.slug), {"targets": ["channel"]}, format="json"
		)

		self.assertEqual(response.status_code, 400)
		self.assertIn("qism qo'shilmagan", response.data["detail"])
		self.assertEqual(self.session.methods("SendPhoto"), [])

	def test_unknown_media_is_a_404(self) -> None:
		response = self.client.get(url("does-not-exist"))

		self.assertEqual(response.status_code, 404)
