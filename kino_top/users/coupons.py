"""Coupon (promo code) creation and first-come-first-served redemption.

A coupon promises a number of *days* of access to a limited number of people.
The order matters: the first ``max_uses`` users who enter the code win the days,
and every later attempt simply reads the coupon as expired. Everything here is
synchronous and wrapped with ``bot.utils.to_async`` by the handlers, so the ORM
never runs on the event loop.
"""

from __future__ import annotations

import secrets
import string
from dataclasses import dataclass
from typing import List, Optional

from django.db import transaction

from .models import Coupon, CouponRedemption, Subscription, TelegramUser

CODE_ALPHABET = string.ascii_uppercase + string.digits
CODE_LENGTH = 8
MIN_CODE_LENGTH = 4
MAX_CODE_LENGTH = 24

# ``redeem_coupon_sync`` outcomes.
REDEEMED = "redeemed"
ALREADY = "already"
EXPIRED = "expired"
NOT_FOUND = "not_found"
NO_ACCOUNT = "no_account"


class CouponCodeInvalid(ValueError):
	"""Raised when an administrator enters a code we cannot accept."""


class CouponCodeTaken(ValueError):
	"""Raised when an administrator reuses an existing code."""


@dataclass(frozen=True)
class RedeemResult:
	status: str
	coupon: Optional[Coupon] = None
	days: int = 0
	expires_at: Optional[object] = None


def normalize_code(code: object) -> str:
	"""Uppercase and strip whitespace so `` ab 12 `` matches ``AB12``."""
	return "".join(str(code or "").split()).upper()


def is_valid_code(code: str) -> bool:
	"""Accept 4-24 alphanumerics that include at least one letter.

	The letter requirement keeps a coupon code from colliding with the 4-digit
	title codes the bot resolves automatically in a plain chat message.
	"""
	if not MIN_CODE_LENGTH <= len(code) <= MAX_CODE_LENGTH:
		return False
	if not all(char in CODE_ALPHABET for char in code):
		return False
	return any(char.isalpha() for char in code)


def generate_code() -> str:
	"""A unique random code (the administrator may always type their own)."""
	for _ in range(50):
		candidate = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
		if not Coupon.objects.filter(code=candidate).exists():
			return candidate
	# Astronomically unlikely, but never loop forever.
	base = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
	suffix = 0
	while Coupon.objects.filter(code=f"{base}{suffix}").exists():
		suffix += 1
	return f"{base}{suffix}"


def create_coupon_sync(
	*,
	days: int,
	max_uses: int,
	code: str = "",
	created_by=None,
) -> Coupon:
	"""Create a coupon. Raises :class:`CouponCodeInvalid`/``Taken`` on bad input."""
	try:
		days = int(days)
		max_uses = int(max_uses)
	except (TypeError, ValueError) as exc:
		raise CouponCodeInvalid("Kunlar va son butun son bo'lishi kerak.") from exc
	if days <= 0 or max_uses <= 0:
		raise CouponCodeInvalid("Kunlar va foydalanuvchilar soni musbat bo'lishi kerak.")

	normalized = normalize_code(code)
	if not normalized:
		normalized = generate_code()
	elif not is_valid_code(normalized):
		raise CouponCodeInvalid(normalized)
	if Coupon.objects.filter(code=normalized).exists():
		raise CouponCodeTaken(normalized)

	return Coupon.objects.create(
		code=normalized,
		days=days,
		max_uses=max_uses,
		created_by=created_by,
	)


def redeem_coupon_sync(code: str, *, telegram_id: int) -> RedeemResult:
	"""Redeem ``code`` for the profile behind ``telegram_id``.

	Runs inside a transaction with the coupon row locked so two users racing for
	the last slot cannot both win it (a no-op lock on SQLite, real on Postgres).
	"""
	normalized = normalize_code(code)
	if not is_valid_code(normalized):
		return RedeemResult(NOT_FOUND)

	try:
		telegram_id = int(telegram_id)
	except (TypeError, ValueError):
		return RedeemResult(NO_ACCOUNT)

	profile = (
		TelegramUser.objects.select_related("auth_user")
		.filter(telegram_id=telegram_id)
		.first()
	)
	if profile is None or profile.auth_user_id is None:
		return RedeemResult(NO_ACCOUNT)

	with transaction.atomic():
		coupon = Coupon.objects.select_for_update().filter(code=normalized).first()
		if coupon is None:
			return RedeemResult(NOT_FOUND)

		# An earlier use always wins over the coupon's current state, so a user
		# who already redeemed never sees a confusing "expired" message.
		if CouponRedemption.objects.filter(
			coupon=coupon, user_id=profile.auth_user_id
		).exists():
			return RedeemResult(ALREADY, coupon, coupon.days)

		if coupon.is_expired:
			return RedeemResult(EXPIRED, coupon, coupon.days)

		subscription, _ = Subscription.objects.get_or_create(user_id=profile.auth_user_id)
		subscription.grant_days(coupon.days)

		coupon.used_count = coupon.used_count + 1
		coupon.save(update_fields=["used_count", "updated_at"])
		CouponRedemption.objects.create(
			coupon=coupon,
			user_id=profile.auth_user_id,
			telegram_id=profile.telegram_id,
			days=coupon.days,
		)
		return RedeemResult(REDEEMED, coupon, coupon.days, subscription.expires_at)


def all_coupons_sync() -> List[Coupon]:
	"""Every coupon, newest first (the admin list paginates in memory)."""
	return list(
		Coupon.objects.select_related("created_by", "posted_channel").order_by(
			"-created_at", "-id"
		)
	)


def coupon_count_sync() -> int:
	return Coupon.objects.count()


def get_coupon_sync(pk: int) -> Optional[Coupon]:
	return Coupon.objects.select_related("posted_channel").filter(pk=pk).first()


def set_coupon_active_sync(pk: int, active: bool) -> Optional[Coupon]:
	coupon = Coupon.objects.filter(pk=pk).first()
	if coupon is None:
		return None
	if coupon.is_active != active:
		coupon.is_active = active
		coupon.save(update_fields=["is_active", "updated_at"])
	return coupon


def delete_coupon_sync(pk: int) -> bool:
	deleted, _ = Coupon.objects.filter(pk=pk).delete()
	return bool(deleted)
