"""Small shared helpers: async ORM bridge, pagination, parsing, formatting."""

from __future__ import annotations

import html
import math
import datetime as dt
from typing import Any, Iterable, Iterator, List, Optional, Sequence, Tuple, TypeVar

from asgiref.sync import sync_to_async

T = TypeVar("T")

ORM_CONCURRENCY = 1


def to_async(func):
	"""Wrap a synchronous ORM helper so it can be awaited from handlers.

	``thread_sensitive=True`` keeps all ORM work on the single Django executor
	thread, which plays well with SQLite and with Django's async test support.
	"""
	return sync_to_async(func, thread_sensitive=True)


def clamp(value: int, low: int, high: int) -> int:
	return max(low, min(high, value))


def parse_int(
	text: Any,
	*,
	minimum: Optional[int] = None,
	maximum: Optional[int] = None,
) -> Optional[int]:
	"""Parse an integer from user input, returning ``None`` when invalid."""
	if text is None:
		return None
	raw = str(text).strip()
	if not raw:
		return None
	if raw.startswith("+") or raw.startswith("-"):
		digits = raw[1:]
	else:
		digits = raw
	if not digits.isdigit():
		return None
	try:
		value = int(raw)
	except ValueError:  # pragma: no cover - guarded by isdigit
		return None
	if minimum is not None and value < minimum:
		return None
	if maximum is not None and value > maximum:
		return None
	return value


def parse_admin_target(text: str) -> Tuple[str, str, Optional[str]]:
	"""Normalise a channel reference entered by an administrator.

	Returns ``(kind, value, username)`` where kind is ``id`` or ``username``.
	Accepts ``@name``, ``name``, ``https://t.me/name``, ``t.me/name`` or a
	numeric chat id such as ``-1001234567890``.
	"""
	raw = (text or "").strip()
	if not raw:
		return ("", "", None)
	if raw.startswith("https://t.me/") or raw.startswith("http://t.me/"):
		raw = raw.split("/", 3)[3]
	raw = raw.split("?", 1)[0].strip("/")
	if raw.startswith("t.me/"):
		raw = raw[len("t.me/"):]
	if raw.startswith("@"):
		return ("username", raw, raw)
	if raw.lstrip("-").isdigit():
		return ("id", raw, None)
	clean = raw.strip()
	if clean and all(ch.isalnum() or ch == "_" for ch in clean):
		return ("username", f"@{clean}", f"@{clean}")
	return ("", "", None)


def paginate(items: Sequence[T], page: int, per_page: int) -> Tuple[List[T], int, int]:
	"""Slice ``items`` for ``page`` (1-based) and return the clamped page count."""
	per_page = max(1, int(per_page))
	total_pages = max(1, math.ceil(len(items) / per_page))
	page = clamp(page, 1, total_pages)
	start = (page - 1) * per_page
	return list(items[start:start + per_page]), page, total_pages


def chunked(iterable: Iterable[T], size: int) -> Iterator[List[T]]:
	size = max(1, int(size))
	chunk: List[T] = []
	for item in iterable:
		chunk.append(item)
		if len(chunk) >= size:
			yield chunk
			chunk = []
	if chunk:
		yield chunk


def escape_html(text: Any) -> str:
	"""Escape a value for Telegram's HTML parse mode.

	The bot sends with ``ParseMode.HTML`` (see ``runner.build_bot``), so a title
	like ``Tom & Jerry`` or ``Kimi ni Natteru? <Signal>`` would be rejected by
	Telegram with ``can't parse entities`` unless ``&`` and the angle brackets
	are escaped first. ``quote=False``: quotes are legal in text content and
	Telegram only decodes the three entities ``html.escape`` writes here.
	"""
	return html.escape(str(text or ""), quote=False)


def truncate(text: Any, limit: int = 100) -> str:
	value = str(text or "")
	if len(value) <= limit:
		return value
	return value[: max(0, limit - 1)].rstrip() + "…"


def human_datetime(value: Optional[dt.datetime]) -> str:
	if not value:
		return "—"
	return value.strftime("%d.%m.%Y %H:%M")


def human_timesince(value: Optional[dt.datetime], now: Optional[dt.datetime] = None) -> str:
	if not value:
		return "—"
	now = now or dt.datetime.now(value.tzinfo) if value.tzinfo else (now or dt.datetime.now())
	delta = now - value
	seconds = int(delta.total_seconds())
	if seconds < 60:
		return "hozir"
	minutes = seconds // 60
	if minutes < 60:
		return f"{minutes} daqiqa oldin"
	hours = minutes // 60
	if hours < 24:
		return f"{hours} soat oldin"
	days = hours // 24
	if days < 30:
		return f"{days} kun oldin"
	return human_datetime(value)


def deep_link(bot_username: str, payload: str) -> str:
	username = (bot_username or "").lstrip("@")
	if not username:
		return ""
	return f"https://t.me/{username}?start={payload}"


def percent(part: int, total: int) -> str:
	if not total:
		return "0%"
	return f"{round(part * 100 / total)}%"


def plan_rank(plan: Optional[str]) -> int:
	"""Ordering helper: free < kunlik < 15 kunlik < 1 oylik < 3 oylik < 1 yillik."""
	# ``coupon`` is a paid window granted by a promo code (see users.coupons),
	# so it ranks above ``free`` just like the shortest catalogue plan.
	order = {
		"free": 0,
		"coupon": 1,
		"daily": 1,
		"d15": 2,
		"monthly": 3,
		"quarterly": 4,
		"yearly": 5,
	}
	return order.get(str(plan or "free").lower(), 0)
