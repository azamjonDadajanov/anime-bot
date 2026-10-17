"""Tests for rule-based episode publishing logic:
- completed media/movie posts only when parts count equals expected parts count;
- ongoing media posts each episode to ongoing channel;
- ongoing media posts to completed channel once finished;
- manga posts to manga channel(s).
"""

from __future__ import annotations

import asyncio

from movies.models import MediaPart, MediaTitle, TelegramChannel
from bot.models import BotSettings
from bot.services.publishing import (
	completed_announcement_text,
	ongoing_announcement_text,
	publish_completed_title,
	publish_ongoing_parts,
	publish_parts_by_rules,
	resolve_target_channel,
)
from bot.tests.base import DispatcherTestCase
from bot.tests.fakes import ADMIN, BOT_TOKEN, FakeSession
from bot.tests.helpers import bot_env, make_channel, make_part, make_title


class PublishingRulesTests(DispatcherTestCase):
	def setUp(self) -> None:
		super().setUp()
		env = bot_env(ADMIN_IDS=str(ADMIN.id), BOT_TOKEN=BOT_TOKEN)
		env.__enter__()
		self.addCleanup(env.__exit__, None, None, None)

		# Setup dedicated channels
		self.general_ch = make_channel(
			chat_id=-1001111111111, title="General Public", purpose=TelegramChannel.Purpose.PUBLIC
		)
		self.completed_ch = make_channel(
			chat_id=-1002222222222, title="Completed Channel", purpose=TelegramChannel.Purpose.PUBLIC
		)
		self.ongoing_ch = make_channel(
			chat_id=-1003333333333, title="Ongoing Channel", purpose=TelegramChannel.Purpose.PUBLIC
		)
		self.manga_ch = make_channel(
			chat_id=-1004444444444, title="Manga Ongoing", purpose=TelegramChannel.Purpose.PUBLIC
		)
		self.manga_completed_ch = make_channel(
			chat_id=-1005555555555, title="Manga Completed", purpose=TelegramChannel.Purpose.PUBLIC
		)

		settings = BotSettings.get_solo()
		settings.publish_channel = self.general_ch
		settings.completed_channel = self.completed_ch
		settings.ongoing_channel = self.ongoing_ch
		settings.manga_channel = self.manga_ch
		settings.manga_completed_channel = self.manga_completed_ch
		settings.auto_publish_new_content = True
		settings.save()

		self.session.reset()

	def _posts_to_chat(self, chat_id: int):
		messages = [
			m for m in self.session.methods("SendMessage")
			if int(getattr(m, "chat_id", 0) or 0) == chat_id
		]
		photos = [
			p for p in self.session.methods("SendPhoto")
			if int(getattr(p, "chat_id", 0) or 0) == chat_id
		]
		return messages + photos

	def test_channel_resolution(self) -> None:
		anime_ongoing = make_title(code="1001", media_type="anime", status="ongoing")
		anime_completed = make_title(code="1002", media_type="anime", status="completed")
		manga_ongoing = make_title(code="1003", media_type="manga", status="ongoing")
		manga_completed = make_title(code="1004", media_type="manga", status="completed")

		target_ao = asyncio.run(resolve_target_channel(anime_ongoing, is_completed=False))
		self.assertEqual(target_ao.pk, self.ongoing_ch.pk)

		target_ac = asyncio.run(resolve_target_channel(anime_completed, is_completed=True))
		self.assertEqual(target_ac.pk, self.completed_ch.pk)

		target_mo = asyncio.run(resolve_target_channel(manga_ongoing, is_completed=False))
		self.assertEqual(target_mo.pk, self.manga_ch.pk)

		target_mc = asyncio.run(resolve_target_channel(manga_completed, is_completed=True))
		self.assertEqual(target_mc.pk, self.manga_completed_ch.pk)

	def test_completed_title_parts_rule(self) -> None:
		"""Completed media does NOT publish until parts count equals episode_count."""
		title = make_title(code="2001", media_type="anime", status="completed")
		title.episode_count = 2
		title.save(update_fields=["episode_count"])
		part1 = make_part(title, number=1)

		# 1 part added out of 2 -> should NOT publish yet
		msg_id1 = asyncio.run(publish_parts_by_rules(self.bot, title, [part1]))
		self.assertIsNone(msg_id1)
		self.assertEqual(len(self._posts_to_chat(self.completed_ch.chat_id)), 0)

		# 2nd part added -> reaches episode_count -> publishes to completed channel
		part2 = make_part(title, number=2)
		msg_id2 = asyncio.run(publish_parts_by_rules(self.bot, title, [part2]))
		self.assertIsNotNone(msg_id2)
		posts = self._posts_to_chat(self.completed_ch.chat_id)
		self.assertEqual(len(posts), 1)

	def test_movie_publishing_rule(self) -> None:
		"""Movie publishes to completed channel when part is added."""
		movie = make_title(code="2002", media_type="movie", status="completed")
		movie.episode_count = 1
		movie.save(update_fields=["episode_count"])
		part = make_part(movie, number=1)

		msg_id = asyncio.run(publish_parts_by_rules(self.bot, movie, [part]))
		self.assertIsNotNone(msg_id)
		posts = self._posts_to_chat(self.completed_ch.chat_id)
		self.assertEqual(len(posts), 1)

	def test_ongoing_parts_and_completion_rule(self) -> None:
		"""Ongoing media posts parts to ongoing channel, and to completed channel when finished."""
		title = make_title(code="2003", media_type="anime", status="ongoing")
		title.episode_count = 2
		title.save(update_fields=["episode_count"])

		# 1st episode added -> posts to ongoing channel
		part1 = make_part(title, number=1)
		msg_id1 = asyncio.run(publish_parts_by_rules(self.bot, title, [part1]))
		self.assertIsNotNone(msg_id1)
		ongoing_posts = self._posts_to_chat(self.ongoing_ch.chat_id)
		self.assertEqual(len(ongoing_posts), 1)

		# 2nd episode added -> reaches episode_count -> marks completed and posts to completed channel!
		part2 = make_part(title, number=2)
		msg_id2 = asyncio.run(publish_parts_by_rules(self.bot, title, [part2]))
		self.assertIsNotNone(msg_id2)
		completed_posts = self._posts_to_chat(self.completed_ch.chat_id)
		self.assertEqual(len(completed_posts), 1)

		title.refresh_from_db()
		self.assertEqual(title.status, MediaTitle.Status.COMPLETED)

	def test_manga_publishing_rule(self) -> None:
		"""Manga posts to manga channels and uses reading action label."""
		manga = make_title(code="2004", media_type="manga", status="ongoing")
		manga.episode_count = 5
		manga.save(update_fields=["episode_count"])

		part1 = make_part(manga, number=1)
		msg_id = asyncio.run(publish_parts_by_rules(self.bot, manga, [part1]))
		self.assertIsNotNone(msg_id)

		manga_posts = self._posts_to_chat(self.manga_ch.chat_id)
		self.assertEqual(len(manga_posts), 1)
		button = manga_posts[0].reply_markup.inline_keyboard[0][0]
		self.assertIn("O'qish", button.text)
