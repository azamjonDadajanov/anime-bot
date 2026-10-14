"""Referral menu and manual milestone claims.

The 👥 button opens the invite screen with the user's permanent deep link; a
milestone reward (10 -> 15 days, 15 -> 30 days) is granted only when the user
presses the claim button and ``users.referrals`` confirms enough attributed
invitees. Nothing is granted automatically.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from users.referrals import (
	ALREADY,
	CLAIMED,
	INVALID,
	NOT_ENOUGH,
	NO_ACCOUNT,
	claim_reward_sync,
	referral_payload,
	referral_stats_sync,
)

from ... import callbacks as cb
from ...keyboards.common import btn, keyboard
from ...keyboards.user import referral_keyboard
from ...services.publishing import bot_username
from ...texts import (
	REFERRAL_ALREADY,
	REFERRAL_CLAIMED,
	REFERRAL_INVALID,
	REFERRAL_MENU,
	REFERRAL_NOT_ENOUGH,
	REFERRAL_NO_ACCOUNT,
)
from ...utils import deep_link, escape_html, human_datetime, to_async
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="user-referral")

get_stats = to_async(referral_stats_sync)
claim_reward = to_async(claim_reward_sync)

CLAIM_MESSAGES = {
	ALREADY: REFERRAL_ALREADY,
	NO_ACCOUNT: REFERRAL_NO_ACCOUNT,
	INVALID: REFERRAL_INVALID,
}


async def referral_link(target, profile) -> str:
	"""Full ``https://t.me/<bot>?start=ref_<id>`` link for ``profile``."""
	username = await bot_username(target.bot)
	return deep_link(username, referral_payload(profile.telegram_id))


async def render_referral_menu(target, profile, *, edit: bool = False) -> None:
	stats = await get_stats(profile.telegram_id)
	link = await referral_link(target, profile)
	text = REFERRAL_MENU.format(
		link=escape_html(link),
		invited=stats.invited_count,
	)
	await render(
		target,
		text,
		markup=referral_keyboard(
			invited=stats.invited_count,
			claimed=stats.claimed_milestones,
			link=link,
		),
		edit=edit,
	)


@router.message(Command("ref", "referral", "taklif"))
async def referral_command(message: Message, profile) -> None:
	await render_referral_menu(message, profile)


@router.callback_query(F.data == cb.REF)
async def referral_menu(callback: CallbackQuery, profile) -> None:
	await render_referral_menu(callback, profile, edit=True)


@router.callback_query(F.data.startswith(f"{cb.REF_CLAIM}:"))
async def claim_milestone(callback: CallbackQuery, profile) -> None:
	raw = (callback.data or "").split(":", 1)[-1]
	try:
		milestone = int(raw)
	except (TypeError, ValueError):
		milestone = 0

	result = await claim_reward(
		telegram_id=callback.from_user.id,
		milestone=milestone,
	)
	if result.status == CLAIMED:
		await render(
			callback,
			REFERRAL_CLAIMED.format(
				days=result.days,
				expires=human_datetime(result.expires_at),
			),
			markup=keyboard(
				[btn("👥 Do'stlar", cb.REF)],
				[btn("🏠 Asosiy menyu", cb.MENU)],
			),
			edit=True,
		)
		return

	if result.status == NOT_ENOUGH:
		await callback.answer(
			REFERRAL_NOT_ENOUGH.format(
				needed=result.milestone, invited=result.invited_count
			)[:200],
			show_alert=True,
		)
		return

	await callback.answer(
		CLAIM_MESSAGES.get(result.status, REFERRAL_INVALID)[:200],
		show_alert=True,
	)
