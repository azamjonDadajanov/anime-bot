"""``/start <username>`` linking the Telegram profile to a website account.

Nothing binds until the inline confirm card is pressed: the deep link only
*offers* the link («Ha, ulash» / «Bekor qilish»), and the real write happens
in the ``alink:<username>`` callback. Negative outcomes (unknown name, taken,
conflict, already linked) still answer immediately — there is nothing to
consent to there.
"""

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

	def test_start_payload_offers_the_link_and_confirming_binds_it(self) -> None:
		site_user = self.site_user("aa", plan="yearly")

		self.feed(build_command("start", payload="aa"))

		# Offered, not yet written: the confirm card is on screen.
		self.assertIn("tasdiqlaysizmi", self.all_text())
		self.assertIn("Ha, ulash", self.button_texts())
		profile = TelegramUser.objects.get(telegram_id=111)
		self.assertNotEqual(profile.auth_user_id, site_user.pk)

		self.feed(build_callback("alink:aa", update_id=2))

		profile.refresh_from_db()
		self.assertEqual(profile.auth_user_id, site_user.pk)
		self.assertIn("ulandi", self.all_text().lower())

	def test_start_payload_accepts_an_at_username(self) -> None:
		site_user = self.site_user("bb")

		self.feed(build_command("start", payload="@bb"))
		self.feed(build_callback("alink:bb", update_id=2))

		profile = TelegramUser.objects.get(telegram_id=111)
		self.assertEqual(profile.auth_user_id, site_user.pk)

	def test_declining_the_link_leaves_the_profile_alone(self) -> None:
		self.site_user("gg")

		self.feed(build_command("start", payload="gg"))
		self.session.reset()
		self.feed(build_callback("alinkno", update_id=2))

		self.assertIn("bekor qilindi", self.all_text().lower())
		profile = TelegramUser.objects.get(telegram_id=111)
		self.assertEqual(profile.auth_user.username, "telegram_111")

	def test_linked_profile_uses_the_site_subscription(self) -> None:
		site_user = self.site_user("cc", plan="monthly")
		self.feed(build_command("start", payload="cc"))
		self.feed(build_callback("alink:cc", update_id=2))
		self.session.reset()

		self.feed(build_callback("prof", update_id=3))

		self.assertIn("<b>1 oylik</b>", self.all_text())

	def test_repeated_start_reports_the_existing_link(self) -> None:
		self.site_user("dd")
		self.feed(build_command("start", payload="dd"))
		self.feed(build_callback("alink:dd", update_id=2))
		self.session.reset()

		self.feed(build_command("start", payload="dd", update_id=3))

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
