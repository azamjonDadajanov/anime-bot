"""Broadcast engine.

Design goals:

* **Bounded concurrency** — a semaphore caps parallel Telegram requests.
* **Rate limiting** — a global token bucket honours Telegram's ~30 msg/s limit
  and respects ``TelegramRetryAfter`` instead of hammering the API.
* **Per-recipient isolation** — one blocked user or bad request never stops the
  campaign; each result is recorded in ``BroadcastDelivery``.
* **Durable, resumable state** — counters and a ``cursor_telegram_id`` are
  flushed after every batch, so a crashed or cancelled run resumes exactly
  where it stopped instead of re-messaging everyone.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from aiogram import Bot
from aiogram.exceptions import (
	TelegramAPIError,
	TelegramBadRequest,
	TelegramForbiddenError,
	TelegramRetryAfter,
)
from aiogram.types import Message
from django.db import transaction
from django.utils import timezone

from ..models import Broadcast, BroadcastDelivery
from ..utils import chunked, to_async
from .bot_settings import get_settings
from .users import recipients_sync

logger = logging.getLogger(__name__)

MAX_RETRIES = 2
BATCH_MULTIPLIER = 4


@dataclass
class BroadcastProgress:
	pk: int
	status: str
	total: int
	sent: int
	failed: int
	blocked: int

	@property
	def processed(self) -> int:
		return self.sent + self.failed + self.blocked


ProgressCallback = Callable[[BroadcastProgress], Awaitable[None]]


class BroadcastPayloadError(RuntimeError):
	"""Raised when the stored broadcast payload is incomplete."""


class RateLimiter:
	"""A tiny global token bucket shared by every broadcast worker."""

	def __init__(self, per_second: float) -> None:
		self._interval = 1.0 / max(1.0, float(per_second))
		self._next_slot = 0.0
		self._lock = asyncio.Lock()

	def _now(self) -> float:
		return asyncio.get_running_loop().time()

	async def acquire(self) -> None:
		async with self._lock:
			now = self._now()
			wait = self._next_slot - now
			if wait > 0:
				await asyncio.sleep(wait)
				now = self._now()
			self._next_slot = max(now, self._next_slot) + self._interval


# ------------------------------------------------------------------- lifecycle
def create_broadcast_sync(**fields: Any) -> Broadcast:
	allowed = {
		"admin_telegram_id",
		"kind",
		"text",
		"caption",
		"file_id",
		"from_chat_id",
		"source_message_id",
		"disable_notification",
		"protect_content",
		"include_blocked",
		"panel_chat_id",
		"panel_message_id",
		"status",
		"total",
		"cursor_telegram_id",
		"sent_count",
		"failed_count",
		"blocked_count",
	}
	payload = {name: value for name, value in fields.items() if name in allowed}
	return Broadcast.objects.create(**payload)


create_broadcast = to_async(create_broadcast_sync)


def get_broadcast_sync(pk: int) -> Optional[Broadcast]:
	return Broadcast.objects.filter(pk=pk).first()


get_broadcast = to_async(get_broadcast_sync)


def active_broadcast_sync(admin_telegram_id: Optional[int] = None) -> Optional[Broadcast]:
	queryset = Broadcast.objects.filter(
		status__in=[Broadcast.Status.RUNNING, Broadcast.Status.PAUSED]
	)
	if admin_telegram_id:
		queryset = queryset.filter(admin_telegram_id=admin_telegram_id)
	return queryset.order_by("-created_at").first()


active_broadcast = to_async(active_broadcast_sync)


def request_cancel_sync(pk: int) -> bool:
	updated = Broadcast.objects.filter(
		pk=pk, status__in=[Broadcast.Status.RUNNING, Broadcast.Status.PAUSED]
	).update(cancel_requested=True)
	if not updated:
		return False
	return True


request_cancel = to_async(request_cancel_sync)


def clear_cancel_sync(pk: int) -> None:
	Broadcast.objects.filter(pk=pk).update(cancel_requested=False)


def recent_broadcasts_sync(limit: int = 10, offset: int = 0) -> List[Broadcast]:
	return list(Broadcast.objects.all()[offset:offset + max(1, limit)])


recent_broadcasts = to_async(recent_broadcasts_sync)


def broadcast_count_sync() -> int:
	return Broadcast.objects.count()


broadcast_count = to_async(broadcast_count_sync)


def set_total_sync(pk: int, total: int) -> None:
	Broadcast.objects.filter(pk=pk).update(total=total)


set_total = to_async(set_total_sync)


def attach_panel_sync(pk: int, chat_id: int, message_id: int) -> None:
	Broadcast.objects.filter(pk=pk).update(panel_chat_id=chat_id, panel_message_id=message_id)


attach_panel = to_async(attach_panel_sync)


def set_silent_sync(pk: int, silent: bool) -> None:
	Broadcast.objects.filter(pk=pk).update(disable_notification=silent)


set_silent = to_async(set_silent_sync)


def _flush_sync(
	pk: int,
	sent: int,
	failed: int,
	blocked: int,
	cursor: int,
	rows: Optional[List[Dict[str, Any]]] = None,
) -> None:
	with transaction.atomic():
		Broadcast.objects.filter(pk=pk).update(
			sent_count=sent,
			failed_count=failed,
			blocked_count=blocked,
			cursor_telegram_id=cursor,
		)
		if rows:
			BroadcastDelivery.objects.bulk_create(
				[BroadcastDelivery(broadcast_id=pk, **row) for row in rows],
				ignore_conflicts=True,
			)


def _mark_finished_sync(pk: int, status: str, sent: int, failed: int, blocked: int, cursor: int) -> None:
	with transaction.atomic():
		Broadcast.objects.filter(pk=pk).update(
			status=status,
			sent_count=sent,
			failed_count=failed,
			blocked_count=blocked,
			cursor_telegram_id=cursor,
			finished_at=timezone.now(),
		)


def _mark_running_sync(pk: int, total: int) -> None:
	now = timezone.now()
	broadcast = Broadcast.objects.filter(pk=pk).first()
	if broadcast is None:
		return
	broadcast.status = Broadcast.Status.RUNNING
	broadcast.cancel_requested = False
	broadcast.total = total
	if broadcast.started_at is None:
		broadcast.started_at = now
	broadcast.finished_at = None
	broadcast.save(
		update_fields=["status", "cancel_requested", "total", "started_at", "finished_at"]
	)


def _is_cancel_requested_sync(pk: int) -> bool:
	return bool(Broadcast.objects.filter(pk=pk, cancel_requested=True).exists())


# ---------------------------------------------------------------------- payload
async def _send(bot: Bot, broadcast: Broadcast, chat_id: int, *, protect: bool) -> None:
	kind = broadcast.kind
	if kind == Broadcast.Kind.TEXT:
		await bot.send_message(
			chat_id=chat_id,
			text=broadcast.text,
			disable_notification=broadcast.disable_notification,
			protect_content=protect,
		)
	elif kind == Broadcast.Kind.PHOTO:
		await bot.send_photo(
			chat_id=chat_id,
			photo=broadcast.file_id,
			caption=broadcast.caption or None,
			disable_notification=broadcast.disable_notification,
			protect_content=protect,
		)
	elif kind == Broadcast.Kind.VIDEO:
		await bot.send_video(
			chat_id=chat_id,
			video=broadcast.file_id,
			caption=broadcast.caption or None,
			supports_streaming=True,
			disable_notification=broadcast.disable_notification,
			protect_content=protect,
		)
	elif kind == Broadcast.Kind.DOCUMENT:
		await bot.send_document(
			chat_id=chat_id,
			document=broadcast.file_id,
			caption=broadcast.caption or None,
			disable_notification=broadcast.disable_notification,
			protect_content=protect,
		)
	elif kind == Broadcast.Kind.AUDIO:
		await bot.send_audio(
			chat_id=chat_id,
			audio=broadcast.file_id,
			caption=broadcast.caption or None,
			disable_notification=broadcast.disable_notification,
			protect_content=protect,
		)
	elif kind == Broadcast.Kind.FORWARD:
		if not broadcast.from_chat_id or not broadcast.source_message_id:
			raise BroadcastPayloadError("Forward manbasi yo'q.")
		await bot.copy_message(
			chat_id=chat_id,
			from_chat_id=broadcast.from_chat_id,
			message_id=broadcast.source_message_id,
			protect_content=protect,
		)
	else:  # pragma: no cover - guarded by choices
		raise BroadcastPayloadError(f"Noma'lum tur: {kind}")


async def _send_with_retry(bot: Bot, broadcast: Broadcast, chat_id: int, *, protect: bool) -> None:
	for attempt in range(MAX_RETRIES + 1):
		try:
			await _send(bot, broadcast, chat_id, protect=protect)
			return
		except TelegramRetryAfter as exc:
			if attempt >= MAX_RETRIES:
				raise
			wait = float(getattr(exc, "retry_after", 1) or 1)
			logger.warning("Telegram asked to retry after %.1fs (attempt %s).", wait, attempt + 1)
			await asyncio.sleep(min(wait, 60))


def payload_from_message(message: Message) -> Dict[str, Any]:
	"""Extract broadcast fields from an administrator's message."""
	if message.forward_origin is not None and message.forward_from_chat is not None:
		return {
			"kind": Broadcast.Kind.FORWARD,
			"from_chat_id": message.forward_from_chat.id,
			"source_message_id": message.forward_from_message_id or message.message_id,
		}
	if message.photo:
		return {
			"kind": Broadcast.Kind.PHOTO,
			"file_id": message.photo[-1].file_id,
			"caption": (message.caption or "")[:1024],
		}
	if message.video:
		return {
			"kind": Broadcast.Kind.VIDEO,
			"file_id": message.video.file_id,
			"caption": (message.caption or "")[:1024],
		}
	if message.audio:
		return {
			"kind": Broadcast.Kind.AUDIO,
			"file_id": message.audio.file_id,
			"caption": (message.caption or "")[:1024],
		}
	if message.document:
		return {
			"kind": Broadcast.Kind.DOCUMENT,
			"file_id": message.document.file_id,
			"caption": (message.caption or "")[:1024],
		}
	return {"kind": Broadcast.Kind.TEXT, "text": message.html_text or message.text or ""}


# ------------------------------------------------------------------------- run
async def run_broadcast(
	bot: Bot,
	broadcast: Broadcast,
	*,
	rate: Optional[int] = None,
	concurrency: Optional[int] = None,
	progress: Optional[ProgressCallback] = None,
) -> Broadcast:
	"""Deliver ``broadcast`` to every recipient, resuming from its cursor."""
	if broadcast.status == Broadcast.Status.COMPLETED:
		return broadcast

	settings = await get_settings()
	rate = int(rate or settings.broadcast_rate_per_second or 25)
	concurrency = max(1, int(concurrency or settings.broadcast_concurrency or 5))
	protect = bool(broadcast.protect_content)

	recipients = await to_async(recipients_sync)(include_blocked=broadcast.include_blocked)
	pending = [telegram_id for telegram_id in recipients if telegram_id > broadcast.cursor_telegram_id]
	total = max(len(recipients), broadcast.sent_count + broadcast.failed_count + broadcast.blocked_count)

	await to_async(_mark_running_sync)(broadcast.pk, total)
	counters = {
		"sent": broadcast.sent_count,
		"failed": broadcast.failed_count,
		"blocked": broadcast.blocked_count,
	}
	cursor = broadcast.cursor_telegram_id
	status = Broadcast.Status.COMPLETED

	if not pending:
		status = Broadcast.Status.COMPLETED
		await to_async(_mark_finished_sync)(broadcast.pk, status, counters["sent"], counters["failed"], counters["blocked"], cursor)
		return await get_broadcast(broadcast.pk)

	limiter = RateLimiter(rate)
	semaphore = asyncio.Semaphore(concurrency)
	batch_size = max(1, concurrency * BATCH_MULTIPLIER)

	async def handle(telegram_id: int):
		async with semaphore:
			await limiter.acquire()
			try:
				await _send_with_retry(bot, broadcast, telegram_id, protect=protect)
			except TelegramForbiddenError as exc:
				return telegram_id, BroadcastDelivery.Status.BLOCKED, str(exc)[:255]
			except TelegramBadRequest as exc:
				return telegram_id, BroadcastDelivery.Status.FAILED, str(exc)[:255]
			except TelegramAPIError as exc:
				return telegram_id, BroadcastDelivery.Status.FAILED, str(exc)[:255]
			except asyncio.CancelledError:  # pragma: no cover - shutdown path
				raise
			except Exception as exc:  # noqa: BLE001 - never let one user stop the run
				logger.exception("Unexpected broadcast failure for %s.", telegram_id)
				return telegram_id, BroadcastDelivery.Status.FAILED, str(exc)[:255]
			return telegram_id, BroadcastDelivery.Status.SENT, ""

	for batch in chunked(pending, batch_size):
		if await to_async(_is_cancel_requested_sync)(broadcast.pk):
			status = Broadcast.Status.CANCELLED
			break

		results = await asyncio.gather(*(handle(telegram_id) for telegram_id in batch))
		rows: List[Dict[str, Any]] = []
		for telegram_id, delivery_status, error in results:
			if delivery_status == BroadcastDelivery.Status.SENT:
				counters["sent"] += 1
			elif delivery_status == BroadcastDelivery.Status.BLOCKED:
				counters["blocked"] += 1
			else:
				counters["failed"] += 1
			rows.append(
				{"telegram_id": telegram_id, "status": delivery_status, "error": error[:255]}
			)
		cursor = batch[-1]

		await to_async(_flush_sync)(
			broadcast.pk, counters["sent"], counters["failed"], counters["blocked"], cursor, rows
		)
		if progress is not None:
			try:
				await progress(
					BroadcastProgress(
						pk=broadcast.pk,
						status=status,
						total=total,
						sent=counters["sent"],
						failed=counters["failed"],
						blocked=counters["blocked"],
					)
				)
			except Exception:  # noqa: BLE001 - UI failures must not stop delivery
				logger.exception("Broadcast progress callback failed.")

	await to_async(_mark_finished_sync)(
		broadcast.pk, status, counters["sent"], counters["failed"], counters["blocked"], cursor
	)
	logger.info(
		"Broadcast %s finished with status %s (sent=%s failed=%s blocked=%s).",
		broadcast.pk,
		status,
		counters["sent"],
		counters["failed"],
		counters["blocked"],
	)
	return await get_broadcast(broadcast.pk)


async def resume_broadcast(
	bot: Bot, pk: int, *, progress: Optional[ProgressCallback] = None
) -> Optional[Broadcast]:
	broadcast = await get_broadcast(pk)
	if broadcast is None:
		return None
	if broadcast.status == Broadcast.Status.CANCELLED:
		# Only an explicit resume may continue a cancelled campaign.
		broadcast.status = Broadcast.Status.PAUSED
		await to_async(broadcast.save)(update_fields=["status"])
	return await run_broadcast(bot, broadcast, progress=progress)


def delivery_summary_sync(broadcast: Broadcast) -> Dict[str, int]:
	rows = BroadcastDelivery.objects.filter(broadcast=broadcast)
	return {
		"sent": rows.filter(status=BroadcastDelivery.Status.SENT).count(),
		"failed": rows.filter(status=BroadcastDelivery.Status.FAILED).count(),
		"blocked": rows.filter(status=BroadcastDelivery.Status.BLOCKED).count(),
	}


delivery_summary = to_async(delivery_summary_sync)
