"""User lookup, moderation and plan management."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from users.models import Subscription

from ... import callbacks as cb
from ...bot_logging import record_event
from ...keyboards.admin import plan_picker, user_actions, user_results, users_menu
from ...keyboards.common import cancel_keyboard
from ...services.users import get_profile, search_users, set_blocked, set_plan, user_card
from ...states import AdminUserStates
from ...texts import (
	ADMIN_INVALID_INPUT,
	ADMIN_USERS_EMPTY,
	ADMIN_USERS_MENU,
	ADMIN_USER_BLOCKED,
	ADMIN_USER_CARD,
	ADMIN_USER_PLAN_UPDATED,
	ADMIN_USER_UNBLOCKED,
	NOT_FOUND,
)
from ...utils import escape_html, human_datetime, human_timesince, parse_int, to_async
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="admin-users")


async def user_card_text(profile) -> str:
	card = await to_async(user_card)(profile)
	return ADMIN_USER_CARD.format(
		name=escape_html(card["name"]),
		telegram_id=card["telegram_id"],
		username=escape_html(card["username"]),
		plan=card["plan_display"],
		blocked="ha" if card["blocked"] else "yo'q",
		favorites=card["favorites"],
		created=human_datetime(card["created"]),
		last_seen=human_timesince(card["last_seen"]),
	)


@router.callback_query(F.data == cb.ADM_USERS)
async def show_menu(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	await render(callback, ADMIN_USERS_MENU, markup=users_menu(), edit=True)


@router.callback_query(F.data == f"{cb.ADM_USERS}:search")
async def ask_search(callback: CallbackQuery, state: FSMContext) -> None:
	await state.set_state(AdminUserStates.query)
	await render(callback, ADMIN_USERS_MENU, markup=cancel_keyboard(), edit=True)


@router.message(AdminUserStates.query)
async def do_search(message: Message, state: FSMContext) -> None:
	query = (message.text or "").strip()
	await state.clear()
	if not query:
		await message.answer(ADMIN_INVALID_INPUT)
		return
	profiles = await search_users(query)
	if not profiles:
		await message.answer(ADMIN_USERS_EMPTY, reply_markup=users_menu())
		return
	await message.answer(
		f"👥 Topildi: <b>{len(profiles)}</b>", reply_markup=user_results(profiles)
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_USERS}:view:"))
async def view_user(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	telegram_id = parse_int(args[0] if args else None, minimum=1)
	profile = await get_profile(telegram_id) if telegram_id else None
	if profile is None:
		await render(callback, NOT_FOUND, markup=users_menu(), edit=True)
		return
	await render(callback, await user_card_text(profile), markup=user_actions(profile), edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_USERS}:block:"))
async def toggle_block(callback: CallbackQuery, profile) -> None:
	args = cb.section_args(callback.data)
	telegram_id = parse_int(args[0] if args else None, minimum=1)
	target = await get_profile(telegram_id) if telegram_id else None
	if target is None:
		await render(callback, NOT_FOUND, markup=users_menu(), edit=True)
		return
	blocked = await set_blocked(target.telegram_id, not target.is_blocked)
	target.is_blocked = bool(blocked)
	await to_async(record_event)(
		"WARNING",
		f"User {target.telegram_id} {'blocked' if blocked else 'unblocked'} by {profile.telegram_id}.",
		telegram_id=profile.telegram_id,
	)
	await render(
		callback,
		(ADMIN_USER_BLOCKED if blocked else ADMIN_USER_UNBLOCKED) + "\n\n" + await user_card_text(target),
		markup=user_actions(target),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_USERS}:plan:"))
async def choose_plan(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	telegram_id = parse_int(args[0] if args else None, minimum=1)
	profile = await get_profile(telegram_id) if telegram_id else None
	if profile is None:
		await render(callback, NOT_FOUND, markup=users_menu(), edit=True)
		return
	card = await to_async(user_card)(profile)
	await render(
		callback,
		f"💎 Joriy tarif: <b>{card['plan_display']}</b>\n\nYangi tarifni tanlang:",
		markup=plan_picker(profile.telegram_id),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_USERS}:setplan:"))
async def apply_plan(callback: CallbackQuery, profile) -> None:
	args = cb.section_args(callback.data)
	telegram_id = parse_int(args[0] if args else None, minimum=1)
	plan = args[1] if len(args) > 1 else ""
	if plan not in Subscription.Plan.values:
		await callback.answer(ADMIN_INVALID_INPUT)
		return
	target = await get_profile(telegram_id) if telegram_id else None
	if target is None:
		await render(callback, NOT_FOUND, markup=users_menu(), edit=True)
		return
	applied = await set_plan(target.telegram_id, plan)
	if applied is None:
		await callback.answer(ADMIN_INVALID_INPUT)
		return
	await to_async(record_event)(
		"INFO",
		f"User {target.telegram_id} plan changed to {applied} by {profile.telegram_id}.",
		telegram_id=profile.telegram_id,
	)
	await callback.answer(ADMIN_USER_PLAN_UPDATED.format(plan=applied.upper()))
	target = await get_profile(telegram_id)
	await render(callback, await user_card_text(target), markup=user_actions(target), edit=True)
