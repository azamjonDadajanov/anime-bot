"""Paid subscription flow tests driven through the real Dispatcher.

Covers the whole loop: the user opens the plan catalogue, picks a plan, sends the
payment screenshot, an administrator approves or rejects the request, and the
user is told the outcome.
"""

from __future__ import annotations

from unittest import mock

from django.test import override_settings

from aiogram.types import PhotoSize

from movies.models import MediaTitle
from users.models import Subscription, SubscriptionRequest, TelegramUser

from .. import callbacks as cb
from ..models import FSMState
from ..texts import (
	ADMIN_ONLY,
	SUBREQ_APPROVED,
	SUBREQ_AWAITING_SCREENSHOT,
	SUBREQ_NOT_FOUND,
	SUBREQ_PENDING_NOTICE,
	SUBREQ_SAVED,
)
from .base import DispatcherTestCase
from .fakes import ADMIN, BOT_TOKEN, USER, build_callback, build_command, build_message
from .helpers import bot_env, make_title

CARD = "8600 0000 0000 0000"


def current_state(user_id: int, *, bot_id: int = 999) -> str | None:
	"""Persisted FSM state of a private chat, e.g. ``UserSubscriptionStates:...``."""
	from aiogram.fsm.storage.base import StorageKey

	from ..storage import DjangoStorage

	key = StorageKey(bot_id=bot_id, chat_id=user_id, user_id=user_id)
	row = FSMState.objects.filter(key=DjangoStorage().build_key(key)).first()
	if row is None:
		return None
	return row.state or None


def photo_message(*, file_id: str = "pay-screenshot", update_id: int = 10):
	"""A private photo message, i.e. the payment screenshot the FSM awaits."""
	return build_message(
		"",
		user=USER,
		update_id=update_id,
		photo=[
			PhotoSize(
				file_id=file_id,
				file_unique_id=f"{file_id}-unique",
				width=10,
				height=10,
			)
		],
	)


class SubscriptionPageTests(DispatcherTestCase):
	"""The catalogue: plan cards, prices, live counters and the card number."""

	def setUp(self) -> None:
		super().setUp()
		self.feed(build_command("start"))
		self.profile = TelegramUser.objects.get(telegram_id=USER.id)
		self.update_id = 100

	def _press(self, data: str) -> None:
		self.update_id += 1
		self.feed(build_callback(data, update_id=self.update_id))

	def test_profile_and_main_menu_offer_the_subscription_page(self) -> None:
		self.session.reset()
		self.feed(build_callback(cb.PROFILE, update_id=200))
		self.assertIn("🎫 Obuna", self.button_texts())

		self.session.reset()
		self.feed(build_callback(cb.MENU, update_id=201))
		self.assertIn("🎫 Obuna", self.button_texts())

	def test_subscription_page_lists_every_plan_with_its_price(self) -> None:
		from users.plans import plan_price

		self._press(cb.SUBSCRIPTION)

		visible = self.visible()
		for label in ("Free", "Plus", "Pro"):
			self.assertIn(label, visible)
		self.assertEqual(visible.count("Bepul"), 1)
		for plan in ("plus", "pro"):
			price = plan_price(plan)
			if price:
				self.assertIn(f"{price:,} so'm", visible)
		self.assertIn("joriy", visible.lower())

	def test_counters_are_computed_from_the_database(self) -> None:
		for number in range(3):
			make_title(code=f"80{number}x", title=f"Free Anime {number}")
		make_title(
			code="8099",
			title="Locked Anime",
			required_plan=MediaTitle.AccessPlan.PRO,
		)

		self._press(cb.SUBSCRIPTION)

		visible = self.visible()
		# Three free anime are visible on every plan, the pro one only on Pro.
		self.assertIn("3 anime", visible)
		self.assertIn("4 anime", visible)

	def test_selecting_a_plan_shows_the_payment_guide_and_the_card_number(self) -> None:
		self._press(f"{cb.SUBSCRIPTION_BUY}:pro")

		text = self.all_text()
		self.assertIn("Obuna to'lovi", text)
		self.assertIn(CARD, text)
		self.assertIn("Screenshot", text)
		self.assertEqual(self._fsm_state(), "UserSubscriptionStates:awaiting_screenshot")

	def test_the_current_plan_cannot_be_bought_again(self) -> None:
		self._press(f"{cb.SUBSCRIPTION_BUY}:free")

		answers = self.session.methods("AnswerCallbackQuery")
		self.assertTrue(answers)
		self.assertEqual(answers[-1].text, "Bu tarif allaqachon sizniki.")
		self.assertIsNone(self._fsm_state())

	def test_a_text_message_while_waiting_for_the_screenshot_is_ignored(self) -> None:
		self._press(f"{cb.SUBSCRIPTION_BUY}:pro")
		self.session.reset()
		self.feed(build_message("kino top", update_id=300))

		self.assertIn(SUBREQ_AWAITING_SCREENSHOT, self.all_text())
		self.assertEqual(SubscriptionRequest.objects.count(), 0)

	def _fsm_state(self):
		return current_state(USER.id)


class SubscriptionRequestFlowTests(DispatcherTestCase):
	"""Screenshot in, administrator decision out."""

	def setUp(self) -> None:
		super().setUp()
		self.feed(build_command("start"))
		self.profile = TelegramUser.objects.get(telegram_id=USER.id)
		self.user = self.profile.auth_user
		self.update_id = 400

	def _press(self, data: str, *, user=USER) -> None:
		self.update_id += 1
		self.feed(build_callback(data, user=user, update_id=self.update_id))

	def test_screenshot_creates_a_pending_request(self) -> None:
		self._press(f"{cb.SUBSCRIPTION_BUY}:pro")
		self.session.reset()

		with mock.patch(
			"users.telegram_notify.notify_admins_new_request", return_value=True
		) as notify:
			self.feed(photo_message(update_id=self.update_id + 1))

		self.assertIn(SUBREQ_SAVED, self.all_text())
		self.assertEqual(notify.call_count, 1)
		request = SubscriptionRequest.objects.get()
		self.assertEqual(request.plan, "pro")
		self.assertEqual(request.status, SubscriptionRequest.Status.PENDING)
		self.assertEqual(request.notes, "telegram_photo:pay-screenshot")
		self.assertEqual(request.card_number, CARD)
		self.assertIsNotNone(request.amount)
		self.assertEqual(request.amount, 50000)
		self.assertIsNone(current_state(USER.id))

	def test_a_second_screenshot_is_refused_while_one_is_pending(self) -> None:
		self._press(f"{cb.SUBSCRIPTION_BUY}:pro")
		with mock.patch("users.telegram_notify.notify_admins_new_request", return_value=True):
			self.feed(photo_message(update_id=self.update_id + 1))

		self.session.reset()
		self._press(f"{cb.SUBSCRIPTION_BUY}:pro")
		answers = self.session.methods("AnswerCallbackQuery")
		self.assertEqual(answers[-1].text, SUBREQ_PENDING_NOTICE)
		self.assertEqual(SubscriptionRequest.objects.count(), 1)

	def test_a_non_picture_message_does_not_create_a_request(self) -> None:
		self._press(f"{cb.SUBSCRIPTION_BUY}:pro")
		self.session.reset()
		self.feed(build_message("shu yerga yuboraman", update_id=self.update_id + 1))

		self.assertIn(SUBREQ_AWAITING_SCREENSHOT, self.all_text())
		self.assertEqual(SubscriptionRequest.objects.count(), 0)

	def test_approval_activates_the_plan_and_tells_the_user(self) -> None:
		request = SubscriptionRequest.objects.create(
			user=self.user, plan="pro", amount=50000, card_number=CARD
		)

		with bot_env(ADMIN_IDS=str(ADMIN.id), BOT_TOKEN=BOT_TOKEN):
			self._press(f"{cb.ADM_SUBREQ_OK}:{request.pk}", user=ADMIN)

		request.refresh_from_db()
		self.assertEqual(request.status, SubscriptionRequest.Status.APPROVED)
		self.assertEqual(
			Subscription.objects.get(user=self.user).plan, "pro"
		)
		self.assertIn(SUBREQ_APPROVED.split("\n")[0].replace("</b>", ""), self.all_text())
		self.assertIn("Ariza tasdiqlandi.", self.all_text())
		self.assertEqual(SubscriptionRequest.objects.count(), 1)

	def test_rejection_keeps_the_plan_and_tells_the_user(self) -> None:
		request = SubscriptionRequest.objects.create(
			user=self.user, plan="pro", amount=50000, card_number=CARD
		)

		with bot_env(ADMIN_IDS=str(ADMIN.id), BOT_TOKEN=BOT_TOKEN):
			self._press(f"{cb.ADM_SUBREQ_NO}:{request.pk}", user=ADMIN)

		request.refresh_from_db()
		self.assertEqual(request.status, SubscriptionRequest.Status.REJECTED)
		self.assertEqual(Subscription.objects.get(user=self.user).plan, "free")
		self.assertIn("Obuna bekor qilindi", self.all_text())
		self.assertIn("Ariza rad etildi.", self.all_text())

	def test_approving_twice_is_refused_and_changes_nothing(self) -> None:
		request = SubscriptionRequest.objects.create(
			user=self.user, plan="plus", amount=30000, card_number=CARD
		)

		with bot_env(ADMIN_IDS=str(ADMIN.id), BOT_TOKEN=BOT_TOKEN):
			self._press(f"{cb.ADM_SUBREQ_OK}:{request.pk}", user=ADMIN)
			self.session.reset()
			self._press(f"{cb.ADM_SUBREQ_OK}:{request.pk}", user=ADMIN)

		answers = self.session.methods("AnswerCallbackQuery")
		self.assertEqual(answers[-1].text, "Bu ariza allaqachon ko'rib chiqilgan.")
		self.assertEqual(
			SubscriptionRequest.objects.filter(
				status=SubscriptionRequest.Status.APPROVED
			).count(),
			1,
		)

	def test_an_unknown_request_pk_is_reported_as_not_found(self) -> None:
		with bot_env(ADMIN_IDS=str(ADMIN.id), BOT_TOKEN=BOT_TOKEN):
			self._press(f"{cb.ADM_SUBREQ_OK}:999999", user=ADMIN)

		answers = self.session.methods("AnswerCallbackQuery")
		self.assertEqual(answers[-1].text, SUBREQ_NOT_FOUND[:200])

	def test_a_non_administrator_cannot_approve_a_request(self) -> None:
		request = SubscriptionRequest.objects.create(
			user=self.user, plan="pro", amount=50000, card_number=CARD
		)

		with bot_env(ADMIN_IDS=str(ADMIN.id), BOT_TOKEN=BOT_TOKEN):
			self._press(f"{cb.ADM_SUBREQ_OK}:{request.pk}", user=USER)

		answers = self.session.methods("AnswerCallbackQuery")
		self.assertEqual(answers[-1].text, ADMIN_ONLY)
		request.refresh_from_db()
		self.assertEqual(request.status, SubscriptionRequest.Status.PENDING)

	def test_admin_notifications_carry_the_screenshot_and_the_buttons(self) -> None:
		"""The notifier forwards the Telegram photo id and both decisions."""
		from users.telegram_notify import (
			API_BASE,
			OK_CALLBACK,
			REJECT_CALLBACK,
			notify_admins_new_request,
		)

		request = SubscriptionRequest.objects.create(
			user=self.user,
			plan="pro",
			amount=50000,
			card_number=CARD,
			notes="telegram_photo:secret-file-id",
		)

		captured = []

		class _Response:
			status_code = 200
			text = "ok"

		class _Client:
			def __init__(self, *args, **kwargs):
				pass

			def __enter__(self):
				return self

			def __exit__(self, *exc):
				return False

			def post(self, url, data=None, files=None):
				captured.append((url, data, files))
				return _Response()

		with mock.patch("users.telegram_notify.httpx.Client", _Client), override_settings(
			ADMIN_IDS=str(ADMIN.id), BOT_TOKEN=BOT_TOKEN
		):
			self.assertTrue(notify_admins_new_request(request))

		url, data, _ = captured[0]
		self.assertIn(f"{API_BASE}/bot{BOT_TOKEN}/sendPhoto", url)
		self.assertEqual(data["photo"], "secret-file-id")
		self.assertEqual(str(data["chat_id"]), str(ADMIN.id))
		self.assertIn("Yangi obuna arizasi", data["caption"])
		self.assertIn(str(request.pk), data["reply_markup"])
		self.assertIn(OK_CALLBACK, data["reply_markup"])
		self.assertIn(REJECT_CALLBACK, data["reply_markup"])
