"""Environment driven configuration for the Telegram bot.

Every value is validated at startup so that a misconfigured deployment fails
loudly instead of silently serving broken functionality. Nothing here is ever
hardcoded: secrets and administrator IDs always come from the environment
(``.env`` in development, real environment variables in production).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import FrozenSet, Iterable, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 8


class ConfigurationError(RuntimeError):
	"""Raised when the bot configuration is missing or invalid."""



def _setting(*names: str, default=None):
	"""Resolve the first configured value among ``names``.

	An environment variable that is *present* wins even when empty, so a
	deployment (or a test) can explicitly clear e.g. ``BOT_TOKEN``. Only when a
	name is absent from the environment does the Django setting act as fallback.
	"""
	for name in names:
		if name in os.environ:
			return os.environ[name]
		value = getattr(settings, name, None)
		if value not in (None, ""):
			return value
	return default



def parse_admin_ids(raw: object) -> FrozenSet[int]:
	"""Parse ``ADMIN_IDS`` from a comma/space separated string or an iterable."""
	if raw in (None, ""):
		return frozenset()
	if isinstance(raw, str):
		candidates: Iterable[object] = raw.replace(",", " ").split()
	else:
		try:
			candidates = list(raw)  # type: ignore[arg-type]
		except TypeError as exc:  # pragma: no cover - defensive
			raise ConfigurationError("ADMIN_IDS must be a string or a list of IDs.") from exc

	admin_ids = set()
	for candidate in candidates:
		text = str(candidate).strip()
		if not text:
			continue
		try:
			value = int(text)
		except ValueError as exc:
			raise ConfigurationError(f"ADMIN_IDS contains a non-numeric value: {text!r}.") from exc
		if value <= 0:
			raise ConfigurationError(f"ADMIN_IDS contains a non-positive value: {value}.")
		admin_ids.add(value)
	return frozenset(admin_ids)


def _as_bool(value: object, *, default: bool = False) -> bool:
	if value is None or value == "":
		return default
	if isinstance(value, bool):
		return value
	text = str(value).strip().lower()
	if text in {"1", "true", "yes", "on", "y"}:
		return True
	if text in {"0", "false", "no", "off", "n"}:
		return False
	raise ConfigurationError(f"Cannot interpret {value!r} as a boolean.")


def _as_int(value: object, *, default: int, minimum: int = 0, maximum: Optional[int] = None) -> int:
	if value in (None, ""):
		return default
	try:
		number = int(str(value).strip())
	except (TypeError, ValueError) as exc:
		raise ConfigurationError(f"Cannot interpret {value!r} as an integer.") from exc
	if number < minimum or (maximum is not None and number > maximum):
		bounds = f">= {minimum}" if maximum is None else f"between {minimum} and {maximum}"
		raise ConfigurationError(f"Value {number} is out of range ({bounds}).")
	return number


def _as_float(value: object, *, default: float, minimum: float = 0.0) -> float:
	if value in (None, ""):
		return default
	try:
		number = float(str(value).strip())
	except (TypeError, ValueError) as exc:
		raise ConfigurationError(f"Cannot interpret {value!r} as a number.") from exc
	if number < minimum:
		raise ConfigurationError(f"Value {number} must be >= {minimum}.")
	return number


@dataclass(frozen=True)
class BotConfig:
	"""Fully resolved and validated bot configuration."""

	token: str
	admin_ids: FrozenSet[int]
	fsm_ttl: int
	require_subscription: bool
	auto_publish: bool
	protect_content: bool
	broadcast_rate: int
	broadcast_concurrency: int
	throttle_rate: float
	page_size: int
	log_channel_id: Optional[int]
	log_level: str

	def is_admin(self, user_id: Optional[int]) -> bool:
		return bool(user_id) and int(user_id) in self.admin_ids

	@property
	def masked_token(self) -> str:
		"""A log-safe representation of the token (never the real value)."""
		if not self.token:
			return "<empty>"
		head, _, tail = self.token.partition(":")
		return f"{head}:{'*' * 8}{tail[-4:] if tail else ''}"


def load_config() -> BotConfig:
	"""Build the configuration from the environment, raising on invalid values."""
	token = str(_setting("BOT_TOKEN", "TELEGRAM_BOT_TOKEN", default="") or "").strip()
	admin_ids = parse_admin_ids(_setting("ADMIN_IDS", "BOT_ADMIN_IDS", default=""))
	log_channel = _setting("BOT_LOG_CHANNEL_ID", default=None)
	log_channel_id = None
	if log_channel not in (None, ""):
		log_channel_id = _as_int(log_channel, default=0) or None

	config = BotConfig(
		token=token,
		admin_ids=admin_ids,
		fsm_ttl=_as_int(_setting("BOT_FSM_TTL", default=86400), default=86400, minimum=0),
		require_subscription=_as_bool(
			_setting("BOT_REQUIRE_SUBSCRIPTION", default=True), default=True
		),
		auto_publish=_as_bool(_setting("BOT_AUTO_PUBLISH", default=False), default=False),
		protect_content=_as_bool(_setting("BOT_PROTECT_CONTENT", default=True), default=True),
		broadcast_rate=_as_int(
			_setting("BOT_BROADCAST_RATE", default=25), default=25, minimum=1, maximum=30
		),
		broadcast_concurrency=_as_int(
			_setting("BOT_BROADCAST_CONCURRENCY", default=5), default=5, minimum=1, maximum=50
		),
		throttle_rate=_as_float(_setting("BOT_THROTTLE_RATE", default=0.4), default=0.4, minimum=0.0),
		page_size=_as_int(_setting("BOT_PAGE_SIZE", default=DEFAULT_PAGE_SIZE), default=DEFAULT_PAGE_SIZE, minimum=1, maximum=50),
		log_channel_id=log_channel_id,
		log_level=str(_setting("BOT_LOG_LEVEL", default="INFO") or "INFO").upper(),
	)
	return config


def validate_config(config: Optional[BotConfig] = None, *, require_token: bool = True) -> BotConfig:
	"""Validate the configuration and return it.

	``require_token`` is only relaxed by management commands and tests that do
	not talk to the Telegram API.
	"""
	config = config or load_config()

	if require_token:
		if not config.token:
			raise ConfigurationError(
				"BOT_TOKEN is not set. Copy .env.example to .env and fill in the token "
				"issued by @BotFather."
			)
		if ":" not in config.token:
			raise ConfigurationError(
				"BOT_TOKEN looks invalid. Expected the '<digits>:<secret>' format from @BotFather."
			)

	if not config.admin_ids:
		raise ConfigurationError(
			"ADMIN_IDS is empty. Set at least one numeric Telegram user ID that may use /admin."
		)
	return config


def page_size() -> int:
	"""Page size for every paginated list (safe to call without a token)."""
	raw = _setting("BOT_PAGE_SIZE", default=DEFAULT_PAGE_SIZE)
	try:
		return max(1, min(50, int(raw)))
	except (TypeError, ValueError):
		return DEFAULT_PAGE_SIZE


def site_url() -> str:
	"""Public website base URL used for links the bot shows (no trailing slash).

	Safe to call without a token so keyboards and tests can resolve it.
	"""
	raw = _setting("BOT_SITE_URL", "SITE_URL", "FRONTEND_URL", default="")
	return str(raw or "").strip().rstrip("/")


def manga_url(slug: str) -> str:
	"""Deep link to the website reader for ``slug`` (empty without a site URL)."""
	base = site_url()
	target = str(slug or "").strip()
	if not base or not target:
		return ""
	return f"{base}/read/{target}"


@lru_cache(maxsize=1)
def get_config() -> BotConfig:
	"""Return the process-wide cached configuration."""
	return validate_config()


def is_admin(user_id: Optional[int]) -> bool:
	"""Whether ``user_id`` is configured as a bot administrator."""
	if not user_id:
		return False
	try:
		return get_config().is_admin(int(user_id))
	except ConfigurationError:
		# With an invalid configuration nobody is an administrator, which is the
		# safe default.
		logger.error("Admin check failed because the bot configuration is invalid.")
		return False


def reset_config_cache() -> None:
	"""Clear the cached configuration (used by tests and the reload command)."""
	get_config.cache_clear()
