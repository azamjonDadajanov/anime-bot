"""Logging plumbing: persists bot log records into the database.

Log records are produced from inside coroutines (the event loop thread), where a
synchronous ORM call would raise ``SynchronousOnlyOperation``. A single daemon
writer thread drains a bounded queue and performs the inserts, so logging can
never block or crash the bot, and DB rows are written off the event loop.
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time
from typing import Any, Dict, Optional

from django.conf import settings
from django.db import connection

from .models import BotLogEntry

HANDLER_MARKER = "_freebuff_bot_db_handler"
DEFAULT_DB_LEVEL = "WARNING"
WRITE_TIMEOUT = 2.0


class _LogWriter(threading.Thread):
	"""Daemon thread that writes ``BotLogEntry`` rows off the event loop."""

	def __init__(self) -> None:
		super().__init__(name="bot-db-log", daemon=True)
		self.queue: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue(maxsize=2000)

	def submit(self, payload: Optional[Dict[str, Any]]) -> bool:
		try:
			self.queue.put_nowait(payload)
			return True
		except queue.Full:
			# Dropping a log line is preferable to blocking the bot or the loop.
			return False

	def run(self) -> None:  # pragma: no cover - thread body
		while True:
			item = self.queue.get()
			try:
				if item is None:
					return
				try:
					BotLogEntry.objects.create(**item)
				except Exception:  # noqa: BLE001 - logging must never raise
					logging.getLogger("bot.logging").debug("Could not persist a log entry.", exc_info=True)
				finally:
					# Do not hold a database connection idle in this thread.
					try:
						connection.close()
					except Exception:  # noqa: BLE001
						pass
			finally:
				self.queue.task_done()

	def flush(self, timeout: float = WRITE_TIMEOUT) -> bool:
		"""Wait until queued rows are written *and* the in-flight insert finished."""
		deadline = time.monotonic() + timeout
		while time.monotonic() < deadline:
			if self.queue.unfinished_tasks == 0:
				return True
			time.sleep(0.005)
		return self.queue.unfinished_tasks == 0


_WRITER: Optional[_LogWriter] = None
_WRITER_LOCK = threading.Lock()


def get_writer() -> _LogWriter:
	global _WRITER
	if _WRITER is not None and _WRITER.is_alive():
		return _WRITER
	with _WRITER_LOCK:
		if _WRITER is None or not _WRITER.is_alive():
			_WRITER = _LogWriter()
			_WRITER.start()
		return _WRITER


def flush_db_logs(timeout: float = WRITE_TIMEOUT) -> bool:
	"""Wait until queued log rows are written (used by tests and shutdown)."""
	writer = _WRITER
	if writer is None:
		return True
	return writer.flush(timeout)


def _db_level() -> int:
	raw = os.environ.get("BOT_DB_LOG_LEVEL") or getattr(settings, "BOT_DB_LOG_LEVEL", DEFAULT_DB_LEVEL)
	return logging.getLevelNamesMapping().get(str(raw).upper(), logging.WARNING)


def _normalize_level(level: object) -> str:
	text = str(level).upper()
	if text in BotLogEntry.Level.values:
		return text
	return BotLogEntry.Level.INFO


class DatabaseLogHandler(logging.Handler):
	"""Queue log records for persistence without blocking the caller."""

	def __init__(self, level: int = logging.WARNING) -> None:
		super().__init__(level=level)
		setattr(self, HANDLER_MARKER, True)

	def emit(self, record: logging.LogRecord) -> None:
		# ``record_event`` already writes its own row; skip the duplicate.
		if getattr(record, "db_persisted", False):
			return
		try:
			get_writer().submit(
				{
					"level": _normalize_level(record.levelname),
					"logger": str(record.name)[:64],
					"message": self.format(record)[:8000],
					"telegram_id": getattr(record, "telegram_id", None),
				}
			)
		except Exception:  # noqa: BLE001 - never let logging break the bot
			self.handleError(record)


def install_db_log_handler(
	logger_name: str = "bot", level: Optional[int] = None
) -> DatabaseLogHandler:
	"""Attach exactly one :class:`DatabaseLogHandler` to ``logger_name``."""
	logger = logging.getLogger(logger_name)
	for handler in list(logger.handlers):
		if getattr(handler, HANDLER_MARKER, False):
			logger.removeHandler(handler)
	handler = DatabaseLogHandler(level=level if level is not None else _db_level())
	logger.addHandler(handler)
	if logger.level == logging.NOTSET:
		logger.setLevel(logging.INFO)
	return handler


def record_event(
	level: object,
	message: str,
	*,
	telegram_id: Optional[int] = None,
	logger_name: str = "bot.events",
) -> Optional[BotLogEntry]:
	"""Write an explicit audit/event row and mirror it to the log stream.

	Call this through ``bot.utils.to_async`` from handlers; when called from
	synchronous code (management commands, tests) it writes immediately.
	"""
	normalized = _normalize_level(level)
	try:
		entry = BotLogEntry.objects.create(
			level=normalized,
			logger=logger_name[:64],
			message=str(message)[:8000],
			telegram_id=telegram_id,
		)
	except Exception:  # noqa: BLE001 - never let auditing break a handler
		logging.getLogger(logger_name).exception("Failed to persist a bot log entry.")
		return None
	logging.getLogger(logger_name).log(
		logging.getLevelNamesMapping().get(normalized, logging.INFO),
		str(message)[:500],
		extra={"db_persisted": True},
	)
	return entry


# Installed on import; ``apps.BotConfig.ready`` imports this module so the
# handler is active for management commands and the bot runner alike.
install_db_log_handler()
