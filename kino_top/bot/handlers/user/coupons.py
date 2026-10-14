"""Coupon (promo code) redemption for users.

The 🎟 button opens a one-field prompt; whatever the user types is normalised
and redeemed first-come-first-served. Redemption extends the caller's
subscription by the coupon's day count through ``users.coupons``.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from users.coupons import (
	ALREADY,
	EXPIRED,
	NO_ACCOUNT,
	REDEEMED,
	redeem_coupon_sync,
)

from ... import callbacks as cb
from ...keyboards.user import coupon_keyboard, main_menu
from ...states import UserCouponStates
from ...texts import (
	COUPON_ALREADY,
	COUPON_EXPIRED,
	COUPON_NOT_FOUND,
	COUPON_NO_ACCOUNT,
	COUPON_PROMPT,
	COUPON_REDEEMED,
)
from ...utils import human_datetime, to_async
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="user-coupons")

redeem_coupon = to_async(redeem_coupon_sync)

# Outcome -> user-facing copy (anything unknown falls back to "not found").
MESSAGES = {
	ALREADY: COUPON_ALREADY,
	EXPIRED: COUPON_EXPIRED,
	NO_ACCOUNT: COUPON_NO_ACCOUNT,
}


@router.callback_query(F.data == cb.COUPON)
async def ask_for_code(callback: CallbackQuery, state: FSMContext) -> None:
	await state.set_state(UserCouponStates.code)
	await render(callback, COUPON_PROMPT, markup=coupon_keyboard(), edit=True)


@router.message(UserCouponStates.code)
async def redeem(message: Message, state: FSMContext, is_admin: bool) -> None:
	code = (message.text or "").strip()
	await state.clear()
	if not code:
		await message.answer(COUPON_NOT_FOUND, reply_markup=main_menu(is_admin))
		return

	result = await redeem_coupon(code, telegram_id=message.from_user.id)
	if result.status == REDEEMED:
		await message.answer(
			COUPON_REDEEMED.format(
				days=result.days,
				expires=human_datetime(result.expires_at),
			),
			reply_markup=main_menu(is_admin),
		)
		return

	await message.answer(
		MESSAGES.get(result.status, COUPON_NOT_FOUND),
		reply_markup=main_menu(is_admin),
	)
