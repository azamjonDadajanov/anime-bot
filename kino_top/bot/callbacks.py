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
# Search screen filters (media type / genre) and "see everything".
S_TYPE = "sft"
S_ALL = "sfall"
S_GENRES = "sfg"
S_GENRE = "sfgi"
CATALOG = "cat"
CATALOG_MENU = "catmenu"
GENRES = "genres"
FAVORITES = "fav"
PROFILE = "prof"
HELP = "help"
SUB_CHECK = "subchk"
SUBSCRIPTION = "subs"
# Coupons: the user's "enter a promo code" screen.
COUPON = "coupon"
# Support: the user's "write to the administrators" screen.
SUPPORT = "support"
# AI yordamchi: the assistant chat (subscribers only). The payload stays short
# ("ai"), the constant is what names it in the handlers.
AI_ASSISTANT = "ai"
# AI yordamchi: opt in/out of giving the assistant the user's favourites/history.
AI_PERSONAL = "aifav"
# Referrals: invite menu and manual milestone claims (``refc:<milestone>``).
REF = "ref"
REF_CLAIM = "refc"
SUBSCRIPTION_BUY = "subs:buy"
WATCH = "watch"
WATCH_TITLE = "wt"
TYPE = "type"
GENRE = "g"
TITLE = "t"
PART = "p"
FAV_TOGGLE = "favt"
# Actions attached under every delivered media message:
# favourite toggle ``favm:<title_pk>:<part_pk>`` and the title's quiz
# ``qz:<title_pk>``.
FAV_MEDIA = "favm"
QUIZ = "qz"
# Quiz answer ``qza:<attempt_pk>:<question_index>:<choice_index>``.
QUIZ_ANSWER = "qza"
# Reyting: the site's rating table (top players, own rank) inside the bot.
RATING = "rt"
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
# Coupons (promo codes): create, list, publish to a channel, toggle, delete.
ADM_COUPONS = "a:cp"
# Giveaways (raffles): wizard, list, draw, delete.
ADM_GIVEAWAY = "a:ga"
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
