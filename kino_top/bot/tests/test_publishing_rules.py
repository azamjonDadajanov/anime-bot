"""Tests for rule-based episode publishing logic:

- ongoing media posts each episode to the section's Ongoing channel;
- ongoing media posts to the Tugagan channel once it finishes;
- completed media/movie posts only when the parts count equals episode_count;
- manga posts to the manga Ongoing channel;
- paid (VIP) media always goes to the section's VIP channel;
- an empty section bucket falls back to the main announcement channel.
"""

from __future__ import annotations

import asyncio

from bot.models import BotSettings
from bot.services.publishing import (
	announcement_purpose_chain,
	completed_announcement_text,
	ongoing_announcement_text,
	publish_completed_title,
	publish_ongoing_parts,
	publish_parts_by_rules,
	resolve_target_channel,
	resolve_target_channels,
)
from bot.tests.base import DispatcherTestCase
from bot.tests.fakes import ADMIN, BOT_TOKEN, FakeSession
from bot.tests.helpers import bot_env, make_channel, make_part, make_title
from movies.models import MediaTitle, TelegramChannel

Purpose = TelegramChannel.Purpose


class PublishingRulesTests(DispatcherTestCase):
	def setUp(self) -> None:
		super().setUp()
		env = bot_env(ADMIN_IDS=str(ADMIN.id), BOT_TOKEN=BOT_TOKEN)
		env.__enter__()
		self.addCleanup(env.__exit__, None, None, None)

		# Bo'limlar bo'yicha e'lon kanallari.
		self.general_ch = make_channel(
			chat_id=-1001111111111, title="Asosiy e'lon", purpose=Purpose.PUBLIC
		)
		self.anime_ongoing_ch = make_channel(
			chat_id=-1002222222222, title="Animelar Ongoing", purpose=Purpose.ANIME_ONGOING
		)
		self.anime_completed_ch = make_channel(
			chat_id=-1002222222223, title="Animelar Tugagan", purpose=Purpose.ANIME_COMPLETED
		)
		self.anime_vip_ch = make_channel(
			chat_id=-1002222222224, title="Animelar VIP", purpose=Purpose.ANIME_VIP
		)
		self.movie_ch = make_channel(
			chat_id=-1003333333333, title="Kinolar", purpose=Purpose.MOVIE
		)
		self.movie_vip_ch = make_channel(
			chat_id=-1003333333334, title="Kinolar VIP", purpose=Purpose.MOVIE_VIP
		)
		self.manga_ch = make_channel(
			chat_id=-1004444444444, title="Mangalar Ongoing", purpose=Purpose.MANGA_ONGOING
		)
		self.manga_completed_ch = make_channel(
			chat_id=-1004444444445, title="Mangalar Tugagan", purpose=Purpose.MANGA_COMPLETED
		)
		self.manga_vip_ch = make_channel(
			chat_id=-1004444444446, title="Mangalar VIP", purpose=Purpose.MANGA_VIP
		)

		settings = BotSettings.get_solo()
		settings.publish_channel = self.general_ch
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

	def test_channel_resolution_per_section_and_status(self) -> None:
		anime_ongoing = make_title(code="1001", media_type="anime", status="ongoing")
		anime_completed = make_title(code="1002", media_type="anime", status="completed")
		manga_ongoing = make_title(code="1003", media_type="manga", status="ongoing")
		manga_completed = make_title(code="1004", media_type="manga", status="completed")
		movie = make_title(code="1005", media_type="movie", status="completed")

		self.assertEqual(
			asyncio.run(resolve_target_channel(anime_ongoing, is_completed=False)).pk,
			self.anime_ongoing_ch.pk,
		)
		self.assertEqual(
			asyncio.run(resolve_target_channel(anime_completed, is_completed=True)).pk,
			self.anime_completed_ch.pk,
		)
		self.assertEqual(
			asyncio.run(resolve_target_channel(manga_ongoing, is_completed=False)).pk,
			self.manga_ch.pk,
		)
		self.assertEqual(
			asyncio.run(resolve_target_channel(manga_completed, is_completed=True)).pk,
			self.manga_completed_ch.pk,
		)
		self.assertEqual(
			asyncio.run(resolve_target_channel(movie, is_completed=True)).pk,
			self.movie_ch.pk,
		)

	def test_paid_media_goes_to_the_vip_channel(self) -> None:
		paid_anime = make_title(code="1101", media_type="anime", required_plan="paid")
		paid_manga = make_title(code="1102", media_type="manga", required_plan="paid")
		paid_movie = make_title(code="1103", media_type="movie", required_plan="paid")

		self.assertEqual(
			asyncio.run(resolve_target_channel(paid_anime, is_completed=False)).pk,
			self.anime_vip_ch.pk,
		)
		self.assertEqual(
			asyncio.run(resolve_target_channel(paid_manga, is_completed=True)).pk,
			self.manga_vip_ch.pk,
		)
		self.assertEqual(
			asyncio.run(resolve_target_channel(paid_movie, is_completed=True)).pk,
			self.movie_vip_ch.pk,
		)

	def test_paid_media_falls_back_when_the_vip_channel_is_missing(self) -> None:
		self.anime_vip_ch.delete()
		paid_anime = make_title(code="1111", media_type="anime", required_plan="paid")

		targets = asyncio.run(resolve_target_channels(paid_anime, is_completed=False))

		self.assertEqual([target.pk for target in targets], [self.anime_ongoing_ch.pk])

	def test_empty_section_uses_the_main_channel(self) -> None:
		self.anime_ongoing_ch.delete()
		anime = make_title(code="1121", media_type="anime", status="ongoing")

		targets = asyncio.run(resolve_target_channels(anime, is_completed=False))

		self.assertEqual([target.pk for target in targets], [self.general_ch.pk])

	def test_purpose_chain_order(self) -> None:
		paid_completed = make_title(
			code="1131", media_type="anime", status="completed", required_plan="paid"
		)
		self.assertEqual(
			announcement_purpose_chain(paid_completed, is_completed=True),
			(Purpose.ANIME_VIP, Purpose.ANIME_COMPLETED, Purpose.ANIME_ONGOING),
		)
		movie = make_title(code="1132", media_type="movie", status="completed")
		self.assertEqual(
			announcement_purpose_chain(movie, is_completed=True),
			(Purpose.MOVIE,),
		)

	def test_completed_title_parts_rule(self) -> None:
		"""Completed media does NOT publish until parts count equals episode_count."""
		title = make_title(code="2001", media_type="anime", status="completed")
		title.episode_count = 2
		title.save(update_fields=["episode_count"])
		part1 = make_part(title, number=1)

		# 1 part added out of 2 -> should NOT publish yet
		msg_id1 = asyncio.run(publish_parts_by_rules(self.bot, title, [part1]))
		self.assertIsNone(msg_id1)
		self.assertEqual(len(self._posts_to_chat(self.anime_completed_ch.chat_id)), 0)

		# 2nd part added -> reaches episode_count -> publishes to completed channel
		part2 = make_part(title, number=2)
		msg_id2 = asyncio.run(publish_parts_by_rules(self.bot, title, [part2]))
		self.assertIsNotNone(msg_id2)
		posts = self._posts_to_chat(self.anime_completed_ch.chat_id)
		self.assertEqual(len(posts), 1)

	def test_movie_publishing_rule(self) -> None:
		"""Movie publishes to the Kinolar channel when its part is added."""
		movie = make_title(code="2002", media_type="movie", status="completed")
		movie.episode_count = 1
		movie.save(update_fields=["episode_count"])
		part = make_part(movie, number=1)

		msg_id = asyncio.run(publish_parts_by_rules(self.bot, movie, [part]))
		self.assertIsNotNone(msg_id)
		self.assertEqual(len(self._posts_to_chat(self.movie_ch.chat_id)), 1)

	def test_paid_movie_publishing_rule(self) -> None:
		"""A paid movie is announced in the Kinolar VIP channel."""
		movie = make_title(
			code="2006", media_type="movie", status="completed", required_plan="paid"
		)
		movie.episode_count = 1
		movie.save(update_fields=["episode_count"])
		part = make_part(movie, number=1)

		msg_id = asyncio.run(publish_parts_by_rules(self.bot, movie, [part]))
		self.assertIsNotNone(msg_id)
		self.assertEqual(len(self._posts_to_chat(self.movie_vip_ch.chat_id)), 1)
		self.assertEqual(len(self._posts_to_chat(self.movie_ch.chat_id)), 0)

	def test_ongoing_parts_and_completion_rule(self) -> None:
		"""Ongoing media posts parts to Ongoing, and to Tugagan once finished."""
		title = make_title(code="2003", media_type="anime", status="ongoing")
		title.episode_count = 2
		title.save(update_fields=["episode_count"])

		# 1st episode added -> posts to the ongoing channel
		part1 = make_part(title, number=1)
		msg_id1 = asyncio.run(publish_parts_by_rules(self.bot, title, [part1]))
		self.assertIsNotNone(msg_id1)
		self.assertEqual(len(self._posts_to_chat(self.anime_ongoing_ch.chat_id)), 1)

		# 2nd episode added -> reaches episode_count -> marks completed and posts
		part2 = make_part(title, number=2)
		msg_id2 = asyncio.run(publish_parts_by_rules(self.bot, title, [part2]))
		self.assertIsNotNone(msg_id2)
		self.assertEqual(len(self._posts_to_chat(self.anime_completed_ch.chat_id)), 1)

		title.refresh_from_db()
		self.assertEqual(title.status, MediaTitle.Status.COMPLETED)

	def test_manga_publishing_rule(self) -> None:
		"""Manga posts to the manga channel and uses the reading action label."""
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

	def test_completed_and_ongoing_text_builders(self) -> None:
		title = make_title(code="2005", media_type="anime", status="ongoing")
		self.assertIn("Tugallandi", completed_announcement_text(title))
		self.assertIn("Test Anime", ongoing_announcement_text(title, []))
