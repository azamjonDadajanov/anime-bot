"""The buttons every delivered media message carries, and the quiz they open.

Driven through the real dispatcher: the keyboard is the one Telegram would
show, the favourite star rebuilds it in place, and the quiz is played one
message per question with a patched clock so the speed bonus is deterministic.
"""

from __future__ import annotations

from unittest import mock

from games.models import QuizAttempt, QuizQuestion
from games.tests import make_questions, watch_via_bot
from movies.models import MediaPart, MediaTitle, TelegramChannel
from users.models import FavoriteContent, TelegramUser

from .. import callbacks as cb
from ..handlers.user import quiz as quiz_handlers
from ..services import quiz as quiz_service
from ..texts import (
	FAVORITE_ADDED,
	FAVORITE_REMOVED,
	QUIZ_NO_QUESTIONS,
	QUIZ_STALE,
	QUIZ_TIME_UP,
	WATCH_PARTS_HINT,
)
from .base import DispatcherTestCase
from .fakes import USER, build_callback, build_command
from .helpers import bot_env, make_channel, make_media, make_part, make_title


class MediaActionButtonsTests(DispatcherTestCase):
	"""Navigator first, then favourite, quiz and main menu — on every file."""

	def _markup(self):
		"""Keyboard of the last message the bot attached one to."""
		for method in reversed(self.session.calls):
			markup = getattr(method, "reply_markup", None)
			if markup is not None and getattr(markup, "inline_keyboard", None):
				return markup
		return None

	def _rows(self):
		markup = self._markup()
		if markup is None:
			return []
		return [[button.text for button in row] for row in markup.inline_keyboard]

	def _callbacks(self):
		markup = self._markup()
		if markup is None:
			return []
		return [[button.callback_data for button in row] for row in markup.inline_keyboard]

	def _season_parts(self, title, count: int = 3):
		parts = [make_part(title, number=number, season=1) for number in range(1, count + 1)]
		for part in parts:
			make_media(part, file_id=f"file-{part.number}", media_type="video", order=1)
		return parts

	def test_actions_follow_the_parts_navigator(self) -> None:
		title = make_title(code="8101", title="Action Anime")
		parts = self._season_parts(title)

		self.feed(build_callback(f"watch:{parts[0].pk}"))

		rows = self._rows()
		self.assertEqual(rows[0], ["🟢 1", "2", "3"])
		self.assertEqual(rows[1], ["⬅️ Oldingi qism", "1-mavsum", "Keyingi qism ➡️"])
		self.assertEqual(rows[2], ["⭐️ Sevimlilarga qo'shish"])
		self.assertEqual(rows[3], ["⬅️ Asosiy menyu"])
		callbacks = self._callbacks()
		self.assertEqual(callbacks[2][0], f"favm:{title.pk}:{parts[0].pk}")
		self.assertEqual(callbacks[3][0], cb.MENU)

	def test_the_star_under_media_toggles_the_favourite(self) -> None:
		title = make_title(code="8102", title="Starred Anime")
		part = make_part(title, number=1, season=1)
		make_media(part, file_id="star-file", media_type="video")
		self.feed(build_callback(f"watch:{part.pk}"))
		self.assertFalse(FavoriteContent.objects.filter(content=title).exists())

		self.session.reset()
		self.feed(build_callback(f"favm:{title.pk}:{part.pk}", update_id=9))

		self.assertTrue(FavoriteContent.objects.filter(content=title).exists())
		alerts = [method.text for method in self.session.methods("AnswerCallbackQuery")]
		self.assertIn(FAVORITE_ADDED, alerts)
		# Only the keyboard is refreshed; the delivered file stays where it is.
		self.assertEqual(self.session.methods("EditMessageMedia"), [])
		self.assertEqual(self._rows()[0], ["💔 Sevimlilardan olib tashlash"])

		self.session.reset()
		self.feed(build_callback(f"favm:{title.pk}:{part.pk}", update_id=10))

		self.assertFalse(FavoriteContent.objects.filter(content=title).exists())
		self.assertIn(FAVORITE_REMOVED, [
			method.text for method in self.session.methods("AnswerCallbackQuery")
		])
		self.assertEqual(self._rows()[0], ["⭐️ Sevimlilarga qo'shish"])

	def test_the_quiz_button_appears_only_when_the_title_has_questions(self) -> None:
		with_bank = make_title(code="8103", title="Quiz Anime")
		part_a = make_part(with_bank, number=1, season=1)
		make_media(part_a, file_id="qa-file", media_type="video")
		make_questions(with_bank, count=2)

		without_bank = make_title(code="8104", title="Silent Anime")
		part_b = make_part(without_bank, number=1, season=1)
		make_media(part_b, file_id="sa-file", media_type="video")

		self.feed(build_callback(f"watch:{part_a.pk}"))
		self.assertIn("Testlarni ishlash", self.button_texts())
		self.assertIn(f"qz:{with_bank.pk}", self._callbacks()[1][0])

		self.session.reset()
		self.feed(build_callback(f"watch:{part_b.pk}", update_id=9))

		self.assertNotIn("Testlarni ishlash", self.button_texts())
		self.assertEqual(self._rows()[0], ["⭐️ Sevimlilarga qo'shish"])

	def test_manga_keeps_the_reader_link_above_the_actions(self) -> None:
		title = make_title(
			code="8105", title="Action Manga", media_type=MediaTitle.MediaType.MANGA
		)
		part = make_part(title, number=1)
		make_media(part, file_id="manga-page", media_type="photo")

		with bot_env(BOT_SITE_URL="https://kino.test"):
			self.feed(build_callback(f"watch:{part.pk}"))

		rows = self._rows()
		self.assertEqual(len(rows), 3)
		self.assertEqual(rows[0], ["📖 Saytda o'qish"])
		self.assertEqual(rows[1], ["⭐️ Sevimlilarga qo'shish"])
		self.assertEqual(rows[2], ["⬅️ Asosiy menyu"])
		self.assertEqual(
			self._markup().inline_keyboard[0][0].url,
			f"https://kino.test/read/{title.slug}",
		)

	def test_the_album_hint_carries_the_action_rows(self) -> None:
		"""A media group cannot hold a keyboard, so its hint message does."""
		title = make_title(code="8106", title="Scanned Action")
		part = make_part(title, number=1, season=1)
		make_media(part, file_id="scan-1", media_type="photo", order=1)
		make_media(part, file_id="scan-2", media_type="photo", order=2)

		self.feed(build_callback(f"watch:{part.pk}"))

		self.assertEqual(len(self.session.methods("SendMediaGroup")), 1)
		hint = [
			method
			for method in self.session.methods("SendMessage")
			if method.text == WATCH_PARTS_HINT
		]
		self.assertEqual(len(hint), 1)
		rows = [
			[button.text for button in row] for row in hint[0].reply_markup.inline_keyboard
		]
		self.assertEqual(rows, [["⭐️ Sevimlilarga qo'shish"], ["⬅️ Asosiy menyu"]])


class QuizFlowTests(DispatcherTestCase):
	"""One question per message, timed, scored by how fast each answer came."""

	def setUp(self) -> None:
		super().setUp()
		self.feed(build_command("start"))

	def _clock(self, start: float = 1_000.0) -> dict:
		"""Replace the quiz module's clock with a holder the test can move."""
		clock = {"now": start}
		patcher = mock.patch.object(
			quiz_handlers, "_now", side_effect=lambda: clock["now"]
		)
		patcher.start()
		self.addCleanup(patcher.stop)
		return clock

	def _profile(self) -> TelegramUser:
		return TelegramUser.objects.get(telegram_id=USER.id)

	def _title_with_quiz(self, *, code: str, size: int = 2, questions: bool = True) -> MediaTitle:
		title = make_title(code=code, title=f"Quiz {code}")
		title.quiz_size = size
		title.save(update_fields=["quiz_size"])
		part = make_part(title, number=1, season=1)
		make_media(part, file_id=f"file-{code}", media_type="video")
		if questions:
			make_questions(title, count=size)
		self._unlock(title)
		return title

	def _unlock(self, title) -> None:
		"""Record the three bot deliveries the game requires."""
		watch_via_bot(self._profile().auth_user, title)

	def _alerts(self) -> list:
		return [
			method.text
			for method in self.session.methods("AnswerCallbackQuery")
			if getattr(method, "text", None)
		]

	def _sent_texts(self) -> list:
		return [method.text for method in self.session.methods("SendMessage")]

	def _correct_choice(self, attempt: QuizAttempt, index: int) -> int:
		"""Position of the right answer inside the shuffle the user saw."""
		question = QuizQuestion.objects.get(pk=attempt.question_ids[index])
		return list(attempt.choice_orders[index]).index(question.correct_index)

	def _play(self, title, *, times=(4.0, 28.0), correct: bool = True) -> QuizAttempt:
		"""Start the quiz and answer every question after ``times[i]`` seconds."""
		clock = self._clock()
		self.feed(build_callback(f"qz:{title.pk}", update_id=20))
		attempt = QuizAttempt.objects.get()
		for index, delay in enumerate(times):
			clock["now"] += delay
			choice = self._correct_choice(attempt, index)
			if not correct:
				choice = (choice + 1) % len(attempt.choice_orders[index])
			self.feed(
				build_callback(
					f"qza:{attempt.pk}:{index}:{choice}", update_id=21 + index
				)
			)
		attempt.refresh_from_db()
		return attempt

	def test_starting_the_quiz_sends_the_first_shuffled_question(self) -> None:
		title = self._title_with_quiz(code="9001")
		self.session.reset()

		self.feed(build_callback(f"qz:{title.pk}", update_id=20))

		self.assertEqual(QuizAttempt.objects.count(), 1)
		attempt = QuizAttempt.objects.get()
		text = "\n".join(self._sent_texts())
		self.assertIn("Savol 1/2", text)
		self.assertIn("soniya", text)
		self.assertIn("to'g'ri javob kerak", text)
		self.assertNotIn("Savol 2/2", text)
		question = QuizQuestion.objects.get(pk=attempt.question_ids[0])
		labels = set(self.button_texts().split("\n"))
		self.assertEqual(labels, {str(choice) for choice in question.choices})
		# The attempt stays open until the last question is answered.
		self.assertEqual(len(attempt.question_ids), 2)
		self.assertIsNone(attempt.finished_at)

	def test_the_next_question_replaces_the_previous_message(self) -> None:
		title = self._title_with_quiz(code="9002")
		self.session.reset()

		self.feed(build_callback(f"qz:{title.pk}", update_id=20))
		first_id = self.session._message_seq  # the id the fake session just handed out
		attempt = QuizAttempt.objects.get()

		self.feed(
			build_callback(
				f"qza:{attempt.pk}:0:{self._correct_choice(attempt, 0)}", update_id=21
			)
		)

		deleted = [method.message_id for method in self.session.methods("DeleteMessage")]
		self.assertEqual(deleted, [first_id])
		self.assertIn("Savol 2/2", "\n".join(self._sent_texts()))

	def test_each_answer_is_scored_by_the_time_it_took(self) -> None:
		title = self._title_with_quiz(code="9003")
		self.session.reset()

		attempt = self._play(title)

		self.assertEqual(attempt.elapsed_ms, 32_000)
		self.assertFalse(attempt.is_suspicious)
		self.assertTrue(attempt.passed)
		# Flat scoring would pay 10 (10 // 2 * 2). The near-limit answer keeps
		# only its half: speed_factor floors at SPEED_FLOOR, so 4.3 + 2.5 -> 7.
		self.assertEqual(attempt.points_awarded, 7)
		result = self._sent_texts()[-1]
		self.assertIn("Test yakunlandi", result)
		self.assertIn("2 / 2 to'g'ri javob", result)
		self.assertIn("<b>7</b>", result)
		self.assertIn("tasdiqlandi", result)
		# The new points also land in the rating table, so the result says where.
		self.assertIn("Reytingdagi o'rningiz", result)
		# The result hands the player back to the main menu keyboard.
		self.assertIn("Katalog", self.button_texts())

	def test_a_timed_out_answer_counts_as_a_miss(self) -> None:
		title = self._title_with_quiz(code="9004")
		self.session.reset()

		attempt = self._play(title, times=(35.0, 4.0))

		self.assertIn(QUIZ_TIME_UP, self._alerts())
		# The window is capped at the limit, so the timeout never reads as speed.
		self.assertEqual(attempt.elapsed_ms, 34_000)
		self.assertEqual(attempt.points_awarded, 4)
		self.assertFalse(attempt.passed)
		self.assertFalse(attempt.is_suspicious)
		result = self._sent_texts()[-1]
		self.assertIn("1 / 2 to'g'ri javob", result)
		self.assertIn("O'tib bo'lmadi", result)

	def test_answering_after_the_finish_is_reported_as_stale(self) -> None:
		title = self._title_with_quiz(code="9005")
		self.session.reset()
		attempt = self._play(title)

		self.session.reset()
		self.feed(
			build_callback(
				f"qza:{attempt.pk}:1:{self._correct_choice(attempt, 1)}", update_id=30
			)
		)

		self.assertIn(QUIZ_STALE, self._alerts())
		self.assertEqual([text for text in self._sent_texts() if "yakunlandi" in text], [])

	def test_an_abandoned_attempt_is_resumed_not_spent(self) -> None:
		title = self._title_with_quiz(code="9006")
		self.session.reset()

		self.feed(build_callback(f"qz:{title.pk}", update_id=20))
		attempt = QuizAttempt.objects.get()
		self.feed(
			build_callback(
				f"qza:{attempt.pk}:0:{self._correct_choice(attempt, 0)}", update_id=21
			)
		)
		# The user gives up for the main menu: the state row is dropped.
		self.feed(build_callback(cb.MENU, update_id=22))

		self.session.reset()
		self.feed(build_callback(f"qz:{title.pk}", update_id=23))

		self.assertEqual(QuizAttempt.objects.count(), 1)
		self.assertEqual(self._alerts(), [])
		self.assertIn("Savol 1/2", "\n".join(self._sent_texts()))

	def test_a_title_without_questions_refuses_the_quiz(self) -> None:
		title = self._title_with_quiz(code="9007", questions=False)
		self.session.reset()

		self.feed(build_callback(f"qz:{title.pk}", update_id=20))

		self.assertIn(QUIZ_NO_QUESTIONS, self._alerts())
		self.assertEqual(QuizAttempt.objects.count(), 0)

	def test_a_profile_without_a_website_account_is_told_to_link(self) -> None:
		title = self._title_with_quiz(code="9008")
		self.session.reset()

		# The profile middleware relinks a missing account on every update, so
		# the guard itself is what has to be reached.
		with mock.patch.object(quiz_service, "auth_user_sync", return_value=None):
			self.feed(build_callback(f"qz:{title.pk}", update_id=20))

		self.assertEqual(QuizAttempt.objects.count(), 0)
		alerts = self._alerts()
		self.assertEqual(len(alerts), 1)
		self.assertIn("hisobingizni saytga ulang", alerts[0])

	def test_the_subscription_gate_lets_the_media_buttons_through(self) -> None:
		make_channel(
			chat_id=-1005550009999,
			title="Majburiy kanal 5",
			purpose=TelegramChannel.Purpose.REQUIRED,
		)
		self.session.member_status = "left"
		title = self._title_with_quiz(code="9009")
		part_pk = MediaPart.objects.get(content=title).pk
		self.session.reset()

		self.feed(build_callback(f"qz:{title.pk}", update_id=20))

		text = self.all_text()
		self.assertNotIn("Majburiy obuna", text)
		self.assertIn("Savol 1/2", text)

		self.session.reset()
		self.feed(build_callback(f"favm:{title.pk}:{part_pk}", update_id=21))

		self.assertNotIn("Majburiy obuna", self.all_text())
		self.assertTrue(FavoriteContent.objects.filter(content=title).exists())
