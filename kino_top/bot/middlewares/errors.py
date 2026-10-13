"""Catch-all error handling so a single bad update never kills the bot."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.types import TelegramObject

from ..texts import OPERATION_FAILED
from .context import respond

logger = logging.getLogger(__name__)


class ErrorHandlingMiddleware(BaseMiddleware):
	"""Log unexpected failures, tell the user, and keep polling."""

	async def __call__(
		self,
		handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
		event: TelegramObject,
		data: Dict[str, Any],
	) -> Any:
		try:
			return await handler(event, data)
		except TelegramForbiddenError:
			# The user blocked the bot mid-conversation; nothing to report.
			logger.info("Telegram forbade an action for this update.")
			return None
		except TelegramAPIError as exc:
			logger.warning("Telegram API error while handling an update: %s", exc)
			await respond(event, OPERATION_FAILED)
			return None
		except Exception:  # noqa: BLE001 - deliberately broad: keep the bot alive
			logger.exception("Unhandled error while processing an update.")
			await respond(event, OPERATION_FAILED)
			return None
