"""Referral tests: attribution rules, manual milestone claims, bot flows.

The service tests pin the one-inviter-per-user contract and the "claim
yourself" reward rule (nothing is granted automatically). The bot tests drive
the real Dispatcher for ``/start ref_<id>`` and the 👥 menu.
"""

from __future__ import annotations

from datetime import timedelta

from aiogram.types import User as TgUser
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from users.models import ReferralReward, Subscription, TelegramUser
from users.referrals import (
	ALREADY,
	CLAIMED,
	INVALID,
	NOT_ENOUGH,
	NO_ACCOUNT,
	claim_reward_sync,
	parse_referral_payload,
	register_referral_sync,
	referral_payload,
	referral_stats_sync,
)

from .. import callbacks as cb
from .base import DispatcherTestCase
from .fakes import USER, build_callback, build_command


def make_profile(telegram_id: int, username: str) -> TelegramUser:
	auth_user = get_user_model().objects.create_user(username=username, password="x")
	Subscription.objects.get_or_create(user=auth_user)
	return TelegramUser.objects.create(
		telegram_id=telegram_id, username=username, auth_user=auth_user
	)


def make_invitees(inviter: TelegramUser, count: int) -> None:
	for index in range(count):
		TelegramUser.objects.create(
			telegram_id=10_000 + index,
			username=f"invitee{index}",
			referred_by=inviter,
		)


class ReferralServiceTests(TestCase):
	def setUp(self) -> None:
		self.inviter = make_profile(111, "inviter")
		self.invitee = make_profile(222, "invitee")

	def test_payload_roundtrip(self) -> None:
		self.assertEqual(referral_payload(111), "ref_111")
		self.assertEqual(parse_referral_payload("ref_111"), 111)
		self.assertIsNone(parse_referral_payload("anime_1234"))
		self.assertIsNone(parse_referral_payload("ref_abc"))

	def test_attribution_happens_once(self) -> None:
		self.assertTrue(
			register_referral_sync(invitee=self.invitee, inviter_tg_id=111)
		)
		self.invitee.refresh_from_db()
		self.assertEqual(self.invitee.referred_by_id, self.inviter.pk)

		self.assertFalse(
			register_referral_sync(invitee=self.invitee, inviter_tg_id=999)
		)
		self.invitee.refresh_from_db()
		self.assertEqual(self.invitee.referred_by_id, self.inviter.pk)

	def test_self_referral_is_ignored(self) -> None:
		self.assertFalse(
			register_referral_sync(invitee=self.invitee, inviter_tg_id=222)
		)
		self.invitee.refresh_from_db()
		self.assertIsNone(self.invitee.referred_by_id)

	def test_unknown_inviter_is_ignored(self) -> None:
		self.assertFalse(
			register_referral_sync(invitee=self.invitee, inviter_tg_id=424242)
		)
		self.invitee.refresh_from_db()
		self.assertIsNone(self.invitee.referred_by_id)

	def test_stats_count_invited_and_claimed(self) -> None:
		make_invitees(self.inviter, 10)
		ReferralReward.objects.create(user=self.inviter.auth_user, milestone=10, days=15)

		stats = referral_stats_sync(111)

		self.assertEqual(stats.invited_count, 10)
		self.assertEqual(stats.claimed_milestones, [10])
		self.assertEqual(stats.link, "ref_111")

	def test_claiming_below_the_milestone_is_refused(self) -> None:
		result = claim_reward_sync(telegram_id=111, milestone=10)

		self.assertEqual(result.status, NOT_ENOUGH)
		self.assertEqual(ReferralReward.objects.count(), 0)
		subscription = Subscription.objects.get(user=self.inviter.auth_user)
		self.assertFalse(subscription.is_active)

	def test_claiming_grants_days_and_blocks_repeats(self) -> None:
		make_invitees(self.inviter, 10)

		first = claim_reward_sync(telegram_id=111, milestone=10)

		self.assertEqual(first.status, CLAIMED)
		self.assertEqual(first.days, 15)
		subscription = Subscription.objects.get(user=self.inviter.auth_user)
		self.assertTrue(subscription.is_active)
		self.assertEqual(subscription.plan, Subscription.Plan.COUPON)
		remaining = subscription.expires_at - timezone.now()
		self.assertGreater(remaining, timedelta(days=14))

		second = claim_reward_sync(telegram_id=111, milestone=10)
		self.assertEqual(second.status, ALREADY)
		subscription.refresh_from_db()
		after = subscription.expires_at - timezone.now()
		self.assertLess(abs((after - remaining).total_seconds()), 60)

	def test_fifteen_referrals_grant_a_month(self) -> None:
		make_invitees(self.inviter, 15)

		result = claim_reward_sync(telegram_id=111, milestone=15)

		self.assertEqual(result.status, CLAIMED)
		self.assertEqual(result.days, 30)
		subscription = Subscription.objects.get(user=self.inviter.auth_user)
		remaining = subscription.expires_at - timezone.now()
		self.assertGreater(remaining, timedelta(days=29))

	def test_invalid_milestone_and_unknown_user(self) -> None:
		self.assertEqual(claim_reward_sync(telegram_id=111, milestone=7).status, INVALID)
		self.assertEqual(
			claim_reward_sync(telegram_id=555, milestone=10).status, NO_ACCOUNT
		)


class ReferralBotFlowTests(DispatcherTestCase):
	def setUp(self) -> None:
		super().setUp()
		self.inviter = make_profile(999, "inviter")

	def me_profile(self) -> TelegramUser:
		"""The profile behind the test USER, created by /start or by hand."""
		return TelegramUser.objects.get(telegram_id=USER.id)

	def test_start_ref_attributes_the_invitee(self) -> None:
		invitee_tg = TgUser(id=333, is_bot=False, first_name="Invitee", username="invitee")

		self.feed(build_command("start", payload="ref_999", user=invitee_tg, update_id=40))

		self.assertIn("Do'stingiz orqali keldingiz", self.all_text())
		invitee = TelegramUser.objects.get(telegram_id=333)
		self.assertEqual(invitee.referred_by_id, self.inviter.pk)

	def test_start_ref_for_brand_new_user(self) -> None:
		self.feed(build_command("start", payload="ref_999", update_id=41))

		profile = TelegramUser.objects.get(telegram_id=USER.id)
		self.assertEqual(profile.referred_by_id, self.inviter.pk)
		self.assertIn("Do'stingiz orqali keldingiz", self.all_text())

	def test_menu_shows_link_and_counter(self) -> None:
		self.feed(build_command("start", user=USER, update_id=42))
		make_invitees(self.me_profile(), 3)

		self.feed(build_callback(cb.REF, user=USER, update_id=43))

		text = self.visible()
		self.assertIn("Do'stlarni taklif qilish", text)
		self.assertIn("ref_111", text)
		self.assertIn(">3<", text)

	def test_claim_button_appears_only_at_the_milestone(self) -> None:
		self.feed(build_command("start", user=USER, update_id=44))
		self.feed(build_callback(cb.REF, user=USER, update_id=45))
		self.assertNotIn("🎁 15 kun olish", self.button_texts())

		make_invitees(self.me_profile(), 10)
		self.feed(build_callback(cb.REF, user=USER, update_id=46))
		self.assertIn("🎁 15 kun olish", self.button_texts())

	def test_claiming_from_the_menu_grants_the_reward(self) -> None:
		self.feed(build_command("start", user=USER, update_id=47))
		make_invitees(self.me_profile(), 10)
		self.session.reset()

		self.feed(build_callback(f"{cb.REF_CLAIM}:10", user=USER, update_id=48))

		self.assertIn("Mukofot olindi", self.visible())
		subscription = Subscription.objects.get(user=self.me_profile().auth_user)
		self.assertTrue(subscription.is_active)
		self.assertEqual(
			ReferralReward.objects.filter(user=self.me_profile().auth_user).count(), 1
		)

	def test_claiming_without_enough_invites_alerts(self) -> None:
		self.feed(build_command("start", user=USER, update_id=49))
		self.session.reset()

		self.feed(build_callback(f"{cb.REF_CLAIM}:10", user=USER, update_id=50))

		alerts = " ".join(
			str(getattr(method, "text", "") or "")
			for method in self.session.methods("AnswerCallbackQuery")
		)
		self.assertIn("Hali erta", alerts)
		self.assertEqual(ReferralReward.objects.count(), 0)
