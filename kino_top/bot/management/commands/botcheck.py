"""``python manage.py botcheck`` — validate configuration and channel access."""

from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from django.core.management.base import BaseCommand, CommandError

from ...config import ConfigurationError, validate_config
from ...services.channels import test_channels


class Command(BaseCommand):
	help = "Validate the bot configuration and test every configured channel."

	def add_arguments(self, parser) -> None:
		parser.add_argument(
			"--channels",
			action="store_true",
			help="Contact Telegram and check bot permissions for every channel.",
		)

	def handle(self, *args, **options) -> None:
		try:
			config = validate_config(require_token=bool(options.get("channels")))
		except ConfigurationError as exc:
			raise CommandError(f"Invalid bot configuration: {exc}") from exc

		self.stdout.write(
			f"token={config.masked_token} admins={sorted(config.admin_ids)} "
			f"require_subscription={config.require_subscription} "
			f"auto_publish={config.auto_publish} fsm_ttl={config.fsm_ttl}s"
		)

		if not options.get("channels"):
			self.stdout.write(self.style.SUCCESS("Configuration is valid."))
			return
		if not config.token:
			raise CommandError("--channels requires BOT_TOKEN to be configured.")

		asyncio.run(self._check_channels(config))

	async def _check_channels(self, config) -> None:
		bot = Bot(token=config.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
		try:
			results = await test_channels(bot)
			if not results:
				self.stdout.write(self.style.WARNING("No channels configured."))
				return
			problems = 0
			for result in results:
				mark = "OK " if result.ok else "ERR"
				if not result.ok:
					problems += 1
				self.stdout.write(
					f"[{mark}] {result.channel.title} ({result.channel.purpose}) "
					f"chat_id={result.channel.chat_id} post={result.can_post} "
					f"check={result.can_check} :: {result.message or result.error}"
				)
			if problems:
				self.stdout.write(self.style.ERROR(f"{problems} channel(s) need attention."))
			else:
				self.stdout.write(self.style.SUCCESS("All channels are healthy."))
		finally:
			await bot.session.close()
