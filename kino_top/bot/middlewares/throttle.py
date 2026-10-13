"""Lightweight in-process flood control for callback queries."""

from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict, Tuple

from django.conf import settings

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, TelegramObject

from .context import inner_event

DEFAULT_RATE = 0.4


def _configured_rate() -> float:
	raw = getattr(settings, "BOT_THROTTLE_RATE", None)
	try:
		return max(0.0, float(raw)) if raw is not None else DEFAULT_RATE
	except (TypeError, ValueError):
		return DEFAULT_RATE


class ThrottlingMiddleware(BaseMiddleware):
	"""Answer "too fast" without running the handler when a user spams buttons.

	Only callback queries are throttled: plain text messages are cheap and the
	search/FSM flows legitimately send several in a row.
	"""

	def __init__(self, rate: float | None = None) -> None:
		super().__init__()
		# ``rate`` is resolved on every call so operators (and tests) can change
		# ``BOT_THROTTLE_RATE`` without rebuilding the dispatcher.
		self._rate = None if rate is None else max(0.0, float(rate))
		self._seen: Dict[Tuple[int, str], float] = {}
		self._checks = 0

	@property
	def rate(self) -> float:
		return _configured_rate() if self._rate is None else self._rate

	async def __call__(
		self,
		handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
		event: TelegramObject,
		data: Dict[str, Any],
	) -> Any:
		payload = inner_event(event)
		if self.rate > 0 and isinstance(payload, CallbackQuery):
			from_user = payload.from_user
			key = (getattr(from_user, "id", 0), payload.data or "")
			now = time.monotonic()
			last = self._seen.get(key, 0.0)
			if now - last < self.rate:
				await payload.answer("⏳ Sekinroq, iltimos.")
				return None
			self._seen[key] = now
			self._checks += 1
			if self._checks % 500 == 0:
				cutoff = now - max(self.rate * 10, 60)
				self._seen = {k: v for k, v in self._seen.items() if v >= cutoff}
		return await handler(event, data)
