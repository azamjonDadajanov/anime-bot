"""Read and update the ``BotSettings`` singleton row."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ..models import BotSettings
from ..utils import to_async

logger = logging.getLogger(__name__)

BOOLEAN_FIELDS = (
	"require_subscription",
	"auto_publish_new_content",
	"protect_content",
	"maintenance_mode",
)
INTEGER_FIELDS = ("broadcast_rate_per_second", "broadcast_concurrency")
TEXT_FIELDS = ("welcome_text", "access_denied_text")
EDITABLE_FIELDS = BOOLEAN_FIELDS + INTEGER_FIELDS + TEXT_FIELDS + (
	"publish_channel",
	"completed_channel",
	"ongoing_channel",
	"manga_channel",
	"manga_completed_channel",
	"log_channel_id",
)


def _initial_defaults() -> Dict[str, Any]:
	"""Seed the singleton from the environment on first creation."""
	try:
		from ..config import load_config

		config = load_config()
	except Exception:  # noqa: BLE001 - a broken env must not break defaults
		logger.warning("Falling back to model defaults for BotSettings.", exc_info=True)
		return {}
	return {
		"require_subscription": config.require_subscription,
		"auto_publish_new_content": config.auto_publish,
		"protect_content": config.protect_content,
		"broadcast_rate_per_second": config.broadcast_rate,
		"broadcast_concurrency": config.broadcast_concurrency,
		"log_channel_id": config.log_channel_id,
	}


def get_settings_sync() -> BotSettings:
	defaults = _initial_defaults()
	obj, _ = BotSettings.objects.get_or_create(pk=1, defaults=defaults)
	return obj


get_settings = to_async(get_settings_sync)


def update_settings_sync(**fields: Any) -> BotSettings:
	obj = get_settings_sync()
	changed = []
	for name, value in fields.items():
		if name not in EDITABLE_FIELDS:
			continue
		if name in INTEGER_FIELDS and value is not None:
			value = int(value)
		if getattr(obj, name) != value:
			setattr(obj, name, value)
			changed.append(name)
	if changed:
		obj.save(update_fields=changed + ["updated_at"])
	return obj


update_settings = to_async(update_settings_sync)


def toggle_setting_sync(name: str) -> bool:
	"""Flip a boolean setting and return its new value."""
	if name not in BOOLEAN_FIELDS:
		raise ValueError(f"{name!r} is not a toggleable setting.")
	obj = get_settings_sync()
	value = not getattr(obj, name)
	setattr(obj, name, value)
	obj.save(update_fields=[name, "updated_at"])
	return value


toggle_setting = to_async(toggle_setting_sync)


def on_off(value: bool) -> str:
	return "✅ yoqilgan" if value else "❌ o'chirilgan"


async def runtime_settings() -> Dict[str, Any]:
	"""Convenience snapshot used by handlers and the status screen."""
	obj = await get_settings()
	return {
		"require_subscription": obj.require_subscription,
		"auto_publish_new_content": obj.auto_publish_new_content,
		"protect_content": obj.protect_content,
		"maintenance_mode": obj.maintenance_mode,
		"broadcast_rate_per_second": obj.broadcast_rate_per_second,
		"broadcast_concurrency": obj.broadcast_concurrency,
		"publish_channel_id": obj.publish_channel_id,
		"log_channel_id": obj.log_channel_id,
	}


async def publish_channel() -> Optional[Any]:
	obj = await get_settings()
	if not obj.publish_channel_id:
		return None
	from .channels import get_channel

	return await get_channel(obj.publish_channel_id)
