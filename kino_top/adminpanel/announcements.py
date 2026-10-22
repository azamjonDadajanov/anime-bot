"""«📢 E'lon qilish» — announce a title from the website admin panel.

The bot owns a live ``Bot`` in its dispatcher; a web request does not, so this
module builds a short-lived one exactly like :mod:`adminpanel.publisher` does
and reuses :mod:`bot.services.announcements`, so both panels post the very same
message.

The channel post is a single Bot API call and happens inside the request, so
the operator immediately learns whether Telegram accepted it. The audience
fan-out to every bot user can take minutes, so it runs in a daemon thread (the
same pattern as :mod:`adminpanel.broadcast_runner`) and reports its counters to
the log when it finishes. Nothing here ever raises into the request.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional, Tuple

from asgiref.sync import async_to_sync
from django.conf import settings
from movies.models import MediaPart, MediaTitle

from bot.services.announcements import (
	SCOPE_LAST,
	SCOPES,
	announcement_caption,
	announcement_parts_sync,
	watch_label,
)
from bot.services.publishing import resolve_target_channel
from bot.services.users import recipients_sync

logger = logging.getLogger(__name__)

TARGET_CHANNEL = "channel"
TARGET_USERS = "users"
# Channel first: it is the single, immediate post, the audience fan-out follows.
TARGETS = (TARGET_CHANNEL, TARGET_USERS)

_lock = threading.Lock()
_running: set[int] = set()


def _bot_token() -> str:
	return getattr(settings, "BOT_TOKEN", "") or getattr(settings, "TELEGRAM_BOT_TOKEN", "")


def normalise_scope(raw: object) -> str:
	return raw if raw in SCOPES else SCOPE_LAST


def normalise_targets(raw: object) -> Tuple[list, Optional[str]]:
	"""Validate the target list: at least one of users/channel."""
	if isinstance(raw, str):
		raw = [raw]
	if not isinstance(raw, (list, tuple)):
		return [], "Kamida bitta manzilni tanlang: foydalanuvchilar yoki kanal."
	targets = {str(item).strip().lower() for item in raw if str(item).strip()}
	unknown = targets - set(TARGETS)
	if unknown:
		return [], "Noma'lum manzil tanlandi."
	if not targets:
		return [], "Kamida bitta manzilni tanlang: foydalanuvchilar yoki kanal."
	# Stable order: the channel first, the audience after it.
	return [target for target in TARGETS if target in targets], None


def _channel_title_sync(title: MediaTitle) -> str:
	"""Name the channel the publishing rules would use (or an empty string)."""
	is_completed = (
		title.status == MediaTitle.Status.COMPLETED
		or title.type == MediaTitle.MediaType.MOVIE
	)
	try:
		channel = async_to_sync(resolve_target_channel)(title, is_completed=is_completed)
	except Exception:  # noqa: BLE001 - a missing settings row must not break the preview
		logger.exception("Could not resolve the announcement channel for #%s.", title.pk)
		return ""
	return channel.title if channel is not None else ""


def preview(title_id: int, scope: object = SCOPE_LAST) -> dict:
	"""Everything the confirmation card shows before anything is sent."""
	title = MediaTitle.objects.filter(pk=title_id).first()
	if title is None:
		raise MediaTitle.DoesNotExist(title_id)
	scope = normalise_scope(scope)
	parts, total = announcement_parts_sync(title, scope)
	return {
		"id": title.pk,
		"slug": title.slug,
		"title": title.title,
		"type": title.type,
		"status": title.status,
		"scope": scope,
		"caption": announcement_caption(title, parts, total_parts=total),
		"button_label": watch_label(title),
		"parts": [part.number for part in parts],
		"total_parts": total,
		"recipients": len(recipients_sync(include_blocked=False)),
		"channel_title": _channel_title_sync(title),
	}


async def _post_to_channel(title_id: int, scope: str):
	from aiogram import Bot

	from bot.services.announcements import send_announcement

	title = await MediaTitle.objects.aget(pk=title_id)
	bot = Bot(token=_bot_token())
	try:
		result = await send_announcement(bot, title, scope=scope, to_channel=True)
	finally:
		await bot.session.close()
	return result.channel_message_id, result.channel_error


def _announce_to_users(title_id: int, scope: str, admin_telegram_id: Optional[int]) -> None:
	"""Thread body: deliver the same announcement to every bot user."""
	from bot.bot_logging import record_event
	from bot.services.announcements import send_announcement

	async def _inner():
		from aiogram import Bot

		title = await MediaTitle.objects.aget(pk=title_id)
		bot = Bot(token=_bot_token())
		try:
			return await send_announcement(bot, title, scope=scope, to_users=True)
		finally:
			await bot.session.close()

	try:
		result = asyncio.run(_inner())
		record_event(
			"INFO",
			f"E'lon (media #{title_id}) foydalanuvchilarga yuborildi: "
			f"{result.users_sent} ta yuborildi, {result.users_failed} ta xato "
			f"({result.users_total} qabul qiluvchi).",
			telegram_id=admin_telegram_id,
		)
	except Exception as exc:  # noqa: BLE001 - a daemon thread must never leak
		logger.exception("Announcement to users for media #%s failed.", title_id)
		try:
			record_event(
				"ERROR",
				f"E'lon (media #{title_id}) foydalanuvchilarga yuborilmadi: {exc}",
				telegram_id=admin_telegram_id,
			)
		except Exception:  # noqa: BLE001
			logger.exception("Could not record the failed announcement.")
	finally:
		with _lock:
			_running.discard(title_id)


def _start_users_announcement(title_id: int, scope: str, admin_telegram_id: Optional[int]) -> bool:
	"""Start the audience fan-out once; ``False`` when it already runs."""
	with _lock:
		if title_id in _running:
			return False
		_running.add(title_id)
	thread = threading.Thread(
		target=_announce_to_users,
		args=(title_id, scope, admin_telegram_id),
		daemon=True,
		name=f"announce-{title_id}",
	)
	thread.start()
	return True


def announce(
	title_id: int,
	*,
	targets: object,
	scope: object = SCOPE_LAST,
	admin_telegram_id: Optional[int] = None,
) -> Tuple[Optional[dict], Optional[str]]:
	"""Announce a title; returns ``(payload, error)`` and never raises.

	``error`` is only set when *nothing* was delivered — a refused channel post
	alongside a started audience fan-out comes back in ``payload`` so the panel
	can show both outcomes.
	"""
	selected, error = normalise_targets(targets)
	if error:
		return None, error
	scope = normalise_scope(scope)

	title = MediaTitle.objects.filter(pk=title_id).first()
	if title is None:
		return None, "Media topilmadi."
	if not MediaPart.objects.filter(content=title).exists():
		# The announcement is about episodes, so there must be one to point at.
		return None, (
			"Bu media uchun hali qism qo'shilmagan — e'lon qilish uchun avval "
			"qism qo'shing."
		)
	if not _bot_token():
		return None, "BOT_TOKEN sozlanmagan, shuning uchun e'lon yuborilmadi."

	payload: dict = {"scope": scope, "targets": selected}

	if TARGET_CHANNEL in selected:
		try:
			message_id, channel_error = async_to_sync(_post_to_channel)(title.pk, scope)
		except Exception as exc:  # noqa: BLE001 - network/Telegram errors must not 500
			logger.exception("Title #%s could not be announced to the channel.", title.pk)
			message_id, channel_error = None, f"Kanalga joylashda xatolik: {exc}"
		if message_id is None:
			payload["channel_error"] = channel_error or "Kanalga joylash amalga oshmadi."
		else:
			payload["channel_message_id"] = message_id

	if TARGET_USERS in selected:
		total = len(recipients_sync(include_blocked=False))
		payload["users_total"] = total
		payload["users_started"] = _start_users_announcement(
			title.pk, scope, admin_telegram_id
		)
		if not payload["users_started"]:
			payload["users_error"] = (
				"Bu media uchun foydalanuvchilarga e'lon allaqachon yuborilmoqda."
			)

	if (
		TARGET_CHANNEL in selected
		and payload.get("channel_message_id") is None
		and not payload.get("users_started")
	):
		return None, payload.get("channel_error") or "E'lon yuborilmadi."
	return payload, None
