"""Global mandatory-subscription gate.

When ``BotSettings.require_subscription`` is on, an update from a user who has
not joined *every* required channel is refused here, before it can reach any
handler — so the bot is unusable (search, catalog, profile, deep links, ...)
until the user subscribes.

Two deliberate exceptions keep the flow usable without weakening the rule:

* the ``✅ Tekshirish`` callback is allowed through, because its handler
  re-checks membership itself and either finishes the pending action or shows
  the same prompt;
* the media callbacks (``watch:``/``wt:``/``q:``) and the buttons riding on a
  delivered file (``favm:``/``qz:``/``qza:``) are allowed through because
  their handlers already enforce access *and* remember the requested episode,
  so pressing ``✅ Tekshirish`` right after joining delivers it, while a quiz
  already in progress is never interrupted;
* the ``✉️ Adminga xabar`` screen stays open (button *and* the message that
  follows it) because "I joined but the bot still refuses me" is exactly the
  question an administrator has to answer.

The prompt lists only the channels the user has not joined yet. Administrators
are never gated, and a channel the bot cannot inspect never blocks anyone
(fail-open, matching the panel's "test" screen).
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Iterable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from .. import callbacks as cb
from ..keyboards.common import subscribe_keyboard
from ..services.access import missing_channels
from ..states import UserSupportStates
from ..texts import SUBSCRIPTION_REQUIRED
from .context import inner_event

logger = logging.getLogger(__name__)

# Callbacks handled even while the gate is closed (see the module docstring).
# Referral screens stay reachable so a user *without* a subscription can invite
# friends and claim the milestone reward that gives them one.
ALLOWED_WHILE_CLOSED = (cb.SUB_CHECK, cb.REF, cb.SUPPORT)
# The text the user types after pressing "✉️ Adminga xabar" is part of the same
# allowed screen, so the gate must not swallow it.
SUPPORT_STATE = UserSupportStates.message.state
REF_CLAIM_PREFIX = f"{cb.REF_CLAIM}:"
MEDIA_CALLBACK_PREFIXES = (
	f"{cb.WATCH}:",
	f"{cb.WATCH_TITLE}:",
	f"{cb.QUALITY}:",
	# Actions riding on an already delivered file: favourite toggle and the
	# title's quiz (including every answer button of a quiz in progress).
	f"{cb.FAV_MEDIA}:",
	f"{cb.QUIZ}:",
	f"{cb.QUIZ_ANSWER}:",
)


def format_channels(channels: Iterable[Any]) -> str:
	"""Bullet list of channel titles (only the ones the user still misses)."""
	return "\n".join(f"• {getattr(channel, 'title', channel)}" for channel in channels) or "—"


class SubscriptionGateMiddleware(BaseMiddleware):
	"""Refuse every update from a user who has not joined all required channels."""

	async def __call__(
		self,
		handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
		event: TelegramObject,
		data: Dict[str, Any],
	) -> Any:
		if data.get("is_admin"):
			return await handler(event, data)

		settings = data.get("settings")
		profile = data.get("profile")
		bot = data.get("bot")
		if settings is None or profile is None or bot is None:
			# Nothing to gate (non-user update or context not ready).
			return await handler(event, data)
		if not getattr(settings, "require_subscription", False):
			return await handler(event, data)

		payload = inner_event(event)
		if isinstance(payload, CallbackQuery):
			if self._is_media_callback(payload.data):
				# The media handlers enforce access themselves and remember the part.
				return await handler(event, data)
			if payload.data in ALLOWED_WHILE_CLOSED:
				# The handler re-checks membership and resumes the pending action.
				return await handler(event, data)
			if payload.data and str(payload.data).startswith(REF_CLAIM_PREFIX):
				# Milestone claims re-validate counts inside the service.
				return await handler(event, data)
		elif data.get("raw_state") == SUPPORT_STATE:
			# The support prompt is already on screen; let the answer through.
			return await handler(event, data)

		missing = await missing_channels(bot, profile.telegram_id)
		if not missing:
			return await handler(event, data)

		await self._refuse(payload, missing)
		return None

	@staticmethod
	def _is_media_callback(data: Any) -> bool:
		return bool(data) and str(data).startswith(MEDIA_CALLBACK_PREFIXES)

	async def _refuse(self, payload: Any, missing: Iterable[Any]) -> None:
		"""Send the subscription prompt listing only the unjoined channels."""
		text = SUBSCRIPTION_REQUIRED.format(channels=format_channels(missing))
		markup = subscribe_keyboard(missing)
		try:
			if isinstance(payload, Message):
				await payload.answer(text, reply_markup=markup)
				return
			if isinstance(payload, CallbackQuery):
				await payload.answer()
				if payload.message is not None:
					await payload.message.answer(text, reply_markup=markup)
				return
		except Exception:  # noqa: BLE001 - refusing must never crash the bot
			logger.warning("Could not send the mandatory-subscription notice.", exc_info=True)
