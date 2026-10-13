"""``python manage.py fsm_cleanup`` — purge expired FSM rows and old logs.

Run this from cron/systemd timers in production so the FSM table (and the log
table) never grow without bound.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import FSMState
from ...services.logs import purge_logs_sync
from ...storage import cleanup_expired_states


class Command(BaseCommand):
	help = "Delete expired FSM state rows and (optionally) old log entries."

	def add_arguments(self, parser) -> None:
		parser.add_argument(
			"--logs-days",
			type=int,
			default=0,
			help="Also delete BotLogEntry rows older than N days (0 disables).",
		)
		parser.add_argument(
			"--dry-run",
			action="store_true",
			help="Report what would be deleted without touching the data.",
		)

	def handle(self, *args, **options) -> None:
		if options["dry_run"]:
			pending = FSMState.objects.filter(
				expires_at__isnull=False, expires_at__lte=timezone.now()
			).count()
			self.stdout.write(f"Dry run: {pending} expired FSM rows would be deleted.")
		else:
			deleted = cleanup_expired_states()
			self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} expired FSM rows."))

		logs_days = int(options.get("logs_days") or 0)
		if logs_days > 0 and not options["dry_run"]:
			removed = purge_logs_sync(days=logs_days)
			self.stdout.write(self.style.SUCCESS(f"Deleted {removed} log entries older than {logs_days} days."))
