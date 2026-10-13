"""Django backed aiogram 3.x FSM storage.

``DjangoStorage`` implements aiogram's :class:`~aiogram.fsm.storage.base.BaseStorage`
on top of the project's existing database, so FSM state and data survive bot
restarts and deployments and live in the same database as the catalog. No
secondary storage backend is introduced.

Concurrency notes:

* ``update_data`` merges inside a single transaction with ``SELECT ... FOR UPDATE``
  so two parallel updates for the same key cannot lose each other's changes.
* ``DjangoEventIsolation`` serializes updates for the same key inside one
  process. It is safe to run multiple bot processes: the row lock still protects
  the merge itself.
"""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import datetime as dt
import json
import logging
import os
from contextlib import asynccontextmanager
from decimal import Decimal
from enum import Enum
from typing import Any, AsyncGenerator, Dict, Mapping, Optional
from uuid import UUID

from aiogram.fsm.state import State
from aiogram.fsm.storage.base import (
	BaseEventIsolation,
	BaseStorage,
	DefaultKeyBuilder,
	KeyBuilder,
	StateType,
	StorageKey,
)
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import FSMState

logger = logging.getLogger(__name__)

TAG = "__fsm__"
DEFAULT_TTL = 86400


def _env_ttl() -> int:
	"""Read the FSM TTL without requiring the rest of the bot configuration."""
	raw = os.environ.get("BOT_FSM_TTL")
	if raw in (None, ""):
		raw = getattr(settings, "BOT_FSM_TTL", DEFAULT_TTL)
	try:
		return int(raw)
	except (TypeError, ValueError):
		logger.warning("Invalid BOT_FSM_TTL value %r, falling back to %s.", raw, DEFAULT_TTL)
		return DEFAULT_TTL


def _encode_default(obj: Any) -> Any:
	"""Fallback encoder that keeps non-JSON FSM payloads round-trippable."""
	if isinstance(obj, dt.datetime):
		return {TAG: "datetime", "value": obj.isoformat()}
	if isinstance(obj, dt.date):
		return {TAG: "date", "value": obj.isoformat()}
	if isinstance(obj, dt.time):
		return {TAG: "time", "value": obj.isoformat()}
	if isinstance(obj, dt.timedelta):
		return {TAG: "timedelta", "value": obj.total_seconds()}
	if isinstance(obj, Decimal):
		return {TAG: "decimal", "value": str(obj)}
	if isinstance(obj, UUID):
		return {TAG: "uuid", "value": str(obj)}
	if isinstance(obj, (bytes, bytearray)):
		return {TAG: "bytes", "value": base64.b64encode(bytes(obj)).decode("ascii")}
	if isinstance(obj, (set, frozenset)):
		return {TAG: "set", "value": sorted(str(item) for item in obj)}
	if isinstance(obj, Enum):
		return {TAG: "enum", "value": obj.value}
	if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
		return {TAG: "dataclass", "value": dataclasses.asdict(obj)}
	if hasattr(obj, "model_dump"):
		# Telegram/pydantic objects are degraded to plain dictionaries.
		return {TAG: "object", "value": obj.model_dump(mode="json")}
	return {TAG: "str", "value": str(obj)}


def _decode_object(obj: Dict[str, Any]) -> Any:
	"""Restore values tagged by :func:`_encode_default`."""
	tag = obj.get(TAG)
	if not tag or set(obj.keys()) - {TAG, "value"}:
		return obj
	value = obj.get("value")
	try:
		if tag == "datetime":
			return dt.datetime.fromisoformat(value)
		if tag == "date":
			return dt.date.fromisoformat(value)
		if tag == "time":
			return dt.time.fromisoformat(value)
		if tag == "timedelta":
			return dt.timedelta(seconds=float(value))
		if tag == "decimal":
			return Decimal(value)
		if tag == "uuid":
			return UUID(value)
		if tag == "bytes":
			return base64.b64decode(value.encode("ascii"))
		if tag == "set":
			return set(value)
	except (TypeError, ValueError, AttributeError):  # pragma: no cover - defensive
		logger.warning("Failed to decode FSM value tagged as %s.", tag)
		return value
	return value


def encode_data(data: Mapping[str, Any]) -> Dict[str, Any]:
	"""Return a JSON-safe copy of ``data`` where exotic values are tagged.

	Only the result of this function is ever written to the database, so the
	``JSONField`` never receives a value it cannot serialize (for example a
	``datetime``).
	"""
	raw = json.dumps(dict(data), default=_encode_default, ensure_ascii=False)
	return json.loads(raw)


def decode_data(payload: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
	"""Restore the values tagged by :func:`_encode_default` on the way out."""
	if not payload:
		return {}
	raw = json.dumps(dict(payload), ensure_ascii=False)
	return json.loads(raw, object_hook=_decode_object)


class DjangoStorage(BaseStorage):
	"""aiogram FSM storage backed by the ``bot.FSMState`` Django model."""

	def __init__(
		self,
		*,
		ttl: Optional[int] = None,
		key_builder: Optional[KeyBuilder] = None,
	) -> None:
		self._ttl = _env_ttl() if ttl is None else int(ttl)
		self._key_builder = key_builder or DefaultKeyBuilder(
			prefix="fsm",
			separator=":",
			with_bot_id=True,
			with_destiny=True,
			with_business_connection_id=True,
		)

	# ------------------------------------------------------------------ helpers
	def build_key(self, key: StorageKey) -> str:
		return self._key_builder.build(key)

	@property
	def ttl(self) -> int:
		return self._ttl

	def _expiry(self, now: dt.datetime) -> Optional[dt.datetime]:
		if not self._ttl or self._ttl <= 0:
			return None
		return now + dt.timedelta(seconds=self._ttl)

	async def _run(self, func, *args, **kwargs):
		"""Run a synchronous database helper without blocking the event loop."""
		return await sync_to_async(func, thread_sensitive=True)(*args, **kwargs)

	# ------------------------------------------------------------------- state
	def _fetch_sync(self, key_str: str) -> Optional[dict]:
		record = FSMState.objects.filter(key=key_str).values(
			"state", "data", "expires_at", "id"
		).first()
		if record is None:
			return None
		if record["expires_at"] is not None and record["expires_at"] <= timezone.now():
			FSMState.objects.filter(pk=record["id"]).delete()
			return None
		return record

	async def set_state(self, key: StorageKey, state: StateType = None) -> None:
		state_value = state.state if isinstance(state, State) else state
		await self._run(
			self._set_state_sync,
			self.build_key(key),
			key.bot_id,
			key.chat_id,
			key.user_id,
			key.thread_id,
			key.business_connection_id or "",
			key.destiny,
			state_value or "",
		)

	@transaction.atomic
	def _set_state_sync(
		self,
		key_str: str,
		bot_id: int,
		chat_id: int,
		user_id: int,
		thread_id: Optional[int],
		business_connection_id: str,
		destiny: str,
		state_value: str,
	) -> None:
		expires_at = self._expiry(timezone.now())
		updated = FSMState.objects.filter(key=key_str).update(
			state=state_value,
			updated_at=timezone.now(),
			expires_at=expires_at,
		)
		if not updated:
			FSMState.objects.update_or_create(
				key=key_str,
				defaults={
					"bot_id": bot_id,
					"chat_id": chat_id,
					"user_id": user_id,
					"thread_id": thread_id,
					"business_connection_id": business_connection_id,
					"destiny": destiny,
					"state": state_value,
					"expires_at": expires_at,
				},
			)

	async def get_state(self, key: StorageKey) -> Optional[str]:
		record = await self._run(self._fetch_sync, self.build_key(key))
		if not record:
			return None
		return record["state"] or None

	# -------------------------------------------------------------------- data
	async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
		await self._run(
			self._set_data_sync,
			self.build_key(key),
			key.bot_id,
			key.chat_id,
			key.user_id,
			key.thread_id,
			key.business_connection_id or "",
			key.destiny,
			encode_data(data),
		)

	@transaction.atomic
	def _set_data_sync(
		self,
		key_str: str,
		bot_id: int,
		chat_id: int,
		user_id: int,
		thread_id: Optional[int],
		business_connection_id: str,
		destiny: str,
		payload: dict,
	) -> None:
		expires_at = self._expiry(timezone.now())
		updated = FSMState.objects.filter(key=key_str).update(
			data=payload,
			updated_at=timezone.now(),
			expires_at=expires_at,
		)
		if not updated:
			FSMState.objects.update_or_create(
				key=key_str,
				defaults={
					"bot_id": bot_id,
					"chat_id": chat_id,
					"user_id": user_id,
					"thread_id": thread_id,
					"business_connection_id": business_connection_id,
					"destiny": destiny,
					"state": "",
					"data": payload,
					"expires_at": expires_at,
				},
			)

	async def get_data(self, key: StorageKey) -> Dict[str, Any]:
		record = await self._run(self._fetch_sync, self.build_key(key))
		if not record:
			return {}
		return decode_data(record["data"])

	async def update_data(
		self, key: StorageKey, data: Mapping[str, Any]
	) -> Dict[str, Any]:
		"""Merge ``data`` into the stored payload atomically."""
		key_str = self.build_key(key)
		payload = encode_data(data)
		last_error: Optional[Exception] = None
		for _ in range(3):
			try:
				return await self._run(
					self._update_data_sync,
					key_str,
					key.bot_id,
					key.chat_id,
					key.user_id,
					key.thread_id,
					key.business_connection_id or "",
					key.destiny,
					payload,
				)
			except IntegrityError as exc:  # pragma: no cover - concurrent create race
				last_error = exc
				await asyncio.sleep(0.05)
		if last_error is not None:
			raise last_error
		return {}

	@transaction.atomic
	def _update_data_sync(
		self,
		key_str: str,
		bot_id: int,
		chat_id: int,
		user_id: int,
		thread_id: Optional[int],
		business_connection_id: str,
		destiny: str,
		payload: dict,
	) -> Dict[str, Any]:
		expires_at = self._expiry(timezone.now())
		record = FSMState.objects.select_for_update().filter(key=key_str).first()
		if record is None:
			record = FSMState.objects.create(
				key=key_str,
				bot_id=bot_id,
				chat_id=chat_id,
				user_id=user_id,
				thread_id=thread_id,
				business_connection_id=business_connection_id,
				destiny=destiny,
				state="",
				data=payload,
				expires_at=expires_at,
			)
			return decode_data(record.data)
		merged = dict(record.data or {})
		merged.update(payload)
		record.data = merged
		record.expires_at = expires_at
		record.save(update_fields=["data", "expires_at", "updated_at"])
		return decode_data(merged)

	# ------------------------------------------------------------------ cleanup
	async def close(self) -> None:
		"""Django owns the connection pool, so there is nothing to close here."""
		return None

	async def cleanup_expired(self) -> int:
		return await self._run(cleanup_expired_states)


def cleanup_expired_states() -> int:
	"""Delete every expired FSM row and return how many were removed."""
	deleted, _ = FSMState.objects.filter(expires_at__isnull=False, expires_at__lte=timezone.now()).delete()
	return deleted


class DjangoEventIsolation(BaseEventIsolation):
	"""Per-key async locks so concurrent updates to one chat serialize."""

	def __init__(self) -> None:
		self._locks: Dict[str, asyncio.Lock] = {}
		self._guard = asyncio.Lock()

	async def _lock_for(self, key: str) -> asyncio.Lock:
		async with self._guard:
			lock = self._locks.get(key)
			if lock is None:
				lock = asyncio.Lock()
				self._locks[key] = lock
			return lock

	@asynccontextmanager
	async def lock(self, key: StorageKey) -> AsyncGenerator[None, None]:
		built = f"{key.bot_id}:{key.chat_id}:{key.user_id}:{key.thread_id}:{key.destiny}"
		lock = await self._lock_for(built)
		async with lock:
			yield None

	async def close(self) -> None:
		self._locks.clear()
