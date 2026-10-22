"""User registration, lookup and moderation helpers.

Registration reuses ``users.telegram_auth.get_or_create_telegram_user`` so the
bot and the website share exactly one account-creation path (auth user,
``TelegramUser`` profile and the auto-created ``Subscription``).
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List, Optional

from django.db import DatabaseError
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from users.models import Subscription, TelegramUser
from users.telegram_auth import (
	get_or_create_telegram_user,
	link_profile_by_username,
	link_profile_status,
)

from ..utils import human_datetime, to_async

logger = logging.getLogger(__name__)

LAST_SEEN_THRESHOLD = dt.timedelta(minutes=5)
ACTIVE_WINDOW_DAYS = 30


def sync_profile_sync(data: Dict[str, Any]) -> Optional[TelegramUser]:
	"""Create or refresh the profile from raw Telegram user data.

	The row is always re-read with ``auth_user`` and its ``subscription``
	pre-loaded: handlers run in an async context where lazy relationship access
	would raise ``SynchronousOnlyOperation``.

	Blocked accounts still get their profile returned (so the handler can
	explain the block) instead of an exception.
	"""
	telegram_id = data.get("id")
	try:
		get_or_create_telegram_user(data)
	except AuthenticationFailed as exc:
		logger.info("Profile %s is not allowed to use the bot: %s", telegram_id, exc)
	except DatabaseError:
		logger.exception("Failed to sync Telegram profile %s.", telegram_id)
		try:
			return TelegramUser.objects.filter(telegram_id=int(telegram_id)).first()
		except (TypeError, ValueError):  # pragma: no cover - defensive
			return None

	try:
		return (
			TelegramUser.objects.select_related("auth_user", "auth_user__subscription")
			.filter(telegram_id=int(telegram_id))
			.first()
		)
	except (TypeError, ValueError):  # pragma: no cover - defensive
		return None


load_profile = to_async(sync_profile_sync)


# ``/start <username>``: bind the Telegram profile to a website account.
link_account_by_username = to_async(link_profile_by_username)
# The same outcome without writing — the confirm card is shown from this.
check_link_by_username = to_async(link_profile_status)


def profile_exists_sync(telegram_id: int) -> bool:
	return TelegramUser.objects.filter(telegram_id=int(telegram_id)).exists()


profile_exists = to_async(profile_exists_sync)


def touch_last_seen_sync(
	telegram_id: int, *, threshold: dt.timedelta = LAST_SEEN_THRESHOLD
) -> None:
	"""Record activity, at most once per ``threshold``."""
	now = timezone.now()
	updated = TelegramUser.objects.filter(telegram_id=telegram_id).filter(
		Q(last_seen_at__isnull=True) | Q(last_seen_at__lt=now - threshold)
	).update(last_seen_at=now)
	if not updated:
		return


touch_last_seen = to_async(touch_last_seen_sync)


def get_profile_sync(telegram_id: int) -> Optional[TelegramUser]:
	return (
		TelegramUser.objects.select_related("auth_user", "auth_user__subscription")
		.filter(telegram_id=int(telegram_id))
		.first()
	)


get_profile = to_async(get_profile_sync)


def search_users_sync(query: str, limit: int = 10) -> List[TelegramUser]:
	query = (query or "").strip()
	if not query:
		return []
	queryset = TelegramUser.objects.select_related("auth_user", "auth_user__subscription")
	numeric = query.lstrip("@+-")
	if numeric.isdigit():
		queryset = queryset.filter(telegram_id=int(numeric))
	else:
		needle = query.lstrip("@")
		queryset = queryset.filter(
			Q(username__icontains=needle)
			| Q(first_name__icontains=needle)
			| Q(last_name__icontains=needle)
		)
	return list(queryset[:limit])


search_users = to_async(search_users_sync)


def set_blocked_sync(telegram_id: int, blocked: bool) -> Optional[bool]:
	profile = TelegramUser.objects.filter(telegram_id=int(telegram_id)).first()
	if profile is None:
		return None
	if profile.is_blocked != blocked:
		profile.is_blocked = blocked
		profile.save(update_fields=["is_blocked", "updated_at"])
	# Blocking must also disable the shared auth account used by the website.
	if profile.auth_user_id and profile.auth_user.is_active == blocked:
		profile.auth_user.is_active = not blocked
		profile.auth_user.save(update_fields=["is_active"])
	return profile.is_blocked


set_blocked = to_async(set_blocked_sync)


def block_from_telegram_sync(telegram_id: int) -> bool:
	"""Mark an account blocked after Telegram reports the user blocked the bot."""
	return bool(set_blocked_sync(telegram_id, True))


block_from_telegram = to_async(block_from_telegram_sync)


def set_plan_sync(telegram_id: int, plan: str) -> Optional[str]:
	if plan not in Subscription.Plan.values:
		raise ValueError(f"Unknown plan: {plan!r}")
	profile = (
		TelegramUser.objects.select_related("auth_user").filter(telegram_id=int(telegram_id)).first()
	)
	if profile is None or profile.auth_user_id is None:
		return None
	subscription, _ = Subscription.objects.get_or_create(user_id=profile.auth_user_id)
	# A changed plan — or a dead one being handed out again — restarts the
	# period, while re-picking the still running plan leaves it alone.
	if subscription.plan != plan or not subscription.is_active:
		subscription.activate(plan)
	return subscription.plan


set_plan = to_async(set_plan_sync)


def user_count_sync() -> int:
	return TelegramUser.objects.count()


def active_user_count_sync(days: int = ACTIVE_WINDOW_DAYS) -> int:
	since = timezone.now() - dt.timedelta(days=days)
	return TelegramUser.objects.filter(is_blocked=False).filter(
		Q(last_seen_at__gte=since) | Q(created_at__gte=since)
	).count()


_user_count = to_async(user_count_sync)
_active_user_count = to_async(active_user_count_sync)


def recipients_sync(*, include_blocked: bool = False) -> List[int]:
	queryset = TelegramUser.objects.all()
	if not include_blocked:
		queryset = queryset.filter(is_blocked=False)
	return list(queryset.order_by("telegram_id").values_list("telegram_id", flat=True))


recipients = to_async(recipients_sync)


def user_card(profile: TelegramUser) -> Dict[str, Any]:
	subscription = getattr(getattr(profile, "auth_user", None), "subscription", None)
	return {
		"telegram_id": profile.telegram_id,
		"name": profile.first_name or profile.username or str(profile.telegram_id),
		"username": f"@{profile.username}" if profile.username else "—",
		"plan": subscription.plan if subscription else "free",
		"plan_display": subscription.get_plan_display() if subscription else "Bepul",
		"plan_active": bool(subscription and subscription.is_active),
		"plan_expires": subscription.expires_at if subscription else None,
		"blocked": profile.is_blocked,
		"favorites": profile.favorites.count(),
		"created": profile.created_at,
		"last_seen": profile.last_seen_at,
	}


def plan_expiry_text(card: Dict[str, Any]) -> str:
	"""Human readable window of the stored plan (``—`` for the free tier)."""
	if card.get("plan") == "free":
		return "—"
	if card.get("plan_active") and card.get("plan_expires"):
		return f"{human_datetime(card['plan_expires'])} gacha"
	return "muddati o'tgan"
