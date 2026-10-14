"""Award the monthly prize to the most active non-subscriber player.

Run from cron at the start of each month, e.g.:

    0 6 1 * * cd /app && python manage.py award_game_monthly_prize

By default it awards the *previous* calendar month. Pass ``--year`` and
``--month`` explicitly to re-run for a specific month (idempotent — the
command will not create a second prize for the same month).
"""

from __future__ import annotations

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from games.services import award_monthly_prize_sync


class Command(BaseCommand):
	help = "Award the monthly game prize (1 month free) to the most active non-subscriber."

	def add_arguments(self, parser):
		today = date.today()
		default_month = today.month - 1 or 12
		default_year = today.year if today.month > 1 else today.year - 1
		parser.add_argument("--year", type=int, default=default_year)
		parser.add_argument("--month", type=int, default=default_month)

	def handle(self, *args, **options):
		year = options["year"]
		month = options["month"]
		if not 1 <= month <= 12:
			raise CommandError("--month must be 1..12")

		prize = award_monthly_prize_sync(year, month)
		if prize is None:
			self.stdout.write(
				self.style.WARNING(f"No eligible winner for {year}-{month:02d} (or already awarded).")
			)
			return

		self.stdout.write(
			self.style.SUCCESS(
				f"Awarded {prize.days} days to user {prize.user_id} "
				f"({prize.points} points) for {year}-{month:02d}."
			)
		)
