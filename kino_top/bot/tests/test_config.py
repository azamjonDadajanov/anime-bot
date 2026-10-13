"""Configuration parsing and validation tests."""

from __future__ import annotations

from bot.config import (
	ConfigurationError,
	parse_admin_ids,
	validate_config,
)
from django.test import TestCase

from .helpers import bot_env


class AdminIdParsingTests(TestCase):
	def test_parses_comma_and_space_separated_ids(self) -> None:
		self.assertEqual(parse_admin_ids("1,2 3"), frozenset({1, 2, 3}))
		self.assertEqual(parse_admin_ids("10,20"), frozenset({10, 20}))

	def test_accepts_an_iterable(self) -> None:
		self.assertEqual(parse_admin_ids([5, "6"]), frozenset({5, 6}))

	def test_empty_values_yield_no_admins(self) -> None:
		self.assertEqual(parse_admin_ids(""), frozenset())
		self.assertEqual(parse_admin_ids(None), frozenset())

	def test_non_numeric_values_are_rejected(self) -> None:
		with self.assertRaises(ConfigurationError):
			parse_admin_ids("123,abc")

	def test_non_positive_values_are_rejected(self) -> None:
		with self.assertRaises(ConfigurationError):
			parse_admin_ids("0")
		with self.assertRaises(ConfigurationError):
			parse_admin_ids("-5")


class ValidationTests(TestCase):
	def test_missing_token_is_rejected(self) -> None:
		with bot_env(BOT_TOKEN="", TELEGRAM_BOT_TOKEN="", ADMIN_IDS="1"):
			with self.assertRaises(ConfigurationError):
				validate_config()

	def test_malformed_token_is_rejected(self) -> None:
		with bot_env(BOT_TOKEN="not-a-token", ADMIN_IDS="1"):
			with self.assertRaises(ConfigurationError):
				validate_config()

	def test_missing_admin_ids_is_rejected(self) -> None:
		with bot_env(BOT_TOKEN="123:abc", ADMIN_IDS=""):
			with self.assertRaises(ConfigurationError):
				validate_config()

	def test_valid_configuration_passes_and_masks_the_token(self) -> None:
		with bot_env(BOT_TOKEN="123456:secret-value-here", ADMIN_IDS="42"):
			config = validate_config()
			self.assertEqual(config.admin_ids, frozenset({42}))
			self.assertTrue(config.is_admin(42))
			self.assertFalse(config.is_admin(43))
			self.assertFalse(config.is_admin(None))
			self.assertNotIn("secret-value-here", config.masked_token)

	def test_require_token_can_be_relaxed_for_read_only_commands(self) -> None:
		with bot_env(BOT_TOKEN="", TELEGRAM_BOT_TOKEN="", ADMIN_IDS="7"):
			config = validate_config(require_token=False)
			self.assertEqual(config.token, "")
			self.assertEqual(config.admin_ids, frozenset({7}))

	def test_out_of_range_broadcast_rate_is_rejected(self) -> None:
		with bot_env(BOT_TOKEN="123:abc", ADMIN_IDS="1", BOT_BROADCAST_RATE="999"):
			with self.assertRaises(ConfigurationError):
				validate_config()

	def test_invalid_boolean_is_rejected(self) -> None:
		with bot_env(BOT_TOKEN="123:abc", ADMIN_IDS="1", BOT_REQUIRE_SUBSCRIPTION="maybe"):
			with self.assertRaises(ConfigurationError):
				validate_config()


class PageSizeTests(TestCase):
	def test_default_page_size(self) -> None:
		from bot.config import page_size

		with bot_env(BOT_PAGE_SIZE="5"):
			self.assertEqual(page_size(), 5)

	def test_page_size_is_clamped_and_falls_back(self) -> None:
		from bot.config import DEFAULT_PAGE_SIZE, page_size

		with bot_env(BOT_PAGE_SIZE="1000"):
			self.assertEqual(page_size(), 50)
		with bot_env(BOT_PAGE_SIZE="not-a-number"):
			self.assertEqual(page_size(), DEFAULT_PAGE_SIZE)
