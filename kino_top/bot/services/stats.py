"""Dashboard statistics and reports for the admin panel."""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict

from django.utils import timezone

from movies.models import Genre, MediaPart, MediaTitle, TelegramChannel, TelegramMedia
from users.models import FavoriteContent

from ..models import BotLogEntry, Broadcast, BroadcastDelivery
from ..utils import to_async
from .users import active_user_count_sync, user_count_sync


def dashboard_sync() -> Dict[str, Any]:
	media_counts = {
		"titles": MediaTitle.objects.count(),
		"episodes": MediaPart.objects.count(),
		"files": TelegramMedia.objects.count(),
		"genres": Genre.objects.count(),
	}
	channel_counts = {
		"total": TelegramChannel.objects.count(),
		"active": TelegramChannel.objects.filter(is_active=True).count(),
		"required": TelegramChannel.objects.filter(purpose=TelegramChannel.Purpose.REQUIRED).count(),
		"storage": TelegramChannel.objects.filter(purpose=TelegramChannel.Purpose.STORAGE).count(),
		"public": TelegramChannel.objects.filter(purpose=TelegramChannel.Purpose.PUBLIC).count(),
	}
	return {
		"users": user_count_sync(),
		"active_users": active_user_count_sync(),
		"favorites": FavoriteContent.objects.count(),
		"media": media_counts,
		"channels": channel_counts,
		"broadcasts": {
			"total": Broadcast.objects.count(),
			"running": Broadcast.objects.filter(status=Broadcast.Status.RUNNING).count(),
		},
		"logs": BotLogEntry.objects.count(),
	}


dashboard = to_async(dashboard_sync)


def reports_sync(days: int = 30) -> Dict[str, Any]:
	since = timezone.now() - dt.timedelta(days=days)
	deliveries = BroadcastDelivery.objects.filter(created_at__gte=since)
	return {
		"window_days": days,
		"broadcasts": Broadcast.objects.filter(created_at__gte=since).count(),
		"sent": deliveries.filter(status=BroadcastDelivery.Status.SENT).count(),
		"blocked": deliveries.filter(status=BroadcastDelivery.Status.BLOCKED).count(),
		"failed": deliveries.filter(status=BroadcastDelivery.Status.FAILED).count(),
		"logs": BotLogEntry.objects.filter(created_at__gte=since).count(),
		"errors": BotLogEntry.objects.filter(
			created_at__gte=since,
			level__in=[BotLogEntry.Level.ERROR, BotLogEntry.Level.CRITICAL],
		).count(),
	}


reports = to_async(reports_sync)
