"""Favourites: listing and toggling."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from movies.models import MediaTitle
from users.models import FavoriteContent

from ... import callbacks as cb
from ...config import page_size
from ...keyboards.user import favorites_keyboard, main_menu
from ...services.media import get_part_by_pk, get_title_by_pk
from ...texts import (
	FAVORITES_EMPTY,
	FAVORITES_TITLE,
	FAVORITE_ADDED,
	FAVORITE_REMOVED,
	NOT_FOUND,
)
from ...utils import paginate, parse_int, to_async
from ..common import render
from .cards import media_markup, send_title_card

logger = logging.getLogger(__name__)

router = Router(name="user-favorites")


def favorites_sync(profile):
	"""Favourites newest-first, read through the explicit through model."""
	return list(
		MediaTitle.objects.filter(user_favorites__user=profile)
		.order_by("-user_favorites__created_at")
		.distinct()
	)


def toggle_favorite_sync(profile, title) -> bool:
	"""Return ``True`` when the title was added, ``False`` when removed."""
	favorite = FavoriteContent.objects.filter(user=profile, content=title).first()
	if favorite is not None:
		favorite.delete()
		return False
	FavoriteContent.objects.create(user=profile, content=title)
	return True


_favorites = to_async(favorites_sync)
_toggle_favorite = to_async(toggle_favorite_sync)


@router.callback_query(F.data.startswith(f"{cb.FAVORITES}:"))
async def list_favorites(callback: CallbackQuery, profile, is_admin: bool) -> None:
	page = parse_int(callback.data.split(":")[1], minimum=1) or 1
	items_all = await _favorites(profile)
	items, page, pages = paginate(items_all, page, page_size())
	if not items:
		await render(callback, FAVORITES_EMPTY, markup=main_menu(is_admin, profile), edit=True)
		return
	await render(
		callback,
		FAVORITES_TITLE.format(page=page, pages=pages),
		markup=favorites_keyboard(items, page, pages),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.FAV_TOGGLE}:"))
async def toggle_favorite(callback: CallbackQuery, profile, bot) -> None:
	parts = callback.data.split(":")
	title_pk = parse_int(parts[1] if len(parts) > 1 else None, minimum=1)
	page = parse_int(parts[2] if len(parts) > 2 else None, minimum=1) or 1
	# Origin may contain colons ("type:anime", "g:3") - keep every trailing part.
	origin = ":".join(parts[3:]).strip(":") or "cat"
	title = await get_title_by_pk(title_pk) if title_pk else None
	if title is None:
		await render(callback, NOT_FOUND, edit=True)
		return
	added = await _toggle_favorite(profile, title)
	await callback.answer(FAVORITE_ADDED if added else FAVORITE_REMOVED)
	await send_title_card(callback, title, profile=profile, bot=bot, page=page, origin=origin, edit=True)


@router.callback_query(F.data.startswith(f"{cb.FAV_MEDIA}:"))
async def toggle_favorite_under_media(callback: CallbackQuery, profile) -> None:
	"""Toggle the favourite of the title whose media message was tapped.

	The delivered file keeps its caption: only the keyboard below it is rebuilt
	so the star flips without touching the navigator above.
	"""
	parts = callback.data.split(":")
	title_pk = parse_int(parts[1] if len(parts) > 1 else None, minimum=1)
	part_pk = parse_int(parts[2] if len(parts) > 2 else None, minimum=1)
	title = await get_title_by_pk(title_pk) if title_pk else None
	if title is None:
		await callback.answer(NOT_FOUND, show_alert=True)
		return

	added = await _toggle_favorite(profile, title)
	await callback.answer(FAVORITE_ADDED if added else FAVORITE_REMOVED)

	part = await get_part_by_pk(part_pk) if part_pk else None
	if part is None or callback.message is None:
		return
	markup = await media_markup(profile, title, part)
	try:
		await callback.message.edit_reply_markup(reply_markup=markup)
	except TelegramBadRequest as exc:  # the keyboard is already what we send
		logger.debug("Media keyboard not refreshed: %s", exc)
