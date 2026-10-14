"""End-to-end tests for the bot's bulk episode uploader.

The uploader follows a strict rule: one part stores exactly one file, every
file the administrator sends is copied to the Cloud channel as its own
``copy_message``, and the part number is derived automatically (parts already
in that season + 1). These tests drive the real Dispatcher so the whole
pipeline — FSM storage, middlewares, keyboards and publishing — is covered.
"""

from __future__ import annotations

from aiogram.types import Document, ReplyKeyboardMarkup, ReplyKeyboardRemove, Video
from movies.models import MediaPart, TelegramChannel, TelegramMedia

from .. import callbacks as cb
from ..keyboards.admin import EPISODE_CANCEL_LABEL, EPISODE_SAVE_LABEL
from ..models import BotSettings
from .base import DispatcherTestCase
from .fakes import ADMIN, BOT_TOKEN, build_callback, build_message
from .helpers import bot_env, make_channel, make_part, make_title


def video_update(*, file_id: str = "v1", message_id: int = 101):
	return build_message(
		"",
		user=ADMIN,
		message_id=message_id,
		video=Video(
			file_id=file_id, file_unique_id=file_id, width=1280, height=720, duration=60
		),
	)


def document_update(*, file_id: str = "d1", message_id: int = 102):
	return build_message(
		"",
		user=ADMIN,
		message_id=message_id,
		document=Document(file_id=file_id, file_unique_id=file_id),
	)


class EpisodeUploadTests(DispatcherTestCase):
	def setUp(self) -> None:
		super().setUp()
		env = bot_env(ADMIN_IDS=str(ADMIN.id), BOT_TOKEN=BOT_TOKEN)
		env.__enter__()
		self.addCleanup(env.__exit__, None, None, None)

		self.title = make_title(code="4321", title="Bulk Anime")
		self.storage = make_channel(
			chat_id=-1007770000010,
			title="Cloud",
			purpose=TelegramChannel.Purpose.STORAGE,
		)
		self.public = make_channel(
			chat_id=-1007770000011,
			title="Ommaviy",
			purpose=TelegramChannel.Purpose.PUBLIC,
			username="bulk_news",
		)
		settings = BotSettings.get_solo()
		settings.publish_channel = self.public
		settings.save()

		self.update_id = 900
		self.session.reset()

	# ------------------------------------------------------------------ helpers
	def start_upload(self, season: str = "1") -> None:
		"""Pick the content and enter the season number (no session reset)."""
		self.update_id += 1
		self.feed(
			build_callback(
				f"{cb.ADM_EPISODES}:add:{self.title.pk}", user=ADMIN, update_id=self.update_id
			)
		)
		self.update_id += 1
		self.feed(build_message(season, user=ADMIN, message_id=50, update_id=self.update_id))

	def send(self, update) -> None:
		self.update_id += 1
		self.feed(update)

	def _chat_id(self, method):
		try:
			return int(method.chat_id)
		except (TypeError, ValueError):
			return None

	def _reply_keyboards(self):
		return [
			method
			for method in self.session.methods("SendMessage")
			if isinstance(method.reply_markup, ReplyKeyboardMarkup)
		]

	def _keyboard_removed(self) -> bool:
		return any(
			isinstance(method.reply_markup, ReplyKeyboardRemove)
			for method in self.session.methods("SendMessage")
		)

	# -------------------------------------------------------------------- tests
	def test_each_file_becomes_its_own_part_copied_to_the_cloud(self) -> None:
		self.start_upload(season="1")
		# Entering the season shows the 💾 Saqlash keyboard instead of asking a
		# part number, so the administrator can start sending files right away.
		keyboards = self._reply_keyboards()
		self.assertTrue(keyboards)
		self.assertEqual(
			keyboards[-1].reply_markup.keyboard[0][0].text, EPISODE_SAVE_LABEL
		)

		self.session.reset()
		self.send(video_update(file_id="v1", message_id=101))
		self.send(document_update(file_id="d1", message_id=102))

		parts = list(MediaPart.objects.filter(content=self.title).order_by("number"))
		self.assertEqual([part.number for part in parts], [1, 2])
		self.assertEqual({part.season_number for part in parts}, {1})

		media = TelegramMedia.objects.filter(part__content=self.title)
		self.assertEqual(media.count(), 2)
		self.assertEqual({row.channel_id for row in media}, {self.storage.pk})
		self.assertTrue(all(row.source_message_id for row in media))
		self.assertEqual({row.media_type for row in media}, {"video", "document"})

		copies = self.session.methods("CopyMessage")
		self.assertEqual(len(copies), 2)
		self.assertEqual({int(copy.from_chat_id) for copy in copies}, {ADMIN.id})
		self.assertEqual({int(copy.chat_id) for copy in copies}, {self.storage.chat_id})

	def test_number_continues_inside_the_season_only(self) -> None:
		make_part(self.title, number=1, season=1)
		make_part(self.title, number=1, season=2)  # another season must not count

		self.start_upload(season="1")
		self.send(video_update(file_id="v2", message_id=103))

		numbers = list(
			MediaPart.objects.filter(content=self.title, season_number=1)
			.order_by("number")
			.values_list("number", flat=True)
		)
		self.assertEqual(numbers, [1, 2])

	def test_save_publishes_the_batch_and_clears_the_keyboard(self) -> None:
		self.start_upload(season="1")
		self.send(video_update(file_id="v3", message_id=104))
		self.session.reset()

		self.send(build_message(EPISODE_SAVE_LABEL, user=ADMIN, message_id=60))

		posts = [
			method
			for method in self.session.methods("SendMessage")
			if self._chat_id(method) == self.public.chat_id
		]
		self.assertEqual(len(posts), 1)
		self.assertIn("Bulk Anime", posts[0].text)
		button = posts[0].reply_markup.inline_keyboard[0][0]
		self.assertIn("?start=anime_4321", button.url)
		self.assertIn("saqlandi", self.all_text())
		self.assertTrue(self._keyboard_removed())

	def test_cancel_clears_the_keyboard(self) -> None:
		self.start_upload(season="1")
		self.session.reset()

		self.send(build_message(EPISODE_CANCEL_LABEL, user=ADMIN, message_id=61))

		self.assertTrue(self._keyboard_removed())
		self.assertEqual(TelegramMedia.objects.count(), 0)
