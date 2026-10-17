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

from datetime import date
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.urls import Resolver404, resolve, reverse
from movies.models import MediaPart, MediaTitle, TelegramChannel
from rest_framework.test import APIClient

from bot.models import BotSettings
from bot.tests.fakes import BOT_TOKEN, FakeSession, make_bot
from games.models import AnimeVerification, GameActivity, MonthlyPrize, QuizAttempt, QuizQuestion
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


# ---------------------------------------------------------------------------
# Auto-publish on create (titles, episodes, coupons)
# ---------------------------------------------------------------------------

CATALOG_BASE = "/api/catalog/"
PARTS_BASE = "/api/parts/"


@override_settings(BOT_TOKEN=BOT_TOKEN, TELEGRAM_BOT_TOKEN=BOT_TOKEN)
class AutoPublishOnCreateTests(TransactionTestCase):
	"""A web save must announce to the public channel when the switch is on.

	The bot panel already publishes new titles and episodes; the web panel used
	to skip that step entirely, so content added from /admin never reached the
	channel. These tests pin the new behaviour.
	"""

	def setUp(self) -> None:
		super().setUp()
		self.staff = get_user_model().objects.create_user(
			username="auto-admin",
			email="auto@example.com",
			password="panel-secret-4829",
			is_staff=True,
		)
		self.client = APIClient()
		self.client.force_authenticate(self.staff)
		self.channel = TelegramChannel.objects.create(
			chat_id=-1007770000042,
			title="E'lonlar",
			username="elonlar",
			purpose=TelegramChannel.Purpose.PUBLIC,
			is_public=True,
		)
		settings = BotSettings.get_solo()
		settings.publish_channel = self.channel
		settings.auto_publish_new_content = True
		settings.save()

	def channel_posts(self, session) -> list:
		return [
			method
			for method in session.methods("SendMessage")
			if getattr(method, "chat_id", None) == self.channel.chat_id
		]

	def test_creating_a_title_publishes_it(self) -> None:
		session = FakeSession()

		with mock.patch("aiogram.Bot", lambda token, **kwargs: make_bot(session)):
			response = self.client.post(
				CATALOG_BASE,
				{"type": "anime", "title": "Yangi Anime", "slug": "yangi-anime"},
				format="json",
			)

		self.assertEqual(response.status_code, 201)
		posts = self.channel_posts(session)
		self.assertEqual(len(posts), 1)
		self.assertIn("Yangi Anime", posts[0].text)
		button = posts[0].reply_markup.inline_keyboard[0][0]
		self.assertIn("?start=anime_", button.url)

	def test_creating_a_part_publishes_an_episode_post(self) -> None:
		title = MediaTitle.objects.create(
			type=MediaTitle.MediaType.ANIME, title="Part Anime", slug="part-anime"
		)
		session = FakeSession()

		with mock.patch("aiogram.Bot", lambda token, **kwargs: make_bot(session)):
			response = self.client.post(
				PARTS_BASE, {"content": title.pk, "number": 1}, format="json"
			)

		self.assertEqual(response.status_code, 201)
		posts = self.channel_posts(session)
		self.assertEqual(len(posts), 1)
		self.assertIn("Part Anime", posts[0].text)
		self.assertIn("1-qism", posts[0].text)

	def test_creating_a_coupon_publishes_it(self) -> None:
		session = FakeSession()

		with mock.patch("aiogram.Bot", lambda token, **kwargs: make_bot(session)):
			response = self.client.post(
				BASE, {"days": 14, "max_uses": 5, "code": "AUTOPUB1"}, format="json"
			)

		self.assertEqual(response.status_code, 201)
		posts = self.channel_posts(session)
		self.assertEqual(len(posts), 1)
		self.assertIn("AUTOPUB1", posts[0].text)
		self.assertIsNotNone(response.data["posted_message_id"])

	def test_the_switch_off_posts_nothing(self) -> None:
		settings = BotSettings.get_solo()
		settings.auto_publish_new_content = False
		settings.save(update_fields=["auto_publish_new_content"])

		# A disabled switch must not even build a Bot (i.e. never touch Telegram).
		with mock.patch("aiogram.Bot", side_effect=AssertionError("a Bot must not be built")):
			response = self.client.post(
				CATALOG_BASE,
				{"type": "movie", "title": "Jim Film", "slug": "jim-film"},
				format="json",
			)

		self.assertEqual(response.status_code, 201)


# ---------------------------------------------------------------------------
# Games admin: quiz questions, leaderboard, attempts, verifications, prizes
# ---------------------------------------------------------------------------

QUIZ_BASE = "/api/admin/quiz-questions/"
ATTEMPT_BASE = "/api/admin/quiz-attempts/"
VERIFY_BASE = "/api/admin/verifications/"
PRIZE_BASE = "/api/admin/monthly-prizes/"
LEADERBOARD_URL = "/api/admin/game/leaderboard/"


class GameAdminTestCase(TransactionTestCase):
	"""Staff client + an ordinary account for the permission boundary."""

	def setUp(self) -> None:
		super().setUp()
		self.staff = get_user_model().objects.create_user(
			username="game-admin",
			email="game-admin@example.com",
			password="panel-secret-4829",
			is_staff=True,
		)
		self.client = APIClient()
		self.client.force_authenticate(self.staff)
		self.title = MediaTitle.objects.create(
			type=MediaTitle.MediaType.ANIME,
			title="Naruto",
			slug="naruto",
		)

	def make_question(self, **payload):
		body = {
			"title": self.title.pk,
			"text": "Qahramonning ismi nima?",
			"choices": ["A", "B", "C", "D"],
			"correct_index": 0,
			"is_active": True,
			**payload,
		}
		return self.client.post(QUIZ_BASE, body, format="json")


class QuizQuestionCrudTests(GameAdminTestCase):
	def test_create_list_update_delete_round_trip(self) -> None:
		created = self.make_question()
		self.assertEqual(created.status_code, 201)
		self.assertEqual(created.data["title_title"], "Naruto")
		self.assertEqual(created.data["choices"], ["A", "B", "C", "D"])
		question_id = created.data["id"]

		listed = self.client.get(QUIZ_BASE)
		self.assertEqual(listed.status_code, 200)
		self.assertEqual(listed.data["count"], 1)

		updated = self.client.patch(
			f"{QUIZ_BASE}{question_id}/",
			{"text": "Yangilangan savol?", "is_active": False},
			format="json",
		)
		self.assertEqual(updated.status_code, 200)
		self.assertEqual(updated.data["text"], "Yangilangan savol?")
		self.assertFalse(updated.data["is_active"])

		deleted = self.client.delete(f"{QUIZ_BASE}{question_id}/")
		self.assertEqual(deleted.status_code, 204)
		self.assertFalse(QuizQuestion.objects.filter(pk=question_id).exists())

	def test_choices_must_be_a_list_of_at_least_two(self) -> None:
		response = self.make_question(choices=["OnlyOne"])
		self.assertEqual(response.status_code, 400)
		self.assertIn("choices", response.data)

	def test_correct_index_out_of_range_is_rejected(self) -> None:
		response = self.make_question(correct_index=10)
		self.assertEqual(response.status_code, 400)
		self.assertIn("correct_index", response.data)

	def test_search_and_filters(self) -> None:
		one = self.make_question(text="Birinchi savol").data["id"]
		self.make_question(text="Ikkinchi savol", is_active=False)

		active = self.client.get(QUIZ_BASE, {"is_active": "1"})
		self.assertEqual([row["id"] for row in active.data["results"]], [one])

		searched = self.client.get(QUIZ_BASE, {"search": "Birinchi"})
		self.assertEqual([row["id"] for row in searched.data["results"]], [one])

		by_title = self.client.get(QUIZ_BASE, {"title": str(self.title.pk)})
		self.assertEqual(by_title.data["count"], 2)


class GameLeaderboardTests(GameAdminTestCase):
	def _player(self, username: str, points: int, verified: int = 0):
		user = get_user_model().objects.create_user(username=username, password="x")
		attempt = QuizAttempt.objects.create(
			user=user,
			title=self.title,
			question_ids=[1, 2],
			answers=[0, 1],
			finished_at="2026-01-01 10:00:00",
			points_awarded=points,
			passed=True,
		)
		for index in range(verified):
			other, _ = MediaTitle.objects.get_or_create(
				slug=f"{username}-verified-{index}",
				defaults={"type": MediaTitle.MediaType.ANIME, "title": f"V{index}"},
			)
			AnimeVerification.objects.create(user=user, title=other, points=points)
		return user, attempt

	def test_leaderboard_orders_by_points_and_reports_fields(self) -> None:
		self._player("low", 10, verified=1)
		self._player("high", 50, verified=2)

		response = self.client.get(LEADERBOARD_URL)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["count"], 2)
		results = response.data["results"]
		self.assertEqual(results[0]["name"], "high")
		self.assertEqual(results[0]["points"], 50)
		self.assertEqual(results[0]["verified"], 2)
		self.assertEqual(results[0]["rank"], 1)
		self.assertEqual(results[1]["name"], "low")
		self.assertEqual(results[1]["rank"], 2)

	def test_suspicious_attempts_are_excluded(self) -> None:
		user, attempt = self._player("cheater", 100)
		attempt.is_suspicious = True
		attempt.save(update_fields=["is_suspicious"])

		response = self.client.get(LEADERBOARD_URL)

		self.assertEqual(response.data["count"], 0)


class QuizAttemptAdminTests(GameAdminTestCase):
	def _attempt(self, username: str = "player", suspicious: bool = False):
		user = get_user_model().objects.create_user(username=username, password="x")
		return QuizAttempt.objects.create(
			user=user,
			title=self.title,
			question_ids=[],
			answers=[],
			finished_at="2026-01-01 10:00:00" if not suspicious else None,
			points_awarded=10,
			is_suspicious=suspicious,
		)

	def test_list_and_filters(self) -> None:
		self._attempt("clean")
		self._attempt("cheater", suspicious=True)

		all_rows = self.client.get(ATTEMPT_BASE)
		self.assertEqual(all_rows.data["count"], 2)

		suspicious = self.client.get(ATTEMPT_BASE, {"suspicious": "1"})
		self.assertEqual(suspicious.data["count"], 1)
		self.assertEqual(suspicious.data["results"][0]["username"], "cheater")

		searched = self.client.get(ATTEMPT_BASE, {"search": "clean"})
		self.assertEqual(searched.data["count"], 1)

	def test_patch_can_flag_suspicious(self) -> None:
		attempt = self._attempt("flagme")

		response = self.client.patch(
			f"{ATTEMPT_BASE}{attempt.pk}/",
			{"is_suspicious": True},
			format="json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.data["is_suspicious"])
		attempt.refresh_from_db()
		self.assertTrue(attempt.is_suspicious)

	def test_delete_removes_attempt(self) -> None:
		attempt = self._attempt("deleteme")

		response = self.client.delete(f"{ATTEMPT_BASE}{attempt.pk}/")

		self.assertEqual(response.status_code, 204)
		self.assertFalse(QuizAttempt.objects.filter(pk=attempt.pk).exists())


class VerificationAdminTests(GameAdminTestCase):
	def test_create_list_delete_round_trip(self) -> None:
		user = get_user_model().objects.create_user(username="verified-player", password="x")

		created = self.client.post(
			VERIFY_BASE,
			{"user": user.pk, "title": self.title.pk, "points": 8},
			format="json",
		)
		self.assertEqual(created.status_code, 201)
		self.assertEqual(created.data["username"], "verified-player")
		verification_id = created.data["id"]

		listed = self.client.get(VERIFY_BASE)
		self.assertEqual(listed.data["count"], 1)

		deleted = self.client.delete(f"{VERIFY_BASE}{verification_id}/")
		self.assertEqual(deleted.status_code, 204)
		self.assertFalse(AnimeVerification.objects.filter(pk=verification_id).exists())

	def test_duplicate_verification_is_rejected(self) -> None:
		user = get_user_model().objects.create_user(username="dupe", password="x")
		body = {"user": user.pk, "title": self.title.pk, "points": 5}
		self.client.post(VERIFY_BASE, body, format="json")

		duplicate = self.client.post(VERIFY_BASE, body, format="json")
		self.assertEqual(duplicate.status_code, 400)


class MonthlyPrizeAdminTests(GameAdminTestCase):
	def _active_player(self, username: str, points: int = 30):
		user = get_user_model().objects.create_user(username=username, password="x")
		QuizAttempt.objects.create(
			user=user,
			title=self.title,
			question_ids=[],
			answers=[],
			finished_at="2026-09-10 10:00:00",
			points_awarded=points,
			passed=True,
		)
		for day in range(1, 11):
			GameActivity.objects.get_or_create(user=user, date=date(2026, 9, day))
		return user

	def test_award_action_gives_prize_to_most_active(self) -> None:
		self._active_player("champion", points=30)

		response = self.client.post(f"{PRIZE_BASE}award/", {"year": 2026, "month": 9}, format="json")

		self.assertEqual(response.status_code, 201)
		self.assertEqual(response.data["year"], 2026)
		self.assertEqual(response.data["month"], 9)
		self.assertEqual(response.data["points"], 30)
		self.assertEqual(MonthlyPrize.objects.count(), 1)

		# Second award for the same month is refused.
		again = self.client.post(f"{PRIZE_BASE}award/", {"year": 2026, "month": 9}, format="json")
		self.assertEqual(again.status_code, 400)

	def test_award_with_no_candidates_is_refused(self) -> None:
		response = self.client.post(f"{PRIZE_BASE}award/", {"year": 2026, "month": 1}, format="json")
		self.assertEqual(response.status_code, 400)

	def test_create_and_delete_prize_manually(self) -> None:
		user = self._active_player("manual")

		created = self.client.post(
			PRIZE_BASE,
			{"year": 2026, "month": 8, "user": user.pk, "points": 20, "days": 30},
			format="json",
		)
		self.assertEqual(created.status_code, 201)
		prize_id = created.data["id"]

		listed = self.client.get(PRIZE_BASE, {"year": "2026"})
		self.assertEqual(listed.data["count"], 1)

		deleted = self.client.delete(f"{PRIZE_BASE}{prize_id}/")
		self.assertEqual(deleted.status_code, 204)


class GameAdminPermissionTests(GameAdminTestCase):
	def test_anonymous_is_rejected(self) -> None:
		anonymous = APIClient()
		for url in (QUIZ_BASE, ATTEMPT_BASE, VERIFY_BASE, PRIZE_BASE, LEADERBOARD_URL):
			self.assertIn(anonymous.get(url).status_code, {401, 403}, url)

	def test_non_staff_is_forbidden(self) -> None:
		user = get_user_model().objects.create_user(username="viewer", password="viewer-4829")
		client = APIClient()
		client.force_authenticate(user)
		for url in (QUIZ_BASE, ATTEMPT_BASE, VERIFY_BASE, PRIZE_BASE, LEADERBOARD_URL):
			self.assertEqual(client.get(url).status_code, 403, url)


# ---------------------------------------------------------------------------
# URL routing: the SPA owns /admin/*, Django's own admin lives at /django-admin/
# ---------------------------------------------------------------------------


class AdminPanelRoutingTests(SimpleTestCase):
	"""The React panel is a SPA served under /admin.

	nginx only hands a path to Django when the SPA does not own it. While
	Django's own admin still answered on /admin/, opening a panel URL directly —
	or simply refreshing one — returned Django's login page instead of the panel,
	so pages such as /admin/game-ratings and /admin/quiz were unreachable.
	"""

	PANEL_PATHS = (
		"/admin/",
		"/admin/login/",
		"/admin/game-ratings",
		"/admin/game-ratings/",
		"/admin/quiz",
		"/admin/media",
	)

	def test_django_admin_lives_under_its_own_prefix(self) -> None:
		self.assertEqual(reverse("admin:index"), "/django-admin/")

	def test_panel_paths_are_not_claimed_by_django(self) -> None:
		for path in self.PANEL_PATHS:
			with self.subTest(path=path):
				with self.assertRaises(Resolver404):
					resolve(path)

	def test_django_admin_still_serves_its_own_paths(self) -> None:
		self.assertEqual(resolve("/django-admin/login/").url_name, "login")

	def test_panel_api_still_resolves(self) -> None:
		for path in (LEADERBOARD_URL, QUIZ_BASE, ATTEMPT_BASE, PRIZE_BASE, VERIFY_BASE):
			with self.subTest(path=path):
				self.assertIsNotNone(resolve(path))

	def test_nginx_does_not_proxy_the_panel_prefix_to_django(self) -> None:
		"""Keep frontend/nginx.conf in sync with urls.py."""
		nginx_conf = settings.BASE_DIR.parent / "frontend" / "nginx.conf"
		if not nginx_conf.exists():  # pragma: no cover - backend-only checkout
			self.skipTest("frontend/nginx.conf is not present")

		directives = [
			line.strip()
			for line in nginx_conf.read_text(encoding="utf-8").splitlines()
			if not line.strip().startswith("#")
		]
		self.assertNotIn("location /admin/ {", directives)
		self.assertFalse(
			any(d.startswith("location /admin") for d in directives),
			"no nginx location may claim the /admin prefix",
		)
		self.assertIn("location /django-admin {", directives)
