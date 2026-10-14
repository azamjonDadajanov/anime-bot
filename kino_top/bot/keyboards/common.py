"""Shared inline keyboard building blocks."""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from .. import callbacks as cb


def btn(
	text: str,
	data: Optional[str] = None,
	url: Optional[str] = None,
	web_app: Optional[str] = None,
) -> InlineKeyboardButton:
	"""Build an inline button from exactly one target.

	``web_app`` opens the Telegram Mini App at that HTTPS URL, ``url`` a normal
	link and ``data`` a callback (the default when the others are absent).
	"""
	if web_app:
		return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=web_app))
	if url:
		return InlineKeyboardButton(text=text, url=url)
	return InlineKeyboardButton(text=text, callback_data=(data or cb.NOOP)[:64])


def keyboard(*rows: Optional[Sequence[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
	return InlineKeyboardMarkup(inline_keyboard=[list(row) for row in rows if row])


def pagination_row(prefix: str, page: int, pages: int) -> List[InlineKeyboardButton]:
	row: List[InlineKeyboardButton] = []
	if page > 1:
		row.append(btn("⬅️", f"{prefix}{page - 1}"))
	row.append(btn(f"{page}/{pages}", cb.NOOP))
	if page < pages:
		row.append(btn("➡️", f"{prefix}{page + 1}"))
	return row


def confirm_keyboard(yes_callback: str, no_callback: str) -> InlineKeyboardMarkup:
	return keyboard(
		[btn("✅ Ha, tasdiqlayman", yes_callback)],
		[btn("↩️ Bekor qilish", no_callback)],
	)


def cancel_keyboard(cancel_callback: str = cb.CANCEL) -> InlineKeyboardMarkup:
	return keyboard([btn("❌ Bekor qilish", cancel_callback)])


def back_keyboard(target: str = cb.MENU, text: str = "⬅️ Orqaga") -> InlineKeyboardMarkup:
	return keyboard([btn(text, target)])


def channel_url(channel) -> Optional[str]:
	"""Best available URL for a channel: invite link or @username."""
	if getattr(channel, "invite_link", ""):
		return channel.invite_link
	username = (getattr(channel, "username", "") or "").strip()
	if username:
		return f"https://t.me/{username.lstrip('@')}"
	return None


def subscribe_keyboard(channels: Iterable, retry_callback: str = cb.SUB_CHECK) -> InlineKeyboardMarkup:
	"""Channel links plus a "check" button.

	No "main menu" button: while the mandatory subscription is missing every
	other action is refused, so offering a menu that immediately bounces back
	to this same prompt would only be confusing.
	"""
	rows: List[List[InlineKeyboardButton]] = []
	for channel in channels:
		url = channel_url(channel)
		if url:
			rows.append([btn(f"📢 {channel.title}", url=url)])
		else:
			rows.append([btn(f"📢 {channel.title} (havola yo'q)", cb.NOOP)])
	rows.append([btn("✅ Tekshirish", retry_callback)])
	return keyboard(*rows)
