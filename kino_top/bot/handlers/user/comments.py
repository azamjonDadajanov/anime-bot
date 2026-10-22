"""💬 Izohlar: read and write the website's comments from inside Telegram.

Everything goes through ``movies.community`` — the single table the website
and the panel read — so a comment typed here appears on the page at once. The
1-10 score is asked for right after the text and stored in its own row: one
score per user per title, re-posting replaces it instead of adding a second
one. After a part-scoped comment the episode is re-delivered with its episode
navigator, so the user lands back where they were.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from movies import community
from movies.models import TitleComment

from ... import callbacks as cb
from ...keyboards.user import (
	comment_list_keyboard,
	comment_prompt_keyboard,
	comment_rating_keyboard,
)
from ...states import UserCommentStates
from ...services.media import get_part_by_pk, get_title_by_pk
from ...texts import (
	CANCELLED,
	COMMENT_DUPLICATE,
	COMMENT_EMPTY,
	COMMENT_LIST_EMPTY,
	COMMENT_LIST_RATING,
	COMMENT_LIST_TITLE,
	COMMENT_NO_ACCOUNT,
	COMMENT_PROMPT,
	COMMENT_RATING_ASK,
	COMMENT_RATING_SUMMARY,
	COMMENT_ROW,
	COMMENT_SAVED,
	COMMENT_SAVED_NO_SCORE,
	COMMENT_SAVED_SCORE,
	COMMENT_STALE,
	COMMENT_TOO_LONG,
	NOT_FOUND,
)
from ...utils import escape_html, human_datetime, parse_int, to_async, truncate
from ..common import render
from .cards import deliver_media_for_part

logger = logging.getLogger(__name__)

router = Router(name="user-comments")

# The community module is synchronous Django; every handler awaits it through
# the single executor thread, exactly like the rest of the bot's ORM access.
list_comments = to_async(community.list_comments_sync)
rating_summary = to_async(community.rating_summary_sync)
create_comment = to_async(community.create_comment_sync)
save_rating = to_async(community.set_rating_sync)

# One comment may be a page long, but a Telegram message is 4096 characters:
# each row is shortened and the list stops well before the limit.
ROW_BODY_LIMIT = 160
PAGE_TEXT_LIMIT = 3400


def account_of(profile):
	"""The website account behind this Telegram profile (``None`` when missing).

	Handlers go through this one line so an unlinked profile can never reach
	the comment table, and tests can stand in for that state.
	"""
	return getattr(profile, "auth_user", None)


async def _title_by_pk(title_pk):
	return await get_title_by_pk(title_pk) if title_pk else None


async def _part_by_pk(part_pk):
	return await get_part_by_pk(part_pk) if part_pk else None


def _row_text(item: dict) -> str:
	"""One comment as a two-line Telegram row (name/date, then the body)."""
	author = item.get("author") or {}
	name = author.get("display_name") or author.get("username") or "Foydalanuvchi"
	crown = " 👑" if author.get("is_premium") else ""
	part = item.get("part") or {}
	suffix = f" · {part.get('number')}-qism" if part.get("number") else ""
	return COMMENT_ROW.format(
		name=escape_html(name),
		crown=crown,
		when=human_datetime(item.get("created_at")) + suffix,
		body=escape_html(truncate(item.get("body"), ROW_BODY_LIMIT)),
	)


@router.callback_query(F.data.startswith(f"{cb.COMMENT_LIST}:"))
async def show_comments(callback: CallbackQuery) -> None:
	"""A page of comments plus the title's live average score."""
	parts = cb.split_data(callback.data)
	title_pk = parse_int(parts[1] if len(parts) > 1 else None, minimum=1)
	page = parse_int(parts[2] if len(parts) > 2 else None, minimum=1) or 1
	title = await _title_by_pk(title_pk)
	if title is None:
		await render(callback, NOT_FOUND, edit=True)
		return

	payload = await list_comments(title, page=page)
	rows = []
	size = 0
	for item in payload["results"]:
		row = _row_text(item)
		if rows and size + len(row) > PAGE_TEXT_LIMIT:
			break
		rows.append(row)
		size += len(row)
	body_text = "".join(rows) if rows else COMMENT_LIST_EMPTY

	summary = ""
	if payload["count"]:
		summary_data = await rating_summary(title)
		summary = COMMENT_LIST_RATING.format(
			summary=COMMENT_RATING_SUMMARY.format(
				average=summary_data["average"],
				count=summary_data["count"],
			)
		)
	text = COMMENT_LIST_TITLE.format(
		title=escape_html(title.title), rows=body_text
	) + summary
	await render(
		callback,
		text,
		markup=comment_list_keyboard(title.pk, payload["page"], payload["pages"]),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.COMMENT}:"))
async def ask_for_comment(callback: CallbackQuery, state: FSMContext, profile) -> None:
	"""``cm:<title_pk>[:<part_pk>]`` — start writing one comment."""
	parts = cb.split_data(callback.data)
	title_pk = parse_int(parts[1] if len(parts) > 1 else None, minimum=1)
	part_pk = parse_int(parts[2] if len(parts) > 2 else None, minimum=1)
	title = await _title_by_pk(title_pk)
	if title is None:
		await render(callback, NOT_FOUND, edit=True)
		return
	if account_of(profile) is None:
		await render(callback, COMMENT_NO_ACCOUNT, edit=False)
		return

	part_label = ""
	if part_pk:
		part = await _part_by_pk(part_pk)
		if part is None:
			await render(callback, NOT_FOUND, edit=True)
			return
		part_label = f" · {part.number}-qism"

	await state.set_state(UserCommentStates.body)
	await state.update_data(
		comment_title_id=title.pk,
		comment_part_id=part_pk or None,
		comment_body="",
	)
	await render(
		callback,
		COMMENT_PROMPT.format(title=escape_html(title.title), part=part_label),
		markup=comment_prompt_keyboard(),
		edit=False,
	)


@router.message(UserCommentStates.body)
async def collect_comment_body(message: Message, state: FSMContext) -> None:
	"""Validate the text now and move on to the 1-10 score picker."""
	raw = message.text or ""
	try:
		body = community.validate_body(raw)
	except community.CommunityError as exc:
		if exc.code == "too_long":
			await message.answer(COMMENT_TOO_LONG, reply_markup=comment_prompt_keyboard())
		else:
			await message.answer(COMMENT_EMPTY, reply_markup=comment_prompt_keyboard())
		return

	data = await state.get_data()
	title = await _title_by_pk(data.get("comment_title_id"))
	if title is None:
		await state.clear()
		await message.answer(NOT_FOUND)
		return

	await state.set_state(UserCommentStates.rating)
	await state.update_data(comment_body=body)
	await message.answer(
		COMMENT_RATING_ASK.format(title=escape_html(title.title)),
		reply_markup=comment_rating_keyboard(),
	)


@router.callback_query(F.data == cb.COMMENT_CANCEL)
async def cancel_comment(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	await render(callback, CANCELLED, edit=True)


async def _finish(
	callback: CallbackQuery,
	state: FSMContext,
	profile,
	bot,
	*,
	score: int | None,
) -> None:
	"""Store the comment (and the optional score), then restore the episode."""
	data = await state.get_data()
	title_id = data.get("comment_title_id")
	body = (data.get("comment_body") or "").strip()
	if not title_id or not body:
		await state.clear()
		await render(callback, COMMENT_STALE, edit=True)
		return

	user = account_of(profile)
	if user is None:
		await state.clear()
		await render(callback, COMMENT_NO_ACCOUNT, edit=True)
		return

	title = await _title_by_pk(int(title_id))
	part = await _part_by_pk(data.get("comment_part_id"))
	if title is None:
		await state.clear()
		await render(callback, NOT_FOUND, edit=True)
		return

	try:
		comment, created = await create_comment(
			user=user,
			title=title,
			body=body,
			part=part,
			source=TitleComment.Source.BOT,
		)
	except community.CommunityError as exc:
		await state.clear()
		if exc.code == "duplicate":
			await render(callback, COMMENT_DUPLICATE, edit=False)
		else:
			await render(callback, exc.detail, edit=False)
		return

	score_line = COMMENT_SAVED_NO_SCORE
	if score is not None:
		try:
			await save_rating(user, title, score)
		except community.CommunityError as exc:
			logger.warning("Rating for %s was rejected: %s", title.pk, exc.detail)
		else:
			score_line = COMMENT_SAVED_SCORE.format(score=score)

	await state.clear()
	await render(
		callback,
		COMMENT_SAVED.format(title=escape_html(title.title), score_line=score_line),
		edit=False,
	)
	if part is not None:
		# Land the user back on the episode they were watching, navigator and
		# action rows included; the confirmation above is already delivered.
		await deliver_media_for_part(
			callback,
			part,
			profile=profile,
			bot=bot,
			announce=False,
		)


@router.callback_query(F.data.startswith(f"{cb.COMMENT_RATE}:"))
async def pick_rating(
	callback: CallbackQuery, state: FSMContext, profile, bot
) -> None:
	"""``cmr:<score>`` — finish the comment with a 1-10 score."""
	parts = cb.split_data(callback.data)
	score = parse_int(parts[1] if len(parts) > 1 else None, minimum=1, maximum=10)
	if score is None:
		await callback.answer()
		return
	await _finish(callback, state, profile, bot, score=score)


@router.callback_query(F.data == cb.COMMENT_RATE_SKIP)
async def skip_rating(
	callback: CallbackQuery, state: FSMContext, profile, bot
) -> None:
	"""Save the comment without scoring the title."""
	await _finish(callback, state, profile, bot, score=None)
