"""Fetch a file from Telegram by ``file_id`` using the Bot HTTP API.

The catalog only stores Telegram ``file_id`` references (see ``TelegramMedia``).
Manga chapters are uploaded as PDF documents; the website renders them into
page images on the server (see ``movies.pdf_pages``) and this module is what
pulls the original bytes down for that rendering. It talks to the Bot API
directly with the standard library, so no extra dependency is required.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Tuple

from django.conf import settings

TIMEOUT_GET_FILE = 20
TIMEOUT_DOWNLOAD = 120


class TelegramFileError(Exception):
	"""Raised when Telegram rejects ``getFile`` or the download fails."""


def _bot_token() -> str:
	token = getattr(settings, "BOT_TOKEN", "") or getattr(settings, "TELEGRAM_BOT_TOKEN", "")
	if not token:
		raise TelegramFileError("Telegram bot token sozlanmagan (BOT_TOKEN).")
	return token


def _http_error_message(exc: urllib.error.HTTPError) -> str:
	"""Extract the ``description`` Telegram puts in an error response body."""
	try:
		payload = json.loads(exc.read().decode("utf-8", "replace"))
		description = payload.get("description")
		if description:
			return description
	except (ValueError, AttributeError):
		pass
	return f"Telegram xatoligi (HTTP {exc.code})"


def user_error_message(exc: "TelegramFileError") -> str:
	"""Turn a :class:`TelegramFileError` into a message a reader can act on."""
	message = str(exc)
	lowered = message.lower()
	if "too big" in lowered or "file is too big" in lowered:
		return "PDF Telegram orqali yuklanmaydi (bot uchun 20MB limit). Faylni saytga (serverga) yuklang."
	if "not found" in lowered or "wrong file" in lowered or "invalid" in lowered:
		return "Telegram file_id yaroqsiz yoki muddati o'tgan."
	return message


def resolve_file_path(file_id: str) -> str:
	"""Resolve a ``file_id`` to the Telegram ``file_path`` via ``getFile``."""
	token = _bot_token()
	query = urllib.parse.urlencode({"file_id": file_id})
	url = f"https://api.telegram.org/bot{token}/getFile?{query}"
	try:
		with urllib.request.urlopen(url, timeout=TIMEOUT_GET_FILE) as response:
			payload = json.load(response)
	except urllib.error.HTTPError as exc:
		raise TelegramFileError(_http_error_message(exc)) from exc
	except (urllib.error.URLError, TimeoutError, ValueError) as exc:
		raise TelegramFileError(f"getFile so'rovi bajarilmadi: {exc}") from exc

	if not payload.get("ok"):
		raise TelegramFileError(payload.get("description") or "getFile failed")
	file_path = (payload.get("result") or {}).get("file_path")
	if not file_path:
		raise TelegramFileError("Telegram file_path qaytarmadi.")
	return file_path


def fetch_file_bytes(file_id: str) -> Tuple[bytes, str]:
	"""Return ``(content, file_path)`` for a Telegram ``file_id``."""
	token = _bot_token()
	file_path = resolve_file_path(file_id)
	url = f"https://api.telegram.org/file/bot{token}/{file_path}"
	try:
		with urllib.request.urlopen(url, timeout=TIMEOUT_DOWNLOAD) as response:
			content = response.read()
	except urllib.error.HTTPError as exc:
		raise TelegramFileError(_http_error_message(exc)) from exc
	except (urllib.error.URLError, TimeoutError) as exc:
		raise TelegramFileError(f"Fayl yuklab olinmadi: {exc}") from exc
	return content, file_path
