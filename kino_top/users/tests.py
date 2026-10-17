import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest import mock
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from movies.models import MediaPart, MediaTitle, MediaView, ReadingProgress

from .models import (
	FavoriteContent,
	Subscription,
	SubscriptionRequest,
	SupportMessage,
	TelegramUser,
)
from .reminders import EXPIRED, EXPIRING, REMIND_AFTER_DAYS, reminder_stage
from .support import MAX_LENGTH as SUPPORT_MAX_LENGTH
from .telegram_auth import get_or_create_telegram_user


BOT_TOKEN = "123456:test-bot-token"


def sign_mini_app_data(user_data, auth_date=None):
	fields = {
		"auth_date": str(auth_date or int(time.time())),
		"user": json.dumps(user_data, separators=(",", ":")),
	}
	check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
	secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
	fields["hash"] = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
	return urlencode(fields)


def sign_widget_data(fields):
	check_string = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
	secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
	signed_fields = {
		**fields,
		"hash": hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest(),
	}
	return signed_fields


@override_settings(TELEGRAM_BOT_TOKEN=BOT_TOKEN)
class AuthenticationApiTests(TestCase):
	def setUp(self):
		self.client = APIClient()

	def test_website_registers_and_logs_in_with_username_and_password(self):
		registration = self.client.post(
			"/api/auth/register/",
			{
				"username": "webuser",
				"email": "webuser@example.com",
				"password": "a-secure-password-4829",
				"password_confirm": "a-secure-password-4829",
			},
			format="json",
		)
		self.assertEqual(registration.status_code, 201)

		login = self.client.post(
			"/api/auth/token/",
			{"username": "webuser", "password": "a-secure-password-4829"},
			format="json",
		)
		self.assertEqual(login.status_code, 200)
		self.assertIn("access", login.data)
		self.assertIn("refresh", login.data)

		self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
		self.assertEqual(self.client.get("/api/auth/me/").data["username"], "webuser")
		self.assertEqual(self.client.get("/api/auth/me/").data["subscription"]["plan"], "free")

	def test_mini_app_requires_valid_init_data_and_issues_user_token(self):
		init_data = sign_mini_app_data({
			"id": 987654321,
			"first_name": "Mini",
			"username": "mini_user",
			"language_code": "uz",
		})
		response = self.client.post(
			"/api/auth/telegram/mini-app/",
			{
				"init_data": init_data,
				"email": "mini@example.com",
				"password": "mini-secure-password-4829",
			},
			format="json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["user"]["telegram_id"], 987654321)
		self.assertEqual(AccessToken(response.data["access"])["telegram_id"], 987654321)
		profile = TelegramUser.objects.get(telegram_id=987654321)
		self.assertEqual(
			str(profile.auth_user_id),
			AccessToken(response.data["access"])["user_id"],
		)
		self.assertTrue(profile.auth_user.check_password("mini-secure-password-4829"))

	def test_mini_app_links_existing_account_after_password_confirmation(self):
		existing_user = get_user_model().objects.create_user(
			username="existing_email_user",
			email="owner@example.com",
			password="existing-secure-password-4829",
		)
		init_data = sign_mini_app_data({"id": 987654322, "username": "linked_user"})

		response = self.client.post(
			"/api/auth/telegram/mini-app/",
			{
				"init_data": init_data,
				"email": "OWNER@example.com",
				"password": "existing-secure-password-4829",
			},
			format="json",
		)

		self.assertEqual(response.status_code, 200)
		profile = TelegramUser.objects.get(telegram_id=987654322)
		self.assertEqual(profile.auth_user, existing_user)
		self.assertEqual(response.data["user"]["email"], "owner@example.com")

	def test_mini_app_can_relink_legacy_telegram_profile_to_existing_account(self):
		telegram_data = {"id": 987654326, "username": "legacy_telegram"}
		legacy_profile = get_or_create_telegram_user(telegram_data)
		existing_user = get_user_model().objects.create_user(
			username="legacy_web_user",
			email="legacy-owner@example.com",
			password="legacy-owner-password-4829",
		)
		init_data = sign_mini_app_data(telegram_data)

		response = self.client.post(
			"/api/auth/telegram/mini-app/",
			{
				"init_data": init_data,
				"email": "legacy-owner@example.com",
				"password": "legacy-owner-password-4829",
			},
			format="json",
		)

		self.assertEqual(response.status_code, 200)
		legacy_profile.refresh_from_db()
		self.assertEqual(legacy_profile.auth_user, existing_user)

	def test_mini_app_does_not_link_existing_email_with_wrong_password(self):
		existing_user = get_user_model().objects.create_user(
			username="protected_account",
			email="protected@example.com",
			password="existing-secure-password-4829",
		)
		init_data = sign_mini_app_data({"id": 987654323})

		response = self.client.post(
			"/api/auth/telegram/mini-app/",
			{
				"init_data": init_data,
				"email": "protected@example.com",
				"password": "wrong-password-4829",
			},
			format="json",
		)

		self.assertEqual(response.status_code, 401)
		self.assertFalse(TelegramUser.objects.filter(telegram_id=987654323).exists())
		self.assertTrue(get_user_model().objects.filter(pk=existing_user.pk).exists())

	def test_mini_app_links_existing_account_with_legacy_short_password(self):
		existing_user = get_user_model().objects.create_user(
			username="legacy_account",
			email="legacy@example.com",
			password="oldpw",
		)
		init_data = sign_mini_app_data({"id": 987654325})

		response = self.client.post(
			"/api/auth/telegram/mini-app/",
			{
				"init_data": init_data,
				"email": "legacy@example.com",
				"password": "oldpw",
			},
			format="json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(TelegramUser.objects.get(telegram_id=987654325).auth_user, existing_user)

	def test_mini_app_can_create_account_without_email_using_password(self):
		init_data = sign_mini_app_data({"id": 987654324})

		response = self.client.post(
			"/api/auth/telegram/mini-app/",
			{
				"init_data": init_data,
				"password": "telegram-secure-password-4829",
			},
			format="json",
		)

		self.assertEqual(response.status_code, 200)
		profile = TelegramUser.objects.get(telegram_id=987654324)
		self.assertEqual(profile.auth_user.email, "")
		self.assertTrue(profile.auth_user.check_password("telegram-secure-password-4829"))

	def test_mini_app_rejects_invalid_signature(self):
		response = self.client.post(
			"/api/auth/telegram/mini-app/",
			{
				"init_data": "auth_date=1700000000&user=%7B%22id%22%3A1%7D&hash=invalid",
				"password": "some-secure-password-4829",
			},
			format="json",
		)

		self.assertEqual(response.status_code, 401)
		self.assertFalse(TelegramUser.objects.exists())

	def test_website_telegram_login_accepts_valid_widget_signature(self):
		widget_data = sign_widget_data({
			"id": "123456789",
			"first_name": "Widget",
			"username": "widget_user",
			"auth_date": str(int(time.time())),
		})

		response = self.client.post(
			"/api/auth/telegram/login/",
			widget_data,
			format="json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["user"]["telegram_id"], 123456789)
		self.assertEqual(
			AccessToken(response.data["access"])["auth_method"],
			"telegram_widget",
		)

	def test_website_telegram_login_rejects_forged_data(self):
		response = self.client.post(
			"/api/auth/telegram/login/",
			{
				"id": "123456789",
				"first_name": "Fake",
				"auth_date": str(int(time.time())),
				"hash": "forged",
			},
			format="json",
		)

		self.assertEqual(response.status_code, 401)
		self.assertFalse(TelegramUser.objects.exists())

	def test_authenticated_user_can_query_me(self):
		user = get_user_model().objects.create_user(username="existing", password="secret")
		self.client.force_authenticate(user)

		response = self.client.get("/api/auth/me/")

		self.assertEqual(response.status_code, 200)
		self.assertIsNone(response.data["telegram_id"])
		self.assertEqual(response.data["subscription"]["plan"], "free")

	def test_subscription_plan_is_visible_on_current_user(self):
		user = get_user_model().objects.create_user(username="monthly-user", password="secret")
		user.subscription.activate("monthly")
		self.client.force_authenticate(user)

		response = self.client.get("/api/auth/me/")

		self.assertEqual(response.status_code, 200)
		subscription = response.data["subscription"]
		self.assertEqual(subscription["plan"], "monthly")
		self.assertEqual(subscription["plan_label"], "1 oylik")
		self.assertTrue(subscription["is_active"])
		self.assertIsNotNone(subscription["expires_at"])

	def test_authenticated_user_can_update_profile(self):
		user = get_user_model().objects.create_user(username="before-edit", email="old@example.com", password="secret")
		self.client.force_authenticate(user)

		response = self.client.patch(
			"/api/auth/me/",
			{"username": "after-edit", "email": "new@example.com"},
			format="json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["username"], "after-edit")
		self.assertEqual(response.data["email"], "new@example.com")

	def test_favorites_endpoint_filters_searches_and_paginates_ten_items(self):
		user = get_user_model().objects.create_user(username="favorite-owner", password="secret")
		profile = TelegramUser.objects.create(telegram_id=998877665, auth_user=user)
		for number in range(12):
			title = MediaTitle.objects.create(
				type=MediaTitle.MediaType.ANIME if number < 11 else MediaTitle.MediaType.MANGA,
				title=f"Favorite {number:02d}",
				slug=f"favorite-{number:02d}",
			)
			profile.favorites.add(title)
		self.client.force_authenticate(user)

		first_page = self.client.get("/api/auth/favorites/?type=anime&search=Favorite")
		second_page = self.client.get("/api/auth/favorites/?type=anime&search=Favorite&page=2")

		self.assertEqual(first_page.status_code, 200)
		self.assertEqual(first_page.data["count"], 11)
		self.assertEqual(len(first_page.data["results"]), 10)
		self.assertEqual(len(second_page.data["results"]), 1)
		self.assertTrue(all(item["type"] == "anime" for item in first_page.data["results"]))

	def test_favorites_endpoint_returns_empty_for_account_without_telegram_profile(self):
		user = get_user_model().objects.create_user(username="no-telegram", password="secret")
		self.client.force_authenticate(user)

		response = self.client.get("/api/auth/favorites/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["count"], 0)
		self.assertEqual(response.data["results"], [])

class ProfileApiTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.user = get_user_model().objects.create_user(
			username="profile-owner",
			email="profile@example.com",
			password="profile-secret-4829",
		)
		self.profile = TelegramUser.objects.create(
			telegram_id=555444333,
			auth_user=self.user,
			username="profile_owner",
			first_name="Aziz",
			last_name="Karimov",
			language_code="uz",
		)
		self.client.force_authenticate(self.user)

	def _title(self, number, media_type=MediaTitle.MediaType.ANIME):
		return MediaTitle.objects.create(
			type=media_type,
			title=f"Profile Title {number}",
			slug=f"profile-title-{number}",
		)

	def _view(self, title, when, part=None, source=MediaView.Source.SITE, count=1):
		view = MediaView.objects.create(
			user=self.user,
			title=title,
			part=part,
			source=source,
			count=count,
		)
		MediaView.objects.filter(pk=view.pk).update(updated_at=when)
		view.refresh_from_db()
		return view

	def test_profile_overview_reports_account_telegram_and_activity_totals(self):
		favorite = self._title(1)
		FavoriteContent.objects.create(user=self.profile, content=favorite)
		manga = self._title(2, MediaTitle.MediaType.MANGA)
		part = MediaPart.objects.create(content=manga, number=1)
		self._view(manga, timezone.now() - timedelta(hours=2), part=part, source=MediaView.Source.BOT)
		ReadingProgress.objects.create(user=self.user, part=part, page=3)

		response = self.client.get("/api/auth/profile/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["account"]["username"], "profile-owner")
		self.assertEqual(response.data["account"]["email"], "profile@example.com")
		self.assertTrue(response.data["telegram"]["linked"])
		self.assertEqual(response.data["telegram"]["telegram_id"], 555444333)
		self.assertEqual(response.data["telegram"]["full_name"], "Aziz Karimov")
		self.assertEqual(
			response.data["stats"],
			{"favorites": 1, "views": 1, "reading": 1, "requests": 0},
		)
		self.assertEqual(response.data["subscription"]["plan"], "free")
		self.assertFalse(response.data["subscription"]["is_active"])
		self.assertEqual(len(response.data["recent_activity"]), 2)

	def test_profile_overview_reports_unlinked_telegram(self):
		user = get_user_model().objects.create_user(username="lonely-web-user", password="secret-4829")
		self.client.force_authenticate(user)

		response = self.client.get("/api/auth/profile/")

		self.assertEqual(response.status_code, 200)
		self.assertFalse(response.data["telegram"]["linked"])
		self.assertEqual(response.data["stats"]["views"], 0)

	def test_profile_history_lists_views_newest_first_with_part_details(self):
		older = self._title(10)
		newer = self._title(11)
		part = MediaPart.objects.create(content=newer, season_number=2, number=4)
		self._view(older, timezone.now() - timedelta(days=3))
		self._view(newer, timezone.now() - timedelta(minutes=5), part=part, count=4)

		response = self.client.get("/api/auth/profile/history/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["count"], 2)
		results = response.data["results"]
		self.assertEqual([item["slug"] for item in results], ["profile-title-11", "profile-title-10"])
		self.assertEqual(results[0]["part_number"], 4)
		self.assertEqual(results[0]["season_number"], 2)
		self.assertEqual(results[0]["kind"], "watch")
		self.assertEqual(results[0]["view_count"], 4)
		self.assertEqual(results[1]["part_number"], None)

	def test_profile_history_paginates_twelve_items_and_hides_other_users(self):
		stranger = get_user_model().objects.create_user(username="stranger", password="secret-4829")
		for number in range(14):
			title = self._title(100 + number)
			self._view(title, timezone.now() - timedelta(minutes=number))
		MediaView.objects.create(user=stranger, title=self._title(900))

		first_page = self.client.get("/api/auth/profile/history/")
		second_page = self.client.get("/api/auth/profile/history/?page=2")

		self.assertEqual(first_page.data["count"], 14)
		self.assertEqual(len(first_page.data["results"]), 12)
		self.assertEqual(len(second_page.data["results"]), 2)

	def test_profile_activity_merges_favorites_views_and_payments(self):
		title = self._title(20)
		part = MediaPart.objects.create(content=title, number=2)
		FavoriteContent.objects.create(user=self.profile, content=title)
		self._view(
			title,
			timezone.now() - timedelta(hours=1),
			part=part,
			source=MediaView.Source.BOT,
		)
		SubscriptionRequest.objects.create(
			user=self.user,
			plan="monthly",
			amount=25000,
			status=SubscriptionRequest.Status.APPROVED,
		)

		response = self.client.get("/api/auth/profile/activity/")

		self.assertEqual(response.status_code, 200)
		kinds = sorted(item["kind"] for item in response.data["results"])
		self.assertEqual(kinds, ["favorite", "subscription", "watch"])
		view_event = next(item for item in response.data["results"] if item["kind"] == "watch")
		self.assertEqual(view_event["label"], "Botda tomosha qilindi")
		self.assertEqual(view_event["detail"], "2-qism")
		self.assertEqual(view_event["slug"], "profile-title-20")

	def test_profile_subscription_summarises_plan_expiry_and_payments(self):
		Subscription.objects.filter(user=self.user).update(
			plan="monthly",
			expires_at=timezone.now() + timedelta(days=27),
		)
		# The signal already cached the reverse relation on this instance.
		self.user.refresh_from_db()
		first = SubscriptionRequest.objects.create(
			user=self.user,
			plan="monthly",
			amount=19000,
			status=SubscriptionRequest.Status.APPROVED,
		)
		SubscriptionRequest.objects.filter(pk=first.pk).update(updated_at=timezone.now() - timedelta(days=40))
		second = SubscriptionRequest.objects.create(
			user=self.user,
			plan="yearly",
			amount=39000,
			status=SubscriptionRequest.Status.APPROVED,
		)
		SubscriptionRequest.objects.filter(pk=second.pk).update(updated_at=timezone.now() - timedelta(days=3))
		SubscriptionRequest.objects.create(
			user=self.user,
			plan="daily",
			amount=29000,
			status=SubscriptionRequest.Status.REJECTED,
		)

		response = self.client.get("/api/auth/profile/subscription/")

		self.assertEqual(response.status_code, 200)
		summary = response.data["summary"]
		self.assertEqual(summary["plan"], "monthly")
		self.assertEqual(summary["plan_label"], "1 oylik")
		self.assertTrue(summary["is_paid"])
		self.assertTrue(summary["is_active"])
		self.assertEqual(summary["period_days"], 30)
		self.assertEqual(summary["days_left"], 27)
		self.assertEqual(float(summary["total_paid"]), 58000.0)
		self.assertEqual(float(summary["last_amount"]), 39000.0)
		self.assertEqual(summary["payments_count"], 2)
		self.assertEqual(len(response.data["requests"]), 3)

	def test_profile_subscription_stays_free_without_payments(self):
		response = self.client.get("/api/auth/profile/subscription/")

		self.assertEqual(response.status_code, 200)
		summary = response.data["summary"]
		self.assertFalse(summary["is_paid"])
		self.assertIsNone(summary["expires_at"])
		self.assertIsNone(summary["days_left"])
		self.assertEqual(response.data["requests"], [])

	def test_user_settings_update_and_are_exposed_on_me(self):
		initial = self.client.get("/api/auth/settings/")

		self.assertEqual(initial.status_code, 200)
		self.assertEqual(initial.data["theme"], "system")
		self.assertEqual(initial.data["language"], "uz")
		self.assertFalse(initial.data["reduce_motion"])

		update = self.client.patch(
			"/api/auth/settings/",
			{"theme": "dark", "language": "ru", "reduce_motion": True},
			format="json",
		)

		self.assertEqual(update.status_code, 200)
		self.assertEqual(update.data["theme"], "dark")

		me = self.client.get("/api/auth/me/")
		self.assertEqual(me.data["settings"]["theme"], "dark")
		self.assertEqual(me.data["settings"]["language"], "ru")
		self.assertTrue(me.data["settings"]["reduce_motion"])
		self.assertEqual(Subscription.objects.filter(user=self.user).count(), 1)

	def test_user_settings_reject_unknown_theme(self):
		response = self.client.patch("/api/auth/settings/", {"theme": "neon"}, format="json")

		self.assertEqual(response.status_code, 400)
		self.assertIn("theme", response.data)

	def test_profile_endpoints_require_authentication(self):
		anonymous = APIClient()
		urls = [
			"/api/auth/profile/",
			"/api/auth/profile/activity/",
			"/api/auth/profile/history/",
			"/api/auth/profile/subscription/",
			"/api/auth/settings/",
		]
		for url in urls:
			self.assertEqual(anonymous.get(url).status_code, 401, url)


class FavoriteApiTests(TestCase):
	def test_user_can_favorite_any_catalog_item(self):
		user = TelegramUser.objects.create(telegram_id=111222333)
		anime = MediaTitle.objects.create(
			type=MediaTitle.MediaType.ANIME,
			title="Sample Anime",
			slug="sample-anime",
		)

		user.favorites.add(anime)

		self.assertEqual(list(user.favorites.all()), [anime])

	def test_toggle_favorite_adds_then_removes(self):
		user = get_user_model().objects.create_user(username="fav-toggle", password="x")
		TelegramUser.objects.create(telegram_id=555666777, auth_user=user)
		MediaTitle.objects.create(
			type=MediaTitle.MediaType.ANIME,
			title="Toggle Anime",
			slug="toggle-anime",
		)
		client = APIClient()
		client.force_authenticate(user)

		added = client.post("/api/auth/favorites/toggle/", {"slug": "toggle-anime"}, format="json")
		self.assertEqual(added.status_code, 200)
		self.assertTrue(added.data["is_favorite"])
		self.assertEqual(
			list(user.telegram_profile.favorites.values_list("slug", flat=True)),
			["toggle-anime"],
		)

		removed = client.post("/api/auth/favorites/toggle/", {"slug": "toggle-anime"}, format="json")
		self.assertEqual(removed.status_code, 200)
		self.assertFalse(removed.data["is_favorite"])
		self.assertEqual(list(user.telegram_profile.favorites.all()), [])

	def test_toggle_favorite_requires_telegram_profile(self):
		user = get_user_model().objects.create_user(username="fav-noprofile", password="x")
		client = APIClient()
		client.force_authenticate(user)

		response = client.post("/api/auth/favorites/toggle/", {"slug": "anything"}, format="json")
		self.assertEqual(response.status_code, 400)

	def test_detail_endpoint_reports_is_favorite(self):
		user = get_user_model().objects.create_user(username="fav-detail", password="x")
		profile = TelegramUser.objects.create(telegram_id=444555666, auth_user=user)
		title = MediaTitle.objects.create(
			type=MediaTitle.MediaType.ANIME,
			title="Detail Anime",
			slug="detail-anime",
		)
		profile.favorites.add(title)
		client = APIClient()
		client.force_authenticate(user)

		response = client.get("/api/catalog/detail-anime/")
		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.data["is_favorite"])

		anonymous = APIClient()
		public = anonymous.get("/api/catalog/detail-anime/")
		self.assertEqual(public.status_code, 200)
		self.assertFalse(public.data["is_favorite"])


def _tiny_png() -> bytes:
	"""A valid 1x1 PNG, the smallest image Django's ImageField accepts."""
	import io

	from PIL import Image

	buffer = io.BytesIO()
	Image.new("RGB", (1, 1), (255, 0, 0)).save(buffer, format="PNG")
	return buffer.getvalue()


PNG_1PX = _tiny_png()


@override_settings(
	SUBSCRIPTION_CARD_NUMBER="8600 0000 0000 0000",
	SUBSCRIPTION_PRICES={
		"free": 0,
		"daily": 6000,
		"d15": 10000,
		"monthly": 25000,
		"quarterly": 64000,
		"yearly": 220000,
	},
)
class SubscriptionApiTests(TestCase):
	"""The "Obuna" page: live plan details, the card number and new requests."""

	def setUp(self):
		self.client = APIClient()
		self.user = get_user_model().objects.create_user(
			username="subscriber", password="subscriber-secret-4829"
		)
		self.client.force_authenticate(self.user)

	def _screenshot(self, name="pay.png"):
		return SimpleUploadedFile(name, PNG_1PX, content_type="image/png")

	def test_plan_catalogue_counts_content_from_the_database(self):
		from users.plans import PLAN_ORDER, plan_details

		for number in range(3):
			MediaTitle.objects.create(
				type=MediaTitle.MediaType.ANIME,
				title=f"Free Anime {number}",
				slug=f"free-anime-{number}",
			)
		MediaTitle.objects.create(
			type=MediaTitle.MediaType.MOVIE,
			title="Locked Movie",
			slug="locked-movie",
			required_plan=MediaTitle.AccessPlan.PAID,
		)

		response = self.client.get("/api/auth/subscription/plans/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["current_plan"], "free")
		self.assertEqual(response.data["card_number"], "8600 0000 0000 0000")
		self.assertIsNone(response.data["pending_request"])

		plans = {item["id"]: item for item in response.data["plans"]}
		self.assertEqual(list(plans), PLAN_ORDER)
		self.assertEqual(
			[plans[plan]["price"] for plan in PLAN_ORDER],
			[6000, 10000, 25000, 64000, 220000],
		)
		self.assertEqual(
			[plans[plan]["days"] for plan in PLAN_ORDER], [1, 15, 30, 90, 365]
		)
		self.assertEqual(
			[plans[plan]["label"] for plan in PLAN_ORDER],
			["Kunlik", "15 kunlik", "1 oylik", "3 oylik", "1 yillik"],
		)

		def count_of(details, media_type):
			return next(
				f["count"] for f in details["features"] if f["type"] == media_type
			)

		free = plan_details("free")
		self.assertEqual(count_of(free, MediaTitle.MediaType.ANIME), 3)
		self.assertEqual(count_of(plans["monthly"], MediaTitle.MediaType.ANIME), 3)
		self.assertEqual(count_of(free, MediaTitle.MediaType.MOVIE), 0)
		self.assertEqual(count_of(plans["monthly"], MediaTitle.MediaType.MOVIE), 1)
		self.assertTrue(plans["yearly"]["description"])

	def test_card_endpoint_returns_the_configured_card_number(self):
		response = self.client.get("/api/auth/subscription/card/")

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["card_number"], "8600 0000 0000 0000")

	@mock.patch("users.telegram_notify.notify_admins_new_request", return_value=True)
	def test_submitting_a_screenshot_creates_a_pending_request(self, notify):
		response = self.client.post(
			"/api/auth/subscription/request/",
			{"plan": "yearly", "screenshot": self._screenshot()},
			format="multipart",
		)

		self.assertEqual(response.status_code, 201, response.data)
		self.assertEqual(response.data["status"], SubscriptionRequest.Status.PENDING)
		self.assertEqual(response.data["plan"], "yearly")
		self.assertEqual(float(response.data["amount"]), 220000.0)
		self.assertEqual(response.data["card_number"], "8600 0000 0000 0000")
		self.assertTrue(response.data["screenshot"])

		request = SubscriptionRequest.objects.get()
		self.assertEqual(request.user, self.user)
		self.assertEqual(request.status, SubscriptionRequest.Status.PENDING)
		self.assertEqual(notify.call_count, 1)
		self.assertEqual(notify.call_args.args[0].pk, request.pk)

		page = self.client.get("/api/auth/subscription/plans/")
		self.assertEqual(page.data["pending_request"]["id"], request.pk)

	@mock.patch("users.telegram_notify.notify_admins_new_request", return_value=True)
	def test_a_second_request_is_rejected_while_one_is_pending(self, notify):
		self.client.post(
			"/api/auth/subscription/request/",
			{"plan": "yearly", "screenshot": self._screenshot()},
			format="multipart",
		)

		second = self.client.post(
			"/api/auth/subscription/request/",
			{"plan": "yearly", "screenshot": self._screenshot("second.png")},
			format="multipart",
		)

		self.assertEqual(second.status_code, 400)
		self.assertEqual(SubscriptionRequest.objects.count(), 1)

	@mock.patch("users.telegram_notify.notify_admins_new_request", return_value=True)
	def test_cannot_buy_the_plan_you_already_have(self, notify):
		self.user.subscription.activate("monthly")

		response = self.client.post(
			"/api/auth/subscription/request/",
			{"plan": "monthly", "screenshot": self._screenshot()},
			format="multipart",
		)

		self.assertEqual(response.status_code, 400)
		self.assertEqual(SubscriptionRequest.objects.count(), 0)

	@mock.patch("users.telegram_notify.notify_admins_new_request", return_value=True)
	def test_an_expired_plan_can_be_bought_again(self, notify):
		self.user.subscription.activate("daily")
		subscription = self.user.subscription
		subscription.expires_at = timezone.now() - timedelta(seconds=1)
		subscription.save(update_fields=["expires_at", "updated_at"])

		response = self.client.post(
			"/api/auth/subscription/request/",
			{"plan": "daily", "screenshot": self._screenshot()},
			format="multipart",
		)

		self.assertEqual(response.status_code, 201, response.data)
		self.assertEqual(SubscriptionRequest.objects.count(), 1)

	@mock.patch("users.telegram_notify.notify_admins_new_request", return_value=True)
	def test_a_screenshot_is_mandatory_and_the_plan_must_be_known(self, notify):
		missing = self.client.post(
			"/api/auth/subscription/request/", {"plan": "yearly"}, format="multipart"
		)
		unknown = self.client.post(
			"/api/auth/subscription/request/",
			{"plan": "gold", "screenshot": self._screenshot()},
			format="multipart",
		)

		self.assertEqual(missing.status_code, 400)
		self.assertEqual(unknown.status_code, 400)
		self.assertIn("plan", unknown.data)
		self.assertEqual(SubscriptionRequest.objects.count(), 0)

	def test_a_request_is_visible_only_to_its_owner(self):
		stranger = get_user_model().objects.create_user(
			username="stranger-subscriber", password="stranger-secret-4829"
		)
		own = SubscriptionRequest.objects.create(
			user=self.user, plan="yearly", amount=220000
		)
		theirs = SubscriptionRequest.objects.create(user=stranger, plan="monthly", amount=25000)

		self.assertEqual(
			self.client.get(f"/api/auth/subscription/requests/{own.pk}/").status_code, 200
		)
		self.assertEqual(
			self.client.get(f"/api/auth/subscription/requests/{theirs.pk}/").status_code, 404
		)

	def test_the_catalogue_requires_authentication(self):
		anonymous = APIClient()

		self.assertEqual(
			anonymous.get("/api/auth/subscription/plans/").status_code, 401
		)
		self.assertEqual(
			anonymous.post(
				"/api/auth/subscription/request/",
				{"plan": "yearly"},
				format="multipart",
			).status_code,
			401,
		)


SUPPORT_URL = "/api/auth/support/"


def fake_telegram_client(captured, *, status_code=200):
	"""Stand-in for ``httpx.Client`` recording every Bot API request."""

	class _Response:
		def __init__(self):
			self.status_code = status_code
			self.text = "ok" if status_code == 200 else "rejected"

	class _Client:
		def __init__(self, *args, **kwargs):
			pass

		def __enter__(self):
			return self

		def __exit__(self, *exc):
			return False

		def post(self, url, data=None, files=None):
			captured.append((url, data or {}))
			return _Response()

	return _Client


class SupportMessageApiTests(TestCase):
	"""The website's "Adminga xabar" endpoint."""

	def setUp(self):
		self.client = APIClient()
		self.user = get_user_model().objects.create_user(
			username="support-user", password="support-secret-4829"
		)
		self.client.force_authenticate(self.user)

	def test_a_message_is_stored_and_forwarded_to_every_admin(self):
		captured = []

		with mock.patch(
			"users.telegram_notify.httpx.Client", fake_telegram_client(captured)
		), override_settings(ADMIN_IDS="111,222", BOT_TOKEN=BOT_TOKEN):
			response = self.client.post(
				SUPPORT_URL, {"text": "Obuna to'lovim tasdiqlanmadi"}, format="json"
			)

		self.assertEqual(response.status_code, 201)
		self.assertTrue(response.data["delivered"])
		message = SupportMessage.objects.get()
		self.assertEqual(message.text, "Obuna to'lovim tasdiqlanmadi")
		self.assertEqual(message.source, SupportMessage.Source.WEB)
		self.assertEqual(message.status, SupportMessage.Status.SENT)
		self.assertEqual(message.user, self.user)
		self.assertEqual(len(captured), 2)
		self.assertEqual({data["chat_id"] for _url, data in captured}, {111, 222})
		self.assertIn("Obuna to'lovim tasdiqlanmadi", captured[0][1]["text"])
		self.assertIn("support-user", captured[0][1]["text"])

	def test_a_telegram_outage_keeps_the_message_and_says_so(self):
		captured = []

		with mock.patch(
			"users.telegram_notify.httpx.Client",
			fake_telegram_client(captured, status_code=500),
		), override_settings(ADMIN_IDS="111", BOT_TOKEN=BOT_TOKEN):
			response = self.client.post(SUPPORT_URL, {"text": "Yuborilmaydigan"}, format="json")

		self.assertEqual(response.status_code, 201)
		self.assertFalse(response.data["delivered"])
		message = SupportMessage.objects.get()
		self.assertEqual(message.status, SupportMessage.Status.FAILED)
		self.assertIn("500", message.error)

	def test_missing_admin_configuration_is_not_delivered(self):
		captured = []

		with mock.patch(
			"users.telegram_notify.httpx.Client", fake_telegram_client(captured)
		), override_settings(ADMIN_IDS="", BOT_ADMIN_IDS="", BOT_TOKEN=BOT_TOKEN):
			response = self.client.post(SUPPORT_URL, {"text": "Adminsiz"}, format="json")

		self.assertEqual(response.status_code, 201)
		self.assertFalse(response.data["delivered"])
		self.assertEqual(captured, [])
		self.assertEqual(SupportMessage.objects.get().status, SupportMessage.Status.FAILED)

	def test_the_message_is_trimmed_and_the_length_is_capped(self):
		with mock.patch(
			"users.telegram_notify.httpx.Client", fake_telegram_client([])
		), override_settings(ADMIN_IDS="111", BOT_TOKEN=BOT_TOKEN):
			trimmed = self.client.post(SUPPORT_URL, {"text": "  salom  "}, format="json")

		self.assertEqual(trimmed.status_code, 201)
		self.assertEqual(SupportMessage.objects.get().text, "salom")

		too_long = self.client.post(
			SUPPORT_URL, {"text": "x" * (SUPPORT_MAX_LENGTH + 1)}, format="json"
		)

		self.assertEqual(too_long.status_code, 400)
		self.assertEqual(SupportMessage.objects.count(), 1)

	def test_an_empty_message_is_rejected(self):
		response = self.client.post(SUPPORT_URL, {"text": "   "}, format="json")

		self.assertEqual(response.status_code, 400)
		self.assertEqual(SupportMessage.objects.count(), 0)

	def test_a_second_message_within_a_minute_is_rate_limited(self):
		with mock.patch(
			"users.telegram_notify.httpx.Client", fake_telegram_client([])
		), override_settings(ADMIN_IDS="111", BOT_TOKEN=BOT_TOKEN):
			self.client.post(SUPPORT_URL, {"text": "birinchi"}, format="json")
			second = self.client.post(SUPPORT_URL, {"text": "ikkinchi"}, format="json")

		self.assertEqual(second.status_code, 429)
		self.assertGreaterEqual(second.data["retry_after"], 1)
		self.assertEqual(SupportMessage.objects.count(), 1)

	def test_sending_requires_authentication(self):
		anonymous = APIClient()

		self.assertEqual(
			anonymous.post(SUPPORT_URL, {"text": "salom"}, format="json").status_code, 401
		)
		self.assertEqual(SupportMessage.objects.count(), 0)


class SubscriptionReminderTests(TestCase):
	"""The reminder stage rule, the cron command and the panel payload."""

	def setUp(self):
		self.user = get_user_model().objects.create_user(
			username="reminder-user", password="reminder-secret-4829"
		)
		subscription = Subscription.objects.get_or_create(user=self.user)[0]
		subscription.plan = Subscription.Plan.MONTHLY
		subscription.save(update_fields=["plan", "updated_at"])
		self.subscription = subscription

	def _set_expiry(self, **delta):
		Subscription.objects.filter(pk=self.subscription.pk).update(
			expires_at=timezone.now() + timedelta(**delta)
		)
		self.subscription.refresh_from_db()

	def _api_client(self):
		"""A client whose user is re-read, so ``user.subscription`` is not stale.

		Attaching the subscription cached it on ``self.user``; ``.update()`` in
		:meth:`_set_expiry` bypasses that cache, exactly like a long-lived caller
		would. Every request in production loads the user fresh.
		"""
		client = APIClient()
		client.force_authenticate(get_user_model().objects.get(pk=self.user.pk))
		return client

	def _link_telegram(self, telegram_id=987654):
		profile = get_or_create_telegram_user(
			{"id": telegram_id, "first_name": "Reminder", "username": "reminder"}
		)
		profile.auth_user = self.user
		profile.save(update_fields=["auth_user", "updated_at"])
		return profile

	def test_stage_is_empty_while_the_plan_is_far_from_ending(self):
		self._set_expiry(days=30)

		self.assertEqual(reminder_stage(self.subscription), "")

	def test_stage_is_expiring_inside_the_window(self):
		self._set_expiry(days=2)

		self.assertEqual(reminder_stage(self.subscription), EXPIRING)

	def test_stage_is_expired_just_after_the_end(self):
		self._set_expiry(days=-2)

		self.assertEqual(reminder_stage(self.subscription), EXPIRED)

	def test_a_long_expired_plan_is_not_reminded(self):
		self._set_expiry(days=-(REMIND_AFTER_DAYS + 5))

		self.assertEqual(reminder_stage(self.subscription), "")

	def test_a_free_plan_never_gets_a_reminder(self):
		self._set_expiry(days=1)
		Subscription.objects.filter(pk=self.subscription.pk).update(plan="free")
		self.subscription.refresh_from_db()

		self.assertEqual(reminder_stage(self.subscription), "")

	def test_activating_a_plan_restarts_the_reminder_cycle(self):
		self._set_expiry(days=2)
		self.subscription.reminder_stage = EXPIRING
		self.subscription.save(update_fields=["reminder_stage", "updated_at"])

		self.subscription.activate("monthly")

		self.assertEqual(self.subscription.reminder_stage, "")
		self.assertIsNone(self.subscription.reminder_sent_at)

	def test_the_command_sends_one_reminder_per_stage(self):
		self._link_telegram()
		self._set_expiry(days=2)
		captured = []

		with mock.patch(
			"users.telegram_notify.httpx.Client", fake_telegram_client(captured)
		), override_settings(ADMIN_IDS="111", BOT_TOKEN=BOT_TOKEN):
			call_command("send_subscription_reminders")
			call_command("send_subscription_reminders")

		self.assertEqual(len(captured), 1, "the second run must be a no-op")
		self.assertIn("/sendMessage", captured[0][0])
		self.assertEqual(captured[0][1]["chat_id"], 987654)
		self.assertIn("tugab qolmoqda", captured[0][1]["text"])
		self.subscription.refresh_from_db()
		self.assertEqual(self.subscription.reminder_stage, EXPIRING)
		self.assertIsNotNone(self.subscription.reminder_sent_at)

	def test_the_command_moves_on_to_the_expired_stage(self):
		self._link_telegram()
		self._set_expiry(days=2)
		captured = []

		with mock.patch(
			"users.telegram_notify.httpx.Client", fake_telegram_client(captured)
		), override_settings(ADMIN_IDS="111", BOT_TOKEN=BOT_TOKEN):
			call_command("send_subscription_reminders")
			self._set_expiry(days=-1)
			call_command("send_subscription_reminders")

		self.assertEqual(len(captured), 2)
		self.assertIn("muddati tugadi", captured[1][1]["text"])
		self.subscription.refresh_from_db()
		self.assertEqual(self.subscription.reminder_stage, EXPIRED)

	def test_a_failed_delivery_is_retried_on_the_next_run(self):
		self._link_telegram()
		self._set_expiry(days=2)

		with mock.patch(
			"users.telegram_notify.httpx.Client", fake_telegram_client([], status_code=500)
		), override_settings(ADMIN_IDS="111", BOT_TOKEN=BOT_TOKEN):
			call_command("send_subscription_reminders")

		self.subscription.refresh_from_db()
		self.assertEqual(self.subscription.reminder_stage, "")
		captured = []
		with mock.patch(
			"users.telegram_notify.httpx.Client", fake_telegram_client(captured)
		), override_settings(ADMIN_IDS="111", BOT_TOKEN=BOT_TOKEN):
			call_command("send_subscription_reminders")

		self.assertEqual(len(captured), 1)

	def test_dry_run_changes_nothing(self):
		self._link_telegram()
		self._set_expiry(days=2)
		captured = []

		with mock.patch(
			"users.telegram_notify.httpx.Client", fake_telegram_client(captured)
		), override_settings(ADMIN_IDS="111", BOT_TOKEN=BOT_TOKEN):
			call_command("send_subscription_reminders", "--dry-run")

		self.assertEqual(captured, [])
		self.subscription.refresh_from_db()
		self.assertEqual(self.subscription.reminder_stage, "")

	def test_an_account_without_telegram_is_skipped(self):
		self._set_expiry(days=2)
		captured = []

		with mock.patch(
			"users.telegram_notify.httpx.Client", fake_telegram_client(captured)
		), override_settings(ADMIN_IDS="111", BOT_TOKEN=BOT_TOKEN):
			call_command("send_subscription_reminders")

		self.assertEqual(captured, [])

	def test_the_plan_catalogue_reports_the_reminder(self):
		self._set_expiry(days=1)

		response = self._api_client().get("/api/auth/subscription/plans/")

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.data["current_active"])
		self.assertEqual(response.data["reminder"]["stage"], EXPIRING)
		self.assertEqual(response.data["reminder"]["days"], 1)

	def test_the_plan_catalogue_has_no_reminder_outside_the_window(self):
		self._set_expiry(days=60)

		response = self._api_client().get("/api/auth/subscription/plans/")

		self.assertEqual(response.status_code, 200)
		self.assertTrue(response.data["current_active"])
		self.assertIsNone(response.data["reminder"])
