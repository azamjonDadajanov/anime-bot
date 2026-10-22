"""Channel management tests for the three logical channel types."""

from __future__ import annotations

import asyncio

from django.test import TransactionTestCase
from movies.models import TelegramChannel

from ..models import BotSettings
from ..services.bot_settings import update_settings_sync
from ..services.channels import (
	add_channel_sync,
	all_channels_sync,
	channels_by_purpose_sync,
	counts_by_purpose_sync,
	delete_channel_sync,
	public_channels_sync,
	required_channels_sync,
	resolve_chat,
	storage_channels_sync,
	test_channel,
	toggle_active_sync,
	update_channel_sync,
	ChatResolutionError,
)
from .fakes import FakeSession, make_bot
from .helpers import make_channel


class ChannelModelTests(TransactionTestCase):
	def test_new_channels_default_to_storage_purpose(self) -> None:
		channel = TelegramChannel.objects.create(chat_id=-1001, title="Default")
		self.assertEqual(channel.purpose, TelegramChannel.Purpose.STORAGE)
		self.assertFalse(channel.is_public)

	def test_public_purpose_keeps_the_legacy_is_public_flag_in_sync(self) -> None:
		channel = make_channel(chat_id=-1002, purpose=TelegramChannel.Purpose.PUBLIC)
		self.assertTrue(channel.is_public)

		update_channel_sync(channel, purpose=TelegramChannel.Purpose.STORAGE)
		channel.refresh_from_db()
		self.assertFalse(channel.is_public)

	def test_username_generates_an_invite_link(self) -> None:
		channel = make_channel(chat_id=-1003, username="my_channel")
		self.assertEqual(channel.invite_link, "https://t.me/my_channel")

	def test_explicit_invite_link_is_preserved(self) -> None:
		channel = TelegramChannel.objects.create(
			chat_id=-1004,
			title="Private",
			username="private_channel",
			invite_link="https://t.me/+abcdef",
		)
		self.assertEqual(channel.invite_link, "https://t.me/+abcdef")


class ChannelServiceTests(TransactionTestCase):
	def test_the_three_types_stay_separate_and_unlimited(self) -> None:
		for index in range(3):
			make_channel(chat_id=-200 - index, purpose=TelegramChannel.Purpose.REQUIRED, title=f"Req {index}")
			make_channel(chat_id=-300 - index, purpose=TelegramChannel.Purpose.STORAGE, title=f"Store {index}")
			make_channel(chat_id=-400 - index, purpose=TelegramChannel.Purpose.PUBLIC, title=f"Pub {index}")

		self.assertEqual(len(required_channels_sync()), 3)
		self.assertEqual(len(storage_channels_sync()), 3)
		self.assertEqual(len(public_channels_sync()), 3)
		self.assertEqual(len(all_channels_sync()), 9)
		counts = counts_by_purpose_sync()
		self.assertEqual(counts["required"], 3)
		self.assertEqual(counts["storage"], 3)
		self.assertEqual(counts["public"], 3)

	def test_only_active_required_channels_are_enforced(self) -> None:
		make_channel(chat_id=-501, purpose=TelegramChannel.Purpose.REQUIRED, is_active=False)
		active = make_channel(chat_id=-502, purpose=TelegramChannel.Purpose.REQUIRED)

		enforced = required_channels_sync(active_only=True)
		self.assertEqual([channel.pk for channel in enforced], [active.pk])
		self.assertEqual(len(required_channels_sync(active_only=False)), 2)

	def test_adding_an_existing_chat_updates_instead_of_duplicating(self) -> None:
		first = add_channel_sync(-600, "Original", purpose=TelegramChannel.Purpose.STORAGE)
		second = add_channel_sync(-600, "Renamed", purpose=TelegramChannel.Purpose.REQUIRED)

		self.assertEqual(first.pk, second.pk)
		self.assertEqual(TelegramChannel.objects.filter(chat_id=-600).count(), 1)
		second.refresh_from_db()
		self.assertEqual(second.title, "Renamed")
		self.assertEqual(second.purpose, TelegramChannel.Purpose.REQUIRED)

	def test_unknown_purpose_is_rejected(self) -> None:
		with self.assertRaises(ValueError):
			add_channel_sync(-601, "Broken", purpose="nonsense")

	def test_toggle_and_delete(self) -> None:
		channel = make_channel(chat_id=-602)
		# ``toggle_active_sync`` returns the *new* state.
		self.assertFalse(toggle_active_sync(channel))
		channel.refresh_from_db()
		self.assertFalse(channel.is_active)
		self.assertTrue(toggle_active_sync(channel))
		channel.refresh_from_db()
		self.assertTrue(channel.is_active)

		delete_channel_sync(channel)
		self.assertFalse(TelegramChannel.objects.filter(chat_id=-602).exists())


class ChannelProbeTests(TransactionTestCase):
	def test_storage_channel_is_healthy_when_the_bot_can_post(self) -> None:
		channel = make_channel(chat_id=-700, purpose=TelegramChannel.Purpose.STORAGE)
		bot = make_bot(FakeSession(bot_status="administrator"))

		result = asyncio.run(test_channel(bot, channel))

		self.assertTrue(result.ok)
		self.assertTrue(result.can_post)
		channel.refresh_from_db()
		self.assertTrue(channel.last_check_ok)
		self.assertIsNotNone(channel.last_checked_at)
		self.assertEqual(channel.check_details["can_post"], True)

	def test_required_channel_needs_administrator_rights(self) -> None:
		channel = make_channel(chat_id=-701, purpose=TelegramChannel.Purpose.REQUIRED)
		bot = make_bot(FakeSession(bot_status="member"))

		result = asyncio.run(test_channel(bot, channel))

		self.assertFalse(result.ok)
		self.assertFalse(result.can_check)
		self.assertIn("administrator", result.message)

	def test_public_channel_must_be_postable_and_checkable(self) -> None:
		"""A public channel is mandatory, so membership must be verifiable too."""
		channel = make_channel(
			chat_id=-703,
			title="Ommaviy",
			purpose=TelegramChannel.Purpose.PUBLIC,
		)
		bot = make_bot(FakeSession(bot_status="member"))

		result = asyncio.run(test_channel(bot, channel))

		self.assertFalse(result.ok)
		self.assertTrue(result.can_post is False or result.can_check is False)
		self.assertIn("administrator", result.message)

	def test_public_channel_is_healthy_for_a_administrator_bot(self) -> None:
		channel = make_channel(
			chat_id=-704,
			title="Ommaviy",
			purpose=TelegramChannel.Purpose.PUBLIC,
		)
		bot = make_bot(FakeSession(bot_status="administrator"))

		result = asyncio.run(test_channel(bot, channel))

		self.assertTrue(result.ok)
		self.assertTrue(result.can_check)

	def test_unreachable_channel_is_reported(self) -> None:
		from aiogram.exceptions import TelegramBadRequest

		channel = make_channel(chat_id=-702, purpose=TelegramChannel.Purpose.STORAGE)
		session = FakeSession()
		session.responders["GetChat"] = lambda method: TelegramBadRequest(
			method=method, message="Bad Request: chat not found"
		)
		bot = make_bot(session)

		result = asyncio.run(test_channel(bot, channel))

		self.assertFalse(result.ok)
		channel.refresh_from_db()
		self.assertFalse(channel.last_check_ok)

	def test_resolve_chat_accepts_username_and_link(self) -> None:
		bot = make_bot(FakeSession())
		chat = asyncio.run(resolve_chat(bot, "@test_channel"))
		self.assertEqual(chat.username, "test_channel")

		chat = asyncio.run(resolve_chat(bot, "https://t.me/test_channel"))
		self.assertEqual(chat.username, "test_channel")

		chat = asyncio.run(resolve_chat(bot, "-1001234567890"))
		self.assertIsNotNone(chat)

	def test_resolve_chat_rejects_garbage(self) -> None:
		bot = make_bot(FakeSession())
		with self.assertRaises(ChatResolutionError):
			asyncio.run(resolve_chat(bot, "!!!not a channel!!!"))


class SettingsChannelBindingTests(TransactionTestCase):
	def test_publish_channel_can_be_selected(self) -> None:
		channel = make_channel(chat_id=-800, purpose=TelegramChannel.Purpose.PUBLIC)
		settings = BotSettings.get_solo()
		settings.publish_channel = channel
		settings.save(update_fields=["publish_channel", "updated_at"])

		self.assertEqual(BotSettings.get_solo().publish_channel_id, channel.pk)
		self.assertEqual([item.pk for item in public_channels_sync()], [channel.pk])

	def test_many_public_channels_are_allowed(self) -> None:
		make_channel(chat_id=-801, purpose=TelegramChannel.Purpose.PUBLIC, title="A")
		make_channel(chat_id=-802, purpose=TelegramChannel.Purpose.PUBLIC, title="B")
		self.assertEqual(len(public_channels_sync()), 2)

	def test_type_channels_can_be_saved_via_update_settings(self) -> None:
		publish = make_channel(chat_id=-803, purpose=TelegramChannel.Purpose.PUBLIC, title="Publish")
		completed = make_channel(chat_id=-804, purpose=TelegramChannel.Purpose.PUBLIC, title="Completed")
		ongoing = make_channel(chat_id=-805, purpose=TelegramChannel.Purpose.PUBLIC, title="Ongoing")
		manga = make_channel(chat_id=-806, purpose=TelegramChannel.Purpose.PUBLIC, title="Manga")
		manga_completed = make_channel(chat_id=-807, purpose=TelegramChannel.Purpose.PUBLIC, title="Manga done")

		settings = update_settings_sync(
			publish_channel=publish,
			completed_channel=completed,
			ongoing_channel=ongoing,
			manga_channel=manga,
			manga_completed_channel=manga_completed,
		)

		self.assertEqual(settings.publish_channel_id, publish.pk)
		self.assertEqual(settings.completed_channel_id, completed.pk)
		self.assertEqual(settings.ongoing_channel_id, ongoing.pk)
		self.assertEqual(settings.manga_channel_id, manga.pk)
		self.assertEqual(settings.manga_completed_channel_id, manga_completed.pk)

		settings = BotSettings.get_solo()
		self.assertEqual(settings.publish_channel_id, publish.pk)
		self.assertEqual(settings.completed_channel_id, completed.pk)
		self.assertEqual(settings.ongoing_channel_id, ongoing.pk)
		self.assertEqual(settings.manga_channel_id, manga.pk)
		self.assertEqual(settings.manga_completed_channel_id, manga_completed.pk)
