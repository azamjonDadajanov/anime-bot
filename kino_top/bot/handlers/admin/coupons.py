"""Coupon administration: create a promo code, publish it and manage the list.

The three-step builder asks for the duration (days), how many people may win it
and finally the code itself. Publishing posts the promotion to the configured
public channel, where users read the code and send it back to the bot.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from users.coupons import (
	CouponCodeInvalid,
	CouponCodeTaken,
	all_coupons_sync,
	coupon_count_sync,
	create_coupon_sync,
	delete_coupon_sync,
	get_coupon_sync,
	set_coupon_active_sync,
)

from ... import callbacks as cb
from ...bot_logging import record_event
from ...config import page_size
from ...keyboards.admin import (
	coupon_actions,
	coupon_confirm_delete,
	coupons_list,
	coupons_menu,
)
from ...keyboards.common import cancel_keyboard
from ...services.publishing import maybe_auto_publish_coupon, publish_coupon
from ...states import AdminCouponStates
from ...texts import (
	ADMIN_COUPON_ASK_CODE,
	ADMIN_COUPON_ASK_DAYS,
	ADMIN_COUPON_ASK_USES,
	ADMIN_COUPON_CARD,
	ADMIN_COUPON_CODE_TAKEN,
	ADMIN_COUPON_CREATED,
	ADMIN_COUPON_DELETE_CONFIRM,
	ADMIN_COUPON_DELETED,
	ADMIN_COUPON_EMPTY,
	ADMIN_COUPON_INVALID,
	ADMIN_COUPON_LIST,
	ADMIN_COUPON_NOT_PUBLISHED,
	ADMIN_COUPON_PUBLISHED,
	ADMIN_COUPON_TOGGLED,
	ADMIN_COUPONS_MENU,
	NOT_FOUND,
)
from ...utils import escape_html, paginate, parse_int, to_async
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="admin-coupons")

all_coupons = to_async(all_coupons_sync)
coupon_count = to_async(coupon_count_sync)
create_coupon = to_async(create_coupon_sync)
get_coupon = to_async(get_coupon_sync)
set_coupon_active = to_async(set_coupon_active_sync)
delete_coupon = to_async(delete_coupon_sync)

CANCEL_TARGET = f"{cb.ADM_COUPONS}:cancel"


def _admin_user_sync(telegram_id: int):
	from django.contrib.auth import get_user_model

	return get_user_model().objects.filter(telegram_profile__telegram_id=telegram_id).first()


admin_user = to_async(_admin_user_sync)


def coupon_card(coupon) -> str:
	return ADMIN_COUPON_CARD.format(
		code=escape_html(coupon.code),
		days=coupon.days,
		max_uses=coupon.max_uses,
		used=coupon.used_count,
		remaining=coupon.remaining,
		status=escape_html(coupon.status_label),
	)


async def _render_menu(target, *, edit: bool = False) -> None:
	total = await coupon_count()
	await render(target, ADMIN_COUPONS_MENU.format(total=total), markup=coupons_menu(), edit=edit)


async def _load(callback: CallbackQuery, index: int):
	"""Resolve a coupon pk from ``a:cp:<action>:<pk>[:<page>]``."""
	args = cb.section_args(callback.data)
	value = args[index] if len(args) > index else None
	pk = parse_int(value, minimum=1)
	coupon = await get_coupon(pk) if pk else None
	if coupon is None:
		await callback.answer(NOT_FOUND[:200], show_alert=True)
	return coupon


@router.callback_query(F.data == cb.ADM_COUPONS)
async def open_menu(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	await _render_menu(callback, edit=True)


@router.callback_query(F.data == CANCEL_TARGET)
async def cancel_builder(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	await _render_menu(callback, edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_COUPONS}:list:"))
async def list_coupons(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	args = cb.section_args(callback.data)
	page = parse_int(args[0] if args else None, minimum=1) or 1
	coupons = await all_coupons()
	items, page, pages = paginate(coupons, page, page_size())
	if not items:
		await render(callback, ADMIN_COUPON_EMPTY, markup=coupons_menu(), edit=True)
		return
	await render(
		callback,
		ADMIN_COUPON_LIST.format(page=page, pages=pages),
		markup=coupons_list(items, page, pages),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_COUPONS}:view:"))
async def show_coupon(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	coupon = await _load(callback, 0)
	if coupon is None:
		return
	await render(callback, coupon_card(coupon), markup=coupon_actions(coupon), edit=True)


@router.callback_query(F.data == f"{cb.ADM_COUPONS}:new")
async def start_builder(callback: CallbackQuery, state: FSMContext) -> None:
	await state.set_state(AdminCouponStates.days)
	await state.update_data(coupon_days=None, coupon_uses=None)
	await render(
		callback,
		ADMIN_COUPON_ASK_DAYS,
		markup=cancel_keyboard(CANCEL_TARGET),
		edit=True,
	)


@router.message(AdminCouponStates.days)
async def receive_days(message: Message, state: FSMContext) -> None:
	days = parse_int(message.text, minimum=1, maximum=3650)
	if days is None:
		await message.answer(ADMIN_COUPON_INVALID)
		return
	await state.update_data(coupon_days=days)
	await state.set_state(AdminCouponStates.uses)
	await message.answer(ADMIN_COUPON_ASK_USES, reply_markup=cancel_keyboard(CANCEL_TARGET))


@router.message(AdminCouponStates.uses)
async def receive_uses(message: Message, state: FSMContext) -> None:
	uses = parse_int(message.text, minimum=1, maximum=1_000_000)
	if uses is None:
		await message.answer(ADMIN_COUPON_INVALID)
		return
	await state.update_data(coupon_uses=uses)
	await state.set_state(AdminCouponStates.code)
	await message.answer(ADMIN_COUPON_ASK_CODE, reply_markup=cancel_keyboard(CANCEL_TARGET))


@router.message(AdminCouponStates.code)
async def receive_code(message: Message, state: FSMContext, bot) -> None:
	data = await state.get_data()
	days = data.get("coupon_days")
	uses = data.get("coupon_uses")
	raw = (message.text or "").strip()
	# A lone "-" lets the bot pick a unique code instead of the administrator.
	code = "" if raw == "-" else raw

	try:
		coupon = await create_coupon(
			days=days,
			max_uses=uses,
			code=code,
			created_by=await admin_user(message.from_user.id),
		)
	except CouponCodeTaken:
		await message.answer(ADMIN_COUPON_CODE_TAKEN)
		return
	except CouponCodeInvalid:
		await message.answer(ADMIN_COUPON_INVALID)
		return

	await state.clear()
	# Announce the coupon publicly right away when auto-publishing is on.
	message_id = await maybe_auto_publish_coupon(bot, coupon)
	await to_async(record_event)(
		"INFO",
		f"Coupon {coupon.code} created by {message.from_user.id} "
		f"({coupon.days} days, {coupon.max_uses} uses).",
		telegram_id=message.from_user.id,
	)
	created_text = ADMIN_COUPON_CREATED.format(card=coupon_card(coupon))
	if message_id:
		created_text += "\n\n" + ADMIN_COUPON_PUBLISHED
	await message.answer(created_text, reply_markup=coupon_actions(coupon))


@router.callback_query(F.data.startswith(f"{cb.ADM_COUPONS}:pub:"))
async def publish(callback: CallbackQuery, bot) -> None:
	coupon = await _load(callback, 0)
	if coupon is None:
		return
	message_id = await publish_coupon(bot, coupon)
	if message_id:
		await callback.answer(ADMIN_COUPON_PUBLISHED[:200])
	else:
		await callback.answer(ADMIN_COUPON_NOT_PUBLISHED[:200], show_alert=True)
	await render(callback, coupon_card(coupon), markup=coupon_actions(coupon), edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_COUPONS}:tog:"))
async def toggle(callback: CallbackQuery) -> None:
	coupon = await _load(callback, 0)
	if coupon is None:
		return
	updated = await set_coupon_active(coupon.pk, not coupon.is_active)
	if updated is None:  # pragma: no cover - deleted between load and write
		await callback.answer(NOT_FOUND[:200], show_alert=True)
		return
	await callback.answer(ADMIN_COUPON_TOGGLED.format(state=updated.status_label)[:200])
	await render(callback, coupon_card(updated), markup=coupon_actions(updated), edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_COUPONS}:del:"))
async def ask_delete(callback: CallbackQuery) -> None:
	coupon = await _load(callback, 0)
	if coupon is None:
		return
	await render(
		callback,
		ADMIN_COUPON_DELETE_CONFIRM.format(code=escape_html(coupon.code)),
		markup=coupon_confirm_delete(coupon),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_COUPONS}:yes:"))
async def confirm_delete(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	pk = parse_int(args[0] if args else None, minimum=1)
	if pk is None:
		await callback.answer(NOT_FOUND[:200], show_alert=True)
		return
	await delete_coupon(pk)
	await callback.answer(ADMIN_COUPON_DELETED[:200])
	await _render_menu(callback, edit=True)
