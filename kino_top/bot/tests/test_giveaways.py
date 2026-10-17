"""Giveaway tests: eligibility, drawing rules and the administrator wizard.

The service tests pin the conditions (active subscription, optional bot-viewed
anime count) and the one-draw-only contract. The bot tests drive the real
Dispatcher through the wizard and a full draw with live channel/bio checks.
"""

from __future__ import annotations

from aiogram.types import Chat
from django.contrib.auth import get_user_model
from django.test import TestCase
from movies.models import MediaTitle, MediaView, TelegramChannel
from users.giveaways import (
	ALREADY_DRAWN,
	NOTHING_TO_DRAW,
	NOT_OPEN,
	GiveawayValidationError,
	candidate_telegram_ids_sync,
	create_giveaway_sync,
	draw_winners_sync,
	record_entry_sync,
	set_giveaway_status_sync,
)
from users.models import Giveaway, GiveawayEntry, GiveawayWinner, Subscription, TelegramUser

from .. import callbacks as cb
from ..models import BotSettings
from .base import DispatcherTestCase
from .fakes import ADMIN, BOT_TOKEN, USER, build_callback, build_command
from .helpers import bot_env, make_channel, make_part, make_title


def make_profile(telegram_id: int, username: str, *, active: bool = True) -> TelegramUser:
	auth_user = get_user_model().objects.create_user(username=username, password="x")
	subscription, _ = Subscription.objects.get_or_create(user=auth_user)
	if active:
		subscription.activate("monthly")
	return TelegramUser.objects.create(
		telegram_id=telegram_id, username=username, auth_user=auth_user
	)


def record_bot_view(profile: TelegramUser, title: MediaTitle) -> None:
	MediaView.objects.create(
		user=profile.auth_user,
		title=title,
		source=MediaView.Source.BOT,
	)


class GiveawayServiceTests(TestCase):
	def setUp(self) -> None:
		self.active = make_profile(111, "active")
		self.free = make_profile(222, "free", active=False)
		self.giveaway = create_giveaway_sync(title="Test", reward_days=15, winner_count=2)

	def test_validation_rejects_bad_wizard_input(self) -> None:
		with self.assertRaises(GiveawayValidationError):
			create_giveaway_sync(title="", reward_days=15)
		with self.assertRaises(GiveawayValidationError):
			create_giveaway_sync(title="X", reward_days=0)
		with self.assertRaises(GiveawayValidationError):
			create_giveaway_sync(title="X", reward_days=5, winner_count=0)

	def test_candidates_require_a_live_subscription(self) -> None:
		self.assertEqual(candidate_telegram_ids_sync(self.giveaway), [111])

	def test_min_bot_views_filters_by_anime_watched_in_the_bot(self) -> None:
		anime = make_title(code="1111", title="Naruto")
		other = make_title(code="2222", title="Bleach", media_type=MediaTitle.MediaType.SERIES)
		record_bot_view(self.active, anime)
		# A series view does not count towards the anime condition.
		record_bot_view(self.active, other)

		self.giveaway.min_bot_views = 2
		self.giveaway.save(update_fields=["min_bot_views"])
		self.assertEqual(candidate_telegram_ids_sync(self.giveaway), [])

		self.giveaway.min_bot_views = 1
		self.giveaway.save(update_fields=["min_bot_views"])
		self.assertEqual(candidate_telegram_ids_sync(self.giveaway), [111])

	def test_drawing_grants_and_blocks_a_second_draw(self) -> None:
		# The eligible list is prepared by the bot-side verification; here only
		# the active subscriber is passed in.
		result = draw_winners_sync(self.giveaway, [111])

		self.assertEqual(result.status, "drawn")
		self.assertEqual(len(result.winners), 1)
		winner = result.winners[0]
		self.assertEqual(winner.telegram_id, 111)
		subscription = Subscription.objects.get(user=self.active.auth_user)
		self.assertTrue(subscription.is_active)
		self.giveaway.refresh_from_db()
		self.assertEqual(self.giveaway.status, Giveaway.Status.DRAWN)

		again = draw_winners_sync(self.giveaway, [111])
		self.assertEqual(again.status, ALREADY_DRAWN)
		self.assertEqual(GiveawayWinner.objects.count(), 1)

	def test_drawing_with_nobody_eligible_changes_nothing(self) -> None:
		result = draw_winners_sync(self.giveaway, [])

		self.assertEqual(result.status, NOTHING_TO_DRAW)
		self.giveaway.refresh_from_db()
		self.assertEqual(self.giveaway.status, Giveaway.Status.OPEN)

	def test_entries_upsert_and_winner_status(self) -> None:
		entry = record_entry_sync(
			giveaway=self.giveaway,
			user=self.active.auth_user,
			telegram_id=111,
			status=GiveawayEntry.Status.NO_BIO,
		)
		self.assertEqual(entry.status, GiveawayEntry.Status.NO_BIO)

		record_entry_sync(
			giveaway=self.giveaway,
			user=self.active.auth_user,
			telegram_id=111,
			status=GiveawayEntry.Status.ELIGIBLE,
		)
		entry.refresh_from_db()
		self.assertEqual(entry.status, GiveawayEntry.Status.ELIGIBLE)
		self.assertEqual(GiveawayEntry.objects.count(), 1)

	def test_closed_giveaway_is_not_drawn_and_status_flips(self) -> None:
		updated = set_giveaway_status_sync(self.giveaway.pk, Giveaway.Status.CLOSED)
		self.assertEqual(updated.status, Giveaway.Status.CLOSED)

		result = draw_winners_sync(updated, [111])
		self.assertEqual(result.status, NOT_OPEN)

		# Reopen, draw, then a finished raffle never flips back.
		set_giveaway_status_sync(self.giveaway.pk, Giveaway.Status.OPEN)
		draw_winners_sync(self.giveaway, [111])
		self.giveaway.refresh_from_db()
		self.assertEqual(self.giveaway.status, Giveaway.Status.DRAWN)
		updated = set_giveaway_status_sync(self.giveaway.pk, Giveaway.Status.OPEN)
		self.assertEqual(updated.status, Giveaway.Status.DRAWN)


class AdminGiveawayFlowTests(DispatcherTestCase):
	def setUp(self) -> None:
		super().setUp()
		env = bot_env(ADMIN_IDS=str(ADMIN.id), BOT_TOKEN=BOT_TOKEN)
		env.__enter__()
		self.addCleanup(env.__exit__, None, None, None)
		BotSettings.get_solo()
		self.update_id = 800

	def click(self, data: str) -> None:
		self.update_id += 1
		self.feed(build_callback(data, user=ADMIN, update_id=self.update_id))

	def type_text(self, text: str) -> None:
		from .fakes import build_message

		self.update_id += 1
		self.feed(build_message(text, user=ADMIN, update_id=self.update_id))

	def build_giveaway(self, *, title="Yangi yil", days=30, winners="3", min_views="0") -> Giveaway:
		self.click(f"{cb.ADM_GIVEAWAY}:new")
		self.type_text(title)
		self.type_text(str(days))
		self.type_text(winners)
		self.type_text(min_views)
		self.click(f"{cb.ADM_GIVEAWAY}:create")
		return Giveaway.objects.get(title=title)

	def test_the_panel_links_the_giveaway_section(self) -> None:
		self.feed(build_command("admin", user=ADMIN))
		self.assertIn("Sovg'alar", self.visible())

	def test_the_builder_creates_a_giveaway(self) -> None:
		giveaway = self.build_giveaway(title="Sumalak", days=15, winners="3", min_views="2")

		self.assertEqual(giveaway.reward_days, 15)
		self.assertEqual(giveaway.winner_count, 3)
		self.assertEqual(giveaway.min_bot_views, 2)
		self.assertEqual(giveaway.status, Giveaway.Status.OPEN)
		self.assertFalse(giveaway.require_channels)
		self.assertFalse(giveaway.require_bio_ref)
		self.assertIn("Sumalak", self.visible())

	def test_flags_toggle_before_creation(self) -> None:
		self.click(f"{cb.ADM_GIVEAWAY}:new")
		self.type_text("Flagged")
		self.type_text("7")
		self.type_text("1")
		self.type_text("0")
		self.click(f"{cb.ADM_GIVEAWAY}:fch")
		self.click(f"{cb.ADM_GIVEAWAY}:fbio")
		self.click(f"{cb.ADM_GIVEAWAY}:create")

		giveaway = Giveaway.objects.get(title="Flagged")
		self.assertTrue(giveaway.require_channels)
		self.assertTrue(giveaway.require_bio_ref)

	def test_invalid_numbers_are_refused(self) -> None:
		self.click(f"{cb.ADM_GIVEAWAY}:new")
		self.type_text("")
		self.assertIn("Noto'g'ri", self.visible())
		self.type_text("Nomi")
		self.type_text("0")
		self.assertEqual(Giveaway.objects.count(), 0)

	def test_list_and_card_render(self) -> None:
		giveaway = self.build_giveaway(title="Cardview")

		self.click(f"{cb.ADM_GIVEAWAY}:list:1")
		self.assertIn("Cardview", self.visible())

		self.click(f"{cb.ADM_GIVEAWAY}:view:{giveaway.pk}")
		self.assertIn("Mukofot", self.visible())

	def test_auto_publish_announces_the_new_giveaway(self) -> None:
		channel = make_channel(
			chat_id=-1007770000012,
			title="Ommaviy",
			purpose=TelegramChannel.Purpose.PUBLIC,
			username="news_giveaway",
		)
		settings = BotSettings.get_solo()
		settings.publish_channel = channel
		settings.auto_publish_new_content = True
		settings.save()

		self.build_giveaway(title="Auto sovg'a")

		posts = [
			method
			for method in self.session.methods("SendMessage")
			if int(method.chat_id) == channel.chat_id
		]
		self.assertEqual(len(posts), 1)
		self.assertIn("30 kunlik obuna", posts[0].text)
		button = posts[0].reply_markup.inline_keyboard[0][0]
		self.assertEqual(button.text, "🎁 Qatnashish")
		self.assertIn("t.me/", button.url)

	def test_manual_publish_from_the_card(self) -> None:
		channel = make_channel(
			chat_id=-1007770000013,
			title="Ommaviy",
			purpose=TelegramChannel.Purpose.PUBLIC,
			username="news_manual",
		)
		settings = BotSettings.get_solo()
		settings.publish_channel = channel
		settings.save()
		giveaway = create_giveaway_sync(title="Qo'lda", reward_days=5, winner_count=1)

		self.click(f"{cb.ADM_GIVEAWAY}:view:{giveaway.pk}")
		self.session.reset()
		self.click(f"{cb.ADM_GIVEAWAY}:pub:{giveaway.pk}")

		posts = [
			method
			for method in self.session.methods("SendMessage")
			if int(method.chat_id) == channel.chat_id
		]
		self.assertEqual(len(posts), 1)
		self.assertIn("5 kunlik obuna", posts[0].text)

	def test_manual_publish_without_a_channel_warns(self) -> None:
		giveaway = create_giveaway_sync(title="Kanalsiz", reward_days=5, winner_count=1)

		self.click(f"{cb.ADM_GIVEAWAY}:view:{giveaway.pk}")
		self.session.reset()
		self.click(f"{cb.ADM_GIVEAWAY}:pub:{giveaway.pk}")

		alerts = " ".join(
			str(method.text or "") for method in self.session.methods("AnswerCallbackQuery")
		)
		self.assertIn("E'lon kanali", alerts)

	def test_deleting_requires_confirmation(self) -> None:
		giveaway = self.build_giveaway(title="Toshadi")

		self.click(f"{cb.ADM_GIVEAWAY}:del:{giveaway.pk}")
		self.assertIn("tasdiqlayman", self.visible().lower())
		self.assertTrue(Giveaway.objects.filter(pk=giveaway.pk).exists())

		self.click(f"{cb.ADM_GIVEAWAY}:dyes:{giveaway.pk}:1")
		self.assertFalse(Giveaway.objects.filter(pk=giveaway.pk).exists())

	def test_full_draw_with_channel_and_bio_checks(self) -> None:
		channel = make_channel(
			chat_id=-1007770000011, title="Homiy", purpose=TelegramChannel.Purpose.REQUIRED
		)
		winner = make_profile(444, "winner")
		loser = make_profile(555, "loser")
		giveaway = create_giveaway_sync(
			title="Drawtest",
			reward_days=10,
			winner_count=1,
			require_channels=True,
			require_bio_ref=True,
		)
		giveaway.channels.add(channel)

		# Winner's bio has the referral payload; the loser's does not.
		def get_chat(method):
			chat_id = int(method.chat_id)
			bio = f"ref_{chat_id}" if chat_id == 444 else "salom"
			return Chat(id=chat_id, type="private", bio=bio)

		self.session.responders["GetChat"] = get_chat
		# Default FakeSession GetChatMember returns "member" (subscribed).

		self.click(f"{cb.ADM_GIVEAWAY}:draw:{giveaway.pk}")
		self.session.reset()
		self.click(f"{cb.ADM_GIVEAWAY}:yes:{giveaway.pk}:1")

		self.assertIn("Sovg'a yakunlandi", self.visible())
		giveaway.refresh_from_db()
		self.assertEqual(giveaway.status, Giveaway.Status.DRAWN)
		winner_row = GiveawayWinner.objects.get(giveaway=giveaway)
		self.assertEqual(winner_row.telegram_id, 444)
		subscription = Subscription.objects.get(user=winner.auth_user)
		self.assertTrue(subscription.is_active)
		# The loser was journaled as missing the bio condition.
		loser_entry = GiveawayEntry.objects.get(
			giveaway=giveaway, user=loser.auth_user
		)
		self.assertEqual(loser_entry.status, GiveawayEntry.Status.NO_BIO)
		# The winner got a DM.
		sent = self.session.methods("SendMessage")
		self.assertTrue(any(getattr(m, "chat_id", None) == 444 for m in sent))

	def test_draw_twice_reports_already(self) -> None:
		winner = make_profile(666, "solo")
		giveaway = create_giveaway_sync(title="Once", reward_days=5, winner_count=1)

		self.click(f"{cb.ADM_GIVEAWAY}:draw:{giveaway.pk}")
		self.click(f"{cb.ADM_GIVEAWAY}:yes:{giveaway.pk}:1")
		self.assertIn("yakunlandi", self.visible())

		self.click(f"{cb.ADM_GIVEAWAY}:yes:{giveaway.pk}:1")
		self.assertIn("allaqachon o'tkazilgan", self.visible())
		self.assertEqual(GiveawayWinner.objects.filter(giveaway=giveaway).count(), 1)

	def test_draw_with_no_candidates_reports_empty(self) -> None:
		giveaway = create_giveaway_sync(title="Bosh", reward_days=5, winner_count=1)

		self.click(f"{cb.ADM_GIVEAWAY}:draw:{giveaway.pk}")
		self.click(f"{cb.ADM_GIVEAWAY}:yes:{giveaway.pk}:1")

		self.assertIn("G'olib topilmadi", self.visible())
		giveaway.refresh_from_db()
		self.assertEqual(giveaway.status, Giveaway.Status.OPEN)
