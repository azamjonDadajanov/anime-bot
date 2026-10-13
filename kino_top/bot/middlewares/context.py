"""Per-update context: profile registration, settings and shared helpers."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update, User

from ..config import is_admin
from ..services.bot_settings import get_settings
from ..services.users import load_profile, profile_exists, touch_last_seen
from ..texts import BOT_BLOCKED, MAINTENANCE, OPERATION_FAILED

logger = logging.getLogger(__name__)


def inner_event(event: TelegramObject) -> TelegramObject:
	"""Return the concrete update payload (Message/CallbackQuery/...)."""
	if isinstance(event, Update):
		return event.event
	return event


def extract_user(event: TelegramObject) -> Optional[User]:
	payload = inner_event(event)
	return getattr(payload, "from_user", None)


async def respond(event: TelegramObject, text: str, *, alert: bool = False) -> bool:
	"""Send a short message back to the user, whatever the update type."""
	payload = inner_event(event)
	try:
		if isinstance(payload, Message):
			await payload.answer(text)
			return True
		if isinstance(payload, CallbackQuery):
			await payload.answer(text[:200], show_alert=alert)
			return True
	except Exception:  # noqa: BLE001 - never fail while reporting an error
		logger.debug("Could not answer the user for a %s update.", type(payload).__name__)
	return False


def user_payload(user: User) -> Dict[str, Any]:
	return {
		"id": user.id,
		"username": user.username or "",
		"first_name": user.first_name or "",
		"last_name": user.last_name or "",
		"language_code": user.language_code or "",
	}


class ContextMiddleware(BaseMiddleware):
	"""Register/refresh the TelegramUser and inject shared context.

	Injected keys: ``profile``, ``is_admin``, ``settings``.
	"""

	async def __call__(
		self,
		handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
		event: TelegramObject,
		data: Dict[str, Any],
	) -> Any:
		user = extract_user(event)
		if user is None or user.is_bot:
			return await handler(event, data)

		existed = await profile_exists(user.id)
		profile = await load_profile(user_payload(user))
		admin = is_admin(user.id)
		data["profile"] = profile
		data["is_admin"] = admin
		data["is_new_user"] = not existed

		if profile is None:
			logger.error("Could not register Telegram user %s.", user.id)
			await respond(event, OPERATION_FAILED)
			return None

		await touch_last_seen(user.id)

		settings = await get_settings()
		data["settings"] = settings

		if profile.is_blocked and not admin:
			await respond(event, BOT_BLOCKED, alert=True)
			return None
		if settings.maintenance_mode and not admin:
			await respond(event, MAINTENANCE)
			return None
		return await handler(event, data)
