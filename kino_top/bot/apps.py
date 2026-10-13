from django.apps import AppConfig


class BotConfig(AppConfig):
	name = "bot"
	verbose_name = "Telegram bot"
	default_auto_field = "django.db.models.BigAutoField"

	def ready(self):
		# Importing the module registers the ``bot`` logger handler so that bot
		# errors are persisted into ``BotLogEntry`` and can be inspected from the
		# admin panel without reading the server log files.
		from . import bot_logging  # noqa: F401
