"""Access control: mandatory subscription and premium (plan) gating.

Both checks are centralized here and used by *every* entry point (deep links,
callbacks, delivery, search results) so no path can bypass them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError

from movies.models import MediaTitle, TelegramChannel

from ..utils import plan_rank, to_async
from .bot_settings import get_settings

logger = logging.getLogger(__name__)

MEMBER_STATUSES = {"member", "administrator", "creator"}
ADMIN_STATUSES = {"administrator", "creator"}


@dataclass
class AccessDenied(Exception):
	"""Raised when a user may not receive a protected media item."""

	reason: str
	channels: List[TelegramChannel] = field(default_factory=list)
	required_plan: str = "free"
	current_plan: str = "free"

	def __post_init__(self) -> None:
		super().__init__(self.reason)

	@property
	def is_subscription(self) -> bool:
		return self.reason == "subscription"

	@property
	def is_premium(self) -> bool:
		return self.reason == "premium"

	@property
	def is_blocked(self) -> bool:
		return self.reason == "blocked"


@dataclass
class ChannelCheck:
	"""Result of a `get_chat_member` probe for one channel."""

	channel: TelegramChannel
	subscribed: Optional[bool]  # None means "could not verify"
	error: str = ""

	@property
	def verified(self) -> bool:
		return self.subscribed is not None


def required_channels_sync(*, active_only: bool = True) -> List[TelegramChannel]:
	queryset = TelegramChannel.objects.filter(purpose=TelegramChannel.Purpose.REQUIRED)
	if active_only:
		queryset = queryset.filter(is_active=True)
	return list(queryset.order_by("title"))


def active_required_channels_sync() -> List[TelegramChannel]:
	return required_channels_sync(active_only=True)


_required_channels_async = to_async(active_required_channels_sync)


def plan_of(profile) -> str:
	"""Resolve the effective plan of a ``TelegramUser`` via its auth user."""
	if profile is None:
		return "free"
	auth_user = getattr(profile, "auth_user", None)
	if auth_user is None:
		return "free"
	subscription = getattr(auth_user, "subscription", None)
	if subscription is None:
		return "free"
	return str(subscription.plan or "free")


def plan_satisfies(plan: Optional[str], required: Optional[str]) -> bool:
	return plan_rank(plan) >= plan_rank(required)


async def membership_state(bot: Bot, chat_id: int, user_id: int) -> Optional[bool]:
	"""Return membership for one channel, or ``None`` when it cannot be checked."""
	try:
		member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
	except (TelegramBadRequest, TelegramForbiddenError) as exc:
		logger.warning(
			"Cannot verify membership for chat %s (bot lacks rights?): %s", chat_id, exc
		)
		return None
	except TelegramAPIError as exc:  # pragma: no cover - network level failure
		logger.warning("Membership probe failed for chat %s: %s", chat_id, exc)
		return None

	status = getattr(member, "status", "")
	if status in MEMBER_STATUSES:
		return True
	if status == "restricted":
		return bool(getattr(member, "is_member", False))
	return False


async def check_channels(bot: Bot, user_id: int, channels: Sequence[TelegramChannel]) -> List[ChannelCheck]:
	checks: List[ChannelCheck] = []
	for channel in channels:
		state = await membership_state(bot, channel.chat_id, user_id)
		checks.append(ChannelCheck(channel=channel, subscribed=state))
	return checks


async def missing_channels(bot: Bot, user_id: int) -> List[TelegramChannel]:
	"""Active required channels the user has *not* joined.

	Channels the bot cannot inspect are skipped (fail-open) and logged, because
	blocking the entire user base on a misconfigured channel would be worse than
	the admin panel's "test permissions" screen warning about it.
	"""
	await_required = _required_channels_async
	channels = await await_required()
	if not channels:
		return []
	missing: List[TelegramChannel] = []
	for check in await check_channels(bot, user_id, channels):
		if check.subscribed is False:
			missing.append(check.channel)
		elif not check.verified:
			logger.warning(
				"Subscription for chat %s could not be verified; skipping enforcement.",
				check.channel.chat_id,
			)
	return missing


async def ensure_access(bot: Bot, profile, media: Optional[MediaTitle] = None) -> None:
	"""Raise :class:`AccessDenied` unless ``profile`` may receive ``media``."""
	if profile is None:
		raise AccessDenied(reason="blocked")
	if profile.is_blocked:
		raise AccessDenied(reason="blocked")

	settings = await get_settings()
	if settings.require_subscription:
		missing = await missing_channels(bot, profile.telegram_id)
		if missing:
			raise AccessDenied(reason="subscription", channels=missing)

	if media is None:
		return
	current = plan_of(profile)
	required = (media.required_plan or "free").lower()
	if not plan_satisfies(current, required):
		raise AccessDenied(reason="premium", required_plan=required, current_plan=current)


async def subscription_ok(bot: Bot, profile) -> bool:
	"""Lightweight check used by the "re-check" button."""
	if profile is None or profile.is_blocked:
		return False
	settings = await get_settings()
	if not settings.require_subscription:
		return True
	return not await missing_channels(bot, profile.telegram_id)
