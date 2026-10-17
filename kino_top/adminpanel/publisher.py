"""Web panelidan kontent va qism e'lonlarini ommaviy kanalga joylash.

The bot owns a live ``Bot`` instance in its dispatcher; a web request does not,
so this module builds a short-lived one exactly like
:mod:`adminpanel.coupon_publisher` does and reuses
:mod:`bot.services.publishing`, so both panels post the same messages.

Every entry point is *safe*: it never raises into the request, and the
``auto_publish_*`` helpers stay silent unless the administrator turned on
``Avtomatik e'lon`` in the bot settings.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from asgiref.sync import async_to_sync
from django.conf import settings

logger = logging.getLogger(__name__)


def _bot_token() -> str:
	return getattr(settings, "BOT_TOKEN", "") or getattr(settings, "TELEGRAM_BOT_TOKEN", "")


def auto_publish_enabled() -> bool:
	"""Whether the panel's single ``Avtomatik e'lon`` switch is on."""
	try:
		from bot.services.bot_settings import get_settings_sync

		return bool(get_settings_sync().auto_publish_new_content)
	except Exception:  # noqa: BLE001 - a broken settings row must not break a save
		logger.exception("Could not read the auto-publish switch.")
		return False


async def _publish(title_id: int, part_id: Optional[int]) -> Tuple[Optional[int], Optional[str]]:
	from aiogram import Bot

	from bot.services.publishing import publish_title
	from movies.models import MediaPart, MediaTitle

	token = _bot_token()
	if not token:
		return None, "BOT_TOKEN sozlanmagan, shuning uchun kanalga joylab bo'lmadi."

	title = await MediaTitle.objects.aget(pk=title_id)
	part = await MediaPart.objects.aget(pk=part_id) if part_id else None
	bot = Bot(token=token)
	try:
		message_id = await publish_title(bot, title, part=part)
	finally:
		await bot.session.close()

	if message_id is None:
		return None, (
			"Kanal tanlanmagan yoki Telegram e'lonni rad etdi. "
			"Sozlamalarda \"E'lon kanali\"ni belgilang."
		)
	return message_id, None


def publish_title_to_channel(
	title_id: int, part_id: Optional[int] = None
) -> Tuple[Optional[int], Optional[str]]:
	"""Post a title (or one freshly added episode) and return ``(message_id, error)``.

	Never raises: the API turns a failure into a readable 400 for the operator.
	"""
	try:
		return async_to_sync(_publish)(title_id, part_id)
	except Exception as exc:  # noqa: BLE001 - network/Telegram errors must not 500
		logger.exception("Title #%s could not be published.", title_id)
		return None, f"Kanalga joylashda xatolik: {exc}"


def auto_publish_title(title_id: int) -> Optional[int]:
	"""Publish a new title after a web save when the switch is on."""
	if not auto_publish_enabled():
		return None
	message_id, error = publish_title_to_channel(title_id)
	if error:
		logger.warning("Auto-publish of title #%s skipped: %s", title_id, error)
	return message_id


def auto_publish_part(title_id: int, part_id: int) -> Optional[int]:
	"""Announce a new episode added through the web panel when the switch is on."""
	if not auto_publish_enabled():
		return None
	message_id, error = publish_title_to_channel(title_id, part_id)
	if error:
		logger.warning("Auto-publish of part #%s skipped: %s", part_id, error)
	return message_id


async def _publish_completed(title_id: int) -> Tuple[Optional[int], Optional[str]]:
	from aiogram import Bot

	from bot.services.publishing import publish_completed_title
	from movies.models import MediaTitle

	token = _bot_token()
	if not token:
		return None, "BOT_TOKEN sozlanmagan, shuning uchun kanalga joylab bo'lmadi."

	title = await MediaTitle.objects.aget(pk=title_id)
	bot = Bot(token=token)
	try:
		message_id = await publish_completed_title(bot, title)
	finally:
		await bot.session.close()

	if message_id is None:
		return None, "Kanal tanlanmagan yoki Telegram e'lonni rad etdi."
	return message_id, None


def auto_publish_completed(title_id: int) -> Optional[int]:
	"""Publish completed announcement when media status transitions to completed."""
	if not auto_publish_enabled():
		return None
	try:
		message_id, error = async_to_sync(_publish_completed)(title_id)
		if error:
			logger.warning("Auto-publish completed for title #%s skipped: %s", title_id, error)
		return message_id
	except Exception as exc:  # noqa: BLE001
		logger.exception("Title #%s could not be published as completed.", title_id)
		return None
