"""Build and run the aiogram bot on top of the Django project."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

# Runner alohida fayl sifatida ishga tushirilsa ham bot paketini topadi.
if __package__ in {None, ""}:
	project_root = Path(__file__).resolve().parent.parent
	sys.path.insert(0, str(project_root))
	__package__ = "bot"
	os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kino_top.settings")
	import django

	django.setup()

from .bot_logging import install_db_log_handler
from .config import BotConfig, validate_config
from .handlers import build_router
from .middlewares import (
	ContextMiddleware,
	ErrorHandlingMiddleware,
	SubscriptionGateMiddleware,
	ThrottlingMiddleware,
)
from .storage import DjangoEventIsolation, DjangoStorage

logger = logging.getLogger("bot.runner")

BASE_COMMANDS = (
	BotCommand(command="start", description="🏠 Boshlash / Asosiy menyu"),
	BotCommand(command="help", description="ℹ️ Yordam"),
)
ADMIN_COMMANDS = BASE_COMMANDS + (
	BotCommand(command="admin", description="🛠 Administrator paneli"),
)


def build_dispatcher(config: Optional[BotConfig] = None) -> Dispatcher:
	"""Create a dispatcher with Django FSM storage and shared middlewares."""
	storage = DjangoStorage()
	isolation = DjangoEventIsolation()
	dispatcher = Dispatcher(storage=storage, events_isolation=isolation)

	# Outer middlewares run for every update, in registration order.
	dispatcher.update.outer_middleware(ErrorHandlingMiddleware())
	dispatcher.update.outer_middleware(ThrottlingMiddleware())
	dispatcher.update.outer_middleware(ContextMiddleware())
	# The subscription gate must run after the context so it can read the
	# profile and settings, and before any handler so nothing can bypass it.
	dispatcher.update.outer_middleware(SubscriptionGateMiddleware())

	dispatcher.include_router(build_router())
	return dispatcher


def build_bot(config: BotConfig) -> Bot:
	return Bot(
		token=config.token,
		default=DefaultBotProperties(parse_mode=ParseMode.HTML),
	)


async def set_commands(bot: Bot, admin_ids) -> None:
	"""Publish the command list; administrators additionally see ``/admin``."""
	try:
		await bot.set_my_commands(list(BASE_COMMANDS), scope=BotCommandScopeDefault())
	except TelegramAPIError as exc:  # pragma: no cover - network failure
		logger.warning("Could not publish the default command list: %s", exc)
		return
	for admin_id in admin_ids:
		try:
			await bot.set_my_commands(
				list(ADMIN_COMMANDS), scope=BotCommandScopeChat(chat_id=admin_id)
			)
		except TelegramAPIError as exc:  # pragma: no cover - admin never started the bot
			logger.debug("Could not publish admin commands for %s: %s", admin_id, exc)


async def run_forever(config: Optional[BotConfig] = None) -> None:
	"""Start long polling and shut down cleanly on cancellation."""
	config = validate_config(config)
	logging.basicConfig(level=getattr(logging, config.log_level, logging.INFO))
	install_db_log_handler("bot")

	bot = build_bot(config)
	dispatcher = build_dispatcher(config)
	logger.info("Starting polling with token %s and %s administrators.", config.masked_token, len(config.admin_ids))
	try:
		await set_commands(bot, config.admin_ids)
		await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
	finally:
		try:
			# ``Dispatcher.fsm`` holds both the storage and the event isolation.
			await dispatcher.fsm.storage.close()
			isolation = getattr(dispatcher.fsm, "events_isolation", None)
			if isolation is not None:
				await isolation.close()
		finally:
			await bot.session.close()
		logger.info("Bot stopped.")


def run() -> None:
	"""Blocking entry point used by the ``runbot`` management command."""
	try:
		asyncio.run(run_forever())
	except KeyboardInterrupt:  # pragma: no cover - developer convenience
		logger.info("Polling interrupted by the operator.")


if __name__ == "__main__":
	run()
