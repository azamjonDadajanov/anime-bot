"""Cover images as media files instead of base64 blobs in the database.

Covers used to live in ``MediaTitle.cover`` as raw bytes, so every catalogue
response inlined the whole poster as base64: the browser re-downloaded it
inside the JSON payload on each navigation and nginx could not cache the image
at all. They are now written to ``MEDIA_ROOT/covers/`` and referenced by URL,
which means nginx serves them straight from the shared volume with long-lived
cache headers and Django never streams image bytes.

This module holds the small helpers shared by the API serializer, the bot
service layer and the import command.
"""

from __future__ import annotations

import base64
import binascii
from typing import Optional, Union

from django.core.files.base import ContentFile

UnionBytes = Union[bytes, bytearray, memoryview]


def sniff_extension(data: bytes) -> str:
	"""File extension guessed from the image magic bytes."""
	if data[:8] == b"\x89PNG\r\n\x1a\n":
		return "png"
	if data[:3] == b"\xff\xd8\xff":
		return "jpg"
	if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
		return "webp"
	if data[:6] in (b"GIF87a", b"GIF89a"):
		return "gif"
	return "jpg"


def content_file(data: Optional[UnionBytes], name: str = "cover") -> Optional[ContentFile]:
	"""Wrap raw image bytes in a ContentFile a FileField can store."""
	if not data:
		return None
	blob = bytes(data)
	return ContentFile(blob, name=f"{name}.{sniff_extension(blob)}")


def decode_base64(raw: str) -> bytes:
	"""Decode a base64 image payload, with or without a ``data:`` prefix."""
	payload = raw.strip()
	if payload.startswith("data:"):
		payload = payload.split(",", 1)[1] if "," in payload else ""
	payload = "".join(payload.split())
	payload += "=" * (-len(payload) % 4)
	try:
		return base64.b64decode(payload, validate=True)
	except (binascii.Error, ValueError) as exc:
		raise ValueError("Rasm base64 ko'rinishida yuborilmagan.") from exc


def cover_bytes(title) -> Optional[bytes]:
	"""Stored cover of ``title`` read from disk (``None`` when absent)."""
	cover = getattr(title, "cover", None)
	if not cover:
		return None
	try:
		cover.open("rb")
		try:
			return cover.read()
		finally:
			cover.close()
	except (OSError, ValueError):  # pragma: no cover - file vanished on disk
		return None


def cover_url(cover) -> str:
	"""Public URL of a stored cover (``""`` when there is none)."""
	if not cover:
		return ""
	try:
		return cover.url
	except ValueError:  # pragma: no cover - field without an associated file
		return ""
