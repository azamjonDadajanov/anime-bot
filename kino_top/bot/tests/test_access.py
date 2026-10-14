"""Access control tests: mandatory channel subscription and paid plans."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from django.test import TransactionTestCase
from django.utils import timezone
from movies.models import TelegramChannel
from users.models import Subscription
from users.telegram_auth import get_or_create_telegram_user

from ..models import BotSettings
from ..services.access import (
	AccessDenied,
	effective_plan,
	ensure_access,
	missing_channels,
	plan_of,
	plan_satisfies,
	subscription_ok,
)
from .fakes import FakeSession, make_bot
from .helpers import make_channel, make_title


def make_profile(
	telegram_id: int = 111,
	plan: str = "free",
	blocked: bool = False,
	expired: bool = False,
):
	profile = get_or_create_telegram_user(
		{"id": telegram_id, "first_name": "Test", "username": f"user{telegram_id}"}
	)
	subscription = profile.auth_user.subscription
	if subscription.plan != plan or not subscription.is_active or expired:
		subscription.activate(plan)
	if expired:
		Subscription.objects.filter(pk=subscription.pk).update(
			expires_at=timezone.now() - timedelta(seconds=1)
		)
		subscription.refresh_from_db()
	if blocked:
		profile.is_blocked = True
		profile.save(update_fields=["is_blocked", "updated_at"])
	return profile


class PlanMathTests(TransactionTestCase):
	def test_plan_ordering(self) -> None:
		self.assertTrue(plan_satisfies("monthly", "free"))
		self.assertTrue(plan_satisfies("yearly", "free"))
		self.assertTrue(plan_satisfies("daily", "paid"))
		self.assertTrue(plan_satisfies("yearly", "paid"))
		self.assertFalse(plan_satisfies("free", "paid"))

	def test_plan_of_a_profile_without_subscription_is_free(self) -> None:
		profile = make_profile(plan="yearly")
		self.assertEqual(plan_of(profile), "yearly")
		self.assertEqual(plan_of(None), "free")

	def test_an_expired_plan_reads_as_free(self) -> None:
		profile = make_profile(telegram_id=112, plan="yearly", expired=True)
		self.assertEqual(plan_of(profile), "yearly")
		self.assertEqual(effective_plan(profile), "free")
		self.assertEqual(effective_plan(None), "free")
		self.assertFalse(plan_satisfies(effective_plan(profile), "paid"))


class SubscriptionEnforcementTests(TransactionTestCase):
	def setUp(self) -> None:
		self.bot = make_bot(FakeSession(member_status="left"))
		self.channel = make_channel(
			chat_id=-100111222,
			title="Required",
			purpose=TelegramChannel.Purpose.REQUIRED,
		)

	def test_missing_channels_lists_unjoined_channels(self) -> None:
		profile = make_profile()
		missing = asyncio.run(missing_channels(self.bot, profile.telegram_id))
		self.assertEqual([channel.pk for channel in missing], [self.channel.pk])

	def test_no_missing_channels_when_the_user_joined(self) -> None:
		self.bot.session.member_status = "member"
		profile = make_profile(telegram_id=222)
		self.assertEqual(asyncio.run(missing_channels(self.bot, profile.telegram_id)), [])

	def test_ensure_access_raises_for_unjoined_users(self) -> None:
		profile = make_profile(telegram_id=333)
		with self.assertRaises(AccessDenied) as ctx:
			asyncio.run(ensure_access(self.bot, profile))
		self.assertTrue(ctx.exception.is_subscription)
		self.assertEqual(len(ctx.exception.channels), 1)

	def test_disabling_the_requirement_in_settings_skips_enforcement(self) -> None:
		settings = BotSettings.get_solo()
		settings.require_subscription = False
		settings.save(update_fields=["require_subscription", "updated_at"])

		profile = make_profile(telegram_id=444)
		asyncio.run(ensure_access(self.bot, profile))
		self.assertTrue(asyncio.run(subscription_ok(self.bot, profile)))

	def test_inactive_channels_are_not_enforced(self) -> None:
		TelegramChannel.objects.filter(pk=self.channel.pk).update(is_active=False)
		profile = make_profile(telegram_id=555)
		asyncio.run(ensure_access(self.bot, profile))

	def test_blocked_profile_is_always_denied(self) -> None:
		profile = make_profile(telegram_id=666, blocked=True)
		with self.assertRaises(AccessDenied) as ctx:
			asyncio.run(ensure_access(self.bot, profile))
		self.assertTrue(ctx.exception.is_blocked)

	def test_subscription_is_checked_before_premium(self) -> None:
		profile = make_profile(telegram_id=777)
		title = make_title(code="1200", required_plan="paid")

		with self.assertRaises(AccessDenied) as ctx:
			asyncio.run(ensure_access(self.bot, profile, title))

		# The subscription problem must be reported first so the user can fix it.
		self.assertTrue(ctx.exception.is_subscription)


class PremiumEnforcementTests(TransactionTestCase):
	def setUp(self) -> None:
		self.bot = make_bot(FakeSession(member_status="member"))

	def test_free_user_is_denied_paid_content(self) -> None:
		profile = make_profile(telegram_id=888, plan="free")
		title = make_title(code="1300", required_plan="paid")
		with self.assertRaises(AccessDenied) as ctx:
			asyncio.run(ensure_access(self.bot, profile, title))
		self.assertTrue(ctx.exception.is_premium)
		self.assertEqual(ctx.exception.required_plan, "paid")
		self.assertEqual(ctx.exception.current_plan, "free")

	def test_an_expired_subscription_is_denied_paid_content(self) -> None:
		profile = make_profile(telegram_id=889, plan="yearly", expired=True)
		title = make_title(code="1301", required_plan="paid")
		with self.assertRaises(AccessDenied) as ctx:
			asyncio.run(ensure_access(self.bot, profile, title))
		self.assertTrue(ctx.exception.is_premium)
		self.assertEqual(ctx.exception.current_plan, "free")

	def test_a_subscriber_can_watch_everything(self) -> None:
		profile = make_profile(telegram_id=890, plan="yearly")
		for code, plan in (("1302", "free"), ("1303", "paid")):
			title = make_title(code=code, required_plan=plan)
			asyncio.run(ensure_access(self.bot, profile, title))

	def test_free_user_can_watch_free_content(self) -> None:
		profile = make_profile(telegram_id=891, plan="free")
		title = make_title(code="1305", required_plan="free")
		asyncio.run(ensure_access(self.bot, profile, title))

	def test_a_daily_plan_is_enough_for_paid_content(self) -> None:
		profile = make_profile(telegram_id=892, plan="daily")
		title = make_title(code="1306", required_plan="paid")
		asyncio.run(ensure_access(self.bot, profile, title))
