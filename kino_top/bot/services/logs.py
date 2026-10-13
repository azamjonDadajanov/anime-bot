"""Log inspection and retention helpers for the admin panel."""

from __future__ import annotations

import datetime as dt
import logging
from typing import List, Optional

from django.utils import timezone

from ..models import BotLogEntry
from ..utils import to_async

logger = logging.getLogger(__name__)


def recent_logs_sync(limit: int = 10, level: Optional[str] = None) -> List[BotLogEntry]:
	queryset = BotLogEntry.objects.all()
	if level:
		queryset = queryset.filter(level=level)
	return list(queryset.order_by("-created_at")[: max(1, limit)])


recent_logs = to_async(recent_logs_sync)


def error_count_sync(days: int = 1) -> int:
	since = timezone.now() - dt.timedelta(days=days)
	return BotLogEntry.objects.filter(
		created_at__gte=since,
		level__in=[BotLogEntry.Level.ERROR, BotLogEntry.Level.CRITICAL],
	).count()


error_count = to_async(error_count_sync)


def purge_logs_sync(days: int = 30) -> int:
	"""Delete log entries older than ``days`` and return the deleted count."""
	if days <= 0:
		return 0
	cutoff = timezone.now() - dt.timedelta(days=days)
	deleted, _ = BotLogEntry.objects.filter(created_at__lt=cutoff).delete()
	return deleted


purge_logs = to_async(purge_logs_sync)


def level_icon(level: str) -> str:
	return {
		BotLogEntry.Level.DEBUG: "⚪️",
		BotLogEntry.Level.INFO: "ℹ️",
		BotLogEntry.Level.WARNING: "⚠️",
		BotLogEntry.Level.ERROR: "❌",
		BotLogEntry.Level.CRITICAL: "🔥",
	}.get(level, "•")
