"""Handlers for updates the administrator router refused or did not recognise.

This router is included *after* every other router, so it only sees updates that
failed the admin filters (a non-administrator trying an administrative action)
or that nothing else matched. It never intercepts a bare 4-digit code or an
active FSM flow because those handlers are registered earlier.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from ...keyboards.user import main_menu
from ...texts import ADMIN_INVALID_INPUT, ADMIN_ONLY, BRAND, HELP_TEXT, SEARCH_EMPTY_QUERY
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="user-fallback")

ADMIN_CALLBACK_PREFIXES = ("a:", "adm:")


@router.message(Command("admin", "panel", "boshqaruv"))
async def refuse_admin_command(message: Message, profile, is_admin: bool) -> None:
	"""A non-administrator ran /admin: the admin router filtered it out."""
	logger.warning("Non-administrator %s tried /admin.", message.from_user and message.from_user.id)
	await message.answer(ADMIN_ONLY, reply_markup=main_menu(is_admin, profile))


@router.callback_query(F.data.startswith(ADMIN_CALLBACK_PREFIXES))
async def refuse_admin_callback(callback: CallbackQuery, profile, is_admin: bool) -> None:
	if is_admin:
		# An administrator pressing an unknown admin button: the panel simply
		# does not know this payload. Never claim they are "not an admin".
		await callback.answer(ADMIN_INVALID_INPUT[:200])
		return
	logger.warning(
		"Non-administrator %s tried an admin callback: %s",
		callback.from_user and callback.from_user.id,
		callback.data,
	)
	await callback.answer(ADMIN_ONLY, show_alert=True)
	await render(callback, ADMIN_ONLY, markup=main_menu(is_admin, profile), edit=True)


@router.message(F.text)
async def unknown_text(message: Message, profile, is_admin: bool) -> None:
	await message.answer(
		f"{SEARCH_EMPTY_QUERY}\n\n{HELP_TEXT.format(brand=BRAND)}",
		reply_markup=main_menu(is_admin, profile),
	)


@router.message()
async def unknown_update(message: Message, profile, is_admin: bool) -> None:
	await render(message, HELP_TEXT.format(brand=BRAND), markup=main_menu(is_admin, profile))
