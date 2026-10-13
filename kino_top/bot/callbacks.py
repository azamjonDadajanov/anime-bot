"""Shared callback-data prefixes and helpers.

Plain string callbacks keep the payload short and easy to debug; every builder
below guarantees the 64-byte callback-data limit.
"""

from __future__ import annotations

from typing import List, Optional

SEP = ":"

# --- navigation -------------------------------------------------------------
MENU = "menu"
BACK = "back"
CANCEL = "cancel"
CLOSE = "close"
NOOP = "noop"

# --- user -------------------------------------------------------------------
SEARCH = "search"
SEARCH_RESULTS = "sres"
CATALOG = "cat"
CATALOG_MENU = "catmenu"
GENRES = "genres"
FAVORITES = "fav"
PROFILE = "prof"
HELP = "help"
SUB_CHECK = "subchk"
SUBSCRIPTION = "subs"
SUBSCRIPTION_BUY = "subs:buy"
WATCH = "watch"
WATCH_TITLE = "wt"
TYPE = "type"
GENRE = "g"
TITLE = "t"
PART = "p"
FAV_TOGGLE = "favt"
QUALITY = "q"

# --- admin ------------------------------------------------------------------
ADMIN = "a"
ADM_STATS = "a:stats"
ADM_MEDIA = "a:m"
ADM_EPISODES = "a:e"
ADM_CHANNELS = "a:c"
ADM_BROADCAST = "a:b"
ADM_USERS = "a:u"
ADM_SETTINGS = "a:s"
ADM_LOGS = "a:l"
# Subscription payment requests (sent by the website, pressed here).
ADM_SUBREQ_OK = "a:subreq:ok"
ADM_SUBREQ_NO = "a:subreq:no"


def join(*parts: object) -> str:
	"""Join callback parts, dropping empty values."""
	return SEP.join(str(part) for part in parts if part not in (None, ""))


def split_data(data: Optional[str]) -> List[str]:
	"""Split callback data on ``:``; empty input yields an empty list."""
	text = data or ""
	return text.split(SEP) if text else []


def section_args(data: Optional[str]) -> List[str]:
	"""Return the argument parts that follow the ``a:<section>:<action>`` prefix.

	Every administrator callback is shaped ``a:<section>:<action>[:<args>]``, so
	index 2 is the action itself and index 3 is the first payload argument.
	Handlers must use this instead of ``split(":")[2]``, which would incorrectly
	return the action name.
	"""
	parts = split_data(data)
	return parts[3:]


def clamp_callback(value: str, limit: int = 64) -> str:
	"""Never let a callback payload exceed Telegram's 64 byte limit."""
	if len(value) <= limit:
		return value
	return value[:limit]


def page_callback(prefix: str, page: int, extra: Optional[str] = None) -> str:
	parts = [prefix, extra, page] if extra is not None else [prefix, page]
	return clamp_callback(join(*parts))
