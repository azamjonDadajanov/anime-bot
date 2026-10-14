"""Referral tracking and manual milestone rewards.

A new user is attributed to exactly one inviter the first time they open the
bot with a ``ref_<telegram_id>`` deep link; the attribution never changes and
self-referrals are ignored. Milestone rewards (10 -> 15 days, 15 -> 30 days)
are claimed *manually* by the inviter via a button — nothing is granted
automatically. Everything here is synchronous and wrapped with
``bot.utils.to_async`` by the handlers, so the ORM never runs on the event loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from django.db import transaction, IntegrityError

from .models import ReferralReward, Subscription, TelegramUser

# ``claim_reward_sync`` outcomes.
CLAIMED = "claimed"
ALREADY = "already"
NOT_ENOUGH = "not_enough"
NOT_FOUND = "not_found"
NO_ACCOUNT = "no_account"
INVALID = "invalid"

REFERRAL_MILESTONES = dict(ReferralReward.MILESTONES)


@dataclass(frozen=True)
class ReferralStats:
	telegram_id: int
	invited_count: int = 0
	claimed_milestones: List[int] = field(default_factory=list)
	link: str = ""


@dataclass(frozen=True)
class ClaimResult:
	status: str
	milestone: int = 0
	days: int = 0
	invited_count: int = 0
	expires_at: Optional[object] = None


def referral_payload(telegram_id: int) -> str:
	"""Deep-link payload that attributes a new user to ``telegram_id``."""
	return f"ref_{int(telegram_id)}"


def parse_referral_payload(payload: object) -> Optional[int]:
	"""Return the inviter's telegram id for a ``ref_<id>`` payload, else None."""
	text = str(payload or "")
	if not text.startswith("ref_"):
		return None
	raw = text[4:]
	if not raw.isdigit():
		return None
	try:
		return int(raw)
	except ValueError:
		return None


def register_referral_sync(*, invitee: TelegramUser, inviter_tg_id: int) -> bool:
	"""Attribute ``invitee`` to ``inviter_tg_id`` once; later calls are no-ops.

	Returns True only when the attribution actually happened.
	"""
	try:
		inviter_tg_id = int(inviter_tg_id)
	except (TypeError, ValueError):
		return False
	if invitee is None or not invitee.pk or invitee.telegram_id == inviter_tg_id:
		return False
	if invitee.referred_by_id is not None:
		return False
	inviter = TelegramUser.objects.filter(telegram_id=inviter_tg_id).first()
	if inviter is None or not inviter.pk or inviter.pk == invitee.pk:
		return False
	updated = TelegramUser.objects.filter(pk=invitee.pk, referred_by__isnull=True).update(
		referred_by=inviter
	)
	return bool(updated)


def referral_stats_sync(telegram_id: int) -> ReferralStats:
	"""Invited count, already-claimed milestones and the invite link."""
	invited = TelegramUser.objects.filter(referred_by__telegram_id=telegram_id).count()
	claimed = list(
		ReferralReward.objects.filter(user__telegram_profile__telegram_id=telegram_id)
		.order_by("milestone")
		.values_list("milestone", flat=True)
	)
	return ReferralStats(
		telegram_id=int(telegram_id),
		invited_count=invited,
		claimed_milestones=claimed,
		link=referral_payload(telegram_id),
	)


def claim_reward_sync(*, telegram_id: int, milestone: int) -> ClaimResult:
	"""Claim the ``milestone`` reward for the profile behind ``telegram_id``.

	The reward is granted only when the inviter has enough attributed users and
	has not claimed this milestone before (UniqueConstraint as the last resort).
	"""
	try:
		telegram_id = int(telegram_id)
		milestone = int(milestone)
	except (TypeError, ValueError):
		return ClaimResult(INVALID)

	days = REFERRAL_MILESTONES.get(milestone)
	if not days:
		return ClaimResult(INVALID)

	profile = (
		TelegramUser.objects.select_related("auth_user")
		.filter(telegram_id=telegram_id)
		.first()
	)
	if profile is None or profile.auth_user_id is None:
		return ClaimResult(NO_ACCOUNT)

	with transaction.atomic():
		profile = TelegramUser.objects.select_for_update().get(pk=profile.pk)
		invited = TelegramUser.objects.filter(referred_by__telegram_id=telegram_id).count()
		if invited < milestone:
			return ClaimResult(NOT_ENOUGH, milestone, days, invited)

		if ReferralReward.objects.filter(
			user_id=profile.auth_user_id, milestone=milestone
		).exists():
			return ClaimResult(ALREADY, milestone, days, invited)

		subscription, _ = Subscription.objects.get_or_create(user_id=profile.auth_user_id)
		subscription.grant_days(days)
		try:
			ReferralReward.objects.create(
				user_id=profile.auth_user_id,
				milestone=milestone,
				days=days,
			)
		except IntegrityError:
			# A racing claim already won; roll the whole transaction back so the
			# stacked subscription days are undone too.
			transaction.set_rollback(True)
			return ClaimResult(ALREADY, milestone, days, invited)
		return ClaimResult(
			CLAIMED, milestone, days, invited, subscription.expires_at
		)
