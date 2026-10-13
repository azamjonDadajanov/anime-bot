"""Protected media delivery and mandatory-subscription re-check."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ... import callbacks as cb
from ...keyboards.common import subscribe_keyboard
from ...keyboards.user import main_menu
from ...services.access import missing_channels
from ...services.media import get_part_by_pk, get_title_by_pk, title_parts
from ...texts import (
	BRAND,
	MAIN_MENU,
	NOT_FOUND,
	PARTS_EMPTY,
	SUBSCRIPTION_OK,
	SUBSCRIPTION_STILL_MISSING,
)
from ...utils import parse_int
from ..common import format_channels, render
from .cards import deliver_media_for_part, deliver_title_media

logger = logging.getLogger(__name__)

router = Router(name="user-delivery")


async def _part_from_callback(callback: CallbackQuery, part_pk):
	part = await get_part_by_pk(part_pk) if part_pk else None
	if part is None:
		await render(callback, NOT_FOUND, edit=True)
	return part


@router.callback_query(F.data.startswith(f"{cb.WATCH}:"))
async def watch_part(callback: CallbackQuery, state: FSMContext, profile, bot) -> None:
	part_pk = parse_int(callback.data.split(":")[1], minimum=1)
	part = await _part_from_callback(callback, part_pk)
	if part is None:
		return
	await deliver_media_for_part(callback, part, profile=profile, bot=bot, state=state)


@router.callback_query(F.data.startswith(f"{cb.WATCH_TITLE}:"))
async def watch_title(callback: CallbackQuery, state: FSMContext, profile, bot) -> None:
	"""Deliver a whole movie/single-part title without an episode list."""
	title_pk = parse_int(callback.data.split(":")[1], minimum=1)
	title = await get_title_by_pk(title_pk) if title_pk else None
	if title is None:
		await render(callback, NOT_FOUND, edit=True)
		return
	parts = await title_parts(title)
	if not parts:
		await render(callback, PARTS_EMPTY, edit=True)
		return
	await deliver_title_media(callback, title, parts, profile=profile, bot=bot, state=state)


@router.callback_query(F.data.startswith(f"{cb.QUALITY}:"))
async def watch_with_quality(callback: CallbackQuery, state: FSMContext, profile, bot) -> None:
	parts = callback.data.split(":")
	part_pk = parse_int(parts[1] if len(parts) > 1 else None, minimum=1)
	quality = parts[2] if len(parts) > 2 and parts[2] else None
	part = await _part_from_callback(callback, part_pk)
	if part is None:
		return
	await deliver_media_for_part(
		callback, part, profile=profile, bot=bot, quality=quality, state=state
	)


@router.callback_query(F.data == cb.SUB_CHECK)
async def recheck_subscription(
	callback: CallbackQuery,
	state: FSMContext,
	profile,
	bot,
	is_admin: bool,
) -> None:
	missing = await missing_channels(bot, profile.telegram_id)
	if missing:
		await render(
			callback,
			SUBSCRIPTION_STILL_MISSING.format(channels=format_channels(missing)),
			markup=subscribe_keyboard(missing),
			edit=True,
		)
		return

	await callback.answer(SUBSCRIPTION_OK)
	data = await state.get_data()
	pending_part_id = data.get("pending_part_id")
	pending_quality = data.get("pending_quality") or None
	if pending_part_id:
		part = await get_part_by_pk(int(pending_part_id))
		if part is not None:
			await deliver_media_for_part(
				callback,
				part,
				profile=profile,
				bot=bot,
				quality=pending_quality,
				state=state,
			)
			return
	await render(
		callback,
		MAIN_MENU.format(brand=BRAND),
		markup=main_menu(is_admin),
		edit=True,
	)
