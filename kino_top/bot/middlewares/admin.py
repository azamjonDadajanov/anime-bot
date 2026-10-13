"""Guard that rejects every non-administrator from the admin router."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from ..config import is_admin
from ..texts import ADMIN_ONLY
from .context import extract_user, respond

logger = logging.getLogger(__name__)


class AdminGuardMiddleware(BaseMiddleware):
	"""Second, independent `ADMIN_IDS` check for the administrator router.

	The handlers are additionally filtered with :class:`bot.filters.AdminFilter`;
	this middleware is defence in depth so that a missing filter can never expose
	an administrative action.
	"""

	async def __call__(
		self,
		handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
		event: TelegramObject,
		data: Dict[str, Any],
	) -> Any:
		user = extract_user(event)
		user_id = getattr(user, "id", None)
		if data.get("is_admin") or is_admin(user_id):
			return await handler(event, data)

		logger.warning(
			"Unauthorized access to the admin router: telegram_id=%s action=%s",
			user_id,
			getattr(event, "event_type", getattr(event, "update_id", "?")),
		)
		await respond(event, ADMIN_ONLY, alert=True)
		return None
