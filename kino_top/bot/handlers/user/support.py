"""``✉️ Adminga xabar``: read what the user writes and forward it to the admins.

The text is stored by ``users.support`` *before* it is delivered, so whatever a
user writes survives a Telegram outage; this handler only reports the outcome.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from users.models import SupportMessage
from users.support import TOO_SOON, send_support_message_sync

from ... import callbacks as cb
from ...keyboards.user import main_menu
from ...states import UserSupportStates
from ...texts import (
	SUPPORT_EMPTY,
	SUPPORT_FAILED,
	SUPPORT_PROMPT,
	SUPPORT_SENT,
	SUPPORT_TOO_SOON,
)
from ...utils import to_async
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="user-support")

send_support_message = to_async(send_support_message_sync)


@router.callback_query(F.data == cb.SUPPORT)
async def ask_for_message(
	callback: CallbackQuery, state: FSMContext, is_admin: bool
) -> None:
	await state.set_state(UserSupportStates.message)
	await render(callback, SUPPORT_PROMPT, markup=main_menu(is_admin), edit=True)


@router.message(UserSupportStates.message)
async def deliver(message: Message, state: FSMContext, profile, is_admin: bool) -> None:
	text = (message.text or "").strip()
	await state.clear()
	if not text:
		await message.answer(SUPPORT_EMPTY, reply_markup=main_menu(is_admin))
		return

	result = await send_support_message(
		profile.auth_user,
		text,
		source=SupportMessage.Source.BOT,
		telegram_id=profile.telegram_id,
	)
	if result.status == TOO_SOON:
		await message.answer(
			SUPPORT_TOO_SOON.format(seconds=result.retry_after),
			reply_markup=main_menu(is_admin),
		)
		return
	if result.delivered:
		await message.answer(SUPPORT_SENT, reply_markup=main_menu(is_admin))
		return
	logger.warning(
		"Support message %s from %s was not delivered.",
		getattr(result.message, "pk", None),
		profile.telegram_id,
	)
	await message.answer(SUPPORT_FAILED, reply_markup=main_menu(is_admin))
