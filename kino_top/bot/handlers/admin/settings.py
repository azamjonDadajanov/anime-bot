"""Bot settings: subscription requirement, auto publishing, access rules."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ... import callbacks as cb
from ...bot_logging import record_event
from ...keyboards.admin import settings_channel_picker, settings_menu
from ...keyboards.common import cancel_keyboard
from ...services.bot_settings import (
	get_settings,
	on_off,
	toggle_setting,
	update_settings,
)
from ...services.channels import get_channel, public_channels
from ...states import AdminSettingsStates
from ...texts import (
	ADMIN_INVALID_INPUT,
	ADMIN_SETTINGS_ASK_VALUE,
	ADMIN_SETTINGS_MENU,
	ADMIN_SETTINGS_SELECT_CHANNEL,
	ADMIN_SETTINGS_UPDATED,
	NOT_FOUND,
)
from ...utils import escape_html, parse_int, to_async
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="admin-settings")

NUMERIC_FIELDS = {"rate": ("broadcast_rate_per_second", 1, 30), "conc": ("broadcast_concurrency", 1, 50)}
TEXT_FIELDS = {"welcome": "welcome_text", "denied": "access_denied_text"}


async def settings_text(settings) -> str:
	# Resolve the FK through the ORM bridge, never the lazy descriptor (that would
	# query the database from the event loop).
	channel = await get_channel(settings.publish_channel_id) if settings.publish_channel_id else None
	return ADMIN_SETTINGS_MENU.format(
		require_subscription=on_off(settings.require_subscription),
		auto_publish=on_off(settings.auto_publish_new_content),
		publish_channel=escape_html(channel.title) if channel else "—",
		protect_content=on_off(settings.protect_content),
		maintenance=on_off(settings.maintenance_mode),
		rate=settings.broadcast_rate_per_second,
		concurrency=settings.broadcast_concurrency,
	)


@router.callback_query(F.data == cb.ADM_SETTINGS)
async def show_settings(callback: CallbackQuery, state: FSMContext) -> None:
	await state.set_state(None)
	settings = await get_settings()
	await render(callback, await settings_text(settings), markup=settings_menu(settings), edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_SETTINGS}:tog:"))
async def toggle(callback: CallbackQuery, profile) -> None:
	args = cb.section_args(callback.data)
	field = args[0] if args else ""
	try:
		value = await toggle_setting(field)
	except ValueError:
		await callback.answer(ADMIN_INVALID_INPUT)
		return
	await to_async(record_event)(
		"INFO",
		f"Setting {field} set to {value} by {profile.telegram_id}.",
		telegram_id=profile.telegram_id,
	)
	await callback.answer(ADMIN_SETTINGS_UPDATED)
	settings = await get_settings()
	await render(callback, await settings_text(settings), markup=settings_menu(settings), edit=True)


@router.callback_query(F.data == f"{cb.ADM_SETTINGS}:rate")
@router.callback_query(F.data == f"{cb.ADM_SETTINGS}:conc")
async def ask_numeric(callback: CallbackQuery, state: FSMContext) -> None:
	field = callback.data.split(":")[2]
	if field not in NUMERIC_FIELDS:
		await callback.answer(ADMIN_INVALID_INPUT)
		return
	_, minimum, maximum = NUMERIC_FIELDS[field]
	await state.set_state(AdminSettingsStates.edit_value)
	await state.update_data(settings_field=field)
	await render(
		callback,
		f"{ADMIN_SETTINGS_ASK_VALUE} ({minimum}–{maximum})",
		markup=cancel_keyboard(),
		edit=True,
	)


@router.callback_query(F.data == f"{cb.ADM_SETTINGS}:welcome")
async def ask_welcome(callback: CallbackQuery, state: FSMContext) -> None:
	await state.set_state(AdminSettingsStates.edit_value)
	await state.update_data(settings_field="welcome")
	await render(callback, ADMIN_SETTINGS_ASK_VALUE, markup=cancel_keyboard(), edit=True)


@router.callback_query(F.data == f"{cb.ADM_SETTINGS}:denied")
async def ask_denied(callback: CallbackQuery, state: FSMContext) -> None:
	await state.set_state(AdminSettingsStates.edit_value)
	await state.update_data(settings_field="denied")
	await render(callback, ADMIN_SETTINGS_ASK_VALUE, markup=cancel_keyboard(), edit=True)


@router.message(AdminSettingsStates.edit_value)
async def save_numeric(message: Message, state: FSMContext) -> None:
	data = await state.get_data()
	field = data.get("settings_field") or ""
	raw = (message.text or "").strip()
	if field in TEXT_FIELDS:
		await update_settings(**{TEXT_FIELDS[field]: raw[:4000]})
		await state.set_state(None)
		await state.update_data(settings_field=None)
		settings = await get_settings()
		await message.answer(await settings_text(settings), reply_markup=settings_menu(settings))
		return
	if field not in NUMERIC_FIELDS:
		await state.clear()
		await message.answer(ADMIN_INVALID_INPUT)
		return
	name, minimum, maximum = NUMERIC_FIELDS[field]
	value = parse_int(raw, minimum=minimum, maximum=maximum)
	if value is None:
		await message.answer(ADMIN_INVALID_INPUT)
		return
	await update_settings(**{name: value})
	await state.set_state(None)
	await state.update_data(settings_field=None)
	settings = await get_settings()
	await message.answer(await settings_text(settings), reply_markup=settings_menu(settings))


@router.callback_query(F.data == f"{cb.ADM_SETTINGS}:chan")
async def choose_channel(callback: CallbackQuery) -> None:
	channels = await public_channels(active_only=False)
	await render(
		callback,
		ADMIN_SETTINGS_SELECT_CHANNEL,
		markup=settings_channel_picker(channels),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_SETTINGS}:setchan:"))
async def set_channel(callback: CallbackQuery, profile) -> None:
	args = cb.section_args(callback.data)
	channel_pk = parse_int(args[0] if args else None, minimum=0)
	if channel_pk is None:
		await callback.answer(ADMIN_INVALID_INPUT)
		return
	channel = await get_channel(channel_pk) if channel_pk else None
	if channel_pk and channel is None:
		await render(callback, NOT_FOUND, edit=True)
		return
	await update_settings(publish_channel=channel)
	await to_async(record_event)(
		"INFO",
		f"Publish channel set to {channel_pk or 'none'} by {profile.telegram_id}.",
		telegram_id=profile.telegram_id,
	)
	settings = await get_settings()
	await render(callback, await settings_text(settings), markup=settings_menu(settings), edit=True)
