"""Plan catalogue helpers shared by the API and the Telegram bot.

Every number shown on the "Obuna" page is computed live from the database:
how many titles of each type a plan unlocks, plus its configured price.
"""

from __future__ import annotations

from typing import Any, Dict, List

from django.conf import settings
from django.db.models import Count

from movies.models import MediaTitle

PLAN_ORDER = ["free", "plus", "pro"]

PLAN_RANK = {"free": 0, "plus": 1, "pro": 2}

PLAN_LABELS = {"free": "Free", "plus": "Plus", "pro": "Pro"}

PLAN_DESCRIPTIONS = {
	"free": "Boshlash uchun asosiy tarif.",
	"plus": "Ko'proq kontent uchun kengaytirilgan tarif.",
	"pro": "Kino Top imkoniyatlarining to'liq to'plami.",
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
	return PLAN_RANK.get(str(plan or "free").lower(), 0)


def plan_price(plan: str | None) -> int:
	prices = getattr(settings, "SUBSCRIPTION_PRICES", {}) or {}
	try:
		return int(prices.get(str(plan or "free").lower(), 0) or 0)
	except (TypeError, ValueError):  # pragma: no cover - defensive
		return 0


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
	"""Titles available to each plan, split by media type."""
	rows = (
		MediaTitle.objects.values("type", "required_plan")
		.order_by()
		.annotate(total=Count("id"))
	)
	counts: Dict[str, Dict[str, int]] = {
		plan: {media_type: 0 for media_type in TYPE_ORDER} for plan in PLAN_ORDER
	}
	for row in rows:
		needed = plan_rank(row["required_plan"])
		total = int(row["total"])
		for plan in PLAN_ORDER:
			if plan_rank(plan) >= needed:
				counts[plan][row["type"]] = counts[plan].get(row["type"], 0) + total
	return counts


def plan_details(plan: str) -> Dict[str, Any]:
	"""Everything the UI needs to render one plan row."""
	plan = str(plan or "free").lower()
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
	return {
		"id": plan,
		"label": PLAN_LABELS.get(plan, plan.title()),
		"description": PLAN_DESCRIPTIONS.get(plan, ""),
		"price": plan_price(plan),
		"features": features,
		"summary": "  ".join(f"{item['display']} {item['label']}" for item in features),
	}


def all_plan_details() -> List[Dict[str, Any]]:
	return [plan_details(plan) for plan in PLAN_ORDER]
