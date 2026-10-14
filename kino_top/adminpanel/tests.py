"""Admin panel (REST) tests for coupons.

The web panel mirrors what the Telegram admin panel can do, so these tests drive
the real endpoints through :class:`APIClient`: create, list with filters, update,
toggle, publish and delete — plus the authorisation boundary between an ordinary
account and a staff account.

``TransactionTestCase`` (not ``TestCase``) because publishing bridges into the
async ORM: ``async_to_sync`` runs the coroutine's database calls in a worker
thread, which can only see committed rows.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings
from movies.models import TelegramChannel
from rest_framework.test import APIClient

from bot.models import BotSettings
from bot.tests.fakes import BOT_TOKEN, FakeSession, make_bot
from users.models import Coupon, CouponRedemption

BASE = "/api/admin/coupons/"


class AdminCouponApiTestCase(TransactionTestCase):
	"""Shared fixtures: one staff client (the panel) and one plain account."""

	def setUp(self) -> None:
		super().setUp()
		self.staff = get_user_model().objects.create_user(
			username="panel-admin",
			email="panel@example.com",
			password="panel-secret-4829",
			is_staff=True,
		)
		self.client = APIClient()
		self.client.force_authenticate(self.staff)

	def create_coupon(self, **payload):
		body = {"days": 7, "max_uses": 3, "code": "SUMMER24", **payload}
		return self.client.post(BASE, body, format="json")


class CouponCrudTests(AdminCouponApiTestCase):
	def test_create_list_update_and_delete_round_trip(self) -> None:
		created = self.create_coupon()
		self.assertEqual(created.status_code, 201)
		self.assertEqual(created.data["code"], "SUMMER24")
		self.assertEqual(created.data["days"], 7)
		self.assertEqual(created.data["max_uses"], 3)
		self.assertEqual(created.data["used_count"], 0)
		self.assertEqual(created.data["remaining"], 3)
		self.assertEqual(created.data["status"], "active")
		self.assertEqual(created.data["status_label"], "Faol")
		self.assertEqual(created.data["created_by"], "panel-admin")
		coupon_id = created.data["id"]
		self.assertEqual(Coupon.objects.get(pk=coupon_id).created_by, self.staff)

		listed = self.client.get(BASE)
		self.assertEqual(listed.status_code, 200)
		self.assertEqual(listed.data["count"], 1)
		self.assertEqual(listed.data["results"][0]["code"], "SUMMER24")

		updated = self.client.patch(
			f"{BASE}{coupon_id}/",
			{"days": 30, "max_uses": 50, "code": "winter24"},
			format="json",
		)
		self.assertEqual(updated.status_code, 200)
		self.assertEqual(updated.data["days"], 30)
		self.assertEqual(updated.data["max_uses"], 50)
		# Codes are stored normalised so a user can type them in any case.
		self.assertEqual(updated.data["code"], "WINTER24")

		deleted = self.client.delete(f"{BASE}{coupon_id}/")
		self.assertEqual(deleted.status_code, 204)
		self.assertFalse(Coupon.objects.filter(pk=coupon_id).exists())

	def test_blank_code_is_generated_server_side(self) -> None:
		response = self.create_coupon(code="")

		self.assertEqual(response.status_code, 201)
		self.assertTrue(response.data["code"])
		self.assertGreaterEqual(len(response.data["code"]), 4)

	def test_editing_with_a_blank_code_keeps_the_existing_one(self) -> None:
		coupon_id = self.create_coupon(code="KEEPME").data["id"]

		response = self.client.patch(f"{BASE}{coupon_id}/", {"code": "", "days": 9}, format="json")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["code"], "KEEPME")
		self.assertEqual(response.data["days"], 9)

	def test_duplicate_and_invalid_codes_are_rejected(self) -> None:
		self.create_coupon(code="SUMMER24")

		duplicate = self.create_coupon(code="summer24")
		self.assertEqual(duplicate.status_code, 400)
		self.assertIn("code", duplicate.data)

		invalid = self.create_coupon(code="1234")
		self.assertEqual(invalid.status_code, 400)
		self.assertIn("code", invalid.data)

		too_short = self.create_coupon(days=0)
		self.assertEqual(too_short.status_code, 400)
		self.assertIn("days", too_short.data)
		self.assertEqual(Coupon.objects.count(), 1)

	def test_exhausted_coupon_reads_as_expired_but_stays_listed(self) -> None:
		coupon_id = self.create_coupon(max_uses=1).data["id"]
		Coupon.objects.filter(pk=coupon_id).update(used_count=1)

		detail = self.client.get(f"{BASE}{coupon_id}/")

		self.assertEqual(detail.data["remaining"], 0)
		self.assertEqual(detail.data["status"], "exhausted")
		self.assertEqual(detail.data["status_label"], "Tugagan")

	def test_search_and_status_filters(self) -> None:
		active_id = self.create_coupon(code="ACTIVE1").data["id"]
		stopped_id = self.create_coupon(code="STOPPED1").data["id"]
		exhausted_id = self.create_coupon(code="DONE1", max_uses=1).data["id"]
		Coupon.objects.filter(pk=stopped_id).update(is_active=False)
		Coupon.objects.filter(pk=exhausted_id).update(used_count=1)

		active = self.client.get(BASE, {"status": "active"})
		self.assertEqual([row["id"] for row in active.data["results"]], [active_id])

		stopped = self.client.get(BASE, {"status": "stopped"})
		self.assertEqual([row["id"] for row in stopped.data["results"]], [stopped_id])

		exhausted = self.client.get(BASE, {"status": "exhausted"})
		self.assertEqual([row["id"] for row in exhausted.data["results"]], [exhausted_id])

		searched = self.client.get(BASE, {"search": "done"})
		self.assertEqual([row["id"] for row in searched.data["results"]], [exhausted_id])

	def test_toggle_stops_and_restarts_a_coupon(self) -> None:
		coupon_id = self.create_coupon().data["id"]

		stopped = self.client.post(f"{BASE}{coupon_id}/toggle/")
		self.assertEqual(stopped.status_code, 200)
		self.assertFalse(stopped.data["is_active"])
		self.assertEqual(stopped.data["status"], "stopped")
		self.assertEqual(stopped.data["status_label"], "To'xtatilgan")

		restarted = self.client.post(f"{BASE}{coupon_id}/toggle/")
		self.assertTrue(restarted.data["is_active"])
		self.assertEqual(restarted.data["status"], "active")

	def test_missing_coupon_returns_404(self) -> None:
		self.assertEqual(self.client.get(f"{BASE}999999/").status_code, 404)
		self.assertEqual(self.client.delete(f"{BASE}999999/").status_code, 404)

	def test_redemptions_endpoint_lists_who_used_the_code(self) -> None:
		coupon_id = self.create_coupon(code="USEDONE").data["id"]
		redeemer = get_user_model().objects.create_user(username="redeemer", password="x-4829")
		CouponRedemption.objects.create(
			coupon=Coupon.objects.get(pk=coupon_id),
			user=redeemer,
			telegram_id=777001,
			days=7,
		)

		response = self.client.get(f"{BASE}{coupon_id}/redemptions/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.data), 1)
		self.assertEqual(response.data[0]["username"], "redeemer")
		self.assertEqual(response.data[0]["telegram_id"], 777001)
		self.assertEqual(response.data[0]["days"], 7)

		detail = self.client.get(f"{BASE}{coupon_id}/")
		self.assertEqual(detail.data["used_count"], 0)
		self.assertEqual(detail.data["redemptions_count"], 1)


class CouponApiPermissionTests(AdminCouponApiTestCase):
	def test_anonymous_visitors_cannot_touch_coupons(self) -> None:
		anonymous = APIClient()

		self.assertIn(anonymous.get(BASE).status_code, {401, 403})
		self.assertIn(anonymous.post(BASE, {"days": 7, "max_uses": 1}, format="json").status_code, {401, 403})
		self.assertEqual(Coupon.objects.count(), 0)

	def test_a_logged_in_non_staff_account_is_forbidden(self) -> None:
		user = get_user_model().objects.create_user(username="viewer", password="viewer-4829")
		client = APIClient()
		client.force_authenticate(user)

		self.assertEqual(client.get(BASE).status_code, 403)
		self.assertEqual(
			client.post(BASE, {"days": 7, "max_uses": 1}, format="json").status_code,
			403,
		)
		self.assertEqual(Coupon.objects.count(), 0)


@override_settings(BOT_TOKEN=BOT_TOKEN, TELEGRAM_BOT_TOKEN=BOT_TOKEN)
class CouponPublishTests(AdminCouponApiTestCase):
	def channel(self) -> TelegramChannel:
		channel = TelegramChannel.objects.create(
			chat_id=-1007770000042,
			title="E'lonlar",
			username="elonlar",
			purpose=TelegramChannel.Purpose.PUBLIC,
			is_public=True,
		)
		settings = BotSettings.get_solo()
		settings.publish_channel = channel
		settings.save()
		return channel

	def test_publish_without_a_channel_explains_the_fix(self) -> None:
		coupon_id = self.create_coupon(code="NOCHAN").data["id"]

		response = self.client.post(f"{BASE}{coupon_id}/publish/")

		self.assertEqual(response.status_code, 400)
		self.assertIn("Kanal", response.data["detail"])
		self.assertIsNone(Coupon.objects.get(pk=coupon_id).posted_message_id)

	def test_publish_without_a_token_reports_it(self) -> None:
		self.channel()
		coupon_id = self.create_coupon(code="NOTOKEN").data["id"]

		with override_settings(BOT_TOKEN="", TELEGRAM_BOT_TOKEN=""):
			response = self.client.post(f"{BASE}{coupon_id}/publish/")

		self.assertEqual(response.status_code, 400)
		self.assertIn("BOT_TOKEN", response.data["detail"])

	def test_publish_posts_to_the_selected_channel_and_remembers_the_message(self) -> None:
		channel = self.channel()
		coupon_id = self.create_coupon(code="PUBLISH1", days=14).data["id"]
		session = FakeSession()

		with mock.patch("aiogram.Bot", lambda token, **kwargs: make_bot(session)):
			response = self.client.post(f"{BASE}{coupon_id}/publish/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["detail"], "Kupon kanalga joylandi.")
		self.assertEqual(response.data["coupon"]["posted_channel"], channel.pk)
		self.assertEqual(response.data["coupon"]["posted_channel_title"], "E'lonlar")

		sent = session.methods("SendMessage")
		self.assertEqual(len(sent), 1)
		self.assertEqual(sent[0].chat_id, channel.chat_id)
		self.assertIn("PUBLISH1", sent[0].text)
		self.assertIn("14", sent[0].text)

		coupon = Coupon.objects.get(pk=coupon_id)
		self.assertEqual(coupon.posted_channel_id, channel.pk)
		self.assertIsNotNone(coupon.posted_message_id)
		self.assertEqual(coupon.posted_message_id, response.data["message_id"])

	def test_publish_survives_a_telegram_failure(self) -> None:
		self.channel()
		coupon_id = self.create_coupon(code="BROKEN1").data["id"]

		with mock.patch("aiogram.Bot", side_effect=RuntimeError("telegram down")):
			# ``assertLogs`` keeps the deliberate traceback out of the test output.
			with self.assertLogs("adminpanel.coupon_publisher", level="ERROR"):
				response = self.client.post(f"{BASE}{coupon_id}/publish/")

		self.assertEqual(response.status_code, 400)
		self.assertIn("xatolik", response.data["detail"])
		self.assertIsNone(Coupon.objects.get(pk=coupon_id).posted_message_id)
