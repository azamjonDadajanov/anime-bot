"""Search by code, title, genre and media type.

The search screen offers three ways in: a free-text query (name or 4-digit
code), a media-type filter (anime/series/manga/movie) and a genre filter. The
active filters live in the FSM data, so a typed query can refine a chosen type
or genre and ``sres:<page>`` can re-run the very same search when paginating.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from movies.models import MediaTitle

from ... import callbacks as cb
from ...config import page_size
from ...keyboards.user import (
	main_menu,
	results_keyboard,
	search_genres_keyboard,
	search_keyboard,
)
from ...services.media import all_genres, get_genre_by_pk, get_title_by_code, search_titles
from ...states import UserSearchStates
from ...texts import (
	CATALOG_EMPTY,
	NOT_FOUND,
	SEARCH_ALL_TITLE,
	SEARCH_EMPTY_QUERY,
	SEARCH_EMPTY_RESULTS,
	SEARCH_GENRE_LIST,
	SEARCH_GENRE_TITLE,
	SEARCH_NOTHING_FOUND,
	SEARCH_PROMPT,
	SEARCH_RESULTS,
	SEARCH_TYPE_TITLE,
)
from ...utils import escape_html, paginate, parse_int
from ..common import render
from .cards import send_title_card

logger = logging.getLogger(__name__)

router = Router(name="user-search")

# Every list produced here is opened from the search screen, so the title-card
# "back" button and the results pagination both resolve to ``sres:<page>``.
SEARCH_ORIGIN = "search"


def _split(data: str) -> list:
	return (data or "").split(":")


def _page(value) -> int:
	return parse_int(value, minimum=1) or 1


def _heading(query: str, media_type: str, genre: str, page: int, pages: int) -> str:
	if query:
		return SEARCH_RESULTS.format(query=escape_html(query))
	if genre:
		return SEARCH_GENRE_TITLE.format(genre=escape_html(genre), page=page, pages=pages)
	if media_type:
		label = dict(MediaTitle.MediaType.choices).get(media_type, media_type)
		return SEARCH_TYPE_TITLE.format(label=escape_html(label), page=page, pages=pages)
	return SEARCH_ALL_TITLE.format(page=page, pages=pages)


def _empty(query: str, genre: str) -> str:
	if query:
		return SEARCH_NOTHING_FOUND.format(query=escape_html(query))
	return SEARCH_EMPTY_RESULTS


async def _filters(state: FSMContext) -> dict:
	data = await state.get_data()
	return {
		"query": str(data.get("last_query") or "").strip(),
		"media_type": str(data.get("last_type") or "").strip(),
		"genre": str(data.get("last_genre") or "").strip(),
	}


async def _see_all(state: FSMContext) -> bool:
	"""True when the active result list came from "Barchasini ko'rish".

	That mode intentionally stores no query/type/genre filters, so pagination
	cannot rely on the filters alone to tell "there is a remembered search".
	"""
	data = await state.get_data()
	return bool(data.get("last_all"))


async def send_search_results(
	target,
	*,
	state: FSMContext,
	page: int = 1,
	edit: bool = False,
) -> None:
	"""Render the results of the search currently remembered in ``state``.

	The ``query``/``media_type``/``genre`` triple is read from the FSM data so
	that pagination and a refined query stay on the same filter.
	"""
	filters = await _filters(state)
	results = await search_titles(
		filters["query"],
		media_type=filters["media_type"],
		genre=filters["genre"],
	)
	items, page, pages = paginate(results, page, page_size())
	if not items:
		# Stay in the query state so the user can immediately try another term.
		await state.set_state(UserSearchStates.query)
		await render(
			target,
			_empty(filters["query"], filters["genre"]),
			markup=search_keyboard(),
			edit=edit,
		)
		return
	await state.set_state(UserSearchStates.query)
	await render(
		target,
		_heading(filters["query"], filters["media_type"], filters["genre"], page, pages),
		markup=results_keyboard(
			items,
			prefix=f"{cb.SEARCH_RESULTS}:",
			page=page,
			pages=pages,
			origin=SEARCH_ORIGIN,
			back=cb.SEARCH,
		),
		edit=edit,
	)


@router.callback_query(F.data == cb.SEARCH)
async def open_search(callback: CallbackQuery, state: FSMContext) -> None:
	"""Open the search screen and drop any filter left from a previous search."""
	await state.set_state(UserSearchStates.query)
	await state.update_data(last_query="", last_type="", last_genre="", last_all=False)
	await render(callback, SEARCH_PROMPT, markup=search_keyboard(), edit=True)


@router.callback_query(F.data.startswith(f"{cb.S_TYPE}:"))
async def search_by_type(callback: CallbackQuery, state: FSMContext) -> None:
	parts = _split(callback.data)
	media_type = parts[1] if len(parts) > 1 else ""
	page = _page(parts[2] if len(parts) > 2 else 1)
	if media_type not in MediaTitle.MediaType.values:
		await render(callback, NOT_FOUND, markup=search_keyboard(), edit=True)
		return
	await state.set_state(UserSearchStates.query)
	await state.update_data(last_query="", last_type=media_type, last_genre="", last_all=False)
	await send_search_results(callback, state=state, page=page, edit=True)


@router.callback_query(F.data.startswith(f"{cb.S_GENRES}:"))
async def open_search_genres(callback: CallbackQuery) -> None:
	parts = _split(callback.data)
	page = _page(parts[1] if len(parts) > 1 else 1)
	genres = await all_genres()
	items, page, pages = paginate(genres, page, page_size())
	if not items:
		await render(callback, CATALOG_EMPTY, markup=search_keyboard(), edit=True)
		return
	await render(
		callback,
		SEARCH_GENRE_LIST,
		markup=search_genres_keyboard(items, page, pages),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.S_GENRE}:"))
async def search_by_genre(callback: CallbackQuery, state: FSMContext) -> None:
	parts = _split(callback.data)
	genre_id = parse_int(parts[1] if len(parts) > 1 else None, minimum=1)
	page = _page(parts[2] if len(parts) > 2 else 1)
	genre = await get_genre_by_pk(genre_id) if genre_id else None
	if genre is None:
		await render(callback, NOT_FOUND, markup=search_keyboard(), edit=True)
		return
	await state.set_state(UserSearchStates.query)
	await state.update_data(last_query="", last_type="", last_genre=genre.name, last_all=False)
	await send_search_results(callback, state=state, page=page, edit=True)


@router.callback_query(F.data == cb.S_ALL)
async def search_everything(callback: CallbackQuery, state: FSMContext) -> None:
	"""The \"see everything\" button: list the whole catalogue, unfiltered."""
	await state.set_state(UserSearchStates.query)
	await state.update_data(last_query="", last_type="", last_genre="", last_all=True)
	await send_search_results(callback, state=state, page=1, edit=True)


@router.message(UserSearchStates.query)
async def search_by_text(
	message: Message, state: FSMContext, profile, bot, is_admin: bool
) -> None:
	query = (message.text or "").strip()
	if not query:
		await message.answer(SEARCH_EMPTY_QUERY, reply_markup=search_keyboard())
		return

	# A bare four-digit code always resolves directly to its title.
	if query.isdigit() and len(query) == 4:
		title = await get_title_by_code(query)
		if title is not None:
			await state.clear()
			await send_title_card(message, title, profile=profile, bot=bot, page=1, origin=SEARCH_ORIGIN)
			return

	# A typed query refines the type/genre filter chosen on the search screen.
	await state.update_data(last_query=query, last_all=False)
	await send_search_results(message, state=state)


@router.callback_query(F.data.startswith(f"{cb.SEARCH_RESULTS}:"))
async def paginate_search(callback: CallbackQuery, state: FSMContext) -> None:
	parts = _split(callback.data)
	page = _page(parts[1] if len(parts) > 1 else None)
	filters = await _filters(state)
	if not any(filters.values()) and not await _see_all(state):
		# No remembered search: re-enter the input flow instead of leaving the
		# user on a dead prompt with no way back. "Barchasini ko'rish" keeps
		# every filter empty on purpose, so it is tracked via ``last_all``.
		await state.set_state(UserSearchStates.query)
		await render(callback, SEARCH_PROMPT, markup=search_keyboard(), edit=True)
		return
	await send_search_results(callback, state=state, page=page, edit=True)


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
