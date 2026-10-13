"""``python manage.py runbot`` — start the Telegram bot long-polling worker."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from ...config import ConfigurationError, validate_config
from ...runner import run


class Command(BaseCommand):
	help = "Run the Telegram bot using the Django database for FSM storage."

	def add_arguments(self, parser) -> None:
		parser.add_argument(
			"--check",
			action="store_true",
			help="Validate the configuration (token, ADMIN_IDS) and exit.",
		)

	def handle(self, *args, **options) -> None:
		try:
			config = validate_config(require_token=True)
		except ConfigurationError as exc:
			raise CommandError(f"Invalid bot configuration: {exc}") from exc

		if options.get("check"):
			self.stdout.write(
				self.style.SUCCESS(
					f"Configuration OK · token={config.masked_token} "
					f"admins={sorted(config.admin_ids)} fsm_ttl={config.fsm_ttl}s "
					f"rate={config.broadcast_rate}/s concurrency={config.broadcast_concurrency}"
				)
			)
			return

		self.stdout.write(
			self.style.WARNING("Starting the bot. Press Ctrl+C to stop.")
		)
		run()
