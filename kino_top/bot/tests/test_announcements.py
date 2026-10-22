"""Tests for the announcement both administrator panels post.

The announcement is one message: the cover as a photo, the required fields in
the caption and a single button that opens the bot on the title's ``/start``
deep link. These tests pin the copy, the episode selection (ongoing: only the
newest episode or the whole run; finished: everything) and the two delivery
destinations — the channel picked by the publishing rules and every bot user.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile

from django.core.files.base import ContentFile
from django.test import TestCase, TransactionTestCase, override_settings
from movies.models import MediaTitle, TelegramChannel
from users.models import TelegramUser

from ..models import BotSettings
from ..services.announcements import (
	SCOPE_ALL,
	SCOPE_LAST,
	announcement_caption,
	announcement_keyboard,
	announcement_parts_sync,
	send_announcement,
)
from .. import callbacks as cb
from .base import DispatcherTestCase
from .fakes import ADMIN, BOT_TOKEN, FakeSession, build_callback, make_bot
from .helpers import bot_env, make_channel, make_part, make_title


def make_user(telegram_id: int, *, blocked: bool = False) -> TelegramUser:
	return TelegramUser.objects.create(
		telegram_id=telegram_id,
		first_name=f"User {telegram_id}",
		is_blocked=blocked,
	)


def build_title(**overrides) -> MediaTitle:
	title = make_title(code=overrides.pop("code", "4321"), title=overrides.pop("title", "Naruto"))
	title.rating = 8
	title.duration_minutes = 24
	title.quality_options = ["1080", "720"]
	title.save(update_fields=["rating", "duration_minutes", "quality_options"])
	return title


class AnnouncementCaptionTests(TestCase):
	def test_caption_has_every_requested_field(self) -> None:
		title = build_title()
		parts = [make_part(title, number=1), make_part(title, number=2)]

		caption = announcement_caption(title, parts, total_parts=2)

		self.assertIn("<b>Naruto</b>", caption)
		self.assertIn("Qismlar: 1–2-qismlar", caption)
		self.assertIn("Reyting: 8/10", caption)
		self.assertIn("Davomiyligi: 24 daqiqa", caption)
		self.assertIn("Qism: 2/2", caption)
		self.assertIn("Sifat: 1080, 720", caption)

	def test_missing_duration_is_shown_as_a_dash(self) -> None:
		title = build_title()
		title.duration_minutes = None
		title.save(update_fields=["duration_minutes"])

		caption = announcement_caption(title, [make_part(title, number=1)], total_parts=1)

		self.assertIn("Davomiyligi: —", caption)

	def test_scope_last_keeps_only_the_newest_episode(self) -> None:
		title = build_title()
		for number in range(1, 13):
			make_part(title, number=number)

		parts, total = announcement_parts_sync(title, SCOPE_LAST)

		self.assertEqual([part.number for part in parts], [12])
		self.assertEqual(total, 12)
		caption = announcement_caption(title, parts, total_parts=total)
		self.assertIn("Qismlar: 12-qism", caption)
		self.assertIn("Qism: 12/12", caption)

	def test_scope_all_keeps_the_whole_run(self) -> None:
		title = build_title()
		for number in range(1, 13):
			make_part(title, number=number)

		parts, total = announcement_parts_sync(title, SCOPE_ALL)

		self.assertEqual([part.number for part in parts], list(range(1, 13)))
		self.assertEqual(total, 12)
		self.assertIn("Qismlar: 1–12-qismlar", announcement_caption(title, parts, total_parts=total))

	def test_keyboard_opens_the_bot_with_the_start_payload(self) -> None:
		title = build_title()

		markup = announcement_keyboard("anichoparbot", title)

		button = markup.inline_keyboard[0][0]
		self.assertEqual(button.url, f"https://t.me/anichoparbot?start=anime_{title.code}")
		self.assertIn("Tomosha qilish", button.text)

	def test_manga_announcement_reads_instead_of_watches(self) -> None:
		title = build_title()
		title.type = MediaTitle.MediaType.MANGA
		title.save(update_fields=["type"])

		self.assertIn("O'qish", announcement_keyboard("anichoparbot", title).inline_keyboard[0][0].text)

	def test_without_a_bot_username_the_button_is_omitted(self) -> None:
		self.assertIsNone(announcement_keyboard("", build_title()))


# ``TransactionTestCase``: the delivery helpers bridge into the async ORM, whose
# worker thread only sees committed rows.
class AnnouncementDeliveryTests(TransactionTestCase):
	def setUp(self) -> None:
		super().setUp()
		env = bot_env(ADMIN_IDS="555", BOT_TOKEN=BOT_TOKEN)
		env.__enter__()
		self.addCleanup(env.__exit__, None, None, None)

		# A real (temporary) media root: the cover is read from disk and sent as
		# an upload, never inlined into the database.
		self.media_root = tempfile.mkdtemp()
		media_override = override_settings(MEDIA_ROOT=self.media_root)
		media_override.enable()
		self.addCleanup(media_override.disable)
		self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)

		self.ongoing = make_channel(
			chat_id=-1009000000001, title="Ongoing", purpose=TelegramChannel.Purpose.PUBLIC
		)
		self.completed = make_channel(
			chat_id=-1009000000002, title="Completed", purpose=TelegramChannel.Purpose.PUBLIC
		)
		settings = BotSettings.get_solo()
		settings.publish_channel = self.ongoing
		settings.ongoing_channel = self.ongoing
		settings.completed_channel = self.completed
		settings.save()

		self.session = FakeSession()
		self.bot = make_bot(self.session)

	def send(self, title, **kwargs):
		return asyncio.run(send_announcement(self.bot, title, **kwargs))

	def title_with_cover(self) -> MediaTitle:
		title = build_title()
		title.cover.save("cover.jpg", ContentFile(b"\xff\xd8\xff\xe0fake-jpeg"), save=True)
		return title

	def test_channel_post_carries_the_caption_and_the_start_button(self) -> None:
		title = self.title_with_cover()
		make_part(title, number=1)

		result = self.send(title, scope=SCOPE_LAST, to_channel=True)

		self.assertTrue(result.channel_sent)
		self.assertEqual(result.channel_error, "")
		photos = self.session.methods("SendPhoto")
		self.assertEqual(len(photos), 1)
		self.assertEqual(photos[0].chat_id, self.ongoing.chat_id)
		self.assertIn("Naruto", photos[0].caption)
		self.assertEqual(
			photos[0].reply_markup.inline_keyboard[0][0].url,
			f"https://t.me/test_bot?start=anime_{title.code}",
		)
		title.refresh_from_db()
		self.assertEqual(title.metadata_channel_id, self.ongoing.pk)
		self.assertEqual(title.metadata_message_id, result.channel_message_id)

	def test_completed_title_is_announced_whole_in_the_completed_channel(self) -> None:
		title = self.title_with_cover()
		title.status = MediaTitle.Status.COMPLETED
		title.save(update_fields=["status"])
		make_part(title, number=1)
		make_part(title, number=2)

		result = self.send(title, scope=SCOPE_ALL, to_channel=True)

		self.assertTrue(result.channel_sent)
		photos = self.session.methods("SendPhoto")
		self.assertEqual(photos[0].chat_id, self.completed.chat_id)
		self.assertIn("1–2-qismlar", photos[0].caption)

	def test_without_a_channel_the_operator_gets_an_explanation(self) -> None:
		settings = BotSettings.get_solo()
		settings.publish_channel = None
		settings.ongoing_channel = None
		settings.save()
		title = build_title()
		make_part(title, number=1)

		result = self.send(title, to_channel=True)

		self.assertFalse(result.channel_sent)
		self.assertIn("E'lon kanali tanlanmagan", result.channel_error)
		self.assertEqual(self.session.methods("SendPhoto"), [])

	def test_announcement_reaches_every_unblocked_user(self) -> None:
		make_user(1001)
		make_user(1002)
		make_user(1003, blocked=True)
		title = self.title_with_cover()
		make_part(title, number=1)

		result = self.send(title, to_users=True)

		self.assertEqual(result.users_total, 2)
		self.assertEqual(result.users_sent, 2)
		self.assertEqual(result.users_failed, 0)
		chat_ids = sorted(photo.chat_id for photo in self.session.methods("SendPhoto"))
		self.assertEqual(chat_ids, [1001, 1002])
		for photo in self.session.methods("SendPhoto"):
			self.assertIn("Naruto", photo.caption)
			self.assertTrue(photo.reply_markup.inline_keyboard[0][0].url.startswith("https://t.me/"))

	def test_both_targets_are_delivered_in_one_call(self) -> None:
		make_user(2001)
		title = self.title_with_cover()
		make_part(title, number=1)

		result = self.send(title, to_channel=True, to_users=True)

		self.assertTrue(result.channel_sent)
		self.assertEqual(result.users_sent, 1)
		chat_ids = {photo.chat_id for photo in self.session.methods("SendPhoto")}
		self.assertEqual(chat_ids, {self.ongoing.chat_id, 2001})

	def test_missing_cover_falls_back_to_a_text_message(self) -> None:
		title = build_title()
		make_part(title, number=1)

		result = self.send(title, to_channel=True)

		self.assertTrue(result.channel_sent)
		self.assertEqual(self.session.methods("SendPhoto"), [])
		messages = self.session.methods("SendMessage")
		self.assertEqual(len(messages), 1)
		self.assertIn("Tomosha qilish", messages[0].text)


class AdminAnnounceFlowTests(DispatcherTestCase):
	"""The «📢 E'lon qilish» button inside the bot's own admin panel."""

	def setUp(self) -> None:
		super().setUp()
		env = bot_env(ADMIN_IDS=str(ADMIN.id), BOT_TOKEN=BOT_TOKEN)
		env.__enter__()
		self.addCleanup(env.__exit__, None, None, None)

		self.ongoing = make_channel(
			chat_id=-1009100000001, title="Ongoing", purpose=TelegramChannel.Purpose.PUBLIC
		)
		self.completed = make_channel(
			chat_id=-1009100000002, title="Completed", purpose=TelegramChannel.Purpose.PUBLIC
		)
		settings = BotSettings.get_solo()
		settings.publish_channel = self.ongoing
		settings.ongoing_channel = self.ongoing
		settings.completed_channel = self.completed
		settings.save()

		self.title = build_title()
		for number in (1, 2, 3):
			make_part(self.title, number=number)
		self.session.reset()

	def click(self, data: str) -> None:
		self.feed(build_callback(data, user=ADMIN))

	def test_the_media_card_offers_the_announcement_button(self) -> None:
		self.click(f"{cb.ADM_MEDIA}:view:{self.title.pk}")

		self.assertIn("E'lon qilish", self.button_texts())

	def test_ongoing_title_asks_whether_the_last_episode_or_everything(self) -> None:
		self.click(f"{cb.ADM_MEDIA}:ann:{self.title.pk}")

		visible = self.visible()
		self.assertIn("Faqat oxirgi qism", visible)
		self.assertIn("Barcha qismlar", visible)
		# Nothing is announced before the operator answers.
		self.assertEqual(self.session.methods("SendMessage"), [])

	def test_announcing_only_the_last_episode(self) -> None:
		self.click(f"{cb.ADM_MEDIA}:annok:{self.title.pk}:last")

		posts = self.session.methods("SendMessage")
		self.assertEqual(len(posts), 1)
		self.assertEqual(posts[0].chat_id, self.ongoing.chat_id)
		self.assertIn("3-qism", posts[0].text)
		self.assertIn("Qism: 3/3", posts[0].text)

	def test_announcing_the_whole_run(self) -> None:
		self.click(f"{cb.ADM_MEDIA}:annok:{self.title.pk}:all")

		posts = self.session.methods("SendMessage")
		self.assertEqual(len(posts), 1)
		self.assertIn("1–3-qismlar", posts[0].text)

	def test_a_finished_title_skips_the_question_and_announces_everything(self) -> None:
		self.title.status = MediaTitle.Status.COMPLETED
		self.title.save(update_fields=["status"])

		self.click(f"{cb.ADM_MEDIA}:ann:{self.title.pk}")

		self.assertNotIn("Faqat oxirgi qism", self.visible())
		posts = self.session.methods("SendMessage")
		self.assertEqual(len(posts), 1)
		self.assertEqual(posts[0].chat_id, self.completed.chat_id)
		self.assertIn("1–3-qismlar", posts[0].text)

	def test_a_title_without_episodes_explains_what_to_add(self) -> None:
		bare = make_title(code="5123", title="Bo'sh Anime")

		self.click(f"{cb.ADM_MEDIA}:ann:{bare.pk}")
		self.click(f"{cb.ADM_MEDIA}:annok:{bare.pk}:all")

		self.assertIn("qism qo'shilmagan", self.visible())
		self.assertEqual(self.session.methods("SendMessage"), [])
