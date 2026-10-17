"""Coupon (promo code) tests: service rules and the bot conversations.

The service tests pin the first-come-first-served contract (the limit, the
one-per-user rule and the "expired once oversubscribed" state). The bot tests
drive the real Dispatcher for both sides: a user redeeming a code and an
administrator building, publishing and deleting one.
"""

from __future__ import annotations

from datetime import timedelta

from aiogram.types import User as TgUser
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from movies.models import TelegramChannel
from users.coupons import (
	ALREADY,
	EXPIRED,
	NOT_FOUND,
	REDEEMED,
	CouponCodeInvalid,
	CouponCodeTaken,
	create_coupon_sync,
	is_valid_code,
	redeem_coupon_sync,
)
from users.models import Coupon, CouponRedemption, Subscription, TelegramUser

from .. import callbacks as cb
from ..keyboards import admin as admin_kb
from ..models import BotSettings
from ..texts import (
	ADMIN_COUPON_NOT_PUBLISHED,
	COUPON_ALREADY,
	COUPON_EXPIRED,
	COUPON_NOT_FOUND,
	COUPON_REDEEMED,
)
from .base import DispatcherTestCase
from .fakes import ADMIN, BOT_TOKEN, USER, build_callback, build_command, build_message
from .helpers import bot_env, make_channel

SECOND = TgUser(id=222, is_bot=False, first_name="Second", username="second")


def make_profile(telegram_id: int, username: str) -> TelegramUser:
	"""A minimal registered profile with the auto-created subscription row."""
	auth_user = get_user_model().objects.create_user(username=username, password="x")
	Subscription.objects.get_or_create(user=auth_user)
	return TelegramUser.objects.create(
		telegram_id=telegram_id, username=username, auth_user=auth_user
	)


class CouponServiceTests(TestCase):
	def setUp(self) -> None:
		self.first = make_profile(111, "first")
		self.second = make_profile(222, "second")

	def test_redeeming_grants_a_coupon_subscription(self) -> None:
		coupon = create_coupon_sync(days=7, max_uses=2, code="anichopar")

		result = redeem_coupon_sync("ANICHOPAR", telegram_id=111)

		self.assertEqual(result.status, REDEEMED)
		self.assertEqual(result.days, 7)
		coupon.refresh_from_db()
		self.assertEqual(coupon.used_count, 1)
		subscription = Subscription.objects.get(user=self.first.auth_user)
		self.assertEqual(subscription.plan, Subscription.Plan.COUPON)
		self.assertTrue(subscription.is_active)
		remaining = subscription.expires_at - timezone.now()
		self.assertGreater(remaining, timedelta(days=6))

	def test_the_limit_is_first_come_first_served(self) -> None:
		coupon = create_coupon_sync(days=3, max_uses=1, code="ONLYONE")

		self.assertEqual(redeem_coupon_sync("ONLYONE", telegram_id=111).status, REDEEMED)
		self.assertEqual(redeem_coupon_sync("ONLYONE", telegram_id=222).status, EXPIRED)

		coupon.refresh_from_db()
		self.assertEqual(coupon.used_count, 1)
		self.assertTrue(coupon.is_exhausted)
		self.assertTrue(coupon.is_expired)
		self.assertEqual(coupon.status_label, "Tugagan")
		self.assertEqual(CouponRedemption.objects.filter(coupon=coupon).count(), 1)

	def test_a_user_cannot_redeem_the_same_coupon_twice(self) -> None:
		coupon = create_coupon_sync(days=5, max_uses=5, code="ONCE5")

		self.assertEqual(redeem_coupon_sync("once5", telegram_id=111).status, REDEEMED)
		self.assertEqual(redeem_coupon_sync("ONCE5", telegram_id=111).status, ALREADY)

		coupon.refresh_from_db()
		self.assertEqual(coupon.used_count, 1)

	def test_a_disabled_coupon_reads_as_expired(self) -> None:
		coupon = create_coupon_sync(days=5, max_uses=5, code="PAUSED")
		coupon.is_active = False
		coupon.save(update_fields=["is_active"])

		self.assertEqual(redeem_coupon_sync("PAUSED", telegram_id=111).status, EXPIRED)
		self.assertEqual(coupon.status_label, "To'xtatilgan")

	def test_a_coupon_extends_a_running_plan_and_keeps_its_label(self) -> None:
		subscription = Subscription.objects.get(user=self.first.auth_user)
		subscription.activate("monthly")
		before = subscription.expires_at

		create_coupon_sync(days=7, max_uses=1, code="EXTEND7")
		self.assertEqual(redeem_coupon_sync("EXTEND7", telegram_id=111).status, REDEEMED)

		subscription.refresh_from_db()
		self.assertEqual(subscription.plan, Subscription.Plan.MONTHLY)
		self.assertAlmostEqual(
			(subscription.expires_at - before).total_seconds(), 7 * 86400, delta=60
		)

	def test_unknown_codes_and_bad_input(self) -> None:
		self.assertEqual(redeem_coupon_sync("NOPE1234", telegram_id=111).status, NOT_FOUND)
		# Codes made only of digits would collide with the 4-digit title codes.
		self.assertFalse(is_valid_code("1234"))
		self.assertFalse(is_valid_code("ab"))
		self.assertTrue(is_valid_code("ANICHOPAR"))

		with self.assertRaises(CouponCodeInvalid):
			create_coupon_sync(days=7, max_uses=1, code="1234")

		create_coupon_sync(days=7, max_uses=1, code="TAKEN")
		with self.assertRaises(CouponCodeTaken):
			create_coupon_sync(days=7, max_uses=1, code="taken")

	def test_an_empty_code_is_generated(self) -> None:
		coupon = create_coupon_sync(days=1, max_uses=1, code="")
		self.assertTrue(is_valid_code(coupon.code))
		self.assertEqual(len(coupon.code), 8)


class UserCouponFlowTests(DispatcherTestCase):
	def setUp(self) -> None:
		super().setUp()
		self.feed(build_command("start", user=USER))

	def test_tapping_the_button_prompts_for_a_code(self) -> None:
		self.feed(build_callback(cb.COUPON, user=USER))

		self.assertIn("Kupon kodini yuboring", self.visible())

	def test_a_valid_code_extends_the_subscription(self) -> None:
		create_coupon_sync(days=10, max_uses=3, code="SOVGA10")

		self.feed(build_callback(cb.COUPON, user=USER, update_id=20))
		self.feed(build_message("sovga10", user=USER, update_id=21))

		text = self.visible()
		self.assertIn("Kupon qabul qilindi", text)
		self.assertIn("10 kunlik", text)
		profile = TelegramUser.objects.get(telegram_id=USER.id)
		subscription = Subscription.objects.get(user=profile.auth_user)
		self.assertTrue(subscription.is_active)
		self.assertEqual(subscription.plan, Subscription.Plan.COUPON)

	def test_an_exhausted_coupon_reports_expiry(self) -> None:
		make_profile(SECOND.id, "second")
		coupon = create_coupon_sync(days=2, max_uses=1, code="LASTONE")
		self.assertEqual(
			redeem_coupon_sync("LASTONE", telegram_id=SECOND.id).status, REDEEMED
		)
		coupon.refresh_from_db()
		self.assertTrue(coupon.is_expired)

		self.feed(build_callback(cb.COUPON, user=USER, update_id=22))
		self.feed(build_message("LASTONE", user=USER, update_id=23))

		self.assertIn(COUPON_EXPIRED, self.visible())

	def test_an_unknown_code_is_reported(self) -> None:
		self.feed(build_callback(cb.COUPON, user=USER, update_id=24))
		self.feed(build_message("YOQKOD", user=USER, update_id=25))

		self.assertIn(COUPON_NOT_FOUND, self.visible())

	def test_a_second_attempt_by_the_same_user_is_flagged(self) -> None:
		create_coupon_sync(days=2, max_uses=5, code="TWICE5")
		redeem_coupon_sync("TWICE5", telegram_id=USER.id)

		self.feed(build_callback(cb.COUPON, user=USER, update_id=26))
		self.feed(build_message("TWICE5", user=USER, update_id=27))

		self.assertIn(COUPON_ALREADY, self.visible())


class AdminCouponFlowTests(DispatcherTestCase):
	def setUp(self) -> None:
		super().setUp()
		env = bot_env(ADMIN_IDS=str(ADMIN.id), BOT_TOKEN=BOT_TOKEN)
		env.__enter__()
		self.addCleanup(env.__exit__, None, None, None)
		BotSettings.get_solo()
		self.update_id = 700

	def click(self, data: str) -> None:
		self.update_id += 1
		self.feed(build_callback(data, user=ADMIN, update_id=self.update_id))

	def send(self, text: str) -> None:
		self.update_id += 1
		self.feed(build_message(text, user=ADMIN, update_id=self.update_id))

	def build_coupon(self, *, days: int = 7, uses: int = 3, code: str = "SUMMER24") -> Coupon:
		self.click(f"{cb.ADM_COUPONS}:new")
		self.send(str(days))
		self.send(str(uses))
		self.send(code)
		return Coupon.objects.get(code=code)

	def test_the_panel_links_the_coupon_section(self) -> None:
		self.feed(build_command("admin", user=ADMIN))
		self.assertIn("Kuponlar", self.visible())

	def test_the_builder_creates_a_coupon(self) -> None:
		coupon = self.build_coupon(days=7, uses=3, code="SUMMER24")

		self.assertEqual(coupon.days, 7)
		self.assertEqual(coupon.max_uses, 3)
		self.assertEqual(coupon.used_count, 0)
		self.assertEqual(coupon.status_label, "Faol")
		self.assertEqual(coupon.created_by, TelegramUser.objects.get(telegram_id=ADMIN.id).auth_user)
		self.assertIn("SUMMER24", self.visible())

	def test_auto_publish_posts_the_new_coupon(self) -> None:
		channel = make_channel(
			chat_id=-1007770000014,
			title="E'lonlar",
			purpose=TelegramChannel.Purpose.PUBLIC,
		)
		settings = BotSettings.get_solo()
		settings.publish_channel = channel
		settings.auto_publish_new_content = True
		settings.save()

		coupon = self.build_coupon(code="AUTOPUB2")

		sent = [
			method
			for method in self.session.methods("SendMessage")
			if getattr(method, "chat_id", None) == channel.chat_id
		]
		self.assertEqual(len(sent), 1)
		self.assertIn("AUTOPUB2", sent[0].text)
		coupon.refresh_from_db()
		self.assertIsNotNone(coupon.posted_message_id)

	def test_a_taken_code_is_refused(self) -> None:
		self.build_coupon(code="SUMMER24")
		self.click(f"{cb.ADM_COUPONS}:new")
		self.send("7")
		self.send("3")
		self.send("SUMMER24")

		self.assertIn("band", self.visible())
		self.assertEqual(Coupon.objects.filter(code="SUMMER24").count(), 1)

	def test_an_invalid_code_is_refused(self) -> None:
		self.click(f"{cb.ADM_COUPONS}:new")
		self.send("7")
		self.send("3")
		self.send("1234")

		self.assertEqual(Coupon.objects.count(), 0)
		self.assertIn("Noto'g'ri", self.visible())

	def test_the_list_and_card_render(self) -> None:
		coupon = self.build_coupon(code="LISTME")

		self.click(f"{cb.ADM_COUPONS}:list:1")
		self.assertIn("LISTME", self.visible())

		self.click(f"{cb.ADM_COUPONS}:view:{coupon.pk}")
		self.assertIn("Kod", self.visible())

	def test_publishing_without_a_channel_warns(self) -> None:
		coupon = self.build_coupon(code="NOCHAN")

		self.click(f"{cb.ADM_COUPONS}:pub:{coupon.pk}")

		alerts = " ".join(
			str(method.text or "") for method in self.session.methods("AnswerCallbackQuery")
		)
		self.assertIn(ADMIN_COUPON_NOT_PUBLISHED, alerts)
		coupon.refresh_from_db()
		self.assertIsNone(coupon.posted_message_id)

	def test_publishing_posts_to_the_selected_channel(self) -> None:
		channel = make_channel(
			chat_id=-1007770000009, title="E'lonlar", purpose=TelegramChannel.Purpose.PUBLIC
		)
		settings = BotSettings.get_solo()
		settings.publish_channel = channel
		settings.save()
		coupon = self.build_coupon(code="PUBLISH1")

		self.session.reset()
		self.click(f"{cb.ADM_COUPONS}:pub:{coupon.pk}")

		sent = self.session.methods("SendMessage")
		self.assertTrue(sent)
		self.assertTrue(any(getattr(m, "chat_id", None) == channel.chat_id for m in sent))
		coupon.refresh_from_db()
		self.assertIsNotNone(coupon.posted_message_id)

	def test_disabling_then_deleting_a_coupon(self) -> None:
		coupon = self.build_coupon(code="REMOVE1")

		self.click(f"{cb.ADM_COUPONS}:tog:{coupon.pk}")
		coupon.refresh_from_db()
		self.assertFalse(coupon.is_active)

		self.click(f"{cb.ADM_COUPONS}:del:{coupon.pk}")
		self.assertIn("tasdiqlayman", self.visible().lower())
		self.assertTrue(Coupon.objects.filter(pk=coupon.pk).exists())

		self.click(f"{cb.ADM_COUPONS}:yes:{coupon.pk}:1")
		self.assertFalse(Coupon.objects.filter(pk=coupon.pk).exists())

	def test_every_coupon_button_answers(self) -> None:
		coupon = self.build_coupon(code="HARVEST1")
		self.click(f"{cb.ADM_COUPONS}:list:1")

		payloads: list[str] = []
		for markup in (
			admin_kb.coupons_menu(),
			admin_kb.coupons_list([coupon], 1, 1),
			admin_kb.coupon_actions(coupon),
			admin_kb.coupon_confirm_delete(coupon),
			admin_kb.admin_panel(),
		):
			for row in markup.inline_keyboard:
				for button in row:
					if button.callback_data and button.callback_data != cb.NOOP:
						payloads.append(button.callback_data)

		for data in payloads:
			with self.subTest(data=data):
				self.session.reset()
				self.click(data)
				names = {type(method).__name__ for method in self.session.calls}
				self.assertTrue(names, f"pressing {data!r} produced no Telegram call")
