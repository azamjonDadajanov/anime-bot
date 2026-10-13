"""``/start <username>`` linking the Telegram profile to a website account."""

from __future__ import annotations

from django.contrib.auth import get_user_model

from users.models import Subscription, TelegramUser

from .base import DispatcherTestCase
from .fakes import build_callback, build_command


class StartAccountLinkTests(DispatcherTestCase):
	def site_user(self, username: str, plan: str = "free"):
		user = get_user_model().objects.create(username=username)
		Subscription.objects.filter(user=user).update(plan=plan)
		return user

	def test_start_payload_links_the_site_account(self) -> None:
		site_user = self.site_user("aa", plan="pro")

		self.feed(build_command("start", payload="aa"))

		profile = TelegramUser.objects.get(telegram_id=111)
		self.assertEqual(profile.auth_user_id, site_user.pk)
		self.assertIn("ulandi", self.all_text().lower())

	def test_start_payload_accepts_an_at_username(self) -> None:
		site_user = self.site_user("bb")

		self.feed(build_command("start", payload="@bb"))

		profile = TelegramUser.objects.get(telegram_id=111)
		self.assertEqual(profile.auth_user_id, site_user.pk)

	def test_linked_profile_uses_the_site_subscription(self) -> None:
		site_user = self.site_user("cc", plan="plus")
		self.feed(build_command("start", payload="cc"))
		self.session.reset()

		self.feed(build_callback("prof", update_id=3))

		self.assertIn("<b>Plus</b>", self.all_text())

	def test_repeated_start_reports_the_existing_link(self) -> None:
		self.site_user("dd")
		self.feed(build_command("start", payload="dd"))
		self.session.reset()

		self.feed(build_command("start", payload="dd", update_id=2))

		self.assertIn("allaqachon", self.all_text())

	def test_unknown_username_falls_back_to_the_content_lookup(self) -> None:
		self.feed(build_command("start", payload="nobody"))

		self.assertIn("topilmadi", self.all_text().lower())
		profile = TelegramUser.objects.get(telegram_id=111)
		self.assertEqual(profile.auth_user.username, "telegram_111")

	def test_username_already_taken_by_another_profile(self) -> None:
		site_user = self.site_user("ee")
		TelegramUser.objects.create(telegram_id=999, auth_user=site_user, username="other")

		self.feed(build_command("start", payload="ee"))

		profile = TelegramUser.objects.get(telegram_id=111)
		self.assertNotEqual(profile.auth_user_id, site_user.pk)
		self.assertIn("boshqa Telegram akkauntga ulangan", self.all_text())

	def test_a_real_bound_account_is_not_stolen(self) -> None:
		bound = get_user_model().objects.create(username="telegram_111")
		bound.set_password("secret-pass")
		bound.save()
		TelegramUser.objects.create(telegram_id=111, auth_user=bound, username="holder")
		self.site_user("ff")

		self.feed(build_command("start", payload="ff"))

		profile = TelegramUser.objects.get(telegram_id=111)
		self.assertEqual(profile.auth_user_id, bound.pk)
		self.assertIn("boshqa sayt hisobiga ulangan", self.all_text())
