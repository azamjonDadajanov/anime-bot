"""Plan catalogue helpers shared by the API and the Telegram bot.

Subscriptions are duration based: a plan unlocks *everything* for a fixed
number of days. Every number shown on the "Obuna" page is computed live from
the database: how many titles each plan unlocks, plus its configured price.
"""

from __future__ import annotations

from typing import Any, Dict, List

from django.conf import settings
from django.db.models import Count

from movies.models import MediaTitle

from .models import Subscription

FREE_PLAN = "free"

# Buyable plans, in the order they appear on the "Obuna" page.
PLAN_ORDER = ["daily", "d15", "monthly", "quarterly", "yearly"]

ALL_PLANS = [FREE_PLAN, *PLAN_ORDER]

# How long a plan keeps the catalogue open once it has been paid for.
PLAN_DAYS = {
	FREE_PLAN: 0,
	"daily": 1,
	"d15": 15,
	"monthly": 30,
	"quarterly": 90,
	"yearly": 365,
}

PLAN_RANK = {plan: index for index, plan in enumerate(ALL_PLANS)}

# Labels live on the model choices so ``get_plan_display()`` and the catalogue
# can never disagree.
PLAN_LABELS = dict(Subscription.Plan.choices)

PLAN_DESCRIPTIONS = {
	FREE_PLAN: "Ro'yxatdan o'tish bilan ochiladigan bepul rejim — cheklangan kontent.",
	"daily": "Bir kunga to'liq kirish.",
	"d15": "15 kunlik to'liq kirish.",
	"monthly": "Bir oyga to'liq kirish — eng mashhur tarif.",
	"quarterly": "Uch oylik to'liq kirish — oylik narxdan 15% arzon.",
	"yearly": "Bir yillik to'liq kirish — eng foydali tarif.",
}

TYPE_LABELS = {
	MediaTitle.MediaType.ANIME: "anime",
	MediaTitle.MediaType.SERIES: "serial",
	MediaTitle.MediaType.MANGA: "manga",
	MediaTitle.MediaType.MOVIE: "kino",
}

TYPE_ORDER = [
	MediaTitle.MediaType.ANIME,
	MediaTitle.MediaType.MOVIE,
	MediaTitle.MediaType.SERIES,
	MediaTitle.MediaType.MANGA,
]


def plan_rank(plan: str | None) -> int:
	return PLAN_RANK.get(str(plan or FREE_PLAN).lower(), 0)


def plan_label(plan: str | None) -> str:
	key = str(plan or FREE_PLAN).lower()
	return PLAN_LABELS.get(key, key.title())


def plan_days(plan: str | None) -> int:
	"""Duration of ``plan`` in days (``0`` for the free tier)."""
	try:
		return int(PLAN_DAYS.get(str(plan or FREE_PLAN).lower(), 0) or 0)
	except (TypeError, ValueError):  # pragma: no cover - defensive
		return 0


def is_paid_plan(plan: str | None) -> bool:
	return plan_days(plan) > 0


def plan_price(plan: str | None) -> int:
	prices = getattr(settings, "SUBSCRIPTION_PRICES", {}) or {}
	try:
		return int(prices.get(str(plan or FREE_PLAN).lower(), 0) or 0)
	except (TypeError, ValueError):  # pragma: no cover - defensive
		return 0


def price_per_day(plan: str | None) -> int:
	days = plan_days(plan)
	if days <= 0:
		return 0
	return round(plan_price(plan) / days)


def card_number() -> str:
	return str(getattr(settings, "SUBSCRIPTION_CARD_NUMBER", "") or "")


def _pretty_count(count: int) -> str:
	"""``173`` -> ``100+`` style label, but never rounds a small number up."""
	if count <= 0:
		return "0"
	if count < 100:
		return str(count)
	step = 100 if count < 1000 else 1000
	return f"{(count // step) * step}+"


def content_counts() -> Dict[str, Dict[str, int]]:
	"""Titles available to each plan, split by media type.

	Content is either open to everyone (``free``) or reserved for a live
	subscription (``paid``): every paid plan therefore unlocks the whole
	catalogue, while the free tier only sees the free titles.
	"""
	rows = (
		MediaTitle.objects.values("type", "required_plan")
		.order_by()
		.annotate(total=Count("id"))
	)
	counts: Dict[str, Dict[str, int]] = {
		plan: {media_type: 0 for media_type in TYPE_ORDER} for plan in ALL_PLANS
	}
	for row in rows:
		media_type = row["type"]
		total = int(row["total"])
		for plan in PLAN_ORDER:
			counts[plan][media_type] = counts[plan].get(media_type, 0) + total
		if str(row["required_plan"] or FREE_PLAN).lower() == FREE_PLAN:
			counts[FREE_PLAN][media_type] = counts[FREE_PLAN].get(media_type, 0) + total
	return counts


def plan_details(plan: str) -> Dict[str, Any]:
	"""Everything the UI needs to render one plan row."""
	plan = str(plan or FREE_PLAN).lower()
	counts = content_counts().get(plan, {})
	features = []
	for media_type in TYPE_ORDER:
		raw = int(counts.get(media_type, 0))
		features.append(
			{
				"type": media_type,
				"label": TYPE_LABELS[media_type],
				"count": raw,
				"display": _pretty_count(raw),
			}
		)
	days = plan_days(plan)
	price = plan_price(plan)
	return {
		"id": plan,
		"label": PLAN_LABELS.get(plan, plan.title()),
		"description": PLAN_DESCRIPTIONS.get(plan, ""),
		"price": price,
		"days": days,
		"price_per_day": price_per_day(plan),
		"is_paid": days > 0,
		"features": features,
		"summary": "  ".join(f"{item['display']} {item['label']}" for item in features),
	}


def all_plan_details() -> List[Dict[str, Any]]:
	return [plan_details(plan) for plan in PLAN_ORDER]
