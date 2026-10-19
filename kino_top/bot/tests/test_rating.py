"""``🏆 Reyting``: the website's rating table, readable straight from the bot.

The screen reads the same table the site's "Reyting" page does
(``games.services.leaderboard``), so these tests create real finished attempts
and check what the player actually reads: the top rows, the caller's own rank,
and the invitation to link an account when there is no rank to report.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone
from games.models import AnimeVerification, QuizAttempt
from users.models import TelegramUser

from .. import callbacks as cb
from ..handlers.user.rating import render_board
from ..texts import RATING_EMPTY, RATING_GUEST
from .base import DispatcherTestCase
from .fakes import USER, build_callback, build_command
from .helpers import bot_env, make_title


def play(user, title, points: int) -> QuizAttempt:
	"""A finished, trustworthy attempt worth ``points``."""
	return QuizAttempt.objects.create(
		user=user,
		title=title,
		question_ids=[],
		finished_at=timezone.now(),
		passed=True,
		points_awarded=points,
		elapsed_ms=30_000,
	)


def make_player(username: str, telegram_id: int, first_name: str):
	user = get_user_model().objects.create_user(username=username, password="x")
	TelegramUser.objects.create(
		telegram_id=telegram_id, auth_user=user, first_name=first_name
	)
	return user


class RatingScreenTests(DispatcherTestCase):
	def setUp(self) -> None:
		super().setUp()
		self.update_id = 500
		self.feed(build_command("start"))
		self.profile = TelegramUser.objects.get(telegram_id=USER.id)

	def press_rating(self) -> None:
		self.update_id += 1
		self.feed(build_callback(cb.RATING, update_id=self.update_id))

	def rows(self) -> list:
		for method in reversed(self.session.calls):
			markup = getattr(method, "reply_markup", None)
			if markup is not None and getattr(markup, "inline_keyboard", None):
				return [[button.text for button in row] for row in markup.inline_keyboard]
		return []

	def urls(self) -> list:
		for method in reversed(self.session.calls):
			markup = getattr(method, "reply_markup", None)
			if markup is not None and getattr(markup, "inline_keyboard", None):
				return [
					button.url
					for row in markup.inline_keyboard
					for button in row
					if button.url
				]
		return []

	def test_the_main_menu_offers_the_rating(self) -> None:
		self.feed(build_callback(cb.MENU, update_id=501))

		self.assertIn("🏆 Reyting", self.button_texts())

	def test_the_table_lists_players_by_points(self) -> None:
		title = make_title(code="9302", title="Naruto")
		other = make_player("ali", 9091, "Ali")
		play(other, title, 90)
		play(self.profile.auth_user, title, 30)

		self.press_rating()

		text = self.all_text()
		self.assertIn("Reyting jadvali", text)
		self.assertIn("Ali", text)
		self.assertIn("<b>90</b> ball", text)
		# The caller's own row is marked and reported above the table.
		self.assertIn("◀ siz", text)
		self.assertIn("#2", text)

	def test_a_linked_player_sees_rank_verified_and_attempts(self) -> None:
		title = make_title(code="9303", title="Bleach")
		play(self.profile.auth_user, title, 60)
		AnimeVerification.objects.create(user=self.profile.auth_user, title=title)

		self.press_rating()

		text = self.all_text()
		self.assertIn("Sizning o'rningiz", text)
		self.assertIn("#1", text)
		self.assertIn("Tasdiqlangan: 1 ta", text)
		self.assertIn("Urinishlar: 1 ta", text)
		self.assertIn("Lv.2", text)

	def test_an_empty_table_is_explained(self) -> None:
		self.press_rating()

		self.assertIn(RATING_EMPTY, self.all_text())
		self.assertIn("🏆 Reyting", self.button_texts())

	def test_the_table_is_public_for_a_visitor_without_an_account(self) -> None:
		title = make_title(code="9304", title="Bleach")
		other = make_player("vali", 9092, "Vali")
		play(other, title, 40)

		board = {"results": [
			{"rank": 1, "name": "Vali", "points": 40, "level": 1}
		], "own": None, "linked": False}
		text = render_board(board)

		self.assertIn("Vali", text)
		self.assertIn(RATING_GUEST, text)
		self.assertNotIn("Sizning o'rningiz", text)

	def test_the_keyboard_links_the_game_and_refreshes(self) -> None:
		with bot_env(BOT_SITE_URL="https://anichopar.uz"):
			self.press_rating()

		self.assertEqual(self.rows()[0], ["🎮 O'yin o'ynash"])
		self.assertEqual(self.rows()[-1], ["🔄 Yangilash", "⬅️ Asosiy menyu"])
		self.assertEqual(self.urls(), ["https://anichopar.uz/game"])

	def test_without_a_site_url_only_the_refresh_and_back_remain(self) -> None:
		with bot_env(BOT_SITE_URL=None):
			self.press_rating()

		self.assertEqual(self.rows(), [["🔄 Yangilash", "⬅️ Asosiy menyu"]])
