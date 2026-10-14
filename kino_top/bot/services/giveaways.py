"""Giveaway draw orchestration: live verification, then the random pick.

The database-side filter (active subscription + optional bot-viewed anime) runs
in ``users.giveaways``; this module adds the checks that must happen *at draw
time* through the Bot API — sponsor-channel membership and the referral link in
the candidate's Telegram bio — and notifies the winners afterwards.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from users.giveaways import (
	ALREADY_DRAWN,
	candidate_profiles_sync,
	draw_winners_sync,
	get_giveaway_sync,
	mark_winner_notified_sync,
	record_entry_sync,
)
from users.models import Giveaway, GiveawayEntry, GiveawayWinner
from users.referrals import referral_payload

from ..services.access import membership_state, required_channels_sync
from ..texts import GIVEAWAY_WINNER_DM
from ..utils import escape_html, human_datetime, to_async

logger = logging.getLogger(__name__)

get_giveaway = to_async(get_giveaway_sync)
candidates = to_async(candidate_profiles_sync)
record_entry = to_async(record_entry_sync)
draw_winners = to_async(draw_winners_sync)
mark_notified = to_async(mark_winner_notified_sync)


def _expiry_for(user_id: int):
	from users.models import Subscription

	subscription = Subscription.objects.filter(user_id=user_id).first()
	return getattr(subscription, "expires_at", None)


winner_expiry = to_async(_expiry_for)


@dataclass
class DrawReport:
	status: str
	giveaway: Optional[Giveaway] = None
	winners: List[GiveawayWinner] = field(default_factory=list)
	eligible_count: int = 0
	candidate_count: int = 0


def _channel_list(giveaway: Giveaway):
	channels = list(giveaway.channels.all())
	if channels:
		return channels
	if giveaway.require_channels:
		return required_channels_sync()
	return []


async def _subscribed_all(bot: Bot, channels, telegram_id: int) -> Optional[bool]:
	"""True/False, or None when membership cannot be inspected (fail-open)."""
	unknown = False
	for channel in channels:
		state = await membership_state(bot, channel.chat_id, telegram_id)
		if state is False:
			return False
		if state is None:
			unknown = True
	return None if unknown else True


async def _bio_has_ref(bot: Bot, telegram_id: int) -> bool:
	"""True when the user's Telegram bio contains their referral payload."""
	try:
		chat = await bot.get_chat(telegram_id)
	except (TelegramAPIError, TypeError) as exc:
		logger.warning("Cannot read bio of %s: %s", telegram_id, exc)
		return False
	bio = str(getattr(chat, "bio", "") or "")
	return referral_payload(telegram_id) in bio


async def run_draw_async(bot: Bot, giveaway_id: int, *, admin_telegram_id: int = 0) -> DrawReport:
	"""Verify every candidate live, pick the winners and DM them."""
	giveaway = await get_giveaway(giveaway_id)
	if giveaway is None:
		return DrawReport("not_found")
	if giveaway.status == Giveaway.Status.DRAWN:
		return DrawReport(ALREADY_DRAWN, giveaway=giveaway)
	if giveaway.status not in (Giveaway.Status.OPEN, Giveaway.Status.DRAFT):
		return DrawReport("not_open", giveaway=giveaway)

	profiles = await candidates(giveaway)
	channels = _channel_list(giveaway) if giveaway.require_channels else []

	eligible_ids: List[int] = []
	for profile in profiles:
		tg_id = profile.telegram_id
		status = GiveawayEntry.Status.ELIGIBLE
		if giveaway.require_channels:
			state = await _subscribed_all(bot, channels, tg_id)
			if state is False:
				status = GiveawayEntry.Status.NO_CHANNEL
			elif state is None:
				# Bot cannot inspect the channel — do not punish the candidate.
				status = GiveawayEntry.Status.ELIGIBLE
		if status == GiveawayEntry.Status.ELIGIBLE and giveaway.require_bio_ref:
			if not await _bio_has_ref(bot, tg_id):
				status = GiveawayEntry.Status.NO_BIO
		await record_entry(
			giveaway=giveaway,
			user=profile.auth_user,
			telegram_id=tg_id,
			status=status,
		)
		if status == GiveawayEntry.Status.ELIGIBLE:
			eligible_ids.append(tg_id)

	report = DrawReport(
		"pending",
		giveaway=giveaway,
		eligible_count=len(eligible_ids),
		candidate_count=len(profiles),
	)

	result = await draw_winners(giveaway, eligible_ids)
	report.status = result.status
	report.winners = list(result.winners)
	report.giveaway = await get_giveaway(giveaway_id)

	for winner in report.winners:
		try:
			expires = await winner_expiry(winner.user_id)
			await bot.send_message(
				winner.telegram_id,
				GIVEAWAY_WINNER_DM.format(
					title=escape_html(report.giveaway.title if report.giveaway else ""),
					days=winner.days,
					expires=human_datetime(expires),
				),
			)
			await mark_notified(winner)
		except TelegramAPIError:
			logger.warning("Could not notify giveaway winner %s", winner.telegram_id)
	return report
