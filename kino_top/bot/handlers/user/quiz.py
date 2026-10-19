"""The in-bot quiz: one question per message, scored by answering speed.

The rules (unlock checks, shuffling, scoring) live in ``games.services`` and
are shared with the website; this router only turns them into a conversation:
a question is asked, its message is deleted the moment the next one arrives,
and the time the user spent on every answer is handed back to the scorer so a
faster correct answer is worth more points.
"""

from __future__ import annotations

import logging
import time

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from games.services import GameError

from ... import callbacks as cb
from ...keyboards.user import main_menu, quiz_keyboard
from ...services import quiz as quiz_service
from ...services.media import get_title_by_pk
from ...states import UserQuizStates
from ...texts import (
	NOT_FOUND,
	QUIZ_FAILED,
	QUIZ_FIRST_HINT,
	QUIZ_NO_QUESTIONS,
	QUIZ_PASSED,
	QUIZ_QUESTION,
	QUIZ_RANK,
	QUIZ_RESULT,
	QUIZ_STALE,
	QUIZ_SUSPICIOUS,
	QUIZ_TIME_UP,
)
from ...utils import escape_html, parse_int
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="user-quiz")


def _now() -> float:
	"""Wall clock in seconds — the seam tests use to fake slow answers."""
	return time.time()


async def _drop(state: FSMContext, bot) -> None:
	"""Delete the question currently on screen, if there is one."""
	data = await state.get_data()
	message_id = data.get("quiz_msg_id")
	chat_id = data.get("quiz_chat_id")
	if not message_id or not chat_id:
		return
	try:
		await bot.delete_message(chat_id, message_id)
	except TelegramAPIError as exc:
		logger.debug("Quiz message %s could not be deleted: %s", message_id, exc)


async def _ask(
	callback: CallbackQuery,
	state: FSMContext,
	bot,
	*,
	attempt_id: int,
	question,
	index: int,
	total: int,
	title: str,
	pass_score: int,
	answers,
	elapsed,
) -> None:
	"""Send question ``index``, replacing the one before it."""
	message = callback.message
	if message is None:  # pragma: no cover - our buttons always sit on a message
		await callback.answer(NOT_FOUND, show_alert=True)
		return
	await _drop(state, bot)

	text = QUIZ_QUESTION.format(
		index=index + 1,
		total=total,
		title=escape_html(title),
		text=escape_html(question["text"]),
		seconds=quiz_service.question_seconds(),
		pass_score=pass_score,
	)
	if index == 0:
		text = f"{text}\n{QUIZ_FIRST_HINT}"

	sent = await message.answer(
		text, reply_markup=quiz_keyboard(attempt_id, index, question["choices"])
	)
	await state.set_state(UserQuizStates.question)
	await state.update_data(
		quiz_id=attempt_id,
		quiz_index=index,
		quiz_total=total,
		quiz_title=title,
		quiz_pass_score=pass_score,
		quiz_answers=list(answers),
		quiz_elapsed=list(elapsed),
		quiz_msg_id=sent.message_id,
		quiz_chat_id=sent.chat.id,
		quiz_at=_now(),
	)


async def _finish(
	callback: CallbackQuery,
	state: FSMContext,
	profile,
	bot,
	is_admin: bool,
	*,
	answers,
	elapsed,
) -> None:
	"""Score the attempt and show the result in place of the last question."""
	data = await state.get_data()
	attempt_id = int(data.get("quiz_id") or 0)
	total = int(data.get("quiz_total") or 0)
	title = data.get("quiz_title") or ""

	# A question the flow never got an answer for (an interrupted run) counts
	# as a miss, with the full window so it never skews the anti-cheat total.
	limit = quiz_service.limit_ms()
	while len(answers) < total:
		answers.append(-1)
		elapsed.append(limit)

	try:
		result = await quiz_service.finish(
			profile, attempt_id, answers, sum(elapsed), elapsed
		)
	except GameError as exc:
		# Already finished / vanished: stop the flow instead of scoring twice.
		await callback.answer(exc.detail[:200], show_alert=True)
		await state.clear()
		return

	await _drop(state, bot)
	await state.clear()

	outcome = (
		QUIZ_SUSPICIOUS
		if result["suspicious"]
		else (QUIZ_PASSED if result["verified"] else QUIZ_FAILED)
	)
	# The result is the natural moment to show where the new points put the
	# player in the rating table (the same one the 🏆 Reyting screen shows).
	text = QUIZ_RESULT.format(
		title=escape_html(title),
		correct=result["correct"],
		total=result["total"],
		points=result["points_awarded"],
		outcome=outcome,
	)
	board = await quiz_service.leaderboard(profile)
	own = board.get("own")
	if own:
		text += "\n\n" + QUIZ_RANK.format(
			rank=own["rank"], points=own["points"], level=own["level"]
		)
	await render(
		callback,
		text,
		markup=main_menu(is_admin, profile),
		edit=False,
	)


@router.callback_query(F.data.startswith(f"{cb.QUIZ}:"))
async def start_quiz(
	callback: CallbackQuery,
	state: FSMContext,
	profile,
	bot,
	is_admin: bool,
) -> None:
	"""Open the title's quiz (or continue the attempt left unfinished)."""
	title_pk = parse_int(callback.data.split(":")[1] if ":" in callback.data else None, minimum=1)
	title = await get_title_by_pk(title_pk) if title_pk else None
	if title is None:
		await callback.answer(NOT_FOUND, show_alert=True)
		return
	if not await quiz_service.has_questions(title):
		await callback.answer(QUIZ_NO_QUESTIONS, show_alert=True)
		return

	try:
		payload = await quiz_service.start(profile, title.pk)
	except GameError as exc:
		await callback.answer(exc.detail[:200], show_alert=True)
		return

	questions = payload["questions"]
	if not questions:  # pragma: no cover - the service refuses empty quizzes
		await callback.answer(QUIZ_NO_QUESTIONS, show_alert=True)
		return

	data = await state.get_data()
	same_attempt = data.get("quiz_id") == payload["attempt_id"]
	# Continuing the same attempt keeps the answers already given and simply
	# re-asks the question that was on screen; anything else starts over.
	answers = list(data.get("quiz_answers") or []) if same_attempt else []
	elapsed = list(data.get("quiz_elapsed") or []) if same_attempt else []
	index = int(data.get("quiz_index") or 0) if same_attempt else 0
	index = max(0, min(index, len(questions) - 1))

	await callback.answer()
	await _ask(
		callback,
		state,
		bot,
		attempt_id=payload["attempt_id"],
		question=questions[index],
		index=index,
		total=len(questions),
		title=payload["title"]["title"],
		pass_score=payload["pass_score"],
		answers=answers,
		elapsed=elapsed,
	)


@router.callback_query(F.data.startswith(f"{cb.QUIZ_ANSWER}:"))
async def answer_question(
	callback: CallbackQuery,
	state: FSMContext,
	profile,
	bot,
	is_admin: bool,
) -> None:
	"""Record one answer; the last one finishes the quiz."""
	parts = cb.split_data(callback.data)
	attempt_id = parse_int(parts[1] if len(parts) > 1 else None, minimum=1)
	index = parse_int(parts[2] if len(parts) > 2 else None, minimum=0)
	choice = parse_int(parts[3] if len(parts) > 3 else None, minimum=0)

	data = await state.get_data()
	if (
		attempt_id is None
		or index is None
		or choice is None
		or data.get("quiz_id") != attempt_id
		or data.get("quiz_index") != index
	):
		# The question was already answered, timed out or abandoned.
		await callback.answer(QUIZ_STALE, show_alert=True)
		return

	answers = list(data.get("quiz_answers") or [])
	elapsed = list(data.get("quiz_elapsed") or [])
	asked_at = float(data.get("quiz_at") or 0)
	limit = quiz_service.limit_ms()
	spent_ms = int(max(0.0, (_now() - asked_at) * 1000)) if asked_at else limit

	if spent_ms > limit:
		# Out of time: recorded as a miss with the whole window, which also
		# keeps the anti-cheat total honest about how long the quiz took.
		answers.append(-1)
		elapsed.append(limit)
		await callback.answer(QUIZ_TIME_UP)
	else:
		answers.append(choice)
		elapsed.append(spent_ms)
		await callback.answer()
	await state.update_data(quiz_answers=answers, quiz_elapsed=elapsed)

	total = int(data.get("quiz_total") or 0)
	next_index = index + 1
	if next_index >= total:
		await _finish(
			callback, state, profile, bot, is_admin, answers=answers, elapsed=elapsed
		)
		return

	try:
		question = await quiz_service.question(profile, attempt_id, next_index)
	except GameError as exc:
		await callback.answer(exc.detail[:200], show_alert=True)
		await state.clear()
		return

	await _ask(
		callback,
		state,
		bot,
		attempt_id=attempt_id,
		question=question,
		index=next_index,
		total=total,
		title=data.get("quiz_title") or "",
		pass_score=int(data.get("quiz_pass_score") or 0),
		answers=answers,
		elapsed=elapsed,
	)
