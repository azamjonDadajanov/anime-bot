"""Send subscription expiry reminders to users.

Run from cron once a day, e.g.:

    0 9 * * * cd /app && python manage.py send_subscription_reminders

Users whose plan is about to run out (``--days-before``, default 3) and users
whose plan ran out within the last ``--days-after`` days (default 7) get one
Telegram message each. ``Subscription.reminder_stage`` makes a repeated run a
no-op, so the schedule may be set more often than daily without spamming
anybody — and a run that could not deliver simply tries again next time.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from users.reminders import due_reminders_sync, send_reminder_sync


class Command(BaseCommand):
	help = "Remind users that their subscription is ending or has ended."

	def add_arguments(self, parser):
		parser.add_argument(
			"--limit",
			type=int,
			default=0,
			help="Send at most N reminders in this run (0 = no limit).",
		)
		parser.add_argument(
			"--dry-run",
			action="store_true",
			help="List who would be reminded without sending anything.",
		)

	def handle(self, *args, **options):
		limit = options["limit"] or None
		reminders = due_reminders_sync(limit=limit)

		if not reminders:
			self.stdout.write("No subscription reminders are due.")
			return

		if options["dry_run"]:
			for reminder in reminders:
				self.stdout.write(
					f"[dry-run] {reminder.stage} -> {reminder.telegram_id} "
					f"({reminder.days} kun, {reminder.subscription.expires_at:%Y-%m-%d})"
				)
			self.stdout.write(
				self.style.WARNING(f"{len(reminders)} reminder(s) would be sent.")
			)
			return

		sent = 0
		failed = 0
		for reminder in reminders:
			if send_reminder_sync(reminder):
				sent += 1
			else:
				failed += 1

		summary = f"Reminders: {sent} sent, {failed} failed, {len(reminders)} due."
		self.stdout.write(self.style.SUCCESS(summary) if not failed else self.style.WARNING(summary))
