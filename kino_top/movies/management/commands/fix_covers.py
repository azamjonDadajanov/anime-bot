"""``python manage.py fix_covers`` — base64 cover payloads become media files.

Covers used to live in the database as base64 text inside the ``cover``
BinaryField: the administrator panel posted base64, the API answered with the
same base64, and the browser rebuilt a ``data:`` URL on every navigation. The
code now expects a real image file under ``MEDIA_ROOT/covers/`` that nginx
serves directly, so every row left behind by that history has to be rewritten:

* a stored file whose bytes are still base64 text is decoded and replaced with
  the image it stands for (the URL changes, so the browser drops whatever it
  cached);
* a row whose file is gone — or that has no file at all — is restored from the
  legacy ``cover_blob`` column while the migration has not dropped it yet;
* a ``cover`` column that itself holds base64 (an unmigrated database) is
  detected and reported instead of written anywhere: the schema has to be
  migrated first, which is what turns those payloads into files;
* rows that already hold a real image are read for a few bytes only, so a full
  run stays cheap.

The command is idempotent and never raises on bad data: every row is handled
on its own, failures are counted and reported, and the exit status stays 0
unless ``--strict`` is given. The web entrypoint runs it after ``migrate`` on
each deploy, which is why production needs no manual repair.

Examples::

    python manage.py fix_covers
    python manage.py fix_covers --dry-run
    python manage.py fix_covers --slug one-piece --strict
"""

from __future__ import annotations

from typing import Optional

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection, transaction

from movies.covers import decode_base64, sniff_extension
from movies.models import MediaTitle

# mime type per file extension, used to keep `cover_content_type` honest.
MIME_BY_EXTENSION = {
	"jpg": "image/jpeg",
	"jpeg": "image/jpeg",
	"png": "image/png",
	"webp": "image/webp",
	"gif": "image/gif",
}


def looks_like_image(data: bytes) -> bool:
	"""True when *data* starts with a magic number this project stores."""
	return (
		data[:8] == b"\x89PNG\r\n\x1a\n"
		or data[:3] == b"\xff\xd8\xff"
		or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")
		or data[:6] in (b"GIF87a", b"GIF89a")
	)


def as_bytes(value) -> Optional[bytes]:
	"""Whatever the database hands back for a blob column, as ``bytes``."""
	if value is None:
		return None
	if isinstance(value, (bytes, bytearray)):
		return bytes(value)
	if isinstance(value, memoryview):
		return value.tobytes()
	if isinstance(value, str):
		# latin-1 maps every codepoint onto a single byte, so base64 text
		# (pure ASCII) and hand-copied binary both survive the trip.
		return value.encode("latin-1", "ignore")
	return None


def payload_to_image(data: Optional[bytes]) -> Optional[bytes]:
	"""Image bytes for *data*, decoding base64 text when that is what it is.

	Already-decoded image bytes come back untouched; anything that is neither
	an image nor base64 gives ``None``.
	"""
	if not data:
		return None
	if looks_like_image(data):
		return data
	try:
		text = data.decode("ascii")
	except UnicodeDecodeError:
		return None
	try:
		decoded = decode_base64(text)
	except ValueError:
		return None
	return decoded if looks_like_image(decoded) else None


def looks_like_payload(name) -> bool:
	"""True when a ``cover`` value is payload text instead of a file path.

	Every stored cover is born under ``covers/`` (the field's ``upload_to``),
	so anything long that is not such a path is the payload itself.
	"""
	if not isinstance(name, str) or len(name) < 120:
		return False
	return not name.startswith("covers/")


class Command(BaseCommand):
	help = "Base64 muqova payloadlarini MEDIA_ROOT/covers/ dagi fayllarga aylantiradi."

	def add_arguments(self, parser) -> None:
		parser.add_argument("--dry-run", action="store_true", help="Fayllarni o'zgartirmaydi, faqat hisobot beradi.")
		parser.add_argument("--slug", type=str, default=None, help="Faqat bitta MediaTitle slug bo'yicha.")
		parser.add_argument("--limit", type=int, default=None, help="Tekshiriladigan qatorlar sonini cheklash.")
		parser.add_argument(
			"--strict",
			action="store_true",
			help="Tuzatilmagan qatorlar qolgan bo'lsa xato kod bilan chiqadi (deploy uchun emas).",
		)

	def handle(self, *args, **options) -> None:
		table = MediaTitle._meta.db_table
		try:
			state, legacy_column = self._schema_state(table)
		except DatabaseError as exc:
			self.stdout.write(self.style.WARNING(f"Jadval o'qilmadi ({exc}); avval `manage.py migrate` bajaring."))
			return

		if state == "pre-migrate":
			self.stdout.write(
				self.style.WARNING(
					"cover hali BinaryField (migratsiya qo'llanmagan): avval `python manage.py migrate` bajaring."
				)
			)
			return

		titles = MediaTitle.objects.all().order_by("pk")
		if options["slug"]:
			titles = titles.filter(slug=options["slug"])
			if not titles.exists():
				raise CommandError(f"MediaTitle slug={options['slug']!r} topilmadi.")
		if options["limit"]:
			rows = titles[: options["limit"]]
		else:
			rows = titles.iterator(chunk_size=50)

		dry_run = bool(options["dry_run"])
		stats = {"checked": 0, "ok": 0, "empty": 0, "fixed": 0, "missing": 0, "failed": 0}

		for title in rows:
			stats["checked"] += 1
			try:
				outcome, detail = self._fix_title(title, legacy_column=legacy_column, dry_run=dry_run)
			except Exception as exc:  # noqa: BLE001 - one bad row must not stop the repair
				stats["failed"] += 1
				self.stdout.write(self.style.WARNING(f"! {title.slug or title.pk}: {exc}"))
				continue
			stats[outcome] += 1
			if outcome == "fixed":
				prefix = "~" if dry_run else "+"
				self.stdout.write(self.style.SUCCESS(f"{prefix} {title.slug or title.pk}: {detail}"))
			elif outcome in ("missing", "failed"):
				self.stdout.write(self.style.WARNING(f"! {title.slug or title.pk}: {detail}"))

		summary = (
			f"checked={stats['checked']} ok={stats['ok']} fixed={stats['fixed']} "
			f"empty={stats['empty']} missing={stats['missing']} failed={stats['failed']}"
		)
		self.stdout.write(f"{'[dry-run] ' if dry_run else ''}{summary}")

		if options["strict"] and (stats["missing"] or stats["failed"]):
			raise CommandError(summary)

		if stats["missing"] or stats["failed"]:
			self.stdout.write(
				self.style.WARNING("Qolgan qatorlarni `--slug` bilan alohida ko'ring yoki muqovani qayta yuklang.")
			)
		else:
			self.stdout.write(self.style.SUCCESS("Muqovalar tayyor."))

	def _schema_state(self, table: str):
		"""``("pre-migrate"|"legacy"|"modern", legacy_column_exists)``.

		An unmigrated database still keeps the payload in its own ``cover``
		column (bytea/BLOB), which the ImageField code cannot address, so that
		state is recognised from the column type rather than from the model:
		postgres reports bytea as OID 17, sqlite reports the declared ``blob``.
		"""
		if self._column_exists(table, "cover_blob"):
			return "legacy", True
		if self._cover_column_is_binary(table):
			return "pre-migrate", False
		return "modern", False

	def _column_exists(self, table: str, column: str) -> bool:
		return self._column_info(table, column) is not None

	def _column_info(self, table: str, column: str):
		with connection.cursor() as cursor:
			return next(
				(
					info
					for info in connection.introspection.get_table_description(cursor, table)
					if info.name == column
				),
				None,
			)

	def _cover_column_is_binary(self, table: str) -> bool:
		info = self._column_info(table, "cover")
		if info is None:
			return False
		code = getattr(info, "type_code", None)
		if isinstance(code, int):
			return code == 17  # postgresql bytea
		return "BLOB" in str(code).upper()

	def _legacy_blob(self, pk):
		quoted = connection.ops.quote_name(MediaTitle._meta.db_table)
		with connection.cursor() as cursor:
			cursor.execute(f'SELECT "cover_blob" FROM {quoted} WHERE "id" = %s', [pk])
			row = cursor.fetchone()
		return row[0] if row else None

	def _read_cover(self, cover) -> Optional[bytes]:
		"""Stored cover bytes, or ``None`` when the file is absent or empty.

		The first kilobyte decides: an image announces itself within the first
		12 bytes, so a healthy row costs one small read instead of the whole
		poster, while base64 text (never an image) is read in full.
		"""
		try:
			cover.open("rb")
			try:
				head = cover.read(1024)
				if looks_like_image(head):
					return head
				if not head:
					return None
				cover.seek(0)
				return cover.read()
			finally:
				cover.close()
		except (OSError, ValueError):
			return None

	def _fix_title(self, title, *, legacy_column: bool, dry_run: bool):
		"""Repair one row: ``(outcome, detail)``.

		Outcomes: ``ok`` (already an image), ``fixed`` (payload rewritten),
		``empty`` (no cover anywhere), ``missing`` (file gone for good) and
		``failed`` (bytes that are neither image nor base64).
		"""
		cover = title.cover
		name = cover.name if cover else None

		if not name:
			payload = payload_to_image(as_bytes(self._legacy_blob(title.pk))) if legacy_column else None
			if payload is None:
				return "empty", ""
			return self._commit(title, payload, source="cover_blob", dry_run=dry_run)

		data = self._read_cover(cover)
		if data and looks_like_image(data):
			extension = sniff_extension(data)
			if self._content_type_issue(title, data):
				if not dry_run:
					title.cover_content_type = MIME_BY_EXTENSION[extension]
					title.save(update_fields=["cover_content_type"])
				return "fixed", f"cover_content_type -> {MIME_BY_EXTENSION[extension]}"
			return "ok", ""

		payload = payload_to_image(data)
		source = "fayl"
		if payload is None and looks_like_payload(name):
			payload = payload_to_image(as_bytes(name))
			source = "cover"
		if payload is None and legacy_column:
			payload = payload_to_image(as_bytes(self._legacy_blob(title.pk)))
			source = "cover_blob"
		if payload is None:
			if not data:
				return "missing", "fayl yo'q (cover_blob ham topilmadi)"
			return "failed", "rasm ham, base64 ham emas"

		return self._commit(title, payload, source=source, dry_run=dry_run)

	def _commit(self, title, payload: bytes, *, source: str, dry_run: bool):
		if dry_run:
			return "fixed", f"{source} -> {self._would_name(title, payload)}"
		return "fixed", f"{source} -> {self._store(title, payload)}"

	def _content_type_issue(self, title, data: bytes) -> bool:
		expected = MIME_BY_EXTENSION.get(sniff_extension(data), "")
		current = title.cover_content_type or ""
		return bool(expected and current and current != expected)

	def _would_name(self, title, payload: bytes) -> str:
		"""Name the file would get, without writing anything."""
		return title.cover.field.generate_filename(title, f"{title.slug or title.pk}.{sniff_extension(payload)}")

	def _store(self, title, payload: bytes) -> str:
		"""Write *payload* as the cover, keep the row in sync, drop the old file."""
		old_name = title.cover.name if title.cover else None
		extension = sniff_extension(payload)
		updates = ["cover"]
		expected = MIME_BY_EXTENSION.get(extension, "")
		if expected and title.cover_content_type and title.cover_content_type != expected:
			title.cover_content_type = expected
			updates.append("cover_content_type")

		with transaction.atomic():
			# The storage de-duplicates the name, so the new URL differs from
			# the broken one and the browser re-fetches instead of using a
			# cached copy of the payload that was never an image.
			title.cover.save(f"{title.slug or title.pk}.{extension}", ContentFile(payload), save=False)
			title.save(update_fields=updates)

		if old_name and isinstance(old_name, str) and old_name != title.cover.name:
			try:
				title.cover.storage.delete(old_name)
			except (OSError, ValueError):
				pass  # an orphaned file never blocks the repair
		return title.cover.name
