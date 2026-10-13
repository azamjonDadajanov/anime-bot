"""FSM storage tests: persistence, merging, expiration and isolation."""

from __future__ import annotations

import asyncio
import datetime as dt
from decimal import Decimal

from aiogram.fsm.storage.base import StorageKey
from django.test import TransactionTestCase
from django.utils import timezone

from ..models import FSMState
from ..storage import DjangoStorage, cleanup_expired_states


def run(coro):
	"""Run a coroutine in a fresh loop (mirrors separate bot invocations)."""
	return asyncio.run(coro)


def key(user_id: int = 3, chat_id: int = 3, bot_id: int = 999, destiny: str = "default") -> StorageKey:
	return StorageKey(bot_id=bot_id, chat_id=chat_id, user_id=user_id, destiny=destiny)


class StoragePersistenceTests(TransactionTestCase):
	def test_state_and_data_survive_a_restart(self) -> None:
		storage = DjangoStorage(ttl=3600)
		run(storage.set_state(key(), "AdminMediaStates:title"))
		run(storage.update_data(key(), {"draft": {"title": "Naruto"}, "page": 2}))

		# A brand new instance models a bot restart / deployment.
		fresh = DjangoStorage(ttl=3600)
		self.assertEqual(run(fresh.get_state(key())), "AdminMediaStates:title")
		self.assertEqual(run(fresh.get_data(key()))["page"], 2)
		self.assertEqual(run(fresh.get_data(key()))["draft"]["title"], "Naruto")

	def test_only_one_row_per_key(self) -> None:
		storage = DjangoStorage(ttl=3600)
		run(storage.set_state(key(), "A:one"))
		run(storage.set_state(key(), "B:two"))

		self.assertEqual(FSMState.objects.count(), 1)
		self.assertEqual(run(storage.get_state(key())), "B:two")

	def test_set_state_none_clears_the_state_but_keeps_data(self) -> None:
		storage = DjangoStorage(ttl=3600)
		run(storage.update_data(key(), {"x": 1}))
		run(storage.set_state(key(), "Some:state"))
		run(storage.set_state(key(), None))

		self.assertIsNone(run(storage.get_state(key())))
		self.assertEqual(run(storage.get_data(key()))["x"], 1)

	def test_set_data_replaces_the_payload(self) -> None:
		storage = DjangoStorage(ttl=3600)
		run(storage.set_data(key(), {"a": 1, "b": 2}))
		run(storage.set_data(key(), {"c": 3}))

		self.assertEqual(run(storage.get_data(key())), {"c": 3})

	def test_missing_key_returns_empty_results(self) -> None:
		storage = DjangoStorage(ttl=3600)
		self.assertIsNone(run(storage.get_state(key(user_id=404))))
		self.assertEqual(run(storage.get_data(key(user_id=404))), {})

	def test_keys_are_isolated_by_user_and_destiny(self) -> None:
		storage = DjangoStorage(ttl=3600)
		run(storage.update_data(key(user_id=1), {"who": "one"}))
		run(storage.update_data(key(user_id=2), {"who": "two"}))
		run(storage.update_data(key(user_id=1, destiny="business"), {"who": "biz"}))

		self.assertEqual(run(storage.get_data(key(user_id=1)))["who"], "one")
		self.assertEqual(run(storage.get_data(key(user_id=2)))["who"], "two")
		self.assertEqual(run(storage.get_data(key(user_id=1, destiny="business")))["who"], "biz")

	def test_exotic_values_are_round_tripped(self) -> None:
		storage = DjangoStorage(ttl=3600)
		payload = {
			"when": dt.datetime(2026, 5, 1, 10, 30, tzinfo=dt.timezone.utc),
			"day": dt.date(2026, 5, 1),
			"price": Decimal("12.50"),
			"tags": {"a", "b"},
			"blob": b"\x00\x01",
		}
		run(storage.update_data(key(), payload))
		restored = run(storage.get_data(key()))

		self.assertEqual(restored["when"], payload["when"])
		self.assertEqual(restored["day"], payload["day"])
		self.assertEqual(restored["price"], payload["price"])
		self.assertEqual(restored["tags"], {"a", "b"})
		self.assertEqual(restored["blob"], b"\x00\x01")

	def test_only_json_safe_values_reach_the_database(self) -> None:
		storage = DjangoStorage(ttl=3600)
		run(storage.update_data(key(), {"when": dt.datetime(2026, 1, 2, 3, 4, 5)}))
		row = FSMState.objects.get(key=storage.build_key(key()))
		self.assertIsInstance(row.data["when"], dict)
		self.assertEqual(row.data["when"]["__fsm__"], "datetime")


class StorageConcurrencyTests(TransactionTestCase):
	def test_parallel_updates_merge_without_losing_data(self) -> None:
		storage = DjangoStorage(ttl=3600)

		async def merge():
			first, second = DjangoStorage(ttl=3600), DjangoStorage(ttl=3600)
			await asyncio.gather(
				first.update_data(key(), {"alpha": 1}),
				second.update_data(key(), {"beta": 2}),
			)
			return await first.get_data(key())

		data = run(merge())
		self.assertEqual(data.get("alpha"), 1)
		self.assertEqual(data.get("beta"), 2)

	def test_many_sequential_updates_accumulate(self) -> None:
		storage = DjangoStorage(ttl=3600)

		async def accumulate():
			for index in range(10):
				await storage.update_data(key(), {f"k{index}": index})
			return await storage.get_data(key())

		data = run(accumulate())
		self.assertEqual(len(data), 10)


class StorageExpirationTests(TransactionTestCase):
	def test_non_expiring_rows_have_no_expiry(self) -> None:
		storage = DjangoStorage(ttl=0)
		run(storage.update_data(key(), {"x": 1}))
		row = FSMState.objects.get(key=storage.build_key(key()))
		self.assertIsNone(row.expires_at)

	def test_expired_rows_are_ignored_and_removed_on_read(self) -> None:
		storage = DjangoStorage(ttl=3600)
		run(storage.update_data(key(), {"x": 1}))

		# Force the row to look expired.
		FSMState.objects.filter(key=storage.build_key(key())).update(
			expires_at=timezone.now() - dt.timedelta(seconds=1)
		)

		self.assertIsNone(run(storage.get_state(key())))
		self.assertEqual(run(storage.get_data(key())), {})
		self.assertFalse(FSMState.objects.filter(key=storage.build_key(key())).exists())

	def test_cleanup_deletes_only_expired_rows(self) -> None:
		fresh = DjangoStorage(ttl=3600)
		stale = DjangoStorage(ttl=3600)
		run(fresh.update_data(key(user_id=1), {"x": 1}))
		run(stale.update_data(key(user_id=2), {"y": 2}))
		FSMState.objects.filter(key=stale.build_key(key(user_id=2))).update(
			expires_at=timezone.now() - dt.timedelta(seconds=5)
		)

		deleted = cleanup_expired_states()

		self.assertEqual(deleted, 1)
		self.assertTrue(FSMState.objects.filter(key=fresh.build_key(key(user_id=1))).exists())

	def test_ttl_refreshes_on_every_write(self) -> None:
		storage = DjangoStorage(ttl=600)
		run(storage.update_data(key(), {"x": 1}))
		first = FSMState.objects.get(key=storage.build_key(key())).expires_at
		run(storage.update_data(key(), {"y": 2}))
		second = FSMState.objects.get(key=storage.build_key(key())).expires_at
		self.assertGreaterEqual(second, first)


class EventIsolationTests(TransactionTestCase):
	def test_lock_serialises_the_same_key(self) -> None:
		from ..storage import DjangoEventIsolation

		isolation = DjangoEventIsolation()
		order: list = []

		async def worker(name: str) -> None:
			async with isolation.lock(key()):
				order.append(f"{name}-in")
				await asyncio.sleep(0.01)
				order.append(f"{name}-out")

		async def scenario() -> None:
			await asyncio.gather(worker("a"), worker("b"))

		run(scenario())
		# Because the same key is locked, the critical sections cannot interleave.
		self.assertEqual(order[0].split("-")[0], order[1].split("-")[0])
		self.assertEqual(order[2].split("-")[0], order[3].split("-")[0])
