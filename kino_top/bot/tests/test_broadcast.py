"""Broadcast engine tests: concurrency, cancellation, resumption and stats."""

from __future__ import annotations

import asyncio

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from asgiref.sync import sync_to_async
from django.test import TransactionTestCase
from users.telegram_auth import get_or_create_telegram_user

from ..models import Broadcast, BroadcastDelivery
from ..services.broadcast import (
	BroadcastProgress,
	RateLimiter,
	create_broadcast_sync,
	request_cancel_sync,
	run_broadcast,
)
from .fakes import FakeSession, NOW, make_bot
from aiogram.types import Chat, Message


def make_users(*ids: int) -> None:
	for telegram_id in ids:
		get_or_create_telegram_user({"id": telegram_id, "first_name": f"User {telegram_id}"})


def send_message_response(method) -> Message:
	return Message(
		message_id=1,
		date=NOW,
		chat=Chat(id=int(getattr(method, "chat_id", 1)), type="private"),
	)


class RateLimiterTests(TransactionTestCase):
	def test_rate_limiter_spaces_requests(self) -> None:
		async def scenario() -> float:
			limiter = RateLimiter(50)  # 20 ms between slots
			start = asyncio.get_running_loop().time()
			for _ in range(4):
				await limiter.acquire()
			return asyncio.get_running_loop().time() - start

		elapsed = asyncio.run(scenario())
		self.assertGreaterEqual(elapsed, 0.045)  # three intervals ≈ 60 ms

	def test_zero_rate_is_normalised(self) -> None:
		limiter = RateLimiter(0)
		self.assertGreater(limiter._interval, 0)  # noqa: SLF001 - explicit invariant


class BroadcastExecutionTests(TransactionTestCase):
	def setUp(self) -> None:
		make_users(1, 2, 3, 4)

	def _broadcast(self, **overrides) -> Broadcast:
		payload = {
			"admin_telegram_id": 555,
			"kind": Broadcast.Kind.TEXT,
			"text": "Hello everyone",
			"protect_content": True,
		}
		payload.update(overrides)
		return create_broadcast_sync(**payload)

	def test_broadcast_reaches_every_user_and_persists_statistics(self) -> None:
		broadcast = self._broadcast()
		session = FakeSession()
		bot = make_bot(session)

		final = asyncio.run(run_broadcast(bot, broadcast, rate=1000, concurrency=3))

		self.assertEqual(final.status, Broadcast.Status.COMPLETED)
		self.assertEqual(final.sent_count, 4)
		self.assertEqual(final.failed_count, 0)
		self.assertEqual(len(session.methods("SendMessage")), 4)
		self.assertEqual(BroadcastDelivery.objects.filter(broadcast=broadcast).count(), 4)
		self.assertEqual(
			BroadcastDelivery.objects.filter(
				broadcast=broadcast, status=BroadcastDelivery.Status.SENT
			).count(),
			4,
		)
		self.assertIsNotNone(final.finished_at)
		self.assertEqual(final.total, 4)

	def test_a_blocked_user_does_not_stop_the_broadcast(self) -> None:
		broadcast = self._broadcast()
		session = FakeSession()

		async def responder(method):
			if int(method.chat_id) == 2:
				raise TelegramForbiddenError(method=method, message="Forbidden: bot was blocked")
			if int(method.chat_id) == 3:
				raise TelegramBadRequest(method=method, message="Bad Request: chat not found")
			return send_message_response(method)

		session.responders["SendMessage"] = responder
		final = asyncio.run(run_broadcast(make_bot(session), broadcast, rate=1000, concurrency=2))

		self.assertEqual(final.sent_count, 2)
		self.assertEqual(final.blocked_count, 1)
		self.assertEqual(final.failed_count, 1)
		self.assertEqual(final.status, Broadcast.Status.COMPLETED)
		self.assertEqual(
			BroadcastDelivery.objects.get(broadcast=broadcast, telegram_id=2).status,
			BroadcastDelivery.Status.BLOCKED,
		)

	def test_one_bad_payload_is_isolated_per_recipient(self) -> None:
		broadcast = self._broadcast()

		async def responder(method):
			raise TelegramBadRequest(method=method, message="Bad Request: message is too long")

		session = FakeSession(responders={"SendMessage": responder})
		final = asyncio.run(run_broadcast(make_bot(session), broadcast, rate=1000, concurrency=2))

		self.assertEqual(final.failed_count, 4)
		self.assertEqual(final.sent_count, 0)
		self.assertEqual(final.status, Broadcast.Status.COMPLETED)

	def test_concurrency_is_bounded(self) -> None:
		broadcast = self._broadcast()
		state = {"active": 0, "peak": 0}

		async def responder(method):
			state["active"] += 1
			state["peak"] = max(state["peak"], state["active"])
			await asyncio.sleep(0.02)
			state["active"] -= 1
			return send_message_response(method)

		session = FakeSession(responders={"SendMessage": responder})
		asyncio.run(run_broadcast(make_bot(session), broadcast, rate=1000, concurrency=2))

		self.assertLessEqual(state["peak"], 2)
		self.assertGreaterEqual(state["peak"], 1)

	def test_progress_callback_receives_live_totals(self) -> None:
		broadcast = self._broadcast()
		seen: list = []

		async def progress(update: BroadcastProgress) -> None:
			seen.append((update.sent, update.total))

		asyncio.run(run_broadcast(make_bot(FakeSession()), broadcast, rate=1000, concurrency=1, progress=progress))

		self.assertTrue(seen)
		self.assertEqual(seen[-1], (4, 4))

	def test_cancellation_stops_the_remaining_batches(self) -> None:
		# Eight recipients with concurrency 1 gives several batches of four.
		make_users(5, 6, 7, 8)
		broadcast = self._broadcast()
		session = FakeSession()
		pk = broadcast.pk

		async def progress(update: BroadcastProgress) -> None:
			# Ask for cancellation after the first batch is flushed.
			await sync_to_async(request_cancel_sync, thread_sensitive=True)(pk)

		final = asyncio.run(
			run_broadcast(make_bot(session), broadcast, rate=1000, concurrency=1, progress=progress)
		)

		self.assertEqual(final.status, Broadcast.Status.CANCELLED)
		self.assertEqual(final.sent_count, 4)
		self.assertLess(final.cursor_telegram_id, 8)
		self.assertEqual(len(session.methods("SendMessage")), 4)

	def test_resume_continues_after_the_cursor(self) -> None:
		make_users(5)
		broadcast = self._broadcast(status=Broadcast.Status.PAUSED, cursor_telegram_id=3)
		Broadcast.objects.filter(pk=broadcast.pk).update(sent_count=3)
		broadcast.refresh_from_db()

		session = FakeSession()
		final = asyncio.run(run_broadcast(make_bot(session), broadcast, rate=1000, concurrency=2))

		# Only recipients after the cursor are contacted again.
		contacted = sorted(int(method.chat_id) for method in session.methods("SendMessage"))
		self.assertEqual(contacted, [4, 5])
		self.assertEqual(final.sent_count, 5)
		self.assertEqual(final.status, Broadcast.Status.COMPLETED)

	def test_resume_after_cancellation_delivers_the_rest(self) -> None:
		make_users(5, 6, 7, 8)
		broadcast = self._broadcast()
		cancelled = asyncio.run(
			run_broadcast(make_bot(FakeSession()), broadcast, rate=1000, concurrency=1,
			              progress=self._cancel_after_first_batch(broadcast.pk))
		)
		self.assertEqual(cancelled.status, Broadcast.Status.CANCELLED)
		self.assertEqual(cancelled.sent_count, 4)

		session = FakeSession()
		final = asyncio.run(run_broadcast(make_bot(session), cancelled, rate=1000, concurrency=1))

		# Resuming must not re-message the first batch.
		self.assertEqual(final.status, Broadcast.Status.COMPLETED)
		self.assertEqual(final.sent_count, 8)
		self.assertEqual(len(session.methods("SendMessage")), 4)

	@staticmethod
	def _cancel_after_first_batch(pk: int):
		async def progress(update: BroadcastProgress) -> None:
			await sync_to_async(request_cancel_sync, thread_sensitive=True)(pk)

		return progress

	def test_completed_broadcast_is_not_rerun(self) -> None:
		broadcast = self._broadcast(status=Broadcast.Status.COMPLETED, sent_count=4)
		session = FakeSession()
		final = asyncio.run(run_broadcast(make_bot(session), broadcast, rate=1000))

		self.assertEqual(final.status, Broadcast.Status.COMPLETED)
		self.assertEqual(session.methods("SendMessage"), [])

	def test_broadcast_media_kinds_use_the_right_api_method(self) -> None:
		cases = [
			({"kind": Broadcast.Kind.PHOTO, "file_id": "photo-id"}, "SendPhoto"),
			({"kind": Broadcast.Kind.VIDEO, "file_id": "video-id"}, "SendVideo"),
			({"kind": Broadcast.Kind.DOCUMENT, "file_id": "doc-id"}, "SendDocument"),
		]
		for overrides, expected in cases:
			with self.subTest(kind=overrides["kind"]):
				broadcast = self._broadcast(text="", **overrides)
				session = FakeSession()
				asyncio.run(run_broadcast(make_bot(session), broadcast, rate=1000, concurrency=2))
				self.assertEqual(len(session.methods(expected)), 4)

	def test_forward_broadcast_copies_the_source_message(self) -> None:
		broadcast = self._broadcast(
			kind=Broadcast.Kind.FORWARD,
			text="",
			file_id="",
			from_chat_id=-100777,
			source_message_id=42,
		)
		session = FakeSession()
		asyncio.run(run_broadcast(make_bot(session), broadcast, rate=1000, concurrency=2))

		copies = session.methods("CopyMessage")
		self.assertEqual(len(copies), 4)
		self.assertEqual(copies[0].from_chat_id, -100777)
		self.assertEqual(copies[0].message_id, 42)

	def test_blocked_users_can_be_included_explicitly(self) -> None:
		profile = get_or_create_telegram_user({"id": 6, "first_name": "Blocked"})
		from users.models import TelegramUser

		TelegramUser.objects.filter(pk=profile.pk).update(is_blocked=True)

		broadcast = self._broadcast(include_blocked=True)
		session = FakeSession()
		final = asyncio.run(run_broadcast(make_bot(session), broadcast, rate=1000, concurrency=2))

		self.assertEqual(final.sent_count, 5)
		self.assertIn(6, sorted(int(method.chat_id) for method in session.methods("SendMessage")))

	def test_rate_limit_retry_after_is_honoured(self) -> None:
		from aiogram.exceptions import TelegramRetryAfter

		broadcast = self._broadcast()
		attempts = {"count": 0}

		async def responder(method):
			attempts["count"] += 1
			if attempts["count"] == 1:
				raise TelegramRetryAfter(method=method, message="Too Many Requests", retry_after=0)
			return send_message_response(method)

		session = FakeSession(responders={"SendMessage": responder})
		final = asyncio.run(run_broadcast(make_bot(session), broadcast, rate=1000, concurrency=1))

		self.assertEqual(final.sent_count, 4)
		self.assertEqual(final.failed_count, 0)
		self.assertGreater(attempts["count"], 4)
