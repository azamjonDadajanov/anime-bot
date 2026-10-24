"""Tests for storage channel listener (direct uploads to Cloud storage channels)."""

from __future__ import annotations

import asyncio
from aiogram.types import Chat, Message, Update, Video

from movies.models import MediaPart, MediaTitle, TelegramChannel, TelegramMedia
from bot.models import BotSettings
from bot.handlers.storage_channel import extract_media_code, extract_season_number
from bot.tests.base import DispatcherTestCase
from bot.tests.fakes import ADMIN, BOT_TOKEN, NOW
from bot.tests.helpers import bot_env, make_channel, make_title


def build_channel_post(
	chat: Chat,
	message_id: int = 100,
	caption: str = "",
	video_id: str = "v1",
) -> Update:
	message = Message(
		message_id=message_id,
		date=NOW,
		chat=chat,
		caption=caption,
		video=Video(
			file_id=video_id,
			file_unique_id=video_id,
			width=1280,
			height=720,
			duration=60,
		),
	)
	return Update(update_id=message_id + 1000, channel_post=message)


class StorageChannelTests(DispatcherTestCase):
	def setUp(self) -> None:
		super().setUp()
		env = bot_env(ADMIN_IDS=str(ADMIN.id), BOT_TOKEN=BOT_TOKEN)
		env.__enter__()
		self.addCleanup(env.__exit__, None, None, None)

		self.storage_ch = make_channel(
			chat_id=-1008880000001,
			title="Storage Cloud",
			purpose=TelegramChannel.Purpose.STORAGE,
		)
		self.completed_ch = make_channel(
			chat_id=-1008880000002,
			title="Completed Ch",
			purpose=TelegramChannel.Purpose.ANIME_COMPLETED,
		)
		self.ongoing_ch = make_channel(
			chat_id=-1008880000003,
			title="Ongoing Ch",
			purpose=TelegramChannel.Purpose.ANIME_ONGOING,
		)

		settings = BotSettings.get_solo()
		settings.publish_channel = self.completed_ch
		settings.auto_publish_new_content = True
		settings.save()

		self.chat = Chat(id=self.storage_ch.chat_id, type="channel", title="Storage Cloud")
		self.session.reset()

	def test_code_and_season_extraction(self) -> None:
		self.assertEqual(extract_media_code("code: 8874"), "8874")
		self.assertEqual(extract_media_code("kod: 8874\nSeason: 2"), "8874")
		self.assertEqual(extract_media_code("Anime nomi #8874"), "8874")
		self.assertEqual(extract_media_code("8874"), "8874")
		self.assertIsNone(extract_media_code("random caption"))

		self.assertEqual(extract_season_number("kod: 8874\nSeason: 2"), 2)
		self.assertEqual(extract_season_number("2-mavsum: kod 8874"), None)
		self.assertEqual(extract_season_number("mavsum: 3"), 3)

	def test_direct_upload_adds_part_and_confirms(self) -> None:
		"""When video with code: 8874 is posted to storage channel, part is created and confirmed."""
		title = make_title(code="8874", title="Storage Anime", media_type="anime", status="ongoing")
		title.episode_count = 10
		title.save(update_fields=["episode_count"])

		update = build_channel_post(self.chat, message_id=501, caption="Yangi qism\ncode: 8874", video_id="video-8874-1")
		self.feed(update)

		# Check MediaPart is created
		part = MediaPart.objects.filter(content=title).first()
		self.assertIsNotNone(part)
		self.assertEqual(part.number, 1)

		# Check TelegramMedia is created
		media = TelegramMedia.objects.filter(part=part).first()
		self.assertIsNotNone(media)
		self.assertEqual(media.file_id, "video-8874-1")
		self.assertEqual(media.channel_id, self.storage_ch.pk)
		self.assertEqual(media.source_message_id, 501)

		# Check confirmation message sent to storage channel
		confirm_posts = [
			m for m in self.session.methods("SendMessage")
			if int(m.chat_id) == self.storage_ch.chat_id
		]
		self.assertTrue(confirm_posts)
		self.assertIn("1-qism muvaffaqiyatli qo'shildi", confirm_posts[0].text)
		self.assertIn("Storage Anime", confirm_posts[0].text)

		# Since it is ongoing and not finished, ongoing channel receives the post
		ongoing_posts = [
			m for m in self.session.methods("SendMessage") + self.session.methods("SendPhoto")
			if int(m.chat_id) == self.ongoing_ch.chat_id
		]
		self.assertEqual(len(ongoing_posts), 1)

	def test_completed_media_waits_for_all_parts(self) -> None:
		"""Completed media or movie uploaded directly to storage waits until all parts exist."""
		title = make_title(code="8875", title="Completed Anime", media_type="anime", status="completed")
		title.episode_count = 2
		title.save(update_fields=["episode_count"])

		# 1st episode posted -> confirmed in storage, but NOT published to completed channel
		upd1 = build_channel_post(self.chat, message_id=601, caption="code: 8875", video_id="video-1")
		self.feed(upd1)

		self.assertEqual(MediaPart.objects.filter(content=title).count(), 1)
		completed_posts = [
			m for m in self.session.methods("SendMessage") + self.session.methods("SendPhoto")
			if int(m.chat_id) == self.completed_ch.chat_id
		]
		self.assertEqual(len(completed_posts), 0)

		# 2nd episode posted -> all parts exist -> published to completed channel!
		upd2 = build_channel_post(self.chat, message_id=602, caption="code: 8875", video_id="video-2")
		self.feed(upd2)

		self.assertEqual(MediaPart.objects.filter(content=title).count(), 2)
		completed_posts = [
			m for m in self.session.methods("SendMessage") + self.session.methods("SendPhoto")
			if int(m.chat_id) == self.completed_ch.chat_id
		]
		self.assertEqual(len(completed_posts), 1)
		self.assertIn("Completed Anime", completed_posts[0].text if hasattr(completed_posts[0], "text") else completed_posts[0].caption)
