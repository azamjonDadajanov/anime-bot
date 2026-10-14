"""Web orqali broadcast yuborish — bot bilan bir xil run_broadcast."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_running: set[int] = set()


def _run_in_thread(broadcast_id: int) -> None:
	async def _inner() -> None:
		from aiogram import Bot

		from bot.models import Broadcast
		from bot.services.broadcast import run_broadcast

		broadcast = await Broadcast.objects.aget(pk=broadcast_id)
		token = getattr(settings, "BOT_TOKEN", "") or getattr(settings, "TELEGRAM_BOT_TOKEN", "")
		if not token:
			broadcast.last_error = "BOT_TOKEN sozlanmagan."
			broadcast.status = Broadcast.Status.FAILED
			broadcast.finished_at = timezone.now()
			await broadcast.asave(
				update_fields=["last_error", "status", "finished_at"],
			)
			return
		bot = Bot(token=token)
		try:
			await run_broadcast(bot, broadcast)
		finally:
			await bot.session.close()

	try:
		asyncio.run(_inner())
	except Exception as exc:  # noqa: BLE001 - broadcast errors must not crash the API
		logger.exception("Broadcast #%s failed.", broadcast_id)
		try:
			from bot.models import Broadcast

			broadcast = Broadcast.objects.get(pk=broadcast_id)
			if broadcast.status == Broadcast.Status.RUNNING:
				broadcast.last_error = str(exc)
				broadcast.mark_finished(Broadcast.Status.FAILED)
		except Exception:  # noqa: BLE001
			logger.exception("Failed to mark broadcast #%s as failed.", broadcast_id)
	finally:
		with _lock:
			_running.discard(broadcast_id)


def start_broadcast_async(broadcast_id: int) -> Optional[str]:
	"""Broadcastni background thread'da ishga tushiradi.

	Returns None if started, or an error message if already running.
	"""
	with _lock:
		if broadcast_id in _running:
			return "Bu broadcast allaqachon ishga tushirilgan."
		_running.add(broadcast_id)

	thread = threading.Thread(
		target=_run_in_thread,
		args=(broadcast_id,),
		daemon=True,
		name=f"broadcast-{broadcast_id}",
	)
	thread.start()
	return None
