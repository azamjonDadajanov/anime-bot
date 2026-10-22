"""The one rule behind every 👑: is this account's subscription live?

Used by the comment payloads, the leaderboards, the profile pages and the
administrator panel — all of them ask *this* function, never the plan label,
so a crown can never outlive the subscription it stands for. The check reads
``Subscription.is_active`` (paid **and** not expired), which is also what the
bot's access gate uses, so every platform agrees.
"""

from __future__ import annotations

from typing import Dict, Iterable, List

from django.db.models import Q
from django.utils import timezone


def _auth_user_of(user):
	"""Return the site account for either an auth user or a Telegram profile."""
	if user is None:
		return None
	# A ``TelegramUser`` is not a Django auth user (no ``is_authenticated``),
	# but it does point at one.
	if not hasattr(user, "is_authenticated"):
		return getattr(user, "auth_user", None)
	return user


def is_premium_user(user) -> bool:
	"""True while ``user`` has a paid, unexpired subscription."""
	account = _auth_user_of(user)
	user_id = getattr(account, "pk", None)
	if not user_id:
		return False
	from .models import Subscription

	subscription = (
		Subscription.objects.filter(user_id=user_id)
		.only("plan", "expires_at")
		.first()
	)
	return bool(subscription and subscription.is_active)


def premium_status(users: Iterable) -> Dict[int, bool]:
	"""Batch variant: ``{user_id: is_premium}`` for a page of rows.

	One query instead of one per comment, which keeps a 10-comment page at a
	constant number of round trips.
	"""
	accounts: List[int] = []
	for user in users:
		account = _auth_user_of(user)
		pk = getattr(account, "pk", None)
		if pk and pk not in accounts:
			accounts.append(pk)
	if not accounts:
		return {}
	from .models import Subscription

	now = timezone.now()
	live = set(
		Subscription.objects.filter(
			Q(expires_at__isnull=False) & Q(expires_at__gt=now)
		)
		.exclude(plan="free")
		.values_list("user_id", flat=True)
	)
	return {user_id: user_id in live for user_id in accounts}
