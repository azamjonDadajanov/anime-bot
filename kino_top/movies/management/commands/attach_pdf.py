"""``python manage.py attach_pdf`` — store a local PDF on a manga part.

The Telegram Bot API can only download files up to 20 MB, so larger chapters
must live on the server. Use this command to attach a PDF file to a
``MediaPart`` so the website reader serves it directly.

Examples::

    python manage.py attach_pdf --part 12 --file C:\\books\\chapter.pdf
    python manage.py attach_pdf --title naruto-manga --number 3 --file chapter.pdf
"""

from __future__ import annotations

import os
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from movies.models import MediaPart, MediaTitle


class Command(BaseCommand):
	help = "Attach a local PDF file to a manga part."

	def add_arguments(self, parser) -> None:
		parser.add_argument("--part", type=int, default=None, help="MediaPart id.")
		parser.add_argument("--title", type=str, default=None, help="MediaTitle slug.")
		parser.add_argument("--number", type=int, default=None, help="Part number (with --title).")
		parser.add_argument("--season", type=int, default=None, help="Optional season number (with --title).")
		parser.add_argument("--file", type=str, required=True, help="Path to the local PDF file.")

	def handle(self, *args, **options) -> None:
		source = Path(options["file"])
		if not source.is_file():
			raise CommandError(f"Fayl topilmadi: {source}")

		part = self._resolve_part(options)
		filename = f"{part.content.slug}-{part.number}.pdf"
		with source.open("rb") as handle:
			part.pdf.save(filename, File(handle), save=True)

		self.stdout.write(
			self.style.SUCCESS(
				f"'{filename}' -> {part.content.title} ({part.number}-qism, id={part.id}) "
				f"({os.path.getsize(source)} bytes)"
			)
		)

	def _resolve_part(self, options) -> MediaPart:
		if options["part"]:
			part = MediaPart.objects.filter(pk=options["part"]).select_related("content").first()
			if part is None:
				raise CommandError(f"MediaPart id={options['part']} topilmadi.")
			return part

		slug = options["title"]
		number = options["number"]
		if not slug or number is None:
			raise CommandError("--part yoki (--title va --number) berilishi shart.")
		title = MediaTitle.objects.filter(slug=slug).first()
		if title is None:
			raise CommandError(f"MediaTitle slug={slug!r} topilmadi.")
		queryset = MediaPart.objects.filter(content=title, number=number)
		if options["season"] is not None:
			queryset = queryset.filter(season_number=options["season"])
		part = queryset.first()
		if part is None:
			raise CommandError(f"{slug} uchun {number}-qism topilmadi.")
		return part
