"""Game rules: unlock checks, quiz flow, anti-cheat scoring and the prize.

All functions are synchronous (``*_sync``) so they can run inside Django REST
views directly and be reused from management commands. The bot does not call
this module — the game lives on the website.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Optional

from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone
from movies.models import MediaTitle, MediaView

from .models import (
	AnimeVerification,
	GameActivity,
	MonthlyPrize,
	QuizAttempt,
	QuizQuestion,
)

# ``start_attempt_sync`` / ``submit_attempt_sync`` outcomes.
OK = "ok"
ALREADY_VERIFIED = "already_verified"
NO_RETRY = "no_retry"
UNFINISHED = "unfinished"
DAILY_LIMIT = "daily_limit"
NOT_WATCHED = "not_watched"
NO_QUESTIONS = "no_questions"
NOT_FOUND = "not_found"
BAD_INPUT = "bad_input"


class GameError(ValueError):
	"""A rule violation the API turns into a 4xx response."""

	def __init__(self, code: str, detail: str = ""):
		super().__init__(detail or code)
		self.code = code
		self.detail = detail or code


def quiz_size() -> int:
	return max(1, int(getattr(settings, "GAME_QUIZ_SIZE", 5)))


def pass_score() -> int:
	return max(1, min(quiz_size(), int(getattr(settings, "GAME_PASS_SCORE", 4))))


def pass_score_for(size: int) -> int:
	"""Pass threshold for a quiz of ``size`` questions.

	Keeps the global ``GAME_PASS_SCORE / GAME_QUIZ_SIZE`` ratio (4/5 by
	default), so a 10-question quiz still needs 8 correct answers.
	"""
	size = max(1, int(size or 1))
	ratio = pass_score() / quiz_size()
	return max(1, min(size, math.ceil(size * ratio)))


def title_quiz_size(title, *, available: Optional[int] = None) -> int:
	"""How many questions the user answers for ``title`` after watching it.

	Per-title override (``MediaTitle.quiz_size``) wins over the global
	default and is clamped to the number of active questions.
	"""
	try:
		size = int(getattr(title, "quiz_size", 0) or 0)
	except (TypeError, ValueError):
		size = 0
	if size <= 0:
		size = quiz_size()
	if available is not None:
		size = min(size, max(1, int(available)))
	return max(1, size)


def min_parts() -> int:
	return max(1, int(getattr(settings, "GAME_MIN_PARTS", 3)))


def min_answer_seconds() -> int:
	return max(0, int(getattr(settings, "GAME_MIN_ANSWER_SECONDS", 3)))


def max_attempts_per_day() -> int:
	return max(1, int(getattr(settings, "GAME_MAX_ATTEMPTS_PER_DAY", 5)))


def activity_days_required() -> int:
	return max(1, int(getattr(settings, "GAME_ACTIVITY_DAYS", 10)))


def points_table() -> dict:
	table = getattr(settings, "GAME_POINTS", None) or {}
	return {
		MediaTitle.MediaType.ANIME: int(table.get("anime", 10)),
		MediaTitle.MediaType.SERIES: int(table.get("series", 10)),
		MediaTitle.MediaType.MOVIE: int(table.get("movie", 8)),
		MediaTitle.MediaType.MANGA: int(table.get("manga", 5)),
	}


LEVEL_NAMES = [
	"Yangi boshlovchi",
	"Mashhur",
	"O'quvchi",
	"Sensey",
	"Usta",
	"Arbob",
	"Legenda",
]
POINTS_PER_LEVEL = max(1, int(getattr(settings, "GAME_POINTS_PER_LEVEL", 50)))


def level_for(points: int) -> dict:
	"""Level number and Uzbek name for a point total."""
	level = int(points or 0) // POINTS_PER_LEVEL + 1
	name = LEVEL_NAMES[min(level, len(LEVEL_NAMES)) - 1] if level >= 1 else LEVEL_NAMES[0]
	return {
		"level": level,
		"name": name,
		"next_in": POINTS_PER_LEVEL - (int(points or 0) % POINTS_PER_LEVEL),
	}


def title_points(title: MediaTitle) -> int:
	return points_table().get(getattr(title, "type", None), 10)


def bot_views_for(user, title: MediaTitle) -> int:
	"""How many times the bot delivered this title to the user."""
	view = MediaView.objects.filter(
		user=user, title=title, source=MediaView.Source.BOT
	).first()
	return int(getattr(view, "count", 0) or 0)


def user_points(user) -> int:
	"""Total trustworthy points (suspicious attempts never count)."""
	total = (
		QuizAttempt.objects.filter(user=user, is_suspicious=False)
		.aggregate(total=Sum("points_awarded"))["total"]
		or 0
	)
	return int(total)


def user_status(user) -> dict:
	points = user_points(user)
	verified = AnimeVerification.objects.filter(user=user).count()
	attempts = QuizAttempt.objects.filter(user=user, finished_at__isnull=False).count()
	return {
		"points": points,
		"verified_count": verified,
		"attempts": attempts,
		**level_for(points),
		"quiz_size": quiz_size(),
		"pass_score": pass_score(),
		"min_parts": min_parts(),
		"no_retry": True,
	}


def eligible_titles(user, query: str = "") -> dict:
	"""Titles unlocked for a quiz plus the already verified ones."""
	viewed_ids = list(
		MediaView.objects.filter(user=user, source=MediaView.Source.BOT)
		.values_list("title_id", flat=True)
	)
	verified_ids = set(
		AnimeVerification.objects.filter(user=user).values_list("title_id", flat=True)
	)
	finished_ids = set(
		QuizAttempt.objects.filter(user=user, finished_at__isnull=False).values_list(
			"title_id", flat=True
		)
	)
	blocked = verified_ids | finished_ids

	unlocked = []
	if viewed_ids:
		titles = MediaTitle.objects.filter(pk__in=viewed_ids).order_by("title")
		if query:
			titles = titles.filter(title__icontains=query)
		for title in titles:
			if title.pk in blocked:
				continue
			if bot_views_for(user, title) < min_parts():
				continue
			active = QuizQuestion.objects.filter(title=title, is_active=True).count()
			needed = title_quiz_size(title)
			unlocked.append(
				{
					"id": title.pk,
					"title": title.title,
					"type": title.type,
					"bot_views": bot_views_for(user, title),
					"points": title_points(title),
					"questions": active,
					"quiz_size": needed,
					"ready": active >= needed,
				}
			)

	verified = []
	for verification in (
		AnimeVerification.objects.select_related("title")
		.filter(user=user)
		.order_by("-verified_at")
	):
		verified.append(
			{
				"id": verification.title_id,
				"title": verification.title.title,
				"type": verification.title.type,
				"points": verification.points,
				"verified_at": verification.verified_at,
			}
		)

	return {"unlocked": unlocked, "verified": verified, "min_parts": min_parts()}


def start_attempt_sync(user, title_id: int, *, rng: Optional[random.Random] = None) -> dict:
	"""Open a quiz for ``title_id``; raises :class:`GameError` on any violation."""
	rng = rng or random.SystemRandom()
	try:
		title_id = int(title_id)
	except (TypeError, ValueError):
		raise GameError(BAD_INPUT, "Noto'g'ri anime.")

	title = MediaTitle.objects.filter(pk=title_id).first()
	if title is None:
		raise GameError(NOT_FOUND, "Anime topilmadi.")

	if AnimeVerification.objects.filter(user=user, title=title).exists():
		raise GameError(ALREADY_VERIFIED, "Bu anime allaqachon tasdiqlangan.")

	if QuizAttempt.objects.filter(user=user, title=title, finished_at__isnull=False).exists():
		raise GameError(NO_RETRY, "Bu anime uchun qayta urinish mavjud emas.")

	if QuizAttempt.objects.filter(user=user, title=title, finished_at__isnull=True).exists():
		raise GameError(UNFINISHED, "Yopilmagan savol bor — avval javob bering.")

	today = timezone.now().date()
	attempts_today = QuizAttempt.objects.filter(
		user=user, started_at__date=today
	).count()
	if attempts_today >= max_attempts_per_day():
		raise GameError(DAILY_LIMIT, "Bugun uchun urinishlar tugadi.")

	if bot_views_for(user, title) < min_parts():
		raise GameError(
			NOT_WATCHED,
			f"Bu animeni botda kamida {min_parts()} marta ochishingiz kerak.",
		)

	pool = list(QuizQuestion.objects.filter(title=title, is_active=True))
	if not pool:
		raise GameError(NO_QUESTIONS, "Bu anime uchun savollar tayyor emas.")

	size = title_quiz_size(title, available=len(pool))
	if len(pool) < size:
		size = len(pool)
	chosen = rng.sample(pool, size)

	# Savollar va variantlar har safar tasodifiy tartibda ko'rsatiladi:
	# savollar sample, variantlar esa shuffle orqali aralashtiriladi.
	questions_payload = []
	choice_orders = []
	for question in chosen:
		order = list(range(len(question.choices)))
		rng.shuffle(order)
		choice_orders.append(order)
		questions_payload.append(
			{
				"id": question.pk,
				"text": question.text,
				"choices": [str(question.choices[index]) for index in order],
			}
		)

	attempt = QuizAttempt.objects.create(
		user=user,
		title=title,
		question_ids=[question.pk for question in chosen],
		choice_orders=choice_orders,
	)
	return {
		"attempt_id": attempt.pk,
		"title": {"id": title.pk, "title": title.title},
		"questions": questions_payload,
		"pass_score": pass_score_for(len(chosen)),
	}


def submit_attempt_sync(
	user,
	attempt_id: int,
	answers: List[int],
	elapsed_ms: int = 0,
) -> dict:
	"""Score a finished quiz; the response never reveals the correct answers."""
	try:
		attempt_id = int(attempt_id)
		elapsed_ms = max(0, int(elapsed_ms or 0))
	except (TypeError, ValueError):
		raise GameError(BAD_INPUT, "Noto'g'ri so'rov.")

	attempt = (
		QuizAttempt.objects.select_related("title")
		.filter(pk=attempt_id, user=user)
		.first()
	)
	if attempt is None:
		raise GameError(NOT_FOUND, "Savol topilmadi.")
	if attempt.finished_at is not None:
		raise GameError(NO_RETRY, "Bu savol allaqachon yopilgan.")

	question_ids = list(attempt.question_ids or [])
	if not isinstance(answers, (list, tuple)) or len(answers) != len(question_ids):
		raise GameError(BAD_INPUT, "Javoblar soni savollarga mos kelmaydi.")

	try:
		answers = [int(value) for value in answers]
	except (TypeError, ValueError):
		raise GameError(BAD_INPUT, "Javoblar noto'g'ri.")

	questions = QuizQuestion.objects.in_bulk(question_ids)
	orders = list(attempt.choice_orders or [])
	correct = 0
	for index, question_id in enumerate(question_ids):
		question = questions.get(question_id)
		if question is None:
			continue
		answer = int(answers[index])
		# Foydalanuvchi ko'rgan variant tartibidan asl indeksga qaytamiz.
		order = orders[index] if index < len(orders) else None
		if order:
			if not 0 <= answer < len(order):
				continue
			answer = int(order[answer])
		if answer == int(question.correct_index):
			correct += 1

	total = len(question_ids) or 1
	per_question = title_points(attempt.title) // total
	points = correct * per_question

	# Anti-cheat: answering the whole quiz faster than physically possible
	# zeroes the points and marks the attempt suspicious (still one-shot).
	suspicious = elapsed_ms < (min_answer_seconds() * 1000 * total)
	if suspicious:
		points = 0

	verified = (correct >= pass_score_for(total)) and not suspicious

	attempt.answers = answers
	attempt.elapsed_ms = elapsed_ms
	attempt.finished_at = timezone.now()
	attempt.passed = verified
	attempt.points_awarded = points
	attempt.is_suspicious = suspicious
	attempt.save(
		update_fields=[
			"answers",
			"elapsed_ms",
			"finished_at",
			"passed",
			"points_awarded",
			"is_suspicious",
		]
	)

	if verified:
		AnimeVerification.objects.get_or_create(
			user=user,
			title=attempt.title,
			defaults={"points": points},
		)

	today = timezone.now().date()
	GameActivity.objects.get_or_create(user=user, date=today)

	return {
		"correct": correct,
		"total": total,
		"points_awarded": points,
		"verified": verified,
		"suspicious": suspicious,
		"no_retry": True,
	}


def leaderboard(user=None, limit: int = 50) -> dict:
	"""Top players by trustworthy points; ``user``'s own rank is included."""
	limit = max(1, min(200, int(limit or 50)))
	rows = (
		QuizAttempt.objects.filter(is_suspicious=False, finished_at__isnull=False)
		.values("user_id")
		.annotate(points=Sum("points_awarded"), verified=Count("id"))
		.order_by("-points", "user_id")[:limit]
	)

	entries = []
	for index, row in enumerate(rows, start=1):
		profile = None
		from django.contrib.auth import get_user_model

		profile = get_user_model().objects.filter(pk=row["user_id"]).first()
		name = ""
		if profile is not None:
			telegram = getattr(profile, "telegram_profile", None)
			name = (
				getattr(telegram, "first_name", "")
				or getattr(profile, "username", "")
				or str(row["user_id"])
			)
		entries.append(
			{
				"rank": index,
				"user_id": row["user_id"],
				"name": name,
				"points": int(row["points"] or 0),
				"verified": int(row["verified"] or 0),
				**level_for(int(row["points"] or 0)),
			}
		)

	own = None
	if user is not None:
		own_points = user_points(user)
		higher = (
			QuizAttempt.objects.filter(is_suspicious=False, finished_at__isnull=False)
			.values("user_id")
			.annotate(points=Sum("points_awarded"))
			.filter(points__gt=own_points)
			.count()
		)
		own = {"rank": higher + 1, "points": own_points, **level_for(own_points)}

	return {"results": entries, "own": own}


def award_monthly_prize_sync(year: int, month: int) -> Optional[MonthlyPrize]:
	"""Give a monthly subscription to the most active non-subscriber player.

	Eligibility: at least ``GAME_ACTIVITY_DAYS`` distinct active days in the
	month AND no live subscription at award time. The command is idempotent —
	one prize per (year, month).
	"""
	if MonthlyPrize.objects.filter(year=year, month=month).exists():
		return None

	start = date(year, month, 1)
	if month == 12:
		end = date(year + 1, 1, 1)
	else:
		end = date(year, month + 1, 1)

	active_ids = set(
		GameActivity.objects.filter(date__gte=start, date__lt=end)
		.values_list("user_id", flat=True)
	)
	if not active_ids:
		return None

	required = activity_days_required()
	counts = (
		GameActivity.objects.filter(date__gte=start, date__lt=end, user_id__in=active_ids)
		.values("user_id")
		.annotate(days=Count("id"))
		.filter(days__gte=required)
	)
	eligible_ids = [row["user_id"] for row in counts]
	if not eligible_ids:
		return None

	from users.models import Subscription

	now = timezone.now()
	best_user_id = None
	best_points = -1
	for user_id in eligible_ids:
		subscription = Subscription.objects.filter(user_id=user_id).first()
		if subscription is not None and subscription.is_active:
			continue
		points = user_points(_user_or_none(user_id))
		if points > best_points:
			best_points = points
			best_user_id = user_id

	if best_user_id is None or best_points <= 0:
		return None

	subscription, _ = Subscription.objects.get_or_create(user_id=best_user_id)
	subscription.activate("monthly")
	return MonthlyPrize.objects.create(
		year=year,
		month=month,
		user_id=best_user_id,
		points=best_points,
	)


def _user_or_none(user_id: int):
	from django.contrib.auth import get_user_model

	return get_user_model().objects.filter(pk=user_id).first()
