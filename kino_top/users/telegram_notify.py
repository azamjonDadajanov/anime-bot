"""Deliver messages from the web process through the Telegram Bot API.

The website and the long-polling bot are separate processes, but the Bot API is
stateless: any process holding the token can deliver a message. The inline
keyboard of a payment request uses the same ``a:<section>:<action>`` callback
convention as the admin panel, so whichever administrator presses a button is
handled by the running bot.

Three callers share this module: new payment requests, user support messages
(``users.support``) and subscription expiry reminders (``users.reminders``).
"""

from __future__ import annotations

import html
import json
import logging
from typing import Iterable, List, Tuple

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"

OK_CALLBACK = "a:subreq:ok"
REJECT_CALLBACK = "a:subreq:no"


def admin_ids() -> List[int]:
	"""Administrator Telegram IDs (``ADMIN_IDS`` / ``BOT_ADMIN_IDS``)."""
	raw = settings.ADMIN_IDS or getattr(settings, "BOT_ADMIN_IDS", "") or ""
	if isinstance(raw, str):
		parts: Iterable[str] = raw.replace(",", " ").split()
	else:
		parts = [str(item) for item in raw]
	ids: List[int] = []
	for part in parts:
		try:
			value = int(str(part).strip())
		except (TypeError, ValueError):
			continue
		if value > 0:
			ids.append(value)
	return ids


def bot_token() -> str:
	return str(settings.BOT_TOKEN or settings.TELEGRAM_BOT_TOKEN or "").strip()


def _request_caption(request, user_display: str) -> str:
	plan = str(request.plan or "free").upper()
	return (
		"🧾 <b>Yangi obuna arizasi</b>\n\n"
		f"👤 Foydalanuvchi: {user_display}\n"
		f"💳 Tarif: <b>{plan}</b>\n"
		f"💰 Summa: <b>{request.amount:g}</b>\n"
		f"💳 Karta: <code>{request.card_number or '-'}</code>\n\n"
		"Quyidagi to'lov screenshoti uchun yuborildi.\n"
		"Arizani tasdiqlang yoki rad eting."
	)


def _user_display(request) -> str:
	profile = getattr(request.user, "telegram_profile", None)
	if profile is not None:
		name = profile.first_name or profile.username or str(profile.telegram_id)
		return f"{name} (<code>{profile.telegram_id}</code>)"
	return str(request.user)


def _telegram_photo(request) -> str:
	"""A Telegram ``file_id`` stored by the bot flow, if any."""
	notes = str(getattr(request, "notes", "") or "")
	if notes.startswith("telegram_photo:"):
		return notes.split(":", 1)[1]
	return ""


def send_telegram_message(
	chat_id: int, text: str, *, parse_mode: str = "HTML"
) -> Tuple[bool, str]:
	"""Send one Bot API message to ``chat_id``.

	Returns ``(delivered, error)``: callers that keep a durable record (support
	messages, reminders) store the reason a delivery failed instead of losing it.
	"""
	token = bot_token()
	if not token:
		logger.warning("Cannot send a Telegram message: BOT_TOKEN is empty.")
		return False, "BOT_TOKEN is empty"
	try:
		with httpx.Client(timeout=30.0, follow_redirects=True) as client:
			response = client.post(
				f"{API_BASE}/bot{token}/sendMessage",
				data={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
			)
	except httpx.HTTPError as exc:  # pragma: no cover - network failure
		logger.warning("Telegram message to %s failed: %s", chat_id, exc)
		return False, str(exc)
	if response.status_code == 200:
		return True, ""
	logger.warning(
		"Telegram rejected the message for %s: %s %s",
		chat_id,
		response.status_code,
		response.text[:300],
	)
	return False, f"{response.status_code} {response.text[:200]}"


def _escape(value) -> str:
	"""Escape the markup characters Telegram's HTML mode understands.

	Apostrophes and quotes stay readable: ``quote=True`` would turn an ordinary
	"to'lovim" into ``to&#x27;lovim`` in the administrator's chat.
	"""
	return html.escape(str(value or ""), quote=False)


def _support_caption(message) -> str:
	"""Header, sender and body of a user's support message."""
	profile = getattr(message.user, "telegram_profile", None)
	if profile is not None:
		name = profile.first_name or profile.username or str(profile.telegram_id)
		who = f"{_escape(name)} (<code>{profile.telegram_id}</code>)"
	else:
		account = (
			getattr(message.user, "username", "")
			or getattr(message.user, "email", "")
			or f"user #{message.user_id}"
		)
		who = f"{_escape(account)} (sayt hisobi)"
	source = "Bot" if message.source == "bot" else "Sayt"
	return (
		"✉️ <b>Foydalanuvchi xabari</b>\n\n"
		f"👤 Kimdan: {who}\n"
		f"📍 Manba: {source}\n"
		f"🕒 {message.created_at:%d.%m.%Y %H:%M}\n\n"
		f"{_escape(message.text)}"
	)


def notify_admins_user_message(message) -> Tuple[bool, str]:
	"""Forward a stored support message to every administrator.

	Returns ``(delivered, error)`` where ``error`` describes the last failure, so
	:meth:`users.models.SupportMessage.mark_delivered` can record it.
	"""
	caption = _support_caption(message)
	targets = admin_ids()
	if not targets:
		logger.warning("Cannot notify admins: ADMIN_IDS is empty.")
		return False, "ADMIN_IDS is empty"
	delivered = False
	error = ""
	for chat_id in targets:
		ok, reason = send_telegram_message(chat_id, caption)
		if ok:
			delivered = True
		else:
			error = reason
	return delivered, error


def notify_admins_new_request(request) -> bool:
	"""Send the screenshot and approve/reject buttons to every admin."""
	token = bot_token()
	targets = admin_ids()
	if not token or not targets:
		logger.warning("Cannot notify admins: BOT_TOKEN or ADMIN_IDS is empty.")
		return False

	keyboard = {
		"inline_keyboard": [
			[
				{"text": "✅ Tasdiqlash", "callback_data": f"{OK_CALLBACK}:{request.pk}"},
				{"text": "❌ Rad etish", "callback_data": f"{REJECT_CALLBACK}:{request.pk}"},
			]
		]
	}
	caption = _request_caption(request, _user_display(request))
	payload = {
		"caption": caption,
		"parse_mode": "HTML",
		"reply_markup": json.dumps(keyboard),
	}

	sent = False
	image_path = None
	try:
		image_path = request.screenshot.path
	except (ValueError, OSError, AttributeError):
		image_path = None
	telegram_photo = _telegram_photo(request)

	with httpx.Client(timeout=30.0, follow_redirects=True) as client:
		for chat_id in targets:
			data = {**payload, "chat_id": chat_id}
			try:
				if telegram_photo:
					response = client.post(
						f"{API_BASE}/bot{token}/sendPhoto",
						data={**data, "photo": telegram_photo},
					)
				elif image_path:
					with open(image_path, "rb") as handle:
						files = {"photo": ("screenshot.png", handle, "image/png")}
						response = client.post(
							f"{API_BASE}/bot{token}/sendPhoto", data=data, files=files
						)
				else:
					response = client.post(
						f"{API_BASE}/bot{token}/sendMessage", data=data
					)
			except httpx.HTTPError as exc:  # pragma: no cover - network failure
				logger.warning("Admin %s could not be notified: %s", chat_id, exc)
				continue
			if response.status_code == 200:
				sent = True
				continue
			logger.warning(
				"Telegram rejected the message for admin %s: %s %s",
				chat_id,
				response.status_code,
				response.text[:300],
			)
	return sent
