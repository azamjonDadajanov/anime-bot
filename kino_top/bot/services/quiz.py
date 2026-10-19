"""Bridge to the game rules for the quiz asked inside the bot.

The rules themselves live in ``games.services`` (synchronous, shared with the
website); this module only adapts them to a Telegram conversation: it resolves
the website account behind a profile, resumes an unfinished attempt, hands out
one question at a time and records the per-question times the bot measures.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from games import services as game
from games.models import QuizAttempt, QuizQuestion

from ..texts import QUIZ_NO_ACCOUNT
from ..utils import to_async


def auth_user_sync(profile: Any):
	"""Website account of a Telegram profile, or ``None`` when unlinked."""
	if profile is None or getattr(profile, "auth_user_id", None) is None:
		return None
	return profile.auth_user


def _user_or_error(profile: Any):
	user = auth_user_sync(profile)
	if user is None:
		raise game.GameError("no_account", QUIZ_NO_ACCOUNT)
	return user


def has_questions_sync(title) -> bool:
	"""Whether the title still has active quiz questions to ask."""
	return bool(QuizQuestion.objects.filter(title=title, is_active=True).exists())


def open_attempt_sync(user, title_pk: int) -> Optional[QuizAttempt]:
	return (
		QuizAttempt.objects.select_related("title")
		.filter(user=user, title_id=title_pk, finished_at__isnull=True)
		.order_by("-started_at")
		.first()
	)


def start_sync(profile: Any, title_pk: int) -> Dict[str, Any]:
	"""Open a quiz for the title, or hand back the one left unfinished.

	An ``UNFINISHED`` violation is not an error for the bot: the user simply
	continues the attempt they abandoned, rebuilt from the stored question
	shuffle so the answers they already gave still line up.
	"""
	user = _user_or_error(profile)
	try:
		return game.start_attempt_sync(user, title_pk)
	except game.GameError as exc:
		if exc.code != game.UNFINISHED:
			raise
		attempt = open_attempt_sync(user, title_pk)
		if attempt is None:  # pragma: no cover - lost between the two queries
			raise
		return game.attempt_payload(attempt)


def question_sync(profile: Any, attempt_id: int, index: int) -> Dict[str, Any]:
	"""Question ``index`` of an attempt, choices already shuffled."""
	user = _user_or_error(profile)
	attempt = (
		QuizAttempt.objects.select_related("title")
		.filter(pk=attempt_id, user=user)
		.first()
	)
	if attempt is None:
		raise game.GameError(game.NOT_FOUND, "Savol topilmadi.")
	questions = game.attempt_payload(attempt)["questions"]
	if not 0 <= index < len(questions):
		raise game.GameError(game.NOT_FOUND, "Savol topilmadi.")
	return questions[index]


def finish_sync(
	profile: Any,
	attempt_id: int,
	answers: List[int],
	elapsed_ms: int,
	question_elapsed_ms: List[int],
) -> Dict[str, Any]:
	"""Score the finished quiz; every answer carries its own time."""
	user = _user_or_error(profile)
	return game.submit_attempt_sync(
		user,
		attempt_id,
		answers,
		elapsed_ms,
		question_elapsed_ms=list(question_elapsed_ms or []),
	)


# How many players the bot's rating table shows. The table itself is public;
# the user's own rank sits above it, so a long list would only push it away.
RATING_LIMIT = 10


def leaderboard_sync(profile: Any, limit: int = RATING_LIMIT) -> Dict[str, Any]:
	"""The rating table (top players) plus the caller's own row when linked.

	This is the same table the website's "Reyting" page renders
	(``games.services.leaderboard``). ``linked`` says whether the Telegram
	visitor has a website account at all: without one the table is still shown,
	but there is no rank to report.
	"""
	user = auth_user_sync(profile)
	board = game.leaderboard(user, limit=limit)
	own = board.get("own")
	if own is not None and user is not None:
		status = game.user_status(user)
		own = {
			**own,
			"verified": status["verified_count"],
			"attempts": status["attempts"],
		}
	return {"results": board["results"], "own": own, "linked": user is not None}


def question_seconds() -> int:
	"""Seconds the user gets for one question (sync settings read only)."""
	return game.question_seconds()


def limit_ms() -> int:
	return question_seconds() * 1000


has_questions = to_async(has_questions_sync)
start = to_async(start_sync)
question = to_async(question_sync)
finish = to_async(finish_sync)
leaderboard = to_async(leaderboard_sync)
