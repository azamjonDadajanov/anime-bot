"""Web admin panelidan kupon e'lonini kanalga joylash.

The bot has a live ``Bot`` instance in its dispatcher; a web request does not, so
this module builds a short-lived one exactly like the broadcast runner does and
reuses :func:`bot.services.publishing.publish_coupon` so both panels post the
same message.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from asgiref.sync import async_to_sync
from django.conf import settings

from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

logger = logging.getLogger(__name__)


def _bot_token() -> str:
    return getattr(settings, "BOT_TOKEN", "") or getattr(settings, "TELEGRAM_BOT_TOKEN", "")


def _build_bot() -> Bot:
    token = _bot_token()
    return Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def _publish(coupon_id: int) -> Tuple[Optional[int], Optional[str]]:
    from bot.services.publishing import publish_coupon
    from users.models import Coupon

    token = _bot_token()
    if not token:
        return None, "BOT_TOKEN sozlanmagan, shuning uchun kanalga joylab bo'lmadi."

    coupon = await Coupon.objects.select_related("posted_channel").aget(pk=coupon_id)
    bot = _build_bot()
    try:
        message_id = await publish_coupon(bot, coupon)
    finally:
        await bot.session.close()

    if message_id is None:
        return None, (
            "Kanal tanlanmagan yoki Telegram e'lonni rad etdi. "
            "Sozlamalarda \"E'lon kanali\"ni belgilang."
        )
    return message_id, None


def publish_coupon_to_channel(coupon_id: int) -> Tuple[Optional[int], Optional[str]]:
	"""Post the coupon to its channel and return ``(message_id, error)``.

	Never raises: the API turns a failure into a readable 400 for the operator.
	"""
	try:
		return async_to_sync(_publish)(coupon_id)
	except Exception as exc:  # noqa: BLE001 - network/Telegram errors must not 500
		logger.exception("Coupon #%s could not be published.", coupon_id)
		return None, f"Kanalga joylashda xatolik: {exc}"


def maybe_auto_publish_coupon(coupon_id: int) -> Optional[int]:
	"""Post a freshly created coupon when the panel's auto-publish switch is on.

	Returns the posted message id, or ``None`` when auto-publishing is off or the
	post was refused. Never raises.
	"""
	from .publisher import auto_publish_enabled

	if not auto_publish_enabled():
		return None
	message_id, error = publish_coupon_to_channel(coupon_id)
	if error:
		logger.warning("Auto-publish of coupon #%s skipped: %s", coupon_id, error)
	return message_id
