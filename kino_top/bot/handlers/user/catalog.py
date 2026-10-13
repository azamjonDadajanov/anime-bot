"""Catalog browsing: types, genres, titles, parts and part cards."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from movies.models import MediaTitle

from ... import callbacks as cb
from ...config import page_size
from ...keyboards.user import catalog_menu, genres_keyboard, parts_keyboard, results_keyboard
from ...services.media import (
	all_genres,
	all_titles,
	get_genre_by_pk,
	get_part_by_pk,
	get_title_by_pk,
	search_titles,
	title_parts,
	titles_by_type,
)
from ...texts import (
	CATALOG_EMPTY,
	CATALOG_PAGE,
	CATALOG_TITLE,
	GENRE_LIST,
	NOT_FOUND,
	PARTS_EMPTY,
	PARTS_LIST,
)
from ...utils import escape_html, paginate, parse_int
from ..common import render
from .cards import send_part_card, send_title_card

logger = logging.getLogger(__name__)

router = Router(name="user-catalog")


def _split(data: str) -> list:
	return (data or "").split(":")


def _page(value) -> int:
	return parse_int(value, minimum=1) or 1


@router.callback_query(F.data == cb.CATALOG_MENU)
async def show_catalog_menu(callback: CallbackQuery) -> None:
	await render(callback, CATALOG_TITLE, markup=catalog_menu(), edit=True)


@router.callback_query(F.data.startswith(f"{cb.CATALOG}:"))
async def list_all_titles(callback: CallbackQuery) -> None:
	page = _page(_split(callback.data)[1] if len(_split(callback.data)) > 1 else 1)
	titles = await all_titles()
	items, page, pages = paginate(titles, page, page_size())
	if not items:
		await render(callback, CATALOG_EMPTY, markup=catalog_menu(), edit=True)
		return
	await render(
		callback,
		CATALOG_PAGE.format(label="Barcha kontent", page=page, pages=pages),
		markup=results_keyboard(
			items,
			prefix=f"{cb.CATALOG}:",
			page=page,
			pages=pages,
			origin="cat",
			back=cb.MENU,
		),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.TYPE}:"))
async def list_titles_of_type(callback: CallbackQuery) -> None:
	parts = _split(callback.data)
	media_type = parts[1] if len(parts) > 1 else ""
	page = _page(parts[2] if len(parts) > 2 else 1)
	if media_type not in MediaTitle.MediaType.values:
		await render(callback, NOT_FOUND, markup=catalog_menu(), edit=True)
		return
	titles = await titles_by_type(media_type)
	items, page, pages = paginate(titles, page, page_size())
	label = dict(MediaTitle.MediaType.choices).get(media_type, media_type)
	if not items:
		await render(callback, CATALOG_EMPTY, markup=catalog_menu(), edit=True)
		return
	await render(
		callback,
		CATALOG_PAGE.format(label=label, page=page, pages=pages),
		markup=results_keyboard(
			items,
			prefix=f"{cb.TYPE}:{media_type}:",
			page=page,
			pages=pages,
			origin=f"{cb.TYPE}:{media_type}",
			back=cb.CATALOG_MENU,
		),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.GENRES}:"))
async def list_genres(callback: CallbackQuery) -> None:
	parts = _split(callback.data)
	page = _page(parts[1] if len(parts) > 1 else 1)
	genres = await all_genres()
	items, page, pages = paginate(genres, page, page_size())
	if not items:
		await render(callback, CATALOG_EMPTY, markup=catalog_menu(), edit=True)
		return
	await render(callback, GENRE_LIST, markup=genres_keyboard(items, page, pages), edit=True)


@router.callback_query(F.data.startswith(f"{cb.GENRE}:"))
async def list_titles_of_genre(callback: CallbackQuery) -> None:
	parts = _split(callback.data)
	genre_id = parse_int(parts[1] if len(parts) > 1 else None, minimum=1)
	page = _page(parts[2] if len(parts) > 2 else 1)
	genre = await get_genre_by_pk(genre_id) if genre_id else None
	if genre is None:
		await render(callback, NOT_FOUND, markup=catalog_menu(), edit=True)
		return
	titles = await search_titles("", genre=genre.name)
	items, page, pages = paginate(titles, page, page_size())
	if not items:
		await render(callback, CATALOG_EMPTY, markup=catalog_menu(), edit=True)
		return
	await render(
		callback,
		CATALOG_PAGE.format(label=genre.name, page=page, pages=pages),
		markup=results_keyboard(
			items,
			prefix=f"{cb.GENRE}:{genre.pk}:",
			page=page,
			pages=pages,
			origin=f"{cb.GENRE}:{genre.pk}",
			back=f"{cb.GENRES}:1",
		),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.TITLE}:"))
async def show_title(callback: CallbackQuery, profile, bot) -> None:
	parts = _split(callback.data)
	title_pk = parse_int(parts[1] if len(parts) > 1 else None, minimum=1)
	page = _page(parts[2] if len(parts) > 2 else 1)
	# The origin may itself contain colons (e.g. "type:anime", "g:3"), so it is
	# everything after "<title_pk>:<page>:" rather than a single segment.
	origin = ":".join(parts[3:]).strip(":") or "cat"
	title = await get_title_by_pk(title_pk) if title_pk else None
	if title is None:
		await render(callback, NOT_FOUND, edit=True)
		return
	await send_title_card(callback, title, profile=profile, bot=bot, page=page, origin=origin, edit=True)


@router.callback_query(F.data.startswith(f"{cb.PART}:list:"))
async def list_parts(callback: CallbackQuery) -> None:
	parts = _split(callback.data)
	title_pk = parse_int(parts[2] if len(parts) > 2 else None, minimum=1)
	page = _page(parts[3] if len(parts) > 3 else 1)
	origin = ":".join(parts[4:]).strip(":") or "cat"
	title = await get_title_by_pk(title_pk) if title_pk else None
	if title is None:
		await render(callback, NOT_FOUND, edit=True)
		return
	all_parts = await title_parts(title)
	items, page, pages = paginate(all_parts, page, page_size())
	if not items:
		await render(callback, PARTS_EMPTY, edit=True)
		return
	first_part_pk = all_parts[0].pk if all_parts else None
	await render(
		callback,
		PARTS_LIST.format(title=escape_html(title.title)),
		markup=parts_keyboard(
			items, title.pk, page, pages, origin=origin, first_part_pk=first_part_pk
		),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.PART}:view:"))
async def view_part(callback: CallbackQuery, profile, bot) -> None:
	parts = _split(callback.data)
	part_pk = parse_int(parts[2] if len(parts) > 2 else None, minimum=1)
	origin = ":".join(parts[3:]).strip(":") or "cat"
	part = await get_part_by_pk(part_pk) if part_pk else None
	if part is None:
		await render(callback, NOT_FOUND, edit=True)
		return
	await send_part_card(callback, part, profile=profile, bot=bot, origin=origin, edit=True)
