"""Chat client for the AI assistant — one model per try, with automatic failover.

One provider is a single point of failure: its free tier runs out, its key gets
rate limited, its endpoint hiccups. So the assistant is not tied to a provider
but to a **chain** of them:

* the chain comes from the ``AIProvider`` table (see :func:`provider_chain`), so
  an operator can change keys, add a second provider or re-order them without a
  redeploy — and each entry carries its own key, model and base URL;
* providers are tried **one at a time, in order**, stopping at the first answer.
  Nothing is ever sent to two providers at once: the question is asked of the
  cheapest/fastest one, and only a failure moves to the next;
* the fastest-known provider goes first (``avg_latency_ms`` is an average of the
  real calls it served), so a working setup keeps answering in one hop;
* a provider that answered "rate limit" / "quota" is put on a cooldown (kept in
  the database, so every gunicorn worker and the bot process see it) and skipped
  until it expires — the next request does not pay for the failure again.

Everything is time-boxed: ``AI_LLM_TIMEOUT`` per attempt and ``AI_LLM_DEADLINE``
for the whole chain, so a dead provider costs seconds, never the user's patience.
If *no* provider answers, :class:`LLMUnavailable` is raised and the caller
reports the assistant unavailable (see :mod:`movies.ai_assistant`): there is no
offline model to fall back to.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

from django.conf import settings
from django.db import DatabaseError
from django.utils import timezone

logger = logging.getLogger(__name__)
# The operator's view of the same events. Records under the "bot" namespace
# are persisted into ``bot.BotLogEntry`` (see ``bot.bot_logging``) and are
# readable from the admin panel, so a dead model or an exhausted key shows up
# there — and not only in the server's console.
operator_log = logging.getLogger("bot.ai")

# The provider kind that is not called directly but routed through the Respan
# Gateway (movies.gateway). A chain entry of this kind gets the gateway's
# model-name routing without the assistant knowing about it.
GATEWAY_KIND = "gateway"

# Presets: base URL and the model to use when the row (or ``AI_LLM_MODEL``) does
# not name one. Kept in one place so adding a provider stays a data change.
PRESETS: Dict[str, Dict[str, str]] = {
	"groq": {
		"base_url": "https://api.groq.com/openai/v1",
		# Multilingual, fast, and offers JSON object/schema modes.
		"model": "qwen/qwen3.8-27b",
	},
	"gemini": {
		"base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
		# The cheap, high-volume Gemini tier (has a free tier as well).
		# Keep this name alive: the whole 2.5 line now answers HTTP 404 ("no
		# longer available to new users"), and a dead preset silently breaks
		# every deployment that relies on it.
		"model": "gemini-3.5-flash-lite",
	},
	"openai": {
		"base_url": "https://api.openai.com/v1",
		"model": "gpt-6-luna",
	},
	"custom": {
		"base_url": "",
		"model": "",
	},
	# Not a URL: a row of this kind is called through the in-process Respan
	# Gateway, which decides where the model goes (see movies.gateway). Such a
	# row therefore needs a model (its route) and no key of its own.
	GATEWAY_KIND: {
		"base_url": "",
		"model": "",
	},
}

DEFAULT_PROVIDER = "groq"
DEFAULT_TIMEOUT = 10
# The whole chain, not one attempt: three dead providers must not add up to a
# minute of waiting.
DEFAULT_DEADLINE = 20
# How long a provider is skipped after it says "rate limit" / "quota". A
# ``Retry-After`` header wins when the provider sends one.
QUOTA_COOLDOWN_SECONDS = 300
# A network error or a 5xx: skip it briefly so the next search is not slowed
# down by the same outage, but come back soon in case it was a blip.
TRANSIENT_COOLDOWN_SECONDS = 60
# Exponential moving average weight for the measured latency (keeps a single
# slow call from re-ordering the chain).
LATENCY_ALPHA = 0.35
MAX_COOLDOWN_SECONDS = 1800
# Quota/limit answers that mean "try the next provider", not "the request is bad".
QUOTA_STATUS_CODES = frozenset({402, 429})
# A model the provider does not know (404) or refuses (400) is a *setup*
# mistake, not a hiccup: retrying it every minute would keep failing the same
# way, so such a provider is left alone for much longer.
MODEL_GONE_STATUS_CODES = frozenset({400, 404})
# How long a misconfigured model is skipped: long enough for the operator to
# notice and fix it, short enough that the fix is picked up the same day.
CONFIG_ERROR_COOLDOWN_SECONDS = 1800
# Appended to the system prompt when the provider that answered cannot be
# asked for functions. The model then talks without the catalogue — and says
# so, instead of inventing titles it never looked up.
TEXT_ONLY_NOTE = (
	"\n\nDIQQAT: senga katalog funksiyalari berilmagan. Katalogdagi kontent "
	"haqida (nomi, qismlari, reytingi, yili) hech narsa aytma — faqat umumiy "
	"suhbat bilan javob ber."
)
# Sent as the User-Agent on every call. Cloudflare (in front of Groq and other
# gateways) rejects urllib's default ``Python-urllib/3.x`` with HTTP 403 Error
# 1010 before the request ever reaches the API, so a browser-like string is used.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


class LLMUnavailable(RuntimeError):
	"""No provider could answer, or none is configured at all.

	Callers treat it as "the assistant cannot answer right now" — the clients say
	so instead of showing a list of unrelated titles.
	"""


class ProviderError(LLMUnavailable):
	"""One provider refused or broke down; the chain moves on to the next.

	``quota`` separates "this provider is out of room right now" (skip it for
	minutes) from "this call went wrong" (skip it for a moment), which is what
	the cooldown lengths are based on. ``config`` marks the third case: the
	provider does not know the model, or refuses the request itself — nothing
	will fix that by retrying, so it is skipped for much longer.
	``retry_after`` is the provider's own suggestion in seconds when it sends
	one.
	"""

	def __init__(
		self,
		message: str,
		*,
		quota: bool = False,
		config: bool = False,
		retry_after: Optional[int] = None,
	):
		super().__init__(message)
		self.quota = quota
		self.config = config
		self.retry_after = retry_after


@dataclass(frozen=True)
class ToolCall:
	"""One function the model asked the assistant to run.

	``arguments`` is the raw JSON string the provider sent (not parsed here):
	the assistant decides which tool it belongs to and how strict to be, so a
	malformed argument list can be reported to the model instead of killing the
	whole request.

	``extra`` is the provider's opaque follow-up metadata. Gemini 3 signs every
	function call with a ``thought_signature`` under ``extra_content`` and rejects
	the next round when it is not echoed back, so it is kept verbatim and sent
	with the call; providers that send nothing leave it ``None``.
	"""

	id: str
	name: str
	arguments: str = ""
	extra: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ChatResult:
	"""One completion: either words, or a request to run tools (or both)."""

	content: str = ""
	tool_calls: tuple = ()
	provider: str = ""

	@property
	def wants_tools(self) -> bool:
		return bool(self.tool_calls)


@dataclass(frozen=True)
class ProviderConfig:
	"""One attempt candidate: where to send it and with which credentials."""

	name: str
	kind: str
	api_key: str
	model: str
	base_url: str
	priority: int = 100
	row_id: Optional[int] = None
	# False for a provider that cannot be asked for functions. It still
	# answers — the question goes to it without the catalogue — but the
	# assistant must not expect a tool call from it.
	supports_tools: bool = True

	@property
	def label(self) -> str:
		return self.name or f"{self.kind}:{self.model}"

	@property
	def key(self) -> str:
		"""How this candidate is remembered inside one process (see the cooldowns)."""
		if self.row_id is not None:
			return f"row:{self.row_id}"
		return f"env:{self.kind}"


# --------------------------------------------------------------------------- #
# Settings helpers
# --------------------------------------------------------------------------- #
def _int_setting(name: str, default: int) -> int:
	try:
		value = int(getattr(settings, name, default) or default)
	except (TypeError, ValueError):
		value = default
	return value


def timeout() -> int:
	return max(3, min(60, _int_setting("AI_LLM_TIMEOUT", DEFAULT_TIMEOUT)))


def deadline() -> int:
	return max(timeout(), min(120, _int_setting("AI_LLM_DEADLINE", DEFAULT_DEADLINE)))


def json_mode() -> bool:
	"""Whether to ask for a strict JSON object.

	Opt-in: Groq and OpenAI support it, but a gateway that does not would answer
	with a 400 — and the prompt already asks for JSON, which the parser handles
	either way.
	"""
	return bool(getattr(settings, "AI_LLM_JSON_MODE", False))


def env_provider() -> ProviderConfig:
	"""The single provider described by the environment (the pre-table setup).

	Used when ``AIProvider`` has no active row, so an existing deployment that
	only sets ``AI_LLM_API_KEY`` keeps working untouched.
	"""
	kind = str(getattr(settings, "AI_LLM_PROVIDER", "") or DEFAULT_PROVIDER).strip().lower()
	if kind not in PRESETS:
		kind = DEFAULT_PROVIDER
	preset = PRESETS[kind]
	return ProviderConfig(
		name=kind,
		kind=kind,
		api_key=str(getattr(settings, "AI_LLM_API_KEY", "") or "").strip(),
		model=str(getattr(settings, "AI_LLM_MODEL", "") or "").strip() or preset["model"],
		base_url=(str(getattr(settings, "AI_LLM_BASE_URL", "") or "").strip() or preset["base_url"]).rstrip("/"),
	)


def _configured(config: ProviderConfig) -> bool:
	if config.kind == GATEWAY_KIND:
		# The gateway holds the provider keys itself, so a row needs only the
		# model (the route) it asks for.
		return bool(config.model)
	return bool(config.api_key and config.model and config.base_url)


def _monotonic() -> float:
	"""The clock every wait in this module reads (a single point to fake in tests)."""
	return time.monotonic()


# --------------------------------------------------------------------------- #
# In-process cooldowns
# --------------------------------------------------------------------------- #
# The database cooldown is what every worker shares, but it costs a write and a
# read to notice. The worker that just hit a limit already knows, so it keeps the
# same information in memory: the very next request in this process skips that
# provider without paying for the failed call again. Keys are
# :attr:`ProviderConfig.key`.
_LOCAL_COOLDOWN: Dict[str, float] = {}
_LOCAL_LOCK = threading.Lock()


def cooldown_left(key: str) -> float:
	"""Seconds this process will still skip ``key`` for (0 when it is usable)."""
	with _LOCAL_LOCK:
		until = _LOCAL_COOLDOWN.get(key, 0.0)
	left = until - _monotonic()
	return left if left > 0 else 0.0


def set_cooldown(key: str, seconds: int) -> None:
	"""Skip ``key`` for ``seconds`` in this process (never longer than the cap)."""
	if not key:
		return
	seconds = max(1, min(MAX_COOLDOWN_SECONDS, int(seconds)))
	with _LOCAL_LOCK:
		_LOCAL_COOLDOWN[key] = _monotonic() + seconds


def clear_cooldown(key: str) -> None:
	"""Forget the in-process cooldown of ``key`` (it just answered)."""
	with _LOCAL_LOCK:
		_LOCAL_COOLDOWN.pop(key, None)


def reset_cooldowns() -> None:
	"""Forget every in-process cooldown (an operator fixed something; tests)."""
	with _LOCAL_LOCK:
		_LOCAL_COOLDOWN.clear()


def soonest_cooldown_seconds() -> Optional[int]:
	"""Seconds until a skipped provider is worth asking again (None if none is)."""
	from .models import AIProvider

	waits: List[float] = []
	try:
		now = timezone.now()
		row = (
			AIProvider.objects.filter(cooldown_until__gt=now)
			.order_by("cooldown_until")
			.values_list("cooldown_until", flat=True)
			.first()
		)
	except DatabaseError:  # pragma: no cover - a DB mid-migration
		row = None
	if row is not None:
		waits.append((row - now).total_seconds())
	with _LOCAL_LOCK:
		waits.extend(until - _monotonic() for until in _LOCAL_COOLDOWN.values())
	positive = [value for value in waits if value > 0]
	return int(max(1, min(positive))) if positive else None


def no_provider_message() -> str:
	"""Why the chain is empty: nothing is configured, or everyone is out of room.

	The second case is the failover working as intended — and it is reported
	with a wait, so the caller (and the operator reading a log) can tell the two
	apart without guessing.
	"""
	wait = soonest_cooldown_seconds()
	if wait is not None:
		# No em dash: this string ends up in management-command output, and a
		# cp1252 console (Windows) cannot print one.
		return (
			f"Barcha AI provayderlar limitda: {wait} soniyadan keyin avtomatik "
			"qayta uriniladi."
		)
	return "LLM sozlanmagan (AI_LLM_API_KEY yoki faol AI provayder qatori kerak)."


# --------------------------------------------------------------------------- #
# The chain (a function over the database, not a hardcoded list)
# --------------------------------------------------------------------------- #
def provider_chain(*, include_cooling: bool = False) -> List[ProviderConfig]:
	"""Every provider that may be tried, fastest usable one first.

	Order is ``priority`` (an operator's preference) and then the measured
	``avg_latency_ms`` (so a fast provider that already proved itself goes
	first). Providers on cooldown are skipped unless ``include_cooling`` is set,
	which the management command uses to *show* them — a cooldown lives both in
	the row (shared by every worker) and in this process (so the worker that hit
	the limit does not ask that provider a second time).

	Reading the rows here — rather than in the caller — means the whole feature
	asks one function "who can answer?". A row may leave its key empty and
	borrow the environment's one (only when it speaks to the same provider),
	and the environment provider itself is the last resort: the database is the
	operator's list, and ``.env`` still answers when that list is empty.
	"""
	from .models import AIProvider

	now = timezone.now()
	configs: List[ProviderConfig] = []
	env = env_provider()
	try:
		rows = list(
			AIProvider.objects.filter(is_active=True).order_by(
				"priority", "avg_latency_ms", "id"
			)
		)
	except DatabaseError as exc:  # pragma: no cover - a DB mid-migration
		# The table may not exist yet (a fresh deployment, or the bot process
		# starting before ``migrate``). Reasoning is optional, so fall back to
		# the environment instead of breaking the search.
		logger.warning("AI providers could not be read (%s); using .env settings.", exc)
		rows = []
	for row in rows:
		if include_cooling:
			pass
		elif row.cooldown_until and row.cooldown_until > now:
			continue
		elif cooldown_left(f"row:{row.pk}") > 0:
			continue
		preset = PRESETS.get(row.kind, PRESETS["custom"])
		api_key = (row.api_key or "").strip()
		if not api_key and row.kind == env.kind:
			# A row without its own key borrows the environment's one — but
			# only when it talks to the same provider: a Gemini key cannot
			# open Groq's door.
			api_key = env.api_key
		config = ProviderConfig(
			name=row.name,
			kind=row.kind,
			api_key=api_key,
			model=(row.model or "").strip() or preset["model"],
			base_url=(row.base_url or "").strip().rstrip("/") or preset["base_url"],
			priority=int(row.priority or 100),
			row_id=row.pk,
			supports_tools=bool(getattr(row, "supports_tools", True)),
		)
		if _configured(config):
			configs.append(config)
	# The environment provider is the reserve: it goes last, and only when the
	# database chain does not already contain the same model.
	if _configured(env) and not any(
		config.kind == env.kind and config.model == env.model for config in configs
	):
		if include_cooling or cooldown_left(env.key) <= 0:
			configs.append(env)
	return configs


def is_configured() -> bool:
	"""True when at least one usable provider exists (DB chain or environment)."""
	if not bool(getattr(settings, "AI_LLM_ENABLED", True)):
		return False
	return bool(provider_chain())


# The answer cache keys on *which* models may answer, and recomputing that from
# the database on every (also cached) question would be a needless query on the
# hot path. Thirty seconds is far below any human-noticeable staleness for a
# configuration that changes when an operator edits a row.
_SIGNATURE_TTL_SECONDS = 30
_SIGNATURE: Dict[str, Any] = {"at": 0.0, "value": ()}


def chain_signature() -> tuple:
	"""A cheap identity of the current chain: ``((name, model), ...)``.

	Two answers produced by different models are not interchangeable, so the
	answer cache must notice a provider change. Cached for
	:data:`_SIGNATURE_TTL_SECONDS` to keep the search path free of extra queries.
	"""
	now = time.monotonic()
	value = _SIGNATURE.get("value")
	if value and now - float(_SIGNATURE.get("at") or 0) < _SIGNATURE_TTL_SECONDS:
		return value
	signature = tuple((config.label, config.model) for config in provider_chain())
	_SIGNATURE["at"] = now
	_SIGNATURE["value"] = signature
	return signature


def reset_signature_cache() -> None:
	"""Drop the cached chain signature (tests, or right after an edit)."""
	_SIGNATURE["at"] = 0.0
	_SIGNATURE["value"] = ()


def configuration() -> Dict[str, Any]:
	"""A safe description for the management command; never returns a key.

	``usable`` is the chain the next question would actually try, so a provider
	that is cooling down is listed but not counted as available.
	"""
	chain = provider_chain(include_cooling=True)
	usable = provider_chain()
	usable_keys = {config.key for config in usable}
	# The last error of every row: without it the operator sees "waiting" and
	# not *why*.
	errors: Dict[str, str] = {}
	for row in health():
		errors[row["name"]] = row["last_error"]
	return {
		"configured": bool(usable),
		"usable": len(usable),
		"next_retry_in": soonest_cooldown_seconds(),
		"providers": [
			{
				"name": config.label,
				"kind": config.kind,
				"model": config.model,
				"base_url": config.base_url,
				"priority": config.priority,
				"key_set": bool(config.api_key),
				"usable": config.key in usable_keys,
				"supports_tools": config.supports_tools,
				"last_error": errors.get(config.label, ""),
			}
			for config in chain
		],
		"timeout": timeout(),
		"deadline": deadline(),
		"from_database": any(config.row_id for config in chain),
	}


def health() -> List[Dict[str, Any]]:
	"""Per-provider runtime state (used by ``--status`` and the admin)."""
	from .models import AIProvider

	now = timezone.now()
	rows = []
	for row in AIProvider.objects.order_by("priority", "avg_latency_ms", "id"):
		rows.append(
			{
				"name": row.name,
				"kind": row.kind,
				"model": row.model or PRESETS.get(row.kind, PRESETS["custom"])["model"],
				"is_active": row.is_active,
				"key_set": bool(row.api_key),
				"priority": row.priority,
				"avg_latency_ms": row.avg_latency_ms,
				"success_count": row.success_count,
				"failure_count": row.failure_count,
				"cooling_down": bool(row.cooldown_until and row.cooldown_until > now),
				"cooldown_until": row.cooldown_until,
				"last_error": row.last_error,
			}
		)
	return rows


def _record_success(row_id: Optional[int], elapsed_ms: int) -> None:
	"""Fold one good call into the row's measured latency (best effort)."""
	from .models import AIProvider

	if row_id is None:
		return
	# Bookkeeping must never cost an answer: a locked table, a replica in
	# recovery or a missing migration cannot turn a working reply into an error.
	try:
		row = AIProvider.objects.filter(pk=row_id).first()
		if row is None:
			return
		previous = int(row.avg_latency_ms or 0)
		average = (
			int(previous * (1 - LATENCY_ALPHA) + elapsed_ms * LATENCY_ALPHA)
			if previous
			else int(elapsed_ms)
		)
		AIProvider.objects.filter(pk=row_id).update(
			avg_latency_ms=average,
			success_count=int(row.success_count or 0) + 1,
			last_used_at=timezone.now(),
			cooldown_until=None,
			last_error="",
		)
	except DatabaseError as exc:
		logger.warning("AI provider %s could not be updated: %s", row_id, exc)


def _record_failure(
	row_id: Optional[int],
	message: str,
	*,
	cooldown_seconds: Optional[int],
	label: str = "",
) -> None:
	"""Count a failure and put the row on cooldown (best effort).

	``label`` is the provider's name: the row may not exist (the provider came
	from ``.env``), and a log line that says "provider None" tells the operator
	nothing about which model actually failed.
	"""
	logger.warning("AI provider %s failed: %s", label or row_id or "?", str(message)[:200])
	operator_log.warning("AI provider %s failed: %s", label or row_id or "?", str(message)[:200])
	from .models import AIProvider

	if row_id is None:
		return
	until = None
	if cooldown_seconds:
		seconds = max(5, min(MAX_COOLDOWN_SECONDS, int(cooldown_seconds)))
		until = timezone.now() + timedelta(seconds=seconds)
	try:
		row = AIProvider.objects.filter(pk=row_id).first()
		if row is None:
			return
		AIProvider.objects.filter(pk=row_id).update(
			failure_count=int(row.failure_count or 0) + 1,
			last_error=str(message)[:200],
			cooldown_until=until,
			last_used_at=timezone.now(),
		)
	except DatabaseError as exc:
		logger.warning("AI provider %s could not be updated: %s", row_id, exc)


def _retry_after_seconds(headers) -> Optional[int]:
	"""``Retry-After`` in seconds when the provider bothers to send one."""
	raw = (headers or {}).get("Retry-After") if headers is not None else None
	try:
		value = int(str(raw).strip())
	except (TypeError, ValueError):
		return None
	return value if value > 0 else None


def _text_only_messages(messages: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
	"""The conversation as a provider that cannot call functions must see it.

	The tool rounds are removed (such a provider would not understand them) and
	the system prompt says the catalogue is out of reach, so the model does not
	invite titles it never looked up.
	"""
	prepared: List[Dict[str, Any]] = []
	saw_system = False
	for item in messages:
		role = str(item.get("role") or "")
		if role == "tool" or item.get("tool_calls"):
			continue
		content = str(item.get("content") or "")
		if role == "system":
			saw_system = True
			content = f"{content}{TEXT_ONLY_NOTE}"
		prepared.append({**item, "content": content})
	if not saw_system:
		# Without a system message the warning would be lost, and the model
		# would talk about the catalogue as if it had looked it up.
		prepared.insert(0, {"role": "system", "content": TEXT_ONLY_NOTE.strip()})
	return prepared


# --------------------------------------------------------------------------- #
# One attempt
# --------------------------------------------------------------------------- #
def _via_gateway(config: ProviderConfig, payload: Dict[str, Any], *, seconds: int) -> Dict[str, Any]:
	"""One attempt through the in-process Respan Gateway (:mod:`movies.gateway`).

	The gateway is a black box that answers OpenAI-shaped bodies, so this is
	where its failures become the four facts the chain already understands: a
	limit (skip for minutes), a withdrawn model or bad request (skip for much
	longer), a timeout or outage (skip briefly), and "it cannot run at all" —
	judged a configuration problem, because no retry will install a package.
	"""
	from . import gateway  # imported here: gateway reads this module's presets

	try:
		return gateway.complete(payload, seconds=seconds)
	except gateway.GatewayUnavailable as exc:
		raise ProviderError(str(exc), config=True) from exc
	except gateway.GatewayCallError as exc:
		raise ProviderError(
			str(exc),
			quota=exc.status in QUOTA_STATUS_CODES,
			config=exc.status in MODEL_GONE_STATUS_CODES,
			retry_after=exc.retry_after,
		) from exc


def _completion_result(body: Dict[str, Any], label: str) -> ChatResult:
	"""One decoded completion body as the answer the assistant works with.

	Shared by both transports — the direct call and the gateway — because the
	body is the same OpenAI shape either way: prose, functions, or both.
	"""
	try:
		message = body["choices"][0]["message"]
		extract = str(message.get("content") or "")
	except (KeyError, IndexError, TypeError, AttributeError) as exc:
		raise ProviderError(f"{label} javobida 'choices' yo'q.") from exc

	calls = []
	for index, item in enumerate(message.get("tool_calls") or []):
		function = item.get("function") or {}
		name = str(function.get("name") or "").strip()
		if not name:
			continue
		extra = item.get("extra_content")
		calls.append(
			ToolCall(
				id=str(item.get("id") or f"call_{index}"),
				name=name,
				arguments=str(function.get("arguments") or "{}"),
				extra=extra if isinstance(extra, dict) and extra else None,
			)
		)
	return ChatResult(content=extract, tool_calls=tuple(calls), provider=label)


def _attempt(
	config: ProviderConfig,
	messages: Sequence[Dict[str, Any]],
	*,
	max_tokens: int,
	temperature: float,
	seconds: int,
	tools: Optional[Sequence[Dict[str, Any]]] = None,
	tool_choice: str = "auto",
) -> ChatResult:
	"""Send one request; failures raise :class:`ProviderError` with a reason."""
	prepared: List[Dict[str, Any]] = list(messages)
	if tools and not config.supports_tools:
		# This provider cannot be asked for functions. The question still goes
		# to it — without the catalogue, and with the prompt saying so.
		prepared = _text_only_messages(messages)
	payload: Dict[str, Any] = {
		"model": config.model,
		"messages": prepared,
		# Deterministic enough that the same request does not produce a different
		# answer every time.
		"temperature": float(temperature),
		"max_tokens": int(max_tokens),
	}
	if tools and config.supports_tools:
		# OpenAI-compatible tool calling: the model answers with ``tool_calls``
		# instead of prose, the assistant runs them and asks again.
		payload["tools"] = list(tools)
		payload["tool_choice"] = tool_choice or "auto"
	elif not tools and json_mode():
		payload["response_format"] = {"type": "json_object"}
	if config.kind == GATEWAY_KIND:
		# The same body, handed to the gateway instead of to a provider: it
		# routes it by model name and answers in the same shape.
		return _completion_result(
			_via_gateway(config, payload, seconds=max(3, int(seconds))), config.label
		)
	request = urllib.request.Request(
		f"{config.base_url}/chat/completions",
		data=json.dumps(payload).encode("utf-8"),
		headers={
			"Content-Type": "application/json",
			"Accept": "application/json",
			"Authorization": f"Bearer {config.api_key}",
			# urllib's default ``Python-urllib/3.x`` trips the Cloudflare bot
			# filter in front of some providers (Groq answers HTTP 403 Error
			# 1010). A browser-like string is treated as a normal client.
			"User-Agent": USER_AGENT,
		},
		method="POST",
	)
	try:
		with urllib.request.urlopen(request, timeout=max(3, int(seconds))) as response:
			body = json.loads(response.read().decode("utf-8", "replace"))
	except urllib.error.HTTPError as exc:
		detail = ""
		try:
			detail = exc.read().decode("utf-8", "replace")[:200]
		except Exception:  # noqa: BLE001 - the error body is best effort
			detail = ""
		raise ProviderError(
			f"{config.label} HTTP {exc.code}: {detail}",
			quota=exc.code in QUOTA_STATUS_CODES,
			# 404/400: the provider does not know this model (or this request).
			# Retrying it every minute would fail the same way, so it is left
			# alone for much longer and the chain moves on.
			config=exc.code in MODEL_GONE_STATUS_CODES,
			retry_after=_retry_after_seconds(exc.headers),
		) from exc
	except urllib.error.URLError as exc:
		raise ProviderError(f"{config.label} javob bermadi: {exc.reason}") from exc
	except (TimeoutError, OSError) as exc:
		raise ProviderError(f"{config.label} bilan aloqa uzildi: {exc}") from exc
	except json.JSONDecodeError as exc:
		raise ProviderError(f"{config.label} noto'g'ri javob qaytardi.") from exc

	return _completion_result(body, config.label)


def probe(config: ProviderConfig, *, seconds: Optional[int] = None) -> Tuple[str, str]:
	"""Ask one provider a trivial question: ``(status, detail)``.

	``status`` is one of ``ok``, ``model_topilmadi``, ``limit`` or ``xato``. The
	point is to see *which* model is broken: a chain that looks ready on paper
	can still answer HTTP 404 for every model in it (a withdrawn model), and
	only a real call tells that apart from a missing key.
	"""
	try:
		result = _attempt(
			config,
			[{"role": "user", "content": "Ha yoki yo'q deb javob ber."}],
			max_tokens=16,
			temperature=0.0,
			seconds=int(timeout() if seconds is None else seconds),
		)
	except ProviderError as exc:
		if getattr(exc, "config", False):
			return "model_topilmadi", str(exc)
		if getattr(exc, "quota", False):
			return "limit", str(exc)
		return "xato", str(exc)
	except LLMUnavailable as exc:  # pragma: no cover - defensive
		return "xato", str(exc)
	answer = (result.content or "").strip()[:80] or "(bo'sh javob)"
	return "ok", answer


def chat(
	messages: Sequence[Dict[str, str]],
	*,
	max_tokens: int = 700,
	temperature: float = 0.2,
	timeout_seconds: Optional[int] = None,
) -> str:
	"""One chat completion, tried over the whole provider chain.

	Providers are attempted strictly one after another (never in parallel, and
	the request is never sent to two of them: the first answer wins and the walk
	stops there). A provider that reports a limit is put on cooldown — in this
	process and in the database, so every worker skips it — and the next one is
	asked; the deadline caps the total wait.

	When *every* provider is on cooldown the call does not touch the network at
	all: it fails immediately with the wait it knows about, which is what keeps a
	search during an outage as fast as one during normal operation. Raises
	:class:`LLMUnavailable` when nobody answers.
	"""
	return chat_completion(
		messages,
		max_tokens=max_tokens,
		temperature=temperature,
		timeout_seconds=timeout_seconds,
	).content


def chat_completion(
	messages: Sequence[Dict[str, Any]],
	*,
	max_tokens: int = 700,
	temperature: float = 0.2,
	timeout_seconds: Optional[int] = None,
	tools: Optional[Sequence[Dict[str, Any]]] = None,
	tool_choice: str = "auto",
) -> ChatResult:
	"""One completion over the chain, with optional tool calling.

	Same failover contract as :func:`chat`, but the answer is kept whole: a
	model that asks for tools returns :class:`ToolCall` objects, and the caller
	runs them and asks again (see :mod:`movies.ai_assistant`).
	"""
	chain = provider_chain()
	if not chain:
		# No network attempt is made in this case: the answer comes from the
		# vectors alone, in milliseconds.
		raise LLMUnavailable(no_provider_message())

	per_attempt = timeout() if timeout_seconds is None else max(3, int(timeout_seconds))
	hard_deadline = _monotonic() + deadline()
	errors: List[str] = []

	for position, config in enumerate(chain):
		# What is left of the chain's budget, not another full timeout: two hard
		# providers cost the deadline, never twice the per-attempt timeout.
		remaining = hard_deadline - _monotonic()
		if remaining <= 1:
			errors.append("vaqt chegarasi tugadi")
			break
		started = _monotonic()
		try:
			result = _attempt(
				config,
				messages,
				max_tokens=max_tokens,
				temperature=temperature,
				seconds=int(min(per_attempt, remaining)),
				tools=tools,
				tool_choice=tool_choice,
			)
		except LLMUnavailable as exc:
			is_quota = bool(getattr(exc, "quota", False))
			is_config = bool(getattr(exc, "config", False))
			retry_after = getattr(exc, "retry_after", None)
			if is_config:
				# A model the provider does not know: waiting a minute and
				# asking again would fail exactly the same way.
				cooldown = CONFIG_ERROR_COOLDOWN_SECONDS
			elif is_quota:
				cooldown = retry_after or QUOTA_COOLDOWN_SECONDS
			else:
				cooldown = TRANSIENT_COOLDOWN_SECONDS
			# Both cooldowns are set before the next provider is tried: this
			# process skips the failed one from the next request on, and every
			# other worker learns about it from the row.
			set_cooldown(config.key, cooldown)
			_record_failure(
				config.row_id,
				str(exc),
				cooldown_seconds=cooldown,
				label=config.label,
			)
			errors.append(str(exc))
			logger.info(
				"AI provider %s failed (%s), trying the next of %s",
				config.label,
				"model topilmadi" if is_config else ("limit" if is_quota else "xato"),
				len(chain) - position - 1,
			)
			continue
		elapsed_ms = int((_monotonic() - started) * 1000)
		clear_cooldown(config.key)
		_record_success(config.row_id, elapsed_ms)
		logger.debug("AI answer from %s in %sms", config.label, elapsed_ms)
		return result

	raise LLMUnavailable("; ".join(errors) or "Hech bir provayder javob bermadi.")


def parse_json_object(text: str) -> Dict[str, Any]:
	"""Pull the JSON object out of a model answer.

	Models wrap JSON in prose or a ``` fence often enough that being strict here
	would throw away good answers; the first ``{...}`` block is extracted and
	parsed. Raises :class:`LLMUnavailable` when there is nothing usable.
	"""
	raw = str(text or "").strip()
	if raw.startswith("```"):
		raw = raw.strip("`")
		if "\n" in raw:
			raw = raw.split("\n", 1)[1]
		raw = raw.replace("```", "")
	start = raw.find("{")
	end = raw.rfind("}")
	if start == -1 or end <= start:
		raise LLMUnavailable("Javobda JSON topilmadi.")
	try:
		parsed = json.loads(raw[start : end + 1])
	except json.JSONDecodeError as exc:
		raise LLMUnavailable(f"JSON o'qilmadi: {exc}") from exc
	if not isinstance(parsed, dict):
		raise LLMUnavailable("JSON obyekt emas.")
	return parsed
