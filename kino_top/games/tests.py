from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from movies.models import MediaTitle, MediaView
from rest_framework.test import APIClient
from users.models import Subscription

from .models import (
	AnimeVerification,
	GameActivity,
	MonthlyPrize,
	QuizAttempt,
	QuizQuestion,
)
from .services import (
	ALREADY_VERIFIED,
	BAD_INPUT,
	DAILY_LIMIT,
	NO_QUESTIONS,
	NO_RETRY,
	NOT_FOUND,
	NOT_WATCHED,
	UNFINISHED,
	GameError,
	award_monthly_prize_sync,
	bot_views_for,
	eligible_titles,
	level_for,
	start_attempt_sync,
	submit_attempt_sync,
	user_points,
	user_status,
)


def make_user(username: str = "player"):
	return get_user_model().objects.create_user(username=username, password="x")


def make_title(title: str = "Naruto", media_type=MediaTitle.MediaType.ANIME):
	return MediaTitle.objects.create(title=title, type=media_type, slug=title.lower())


def make_questions(title, count: int = 5) -> list:
	questions = []
	for index in range(count):
		questions.append(
			QuizQuestion.objects.create(
				title=title,
				text=f"Savol {index + 1}?",
				choices=["A", "B", "C", "D"],
				correct_index=index % 4,
			)
		)
	return questions


def watch_via_bot(user, title, times: int = 3) -> None:
	for _ in range(times):
		MediaView.record(user, title, part=None, source=MediaView.Source.BOT)


def as_presented(original_answers, choice_orders) -> list:
	"""Map original choice indices to the shuffled indices the user saw."""
	presented = []
	for order, original in zip(choice_orders, original_answers):
		presented.append(list(order).index(original))
	return presented


def original_answers_for(attempt) -> list:
	questions = QuizQuestion.objects.in_bulk(attempt.question_ids)
	return as_presented(
		[questions[qid].correct_index for qid in attempt.question_ids],
		attempt.choice_orders,
	)


class GameServiceTests(TestCase):
	def setUp(self):
		self.user = make_user()
		self.title = make_title()
		make_questions(self.title)
		watch_via_bot(self.user, self.title)

	def test_unlock_requires_min_bot_views(self) -> None:
		fresh_user = make_user("fresh")
		payload = eligible_titles(fresh_user)
		self.assertEqual(payload["unlocked"], [])

		watch_via_bot(fresh_user, self.title, times=2)
		payload = eligible_titles(fresh_user)
		self.assertEqual(payload["unlocked"], [])

		watch_via_bot(fresh_user, self.title, times=1)
		payload = eligible_titles(fresh_user)
		self.assertEqual(len(payload["unlocked"]), 1)
		self.assertEqual(payload["unlocked"][0]["id"], self.title.pk)
		self.assertTrue(payload["unlocked"][0]["ready"])

	def test_start_returns_questions_without_answers(self) -> None:
		payload = start_attempt_sync(self.user, self.title.pk)
		self.assertIn("attempt_id", payload)
		self.assertEqual(len(payload["questions"]), 5)
		self.assertEqual(payload["pass_score"], 4)
		for question in payload["questions"]:
			self.assertNotIn("correct_index", question)
			self.assertNotIn("correct_choice", question)
			self.assertEqual(len(question["choices"]), 4)

	def test_start_shuffles_choices_as_a_permutation(self) -> None:
		payload = start_attempt_sync(self.user, self.title.pk)
		attempt = QuizAttempt.objects.get(pk=payload["attempt_id"])
		questions = QuizQuestion.objects.in_bulk(attempt.question_ids)
		for question_id, order, sent in zip(
			attempt.question_ids, attempt.choice_orders, payload["questions"]
		):
			self.assertEqual(sorted(order), list(range(len(questions[question_id].choices))))
			expected = [str(questions[question_id].choices[i]) for i in order]
			self.assertEqual(sent["choices"], expected)

	def test_per_title_quiz_size_limits_the_quiz(self) -> None:
		self.title.quiz_size = 3
		self.title.save(update_fields=["quiz_size"])
		make_questions(self.title, count=10)

		payload = start_attempt_sync(self.user, self.title.pk)
		self.assertEqual(len(payload["questions"]), 3)
		self.assertEqual(payload["pass_score"], 3)  # ceil(3 * 4/5)

		titles = eligible_titles(self.user)["unlocked"]
		self.assertEqual(titles[0]["quiz_size"], 3)
		self.assertTrue(titles[0]["ready"])

	def test_submit_scoring_and_verification(self) -> None:
		payload = start_attempt_sync(self.user, self.title.pk)
		attempt = QuizAttempt.objects.get(pk=payload["attempt_id"])
		originals = [
			QuizQuestion.objects.get(pk=qid).correct_index
			for qid in attempt.question_ids
		]

		# 4 correct, 1 wrong → pass.
		answers = as_presented(originals, attempt.choice_orders)
		answers[4] = (answers[4] + 1) % 4

		result = submit_attempt_sync(self.user, attempt.pk, answers, elapsed_ms=60_000)
		self.assertEqual(result["correct"], 4)
		self.assertEqual(result["total"], 5)
		self.assertTrue(result["verified"])
		self.assertEqual(result["points_awarded"], 4 * 2)  # 10 points // 5 * 4
		# The response must not reveal which answers were right.
		self.assertNotIn("answers", result)
		self.assertNotIn("correct_indices", result)

		self.assertTrue(
			AnimeVerification.objects.filter(user=self.user, title=self.title).exists()
		)
		self.assertEqual(user_points(self.user), 8)
		status = user_status(self.user)
		self.assertEqual(status["verified_count"], 1)
		self.assertEqual(status["level"], 1)

	def test_failed_quiz_cannot_be_retried(self) -> None:
		payload = start_attempt_sync(self.user, self.title.pk)
		attempt = QuizAttempt.objects.get(pk=payload["attempt_id"])
		originals = [
			QuizQuestion.objects.get(pk=qid).correct_index
			for qid in attempt.question_ids
		]
		answers = as_presented(
			[(index + 1) % 4 for index in originals], attempt.choice_orders
		)

		# All wrong → fail, but still one-shot.
		result = submit_attempt_sync(self.user, attempt.pk, answers, elapsed_ms=60_000)
		self.assertEqual(result["correct"], 0)
		self.assertFalse(result["verified"])
		self.assertFalse(
			AnimeVerification.objects.filter(user=self.user, title=self.title).exists()
		)

		with self.assertRaises(GameError) as ctx:
			start_attempt_sync(self.user, self.title.pk)
		self.assertEqual(ctx.exception.code, NO_RETRY)

	def test_double_submit_is_rejected(self) -> None:
		payload = start_attempt_sync(self.user, self.title.pk)
		attempt = QuizAttempt.objects.get(pk=payload["attempt_id"])
		answers = [0] * 5
		submit_attempt_sync(self.user, attempt.pk, answers, elapsed_ms=60_000)
		with self.assertRaises(GameError) as ctx:
			submit_attempt_sync(self.user, attempt.pk, answers, elapsed_ms=60_000)
		self.assertEqual(ctx.exception.code, NO_RETRY)

	def test_verified_title_is_not_offered_again(self) -> None:
		payload = start_attempt_sync(self.user, self.title.pk)
		attempt = QuizAttempt.objects.get(pk=payload["attempt_id"])
		answers = original_answers_for(attempt)
		submit_attempt_sync(self.user, attempt.pk, answers, elapsed_ms=60_000)

		payload = eligible_titles(self.user)
		self.assertEqual(payload["unlocked"], [])
		self.assertEqual(len(payload["verified"]), 1)
		with self.assertRaises(GameError) as ctx:
			start_attempt_sync(self.user, self.title.pk)
		self.assertEqual(ctx.exception.code, ALREADY_VERIFIED)

	def test_unlocked_but_unwatched_title_is_blocked(self) -> None:
		other = make_title("Boruto")
		make_questions(other)
		with self.assertRaises(GameError) as ctx:
			start_attempt_sync(self.user, other.pk)
		self.assertEqual(ctx.exception.code, NOT_WATCHED)

	def test_daily_attempt_limit(self) -> None:
		for index in range(5):
			title = make_title(f"Title{index}")
			make_questions(title)
			watch_via_bot(self.user, title)
			start_attempt_sync(self.user, title.pk)

		title = make_title("Overflow")
		make_questions(title)
		watch_via_bot(self.user, title)
		with self.assertRaises(GameError) as ctx:
			start_attempt_sync(self.user, title.pk)
		self.assertEqual(ctx.exception.code, DAILY_LIMIT)

	def test_fast_answers_are_suspicious_and_score_zero(self) -> None:
		payload = start_attempt_sync(self.user, self.title.pk)
		attempt = QuizAttempt.objects.get(pk=payload["attempt_id"])
		answers = original_answers_for(attempt)

		# 5 questions * 3s minimum = 15s; 1s total is impossible.
		result = submit_attempt_sync(self.user, attempt.pk, answers, elapsed_ms=1_000)
		self.assertEqual(result["correct"], 5)
		self.assertEqual(result["points_awarded"], 0)
		self.assertTrue(result["suspicious"])
		self.assertFalse(result["verified"])
		self.assertEqual(user_points(self.user), 0)
		attempt.refresh_from_db()
		self.assertTrue(attempt.is_suspicious)

	def test_bad_answers_length_is_rejected(self) -> None:
		payload = start_attempt_sync(self.user, self.title.pk)
		with self.assertRaises(GameError) as ctx:
			submit_attempt_sync(self.user, payload["attempt_id"], [0, 1], elapsed_ms=30_000)
		self.assertEqual(ctx.exception.code, BAD_INPUT)

	def test_missing_question_bank(self) -> None:
		empty = make_title("Empty")
		QuizQuestion.objects.filter(title=empty).delete()
		watch_via_bot(self.user, empty)
		with self.assertRaises(GameError) as ctx:
			start_attempt_sync(self.user, empty.pk)
		self.assertEqual(ctx.exception.code, NO_QUESTIONS)

	def test_unknown_title(self) -> None:
		with self.assertRaises(GameError) as ctx:
			start_attempt_sync(self.user, 99_999)
		self.assertEqual(ctx.exception.code, NOT_FOUND)

	def test_level_for_points(self) -> None:
		self.assertEqual(level_for(0)["level"], 1)
		self.assertEqual(level_for(49)["level"], 1)
		self.assertEqual(level_for(50)["level"], 2)
		self.assertEqual(level_for(120)["level"], 3)


class MonthlyPrizeTests(TestCase):
	def setUp(self):
		self.active = make_user("active_player")
		self.subscriber = make_user("subscriber")
		subscription, _ = Subscription.objects.get_or_create(user=self.subscriber)
		subscription.grant_days(365)

	def _record_activity(self, user, year: int, month: int, days: int) -> None:
		for day in range(1, days + 1):
			GameActivity.objects.get_or_create(user=user, date=date(year, month, day))

	def test_most_active_non_subscriber_wins(self) -> None:
		self._record_activity(self.active, 2026, 9, 10)
		self._record_activity(self.subscriber, 2026, 9, 12)

		title = make_title("Prize")
		QuizAttempt.objects.create(
			user=self.active,
			title=title,
			question_ids=[1, 2, 3, 4, 5],
			answers=[0, 0, 0, 0, 0],
			finished_at="2026-09-10 10:00:00",
			points_awarded=50,
		)

		prize = award_monthly_prize_sync(2026, 9)
		self.assertIsNotNone(prize)
		self.assertEqual(prize.user_id, self.active.pk)
		self.assertEqual(prize.points, 50)

		subscription = Subscription.objects.get(user=self.active)
		self.assertTrue(subscription.is_active)
		self.assertEqual(subscription.plan, "monthly")

		# Idempotent for the same month.
		self.assertIsNone(award_monthly_prize_sync(2026, 9))

	def test_not_enough_activity_days(self) -> None:
		self._record_activity(self.active, 2026, 9, 5)
		self.assertIsNone(award_monthly_prize_sync(2026, 9))
		self.assertFalse(MonthlyPrize.objects.exists())

	def test_all_subscribers_means_no_prize(self) -> None:
		self._record_activity(self.subscriber, 2026, 9, 15)
		self.assertIsNone(award_monthly_prize_sync(2026, 9))


class GameApiTests(TestCase):
	def setUp(self):
		self.client = APIClient()
		self.user = make_user()
		self.client.force_authenticate(self.user)
		self.title = make_title()
		make_questions(self.title)
		watch_via_bot(self.user, self.title)

	def test_status_requires_auth(self) -> None:
		anonymous = APIClient()
		response = anonymous.get(reverse("games:game-status"))
		self.assertEqual(response.status_code, 401)

	def test_status_endpoint(self) -> None:
		response = self.client.get(reverse("games:game-status"))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.data["points"], 0)
		self.assertEqual(response.data["quiz_size"], 5)
		self.assertTrue(response.data["no_retry"])

	def test_titles_endpoint(self) -> None:
		response = self.client.get(reverse("games:game-titles"))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(len(response.data["unlocked"]), 1)
		self.assertEqual(response.data["unlocked"][0]["id"], self.title.pk)

	def test_quiz_flow_via_api(self) -> None:
		start = self.client.post(
			reverse("games:quiz-start"), {"title_id": self.title.pk}, format="json"
		)
		self.assertEqual(start.status_code, 201)
		attempt_id = start.data["attempt_id"]
		answers = [0, 0, 0, 0, 0]

		submit = self.client.post(
			reverse("games:quiz-submit"),
			{"attempt_id": attempt_id, "answers": answers, "elapsed_ms": 30_000},
			format="json",
		)
		self.assertEqual(submit.status_code, 200)
		self.assertIn("correct", submit.data)
		self.assertNotIn("correct_index", submit.data)

		retry = self.client.post(
			reverse("games:quiz-start"), {"title_id": self.title.pk}, format="json"
		)
		self.assertEqual(retry.status_code, 409)
		self.assertEqual(retry.data["code"], NO_RETRY)

	def test_quiz_start_for_unwatched_title(self) -> None:
		other = make_title("Locked")
		make_questions(other)
		response = self.client.post(
			reverse("games:quiz-start"), {"title_id": other.pk}, format="json"
		)
		self.assertEqual(response.status_code, 403)
		self.assertEqual(response.data["code"], NOT_WATCHED)

	def test_leaderboard_endpoint(self) -> None:
		response = self.client.get(reverse("games:game-leaderboard"))
		self.assertEqual(response.status_code, 200)
		self.assertIn("results", response.data)
		self.assertIn("own", response.data)
		self.assertEqual(response.data["own"]["points"], 0)
