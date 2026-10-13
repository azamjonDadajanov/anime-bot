"""Search by code, title, genre and media type."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ... import callbacks as cb
from ...config import page_size
from ...keyboards.user import main_menu, results_keyboard
from ...services.media import get_title_by_code, search_titles
from ...states import UserSearchStates
from ...texts import (
	NOT_FOUND,
	SEARCH_EMPTY_QUERY,
	SEARCH_NOTHING_FOUND,
	SEARCH_PROMPT,
	SEARCH_RESULTS,
)
from ...utils import escape_html, paginate, parse_int
from ..common import render
from .cards import send_title_card

logger = logging.getLogger(__name__)

router = Router(name="user-search")


async def run_search(
	message: Message,
	query: str,
	*,
	state: FSMContext,
	profile,
	bot,
	is_admin: bool = False,
) -> None:
	query = (query or "").strip()
	if not query:
		await message.answer(SEARCH_EMPTY_QUERY)
		return

	# A bare four-digit code always resolves directly to its title.
	if query.isdigit() and len(query) == 4:
		title = await get_title_by_code(query)
		if title is not None:
			await state.clear()
			await send_title_card(message, title, profile=profile, bot=bot, page=1, origin="cat")
			return

	results = await search_titles(query)
	if not results:
		await state.clear()
		await message.answer(
			SEARCH_NOTHING_FOUND.format(query=escape_html(query)),
			reply_markup=main_menu(is_admin),
		)
		return

	items, page, pages = paginate(results, 1, page_size())
	await state.set_state(UserSearchStates.results)
	await state.update_data(last_query=query)
	await message.answer(
		SEARCH_RESULTS.format(query=escape_html(query)),
		reply_markup=results_keyboard(
			items,
			prefix=f"{cb.SEARCH_RESULTS}:",
			page=page,
			pages=pages,
			origin="cat",
			back=cb.MENU,
		),
	)


@router.callback_query(F.data == cb.SEARCH)
async def ask_for_query(callback: CallbackQuery, state: FSMContext) -> None:
	await state.set_state(UserSearchStates.query)
	await render(callback, SEARCH_PROMPT, edit=True)


@router.message(UserSearchStates.query)
async def search_by_text(
	message: Message, state: FSMContext, profile, bot, is_admin: bool
) -> None:
	await run_search(
		message, message.text or "", state=state, profile=profile, bot=bot, is_admin=is_admin
	)


@router.callback_query(F.data.startswith(f"{cb.SEARCH_RESULTS}:"))
async def paginate_search(callback: CallbackQuery, state: FSMContext, profile, bot) -> None:
	parts = callback.data.split(":")
	page = parse_int(parts[1] if len(parts) > 1 else None, minimum=1) or 1
	data = await state.get_data()
	query = str(data.get("last_query") or "").strip()
	if not query:
		# No remembered query: re-enter the input flow instead of leaving the
		# user on a dead prompt with no way back.
		await state.set_state(UserSearchStates.query)
		await render(callback, SEARCH_PROMPT, edit=True)
		return
	results = await search_titles(query)
	items, page, pages = paginate(results, page, page_size())
	if not items:
		await render(callback, SEARCH_NOTHING_FOUND.format(query=escape_html(query)), edit=True)
		return
	await render(
		callback,
		SEARCH_RESULTS.format(query=escape_html(query)),
		markup=results_keyboard(
			items,
			prefix=f"{cb.SEARCH_RESULTS}:",
			page=page,
			pages=pages,
			origin="cat",
			back=cb.MENU,
		),
		edit=True,
	)


@router.message(F.text.regexp(r"^\s*\d{4}\s*$"))
async def code_lookup(message: Message, state: FSMContext, profile, bot, is_admin: bool) -> None:
	"""A bare code outside the search flow jumps straight to the title."""
	code = (message.text or "").strip()
	title = await get_title_by_code(code)
	if title is None:
		await message.answer(NOT_FOUND, reply_markup=main_menu(is_admin))
		return
	await state.clear()
	await send_title_card(message, title, profile=profile, bot=bot, page=1, origin="cat")
