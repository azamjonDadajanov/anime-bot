"""Server-side rendering of chapter PDFs into JPEG page images.

The reader never receives the PDF bytes — only pre-rendered page images — so
a visitor has no file to download. Two directories are used, both below
``MEDIA_ROOT``:

``manga/render/<part_id>/<signature>/``
    The source PDF (Telegram copies are cached on disk here), the page count
    and every intermediate artefact. ``<signature>`` describes the source PDF
    (local upload size/mtime or the Telegram ``file_id``), so a changed source
    simply points at a new directory and stale pages can never be served.
    nginx refuses this whole subtree.

``manga/pages/<part_id>/page_<n>.jpg``
    The published pages, with a ``version.txt`` holding the current signature
    digest. This is what the browser requests: nginx serves it straight from
    the shared volume with an immutable cache header, so **Django never
    streams an image byte in production**. The version travels in the URL
    (``?v=<digest>``), which means a re-rendered chapter lands at a new URL
    instead of fighting a stale browser cache.

pypdfium2 is driven behind a process-wide lock because PDFium is not safe to
call from several threads at once; a page render takes milliseconds.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import threading
import uuid
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

from django.conf import settings

try:
	import pypdfium2 as pdfium
except ImportError:  # pragma: no cover - reported through describe()
	pdfium = None

from .models import MediaPart, TelegramMedia
from .telegram_files import TelegramFileError, fetch_file_bytes, user_error_message

logger = logging.getLogger(__name__)

# pypdfium2 treats scale=1.0 as 72 DPI, so 2.0 renders at 144 DPI: crisp on
# phones without producing huge JPEGs.
RENDER_SCALE = 2.0
RENDER_QUALITY = 82


class PdfUnavailable(Exception):
	"""The chapter PDF is missing or cannot be opened for rendering."""

	def __init__(self, message: str, status: int = 404):
		super().__init__(message)
		self.status = status


_RENDER_LOCK = threading.Lock()


def _part_root(part: MediaPart) -> Path:
	return Path(settings.MEDIA_ROOT) / "manga" / "render" / str(part.pk)


def _public_root(part: MediaPart) -> Path:
	"""Directory nginx serves as ``/media/manga/pages/<part_id>/``."""
	return Path(settings.MEDIA_ROOT) / "manga" / "pages" / str(part.pk)


def _digest(signature: str) -> str:
	return hashlib.sha1(signature.encode("utf-8")).hexdigest()[:16]


def telegram_document(part: MediaPart) -> Optional[TelegramMedia]:
	"""The stored Telegram PDF copy for ``part`` (``None`` when absent)."""
	return next(
		(
			item
			for item in part.telegram_media.all()
			if item.media_type == TelegramMedia.MediaType.DOCUMENT
		),
		None,
	)


def _local_pdf_path(part: MediaPart) -> Optional[Path]:
	if not part.pdf:
		return None
	try:
		if not part.pdf.storage.exists(part.pdf.name):
			return None
		return Path(part.pdf.path)
	except NotImplementedError:  # pragma: no cover - non-filesystem storage
		return None


def _source_signature(part: MediaPart) -> str:
	"""Describe the current PDF so stale renders are dropped automatically."""
	path = _local_pdf_path(part)
	if path is not None:
		stat = path.stat()
		return f"local:{stat.st_size}:{stat.st_mtime_ns}"
	document = telegram_document(part)
	if document is None:
		raise PdfUnavailable("Bu qism uchun PDF topilmadi.")
	return f"tg:{document.file_id}"


def _atomic_tmp(target: Path) -> Path:
	"""A unique scratch path: several gunicorn workers may render at once."""
	return target.parent / f"{target.name}.{uuid.uuid4().hex}.tmp"


def _sync_dir(part: MediaPart) -> Tuple[Path, str]:
	"""Return the cache directory for the *current* PDF and its signature."""
	signature = _source_signature(part)
	root = _part_root(part)
	directory = root / _digest(signature)
	directory.mkdir(parents=True, exist_ok=True)
	for stale in directory.glob("*.tmp"):
		stale.unlink(missing_ok=True)
	for entry in root.iterdir():
		if entry == directory:
			continue
		# Stale renders from a previous PDF: best-effort (a page may be
		# locked by an in-flight download on Windows); correctness holds
		# because every lookup goes through the signature directory.
		if entry.is_dir():
			shutil.rmtree(entry, ignore_errors=True)
		else:
			entry.unlink(missing_ok=True)
	return directory, signature


def _source_file(part: MediaPart, directory: Path, signature: str) -> Path:
	"""Local path of the PDF to render (Telegram copies are cached on disk)."""
	if signature.startswith("local:"):
		path = _local_pdf_path(part)
		if path is None:
			raise PdfUnavailable("Bu qism uchun PDF topilmadi.")
		return path

	cached = directory / "source.pdf"
	if not cached.exists():
		document = telegram_document(part)
		if document is None:
			raise PdfUnavailable("Bu qism uchun PDF topilmadi.")
		try:
			content, _ = fetch_file_bytes(document.file_id)
		except TelegramFileError as exc:
			raise PdfUnavailable(user_error_message(exc), status=502) from exc
		tmp = _atomic_tmp(cached)
		tmp.write_bytes(content)
		tmp.replace(cached)
	return cached


def _open_document(source: Path):
	if pdfium is None:
		raise PdfUnavailable("Serverda PDF renderer o'rnatilmagan (pypdfium2).", status=500)
	try:
		return pdfium.PdfDocument(str(source))
	except Exception as exc:  # noqa: BLE001 - pypdfium2 raises its own types
		logger.warning("Could not open PDF %s: %s", source, exc)
		raise PdfUnavailable("PDF faylini o'qib bo'lmadi.", status=422) from exc


def _page_count(directory: Path, source: Path) -> int:
	count_file = directory / "count.txt"
	if count_file.exists():
		try:
			return int(count_file.read_text(encoding="utf-8"))
		except (ValueError, OSError):
			count_file.unlink(missing_ok=True)
	document = _open_document(source)
	try:
		count = len(document)
	finally:
		document.close()
	count_tmp = _atomic_tmp(count_file)
	count_tmp.write_text(str(count), encoding="utf-8")
	count_tmp.replace(count_file)
	return count


def _etag(signature: str) -> str:
	return f'"{_digest(signature)}"'


def _sync_public(part: MediaPart, digest: str) -> Path:
	"""Published page directory for the current PDF (served by nginx)."""
	root = _public_root(part)
	root.mkdir(parents=True, exist_ok=True)
	for stale in root.glob("*.tmp"):
		stale.unlink(missing_ok=True)
	marker = root / "version.txt"
	try:
		current = marker.read_text(encoding="utf-8").strip() if marker.exists() else ""
	except OSError:  # pragma: no cover - unreadable marker
		current = ""
	if current != digest:
		# The source PDF changed: drop the old pages so a reader can never
		# mix two versions of one chapter.
		for page in root.glob("page_*.jpg"):
			page.unlink(missing_ok=True)
		tmp = _atomic_tmp(marker)
		tmp.write_text(digest, encoding="utf-8")
		tmp.replace(marker)
	return root


def public_base_url(part: MediaPart) -> str:
	"""URL prefix of the published pages: nginx, never Django, serves them."""
	return f"{settings.MEDIA_URL}manga/pages/{part.pk}/"


def page_url(part: MediaPart, number: int, digest: str) -> str:
	"""Cache-busted URL of one published page (``?v=`` changes on re-render)."""
	return f"{public_base_url(part)}page_{number}.jpg?v={digest}"


def _result(signature: str, count: int) -> Dict[str, Union[bool, int, str]]:
	return {
		"available": True,
		"count": count,
		"etag": _etag(signature),
		"version": _digest(signature),
	}


def describe(part: MediaPart) -> Dict[str, Union[bool, int, str]]:
	"""Availability, page count and cache validators for the reader."""
	try:
		with _RENDER_LOCK:
			directory, signature = _sync_dir(part)
			source = _source_file(part, directory, signature)
			count = _page_count(directory, source)
	except PdfUnavailable as exc:
		return {"available": False, "reason": str(exc)}
	if count < 1:
		return {"available": False, "reason": "PDF hujjatida sahifalar yo'q."}
	return _result(signature, count)


def ensure_pages(part: MediaPart) -> Dict[str, Union[bool, int, str]]:
	"""Describe *and* render every page into the nginx-served directory.

	The first request for a chapter does the rendering (milliseconds per page,
	once per PDF); every later request — the browser's included — is answered
	by nginx straight from the shared media volume.
	"""
	try:
		with _RENDER_LOCK:
			directory, signature = _sync_dir(part)
			source = _source_file(part, directory, signature)
			count = _page_count(directory, source)
			if count < 1:
				return {"available": False, "reason": "PDF hujjatida sahifalar yo'q."}
			public = _sync_public(part, _digest(signature))
			for number in range(1, count + 1):
				target = public / f"page_{number}.jpg"
				if target.exists():
					continue
				try:
					_render_into(source, number, target)
				except PdfUnavailable as exc:  # pragma: no cover - single bad page
					logger.warning(
						"Could not pre-render page %s of part %s: %s", number, part.pk, exc
					)
	except PdfUnavailable as exc:
		return {"available": False, "reason": str(exc)}
	return _result(signature, count)


def render_page(part: MediaPart, number: int) -> Path:
	"""JPEG path for the 1-based ``number``; rendered on first request.

	This is the API fallback used by a client that asks Django directly (and
	by a browser that hit a page nginx has not got yet); the file lands in the
	same public directory nginx serves, so the retry is answered by nginx.
	"""
	with _RENDER_LOCK:
		directory, signature = _sync_dir(part)
		source = _source_file(part, directory, signature)
		count = _page_count(directory, source)
		if not 1 <= number <= count:
			raise PdfUnavailable("Sahifa topilmadi.", status=404)
		public = _sync_public(part, _digest(signature))
		target = public / f"page_{number}.jpg"
		if target.exists():
			return target
		_render_into(source, number, target)
		return target


def _render_into(source: Path, number: int, target: Path) -> None:
	tmp = _atomic_tmp(target)
	document = _open_document(source)
	try:
		page = document[number - 1]
		bitmap = page.render(scale=RENDER_SCALE)
		try:
			bitmap.to_pil().save(tmp, "JPEG", quality=RENDER_QUALITY)
		finally:
			bitmap.close()
	except Exception as exc:  # noqa: BLE001 - pypdfium2 raises its own types
		tmp.unlink(missing_ok=True)
		logger.warning("Could not render page %s of %s: %s", number, source, exc)
		raise PdfUnavailable("PDF sahifasini tayyorlab bo'lmadi.", status=422) from exc
	finally:
		document.close()
	tmp.replace(target)


def invalidate(part: MediaPart) -> None:
	"""Drop every cached render for ``part`` (called when the PDF changes)."""
	with _RENDER_LOCK:
		shutil.rmtree(_part_root(part), ignore_errors=True)
		shutil.rmtree(_public_root(part), ignore_errors=True)
