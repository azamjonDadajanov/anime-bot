"""Giveaway (raffle) creation, eligibility and drawing.

The administrator builds a giveaway with conditions (watched N anime via the
bot, sponsor-channel membership, referral link in the bio); the *channel* and
*bio* checks run at draw time through the Bot API (see ``bot.services.giveaways``),
while the DB-side eligibility filter and the winner grant live here. Everything
is synchronous and wrapped with ``bot.utils.to_async`` by the handlers.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from movies.models import MediaTitle, MediaView

from .models import Giveaway, GiveawayEntry, GiveawayWinner, Subscription, TelegramUser

# ``draw_winners_sync`` outcomes.
DRAWN = "drawn"
ALREADY_DRAWN = "already_drawn"
NOTHING_TO_DRAW = "nothing_to_draw"
NOT_OPEN = "not_open"

# Plans that count as a live paid subscription (everything except free).
PAID_PLANS = [
	plan
	for plan, _label in Subscription.Plan.choices
	if plan != Subscription.Plan.FREE
]


@dataclass(frozen=True)
class DrawResult:
	status: str
	winners: List[GiveawayWinner] = field(default_factory=list)
	eligible_count: int = 0


class GiveawayValidationError(ValueError):
	"""Raised when the wizard input cannot create a giveaway."""


def create_giveaway_sync(
	*,
	title: str,
	reward_days: int,
	winner_count: int = 3,
	min_bot_views: int = 0,
	require_channels: bool = False,
	require_bio_ref: bool = False,
	created_by=None,
) -> Giveaway:
	"""Validate wizard input and create an OPEN giveaway."""
	clean_title = str(title or "").strip()
	if not clean_title:
		raise GiveawayValidationError("Nomi bo'sh.")
	if len(clean_title) > 200:
		clean_title = clean_title[:200]
	try:
		reward_days = int(reward_days)
		winner_count = int(winner_count)
		min_bot_views = int(min_bot_views or 0)
	except (TypeError, ValueError) as exc:
		raise GiveawayValidationError("Raqamlar noto'g'ri.") from exc
	if reward_days <= 0:
		raise GiveawayValidationError("Mukofot kunlari musbat bo'lishi kerak.")
	if winner_count <= 0 or winner_count > 50:
		raise GiveawayValidationError("G'oliblar soni 1–50 oralig'ida bo'lishi kerak.")
	if min_bot_views < 0:
		min_bot_views = 0

	return Giveaway.objects.create(
		title=clean_title,
		reward_days=reward_days,
		winner_count=winner_count,
		min_bot_views=min_bot_views,
		require_channels=bool(require_channels),
		require_bio_ref=bool(require_bio_ref),
		status=Giveaway.Status.OPEN,
		created_by=created_by,
	)


def all_giveaways_sync() -> List[Giveaway]:
	return list(
		Giveaway.objects.select_related("created_by").prefetch_related("channels").order_by(
			"-created_at", "-id"
		)
	)


def giveaway_count_sync() -> int:
	return Giveaway.objects.count()


def get_giveaway_sync(pk: int) -> Optional[Giveaway]:
	return (
		Giveaway.objects.select_related("created_by")
		.prefetch_related("channels", "winners")
		.filter(pk=pk)
		.first()
	)


def set_giveaway_status_sync(pk: int, status: str) -> Optional[Giveaway]:
	giveaway = Giveaway.objects.filter(pk=pk).first()
	if giveaway is None:
		return None
	if giveaway.status == Giveaway.Status.DRAWN:
		# A finished raffle's status is history and never flips back.
		return giveaway
	if giveaway.status != status:
		giveaway.status = status
		giveaway.save(update_fields=["status", "updated_at"])
	return giveaway


def delete_giveaway_sync(pk: int) -> bool:
	deleted, _ = Giveaway.objects.filter(pk=pk).delete()
	return bool(deleted)


def candidate_profiles_sync(giveaway: Giveaway) -> List[TelegramUser]:
	"""Profiles that pass the *database-side* conditions.

	Channel membership and the bio check are verified live at draw time (the
	bot side), so they are intentionally not filtered here.
	"""
	now = timezone.now()
	base = (
		TelegramUser.objects.filter(
			auth_user__isnull=False,
			auth_user__subscription__plan__in=PAID_PLANS,
			auth_user__subscription__expires_at__gt=now,
		)
		.select_related("auth_user", "auth_user__subscription")
		.order_by("telegram_id")
	)
	if giveaway.min_bot_views > 0:
		base = base.annotate(
			bot_anime=Count(
				"auth_user__media_views__title",
				distinct=True,
				filter=Q(
					auth_user__media_views__source=MediaView.Source.BOT,
					auth_user__media_views__title__type=MediaTitle.MediaType.ANIME,
				),
			)
		).filter(bot_anime__gte=giveaway.min_bot_views)
	return list(base)


def candidate_telegram_ids_sync(giveaway: Giveaway) -> List[int]:
	return [profile.telegram_id for profile in candidate_profiles_sync(giveaway)]


def record_entry_sync(
	*, giveaway: Giveaway, user, telegram_id: int, status: str
) -> GiveawayEntry:
	"""Upsert the per-candidate journal row (statuses accumulate per draw)."""
	entry = GiveawayEntry.objects.filter(giveaway=giveaway, user=user).first()
	if entry is None:
		return GiveawayEntry.objects.create(
			giveaway=giveaway,
			user=user,
			telegram_id=telegram_id,
			status=status,
		)
	if entry.status != status:
		entry.status = status
		entry.save(update_fields=["status"])
	return entry


def draw_winners_sync(
	giveaway: Giveaway,
	eligible_telegram_ids: List[int],
	*,
	rng: Optional[random.Random] = None,
) -> DrawResult:
	"""Grant the reward to ``winner_count`` random eligible users, once.

	The giveaway row is locked so a double press of the draw button cannot pay
	out twice; a finished giveaway reports ``ALREADY_DRAWN``.
	"""
	rng = rng or random.SystemRandom()
	with transaction.atomic():
		giveaway = Giveaway.objects.select_for_update().get(pk=giveaway.pk)
		if giveaway.status == Giveaway.Status.DRAWN:
			return DrawResult(ALREADY_DRAWN)
		if giveaway.status not in (Giveaway.Status.OPEN, Giveaway.Status.DRAFT):
			return DrawResult(NOT_OPEN)

		already = set(
			GiveawayWinner.objects.filter(giveaway=giveaway).values_list(
				"telegram_id", flat=True
			)
		)
		pool = [tg_id for tg_id in dict.fromkeys(eligible_telegram_ids) if tg_id not in already]
		if not pool:
			return DrawResult(NOTHING_TO_DRAW, eligible_count=0)

		count = min(int(giveaway.winner_count or 3), len(pool))
		picked = rng.sample(pool, count)

		winners: List[GiveawayWinner] = []
		for telegram_id in picked:
			profile = TelegramUser.objects.select_related("auth_user").filter(
				telegram_id=telegram_id
			).first()
			if profile is None or profile.auth_user_id is None:
				continue
			subscription, _ = Subscription.objects.get_or_create(user_id=profile.auth_user_id)
			subscription.grant_days(giveaway.reward_days)
			winners.append(
				GiveawayWinner.objects.create(
					giveaway=giveaway,
					user_id=profile.auth_user_id,
					telegram_id=telegram_id,
					days=giveaway.reward_days,
				)
			)
			GiveawayEntry.objects.filter(giveaway=giveaway, user_id=profile.auth_user_id).update(
				status=GiveawayEntry.Status.WINNER
			)

		giveaway.status = Giveaway.Status.DRAWN
		giveaway.drawn_at = timezone.now()
		giveaway.save(update_fields=["status", "drawn_at", "updated_at"])
		return DrawResult(DRAWN, winners=winners, eligible_count=len(pool))


def mark_winner_notified_sync(winner: GiveawayWinner) -> None:
	if winner.notified_at is None:
		winner.notified_at = timezone.now()
		winner.save(update_fields=["notified_at"])
