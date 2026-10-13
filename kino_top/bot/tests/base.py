"""Base class for tests that drive the real aiogram dispatcher.

``TransactionTestCase`` is required: the storage writes happen on Django's
async ORM executor thread (exactly like in production), so they must be
committed to be visible to the test thread. Each update is fed with its own
``asyncio.run`` so the synchronous ORM remains usable for assertions.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from django.test import TransactionTestCase, override_settings

from ..config import reset_config_cache
from ..runner import build_dispatcher
from .fakes import FakeSession, make_bot


_DISPATCHER = None


def _silence_db_log_handler() -> None:
	"""Keep the background BotLogEntry writer out of test runs.

	The writer thread performs SQLite inserts from its own connection while the
	ORM thread writes from another; on the shared in-memory test database this
	raises SQLITE_LOCKED ("database table is locked"), which is not retried by
	the busy timeout. Tests create BotLogEntry rows explicitly where needed.
	"""
	from ..bot_logging import HANDLER_MARKER

	for handler in list(logging.getLogger("bot").handlers):
		if getattr(handler, HANDLER_MARKER, False):
			handler.setLevel(logging.CRITICAL)


_silence_db_log_handler()


def get_dispatcher():
	"""Reuse one Dispatcher, mirroring the single-dispatcher production process.

	aiogram routers can only be attached to one parent, so a dispatcher is built
	once per test process instead of once per test.
	"""
	global _DISPATCHER
	if _DISPATCHER is None:
		_DISPATCHER = build_dispatcher()
	return _DISPATCHER


@override_settings(BOT_THROTTLE_RATE=0)
class DispatcherTestCase(TransactionTestCase):
	reset_sequences = True

	def setUp(self) -> None:
		super().setUp()
		reset_config_cache()
		self.session = FakeSession()
		self.bot = make_bot(self.session)
		self.dispatcher = get_dispatcher()

	def tearDown(self) -> None:
		# The daemon log-writer thread inserts BotLogEntry rows asynchronously;
		# drain it before this test's tables are truncated so its writes can
		# neither collide with the next test's queries nor leak rows into it.
		from ..bot_logging import flush_db_logs

		flush_db_logs()
		super().tearDown()

	def feed(self, update: Any) -> None:
		"""Deliver one update through middlewares, routers and handlers."""
		asyncio.run(self.dispatcher.feed_update(self.bot, update))

	def texts(self) -> str:
		return "\n".join(self.session.sent_texts())

	def replies(self) -> list:
		"""All texts the bot produced (messages plus edited message bodies)."""
		out = []
		for method in self.session.calls:
			name = type(method).__name__
			if name in {"SendMessage", "EditMessageText"}:
				out.append(getattr(method, "text", "") or "")
		return out

	def button_texts(self) -> str:
		"""Every inline button label, i.e. everything the user can read."""
		out = []
		for method in self.session.calls:
			markup = getattr(method, "reply_markup", None)
			rows = getattr(markup, "inline_keyboard", None) or []
			for row in rows:
				for button in row:
					out.append(button.text)
		return "\n".join(out)

	def all_text(self) -> str:
		return "\n".join(self.replies())

	def visible(self) -> str:
		"""Message bodies plus inline button labels."""
		return f"{self.all_text()}\n{self.button_texts()}"
