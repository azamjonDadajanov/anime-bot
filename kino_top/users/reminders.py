"""Subscription expiry reminders.

A cron job runs ``manage.py send_subscription_reminders``; this module decides
who is due and what to say. Two stages exist:

* ``expiring`` — the plan runs out within :data:`REMIND_BEFORE_DAYS` days;
* ``expired``  — it ran out within the last :data:`REMIND_AFTER_DAYS` days.

``Subscription.reminder_stage`` remembers the stage already delivered for the
current window, so a daily cron sends each stage at most once, and it is marked
only after a successful delivery (a failed attempt simply retries tomorrow).
Activating, extending or ending a plan clears the marker and starts a new cycle
(see ``Subscription.reset_reminder``).

Reminders are Telegram direct messages, so the copy lives here rather than in
``bot.texts``: ``users`` must not import the bot package (the bot imports
``users``).
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional

from django.utils import timezone

from .models import Subscription
from .telegram_notify import send_telegram_message

logger = logging.getLogger(__name__)

REMIND_BEFORE_DAYS = 3
REMIND_AFTER_DAYS = 7

EXPIRING = "expiring"
EXPIRED = "expired"

EXPIRING_TEXT = (
	"⏳ <b>Obunangiz tugab qolmoqda</b>\n\n"
	"💎 Tarif: <b>{plan}</b>\n"
	"📅 Tugash sanasi: <b>{expires}</b>\n"
	"🕒 Qolgan vaqt: <b>{days} kun</b>\n\n"
	"Uzaytirish uchun «🎫 Obuna» bo'limiga o'ting."
)
EXPIRED_TEXT = (
	"⚠️ <b>Obunangiz muddati tugadi</b>\n\n"
	"💎 Tarif: <b>{plan}</b>\n"
	"📅 Tugagan sana: <b>{expires}</b>\n\n"
	"Kontent yana ochilishi uchun obunani yangilang: «🎫 Obuna»."
)


@dataclass(frozen=True)
class Reminder:
	"""A reminder that is due for one subscription."""

	subscription: Subscription
	telegram_id: int
	stage: str
	days: int

	def render(self) -> str:
		plan = self.subscription.get_plan_display()
		expires = _human_date(self.subscription.expires_at)
		if self.stage == EXPIRING:
			return EXPIRING_TEXT.format(plan=plan, expires=expires, days=self.days)
		return EXPIRED_TEXT.format(plan=plan, expires=expires)


def _human_date(value: Optional[datetime]) -> str:
	return value.strftime("%d.%m.%Y") if value else "—"


def _days(subscription: Subscription, now: datetime, stage: str) -> int:
	expires_at = subscription.expires_at
	if expires_at is None:  # pragma: no cover - callers filter this out
		return 0
	if stage == EXPIRING:
		return max(1, math.ceil((expires_at - now).total_seconds() / 86400))
	return max(0, int((now - expires_at).total_seconds() // 86400))


def reminder_stage(
	subscription: Optional[Subscription], now: Optional[datetime] = None
) -> str:
	"""Which reminder stage is due right now (``""`` when none is)."""
	if subscription is None:
		return ""
	plan = subscription.plan or Subscription.Plan.FREE
	if plan == Subscription.Plan.FREE or subscription.expires_at is None:
		return ""
	now = now or timezone.now()
	expires_at = subscription.expires_at
	if expires_at > now:
		days_left = math.ceil((expires_at - now).total_seconds() / 86400)
		return EXPIRING if days_left <= REMIND_BEFORE_DAYS else ""
	days_since = int((now - expires_at).total_seconds() // 86400)
	return EXPIRED if days_since <= REMIND_AFTER_DAYS else ""


def reminder_payload(
	subscription: Optional[Subscription], now: Optional[datetime] = None
) -> Optional[dict]:
	"""Compact state for the website banner.

	Deliberately ignores ``reminder_stage``: the panel describes the *state* of
	the subscription, not whether the bot already sent a direct message about it.
	"""
	stage = reminder_stage(subscription, now)
	if not stage:
		return None
	now = now or timezone.now()
	return {
		"stage": stage,
		"days": _days(subscription, now, stage),
		"expires_at": subscription.expires_at,
	}


def due_reminders_sync(
	now: Optional[datetime] = None, *, limit: Optional[int] = None
) -> List[Reminder]:
	"""Every subscription whose next reminder has not been delivered yet."""
	now = now or timezone.now()
	queryset = (
		Subscription.objects.select_related("user", "user__telegram_profile")
		.exclude(plan=Subscription.Plan.FREE)
		.exclude(expires_at__isnull=True)
		.filter(
			expires_at__lte=now + timedelta(days=REMIND_BEFORE_DAYS),
			expires_at__gte=now - timedelta(days=REMIND_AFTER_DAYS + 1),
		)
		.order_by("expires_at")
	)

	reminders: List[Reminder] = []
	for subscription in queryset.iterator():
		stage = reminder_stage(subscription, now)
		if not stage or stage == subscription.reminder_stage:
			continue
		profile = getattr(subscription.user, "telegram_profile", None)
		# Without a Telegram profile (or after a block) the Bot API cannot reach
		# the account at all, so there is nothing to remind.
		if profile is None or profile.is_blocked:
			continue
		reminders.append(
			Reminder(
				subscription=subscription,
				telegram_id=profile.telegram_id,
				stage=stage,
				days=_days(subscription, now, stage),
			)
		)
		if limit and len(reminders) >= limit:
			break
	return reminders


def mark_reminded(
	subscription: Subscription, stage: str, *, now: Optional[datetime] = None
) -> None:
	subscription.reminder_stage = stage
	subscription.reminder_sent_at = now or timezone.now()
	subscription.save(
		update_fields=[*Subscription.REMINDER_FIELDS, "updated_at"]
	)


def send_reminder_sync(reminder: Reminder, *, now: Optional[datetime] = None) -> bool:
	"""Deliver one reminder and remember it was sent.

	The marker is written only on success so a transient Telegram failure is
	retried by the next run.
	"""
	delivered, error = send_telegram_message(
		reminder.telegram_id, reminder.render()
	)
	if delivered:
		mark_reminded(reminder.subscription, reminder.stage, now=now)
	else:
		logger.warning(
			"Reminder (%s) for %s was not delivered: %s",
			reminder.stage,
			reminder.telegram_id,
			error or "unknown",
		)
	return delivered
