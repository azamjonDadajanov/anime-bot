"""Respan Gateway — the in-process router in front of the assistant's model calls.

``movies.llm`` walks a chain of providers and normally calls each one over
HTTP itself. A provider row of kind ``gateway`` is different: the request goes
to `Respan Gateway <https://github.com/respanai/respan-gateway>`__, which runs
**inside this process** (the Python wheel, no socket, no port) and reaches the
model from there.

The gateway is the piece that knows how to talk to every vendor: the assistant
keeps sending one OpenAI-shaped request, and the gateway routes it by model
name, translates it for whichever provider serves it and, when a route names
several candidates, falls back between them on its own. The assistant's own
chain still sits on top: a gateway that is dead costs one skipped row, never
the feature.

Two ways to configure it, in this order:

* ``AI_GATEWAY_CONFIG`` — the path of a ``gateway.toml``, in the gateway's own
  format (providers, routes, fallback, tools, prices). This is where an
  operator says "this model goes there, that one goes here".
* otherwise the gateway is given the deployment's own provider — the one
  ``AI_LLM_*`` describes — behind a catch-all route, so a gateway row behaves
  exactly like a direct one while gaining the gateway's routing.

Nothing fails silently: an error status, a timeout or a configuration problem
is raised as :class:`GatewayCallError` (or :class:`GatewayUnavailable`), and
:func:`movies.llm._via_gateway` turns it into the same ``ProviderError`` the
direct callers produce — quota, withdrawn model or transient — so the chain's
cooldown rules need no special case. No secret ever lands in a log line here.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

# The gateway serves an OpenAI-compatible API; one chat is its chat endpoint.
CHAT_PATH = "/v1/chat/completions"
# How a config built from ``AI_LLM_*`` names the deployment's own provider, and
# the catch-all route that sends every requested model to it unchanged.
APP_PROVIDER = "app"
CATCH_ALL_ROUTE = "*"


class GatewayUnavailable(RuntimeError):
	"""The gateway cannot run here at all: not installed, or nothing to route to.

	That is a *configuration* problem, not an answer from a provider, so the
	chain skips the row instead of treating it as an outage.
	"""


class GatewayCallError(RuntimeError):
	"""One request through the gateway failed.

	``status`` is the HTTP status the gateway answered with (``None`` for a
	timeout or a transport error), ``retry_after`` the provider's own hint in
	seconds when one came back — the same two facts a direct call reports, so
	the caller's cooldown decision is unchanged.
	"""

	def __init__(
		self,
		message: str,
		*,
		status: Optional[int] = None,
		retry_after: Optional[int] = None,
	) -> None:
		super().__init__(message)
		self.status = status
		self.retry_after = retry_after


def _module():
	"""``respan_gateway``, or ``None`` when its wheel is not installed."""
	try:
		import respan_gateway
	except ImportError:
		return None
	return respan_gateway


def config_path() -> str:
	"""The operator's ``gateway.toml`` (``AI_GATEWAY_CONFIG``), or ``""``.

	A relative value is read from the project directory, the same way the
	project reads every other file path of its own.
	"""
	raw = str(getattr(settings, "AI_GATEWAY_CONFIG", "") or "").strip()
	if not raw:
		return ""
	path = Path(raw).expanduser()
	if not path.is_absolute():
		path = Path(settings.BASE_DIR) / path
	return str(path)


def build_config() -> Optional[Dict[str, Any]]:
	"""A gateway config for the deployment's own provider, or ``None``.

	``None`` means "the operator's file decides" (or "nothing to route to", and
	the caller refuses): the file wins whenever ``AI_GATEWAY_CONFIG`` is set.

	Otherwise the provider ``AI_LLM_*`` describes becomes the gateway's single
	provider, and a catch-all route hands it the model unchanged. The key
	travels inside this in-process mapping only — it is never written anywhere,
	and the gateway's own log is off here.
	"""
	if config_path():
		return None
	# Imported here, not at module level: movies.llm imports this module.
	from .llm import env_provider

	provider = env_provider()
	if not provider.api_key or not provider.base_url:
		return None
	return {
		"log": "off",
		"ui": False,
		"providers": {
			APP_PROVIDER: {
				# Every preset the project knows (Groq, Gemini, OpenAI, a
				# custom endpoint) speaks the OpenAI chat format with a bearer
				# key, which is exactly what the direct caller assumed too.
				"formats": ["openai-chat"],
				"base_url": provider.base_url,
				"key": provider.api_key,
			}
		},
		"routes": {CATCH_ALL_ROUTE: {"to": APP_PROVIDER}},
	}


def _cache_key() -> str:
	"""What the cached gateway was built from (a changed setting rebuilds it).

	The key is part of the identity — a rotated key must rebuild — but it is
	only ever compared here, never logged.
	"""
	path = config_path()
	if path:
		return f"file:{path}"
	from .llm import env_provider

	provider = env_provider()
	return f"env:{provider.kind}:{provider.model}:{provider.base_url}:{provider.api_key}"


_LOCK = threading.Lock()
_CACHE: Dict[str, Any] = {"key": "", "gateway": None}


def _close(gateway) -> None:
	"""Stop what the gateway started; a shutdown must not raise."""
	try:
		gateway.close()
	except Exception:  # noqa: BLE001 - closing is best effort
		logger.debug("Respan Gateway could not be closed", exc_info=True)


def gateway():
	"""The process-wide gateway, built on first use.

	One per process (and rebuilt when the settings behind it change): building
	it starts a tokio runtime and compiles the routing table, which a chat path
	must pay for once, not once per question. ``Gateway()`` is thread safe, so
	the bot and every gunicorn worker thread share this one.
	"""
	module = _module()
	if module is None:
		raise GatewayUnavailable(
			"respan-gateway o'rnatilmagan: pip install respan-gateway==0.3.0"
		)
	key = _cache_key()
	with _LOCK:
		cached = _CACHE["gateway"]
		if cached is not None and _CACHE["key"] == key:
			return cached
		# Being rebuilt: the old one is closed once the new one is in place,
		# so no thread is ever left holding a gateway that is shutting down.
		previous, _CACHE["gateway"] = cached, None
	path = config_path()
	try:
		if path:
			built = module.Gateway.from_file(path)
		else:
			config = build_config()
			if config is None:
				raise GatewayUnavailable(
					"Respan Gateway sozlanmagan: AI_LLM_API_KEY yoki "
					"AI_GATEWAY_CONFIG kerak."
				)
			built = module.Gateway(config=config)
	except GatewayUnavailable:
		raise
	except Exception as exc:  # noqa: BLE001 - ConfigError and friends
		raise GatewayUnavailable(f"Respan Gateway sozlanmadi: {exc}") from exc
	with _LOCK:
		_CACHE["gateway"], _CACHE["key"] = built, key
	if previous is not None:
		_close(previous)
	return built


def reset() -> None:
	"""Drop the cached gateway (tests, or a settings change an operator made)."""
	with _LOCK:
		stopped, _CACHE["gateway"], _CACHE["key"] = _CACHE["gateway"], None, ""
	if stopped is not None:
		_close(stopped)


def _retry_after(headers) -> Optional[int]:
	"""The provider's ``Retry-After`` in seconds, when it bothered to send one."""
	try:
		value = int(str((headers or {}).get("retry-after") or "").strip())
	except (TypeError, ValueError):
		return None
	return value if value > 0 else None


def complete(payload: Dict[str, Any], *, seconds: int) -> Dict[str, Any]:
	"""One chat completion through the gateway: the decoded JSON body.

	``payload`` is the OpenAI-shaped request the assistant already builds, and
	the answer is returned untouched — the same body a direct provider would
	have sent, so the caller parses it with the same code.
	"""
	built = gateway()
	timeout = float(max(1, int(seconds)))
	try:
		response = built.request("POST", CHAT_PATH, json=payload, timeout=timeout)
	except httpx.TimeoutException as exc:
		raise GatewayCallError(
			f"Respan Gateway {int(timeout)}s ichida javob bermadi."
		) from exc
	except Exception as exc:  # noqa: BLE001 - the gateway is a black box
		raise GatewayCallError(f"Respan Gateway bilan aloqa uzildi: {exc}") from exc
	if response.status_code >= 400:
		# The body of an error is the provider's own complaint, which is what
		# the operator needs; it never contains the key (the gateway holds it).
		detail = (response.text or "").strip()[:200]
		raise GatewayCallError(
			f"Respan Gateway HTTP {response.status_code}: {detail}",
			status=response.status_code,
			retry_after=_retry_after(response.headers),
		)
	try:
		body = response.json()
	except ValueError as exc:
		raise GatewayCallError("Respan Gateway noto'g'ri javob qaytardi.") from exc
	if not isinstance(body, dict):
		raise GatewayCallError("Respan Gateway JSON obyekt emas.")
	return body
