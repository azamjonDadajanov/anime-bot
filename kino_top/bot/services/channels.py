"""Channel management for the three logical channel types.

* ``required`` — membership is mandatory before protected content is delivered.
* ``storage``  — stores video/photo/document ``file_id`` references.
* ``public``   — receives announcements and new-episode posts.

The types are fully independent: each may contain zero or many channels.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from django.utils import timezone

from movies.models import TelegramChannel

from ..utils import parse_admin_target, to_async

logger = logging.getLogger(__name__)

PURPOSE_LABELS = {
	TelegramChannel.Purpose.REQUIRED: "🔒 Majburiy obuna",
	TelegramChannel.Purpose.STORAGE: "☁️ Cloud saqlash",
	TelegramChannel.Purpose.PUBLIC: "📢 Ommaviy kanal",
}
PURPOSE_ORDER = (
	TelegramChannel.Purpose.REQUIRED,
	TelegramChannel.Purpose.STORAGE,
	TelegramChannel.Purpose.PUBLIC,
)
ADMIN_STATUSES = {"administrator", "creator"}


class ChatResolutionError(RuntimeError):
	"""Raised when a channel reference cannot be resolved with Telegram."""


@dataclass
class ChannelTestResult:
	channel: TelegramChannel
	ok: bool
	title: str = ""
	chat_type: str = ""
	can_post: bool = False
	can_check: bool = False
	message: str = ""
	error: str = ""

	@property
	def status_text(self) -> str:
		return "✅ Ishlayapti" if self.ok else "❌ Muammo bor"


def purpose_label(purpose: str) -> str:
	return PURPOSE_LABELS.get(purpose, purpose)


def channels_by_purpose_sync(
	purpose: str, *, active_only: bool = False
) -> List[TelegramChannel]:
	queryset = TelegramChannel.objects.filter(purpose=purpose)
	if active_only:
		queryset = queryset.filter(is_active=True)
	return list(queryset.order_by("title"))


def all_channels_sync() -> List[TelegramChannel]:
	return list(TelegramChannel.objects.order_by("purpose", "title"))


def required_channels_sync(*, active_only: bool = True) -> List[TelegramChannel]:
	return channels_by_purpose_sync(TelegramChannel.Purpose.REQUIRED, active_only=active_only)


def storage_channels_sync(*, active_only: bool = True) -> List[TelegramChannel]:
	return channels_by_purpose_sync(TelegramChannel.Purpose.STORAGE, active_only=active_only)


def public_channels_sync(*, active_only: bool = True) -> List[TelegramChannel]:
	return channels_by_purpose_sync(TelegramChannel.Purpose.PUBLIC, active_only=active_only)


all_channels = to_async(all_channels_sync)
storage_channels = to_async(storage_channels_sync)
public_channels = to_async(public_channels_sync)


def counts_by_purpose_sync() -> Dict[str, int]:
	return {
		purpose: TelegramChannel.objects.filter(purpose=purpose).count()
		for purpose in PURPOSE_ORDER
	}


counts_by_purpose = to_async(counts_by_purpose_sync)


def add_channel_sync(
	chat_id: int,
	title: str,
	*,
	purpose: str = TelegramChannel.Purpose.STORAGE,
	username: str = "",
	invite_link: str = "",
	is_active: bool = True,
) -> TelegramChannel:
	if purpose not in TelegramChannel.Purpose.values:
		raise ValueError(f"Unknown channel purpose: {purpose!r}")
	channel, created = TelegramChannel.objects.get_or_create(
		chat_id=int(chat_id),
		defaults={
			"title": title,
			"username": username,
			"purpose": purpose,
			"invite_link": invite_link,
			"is_active": is_active,
		},
	)
	if not created:
		channel.title = title
		channel.purpose = purpose
		channel.username = username or channel.username
		channel.invite_link = invite_link or channel.invite_link
		channel.is_active = is_active
		channel.save()
	return channel


add_channel = to_async(add_channel_sync)


def update_channel_sync(channel: TelegramChannel, **fields: Any) -> TelegramChannel:
	allowed = {"title", "username", "purpose", "invite_link", "is_active"}
	changed = []
	for name, value in fields.items():
		if name not in allowed:
			continue
		if name == "purpose" and value not in TelegramChannel.Purpose.values:
			raise ValueError(f"Unknown channel purpose: {value!r}")
		if getattr(channel, name) != value:
			setattr(channel, name, value)
			changed.append(name)
	if "purpose" in changed:
		changed.append("is_public")
	if changed:
		channel.save(update_fields=changed)
	return channel


update_channel = to_async(update_channel_sync)


def toggle_active_sync(channel: TelegramChannel) -> bool:
	channel.is_active = not channel.is_active
	channel.save(update_fields=["is_active"])
	return channel.is_active


toggle_active = to_async(toggle_active_sync)


def delete_channel_sync(channel: TelegramChannel) -> None:
	channel.delete()


delete_channel = to_async(delete_channel_sync)


def get_channel_sync(channel_id: int) -> Optional[TelegramChannel]:
	return TelegramChannel.objects.filter(pk=channel_id).first()


get_channel = to_async(get_channel_sync)


async def resolve_chat(bot: Bot, raw: str):
	"""Resolve an id/@username/t.me link into a Telegram chat object."""
	kind, value, _username = parse_admin_target(raw)
	if not kind:
		raise ChatResolutionError("Chat ID yoki @username noto'g'ri kiritildi.")
	target: Any = int(value) if kind == "id" else value
	try:
		return await bot.get_chat(target)
	except (TelegramBadRequest, TelegramForbiddenError) as exc:
		raise ChatResolutionError(
			"Kanal topilmadi yoki bot unga qo'shilmagan. Botni kanalga administrator qilib qo'shing."
		) from exc
	except TelegramAPIError as exc:  # pragma: no cover - network failure
		raise ChatResolutionError("Telegram bilan aloqa xatosi. Keyinroq urinib ko'ring.") from exc


async def _bot_membership(bot: Bot, chat_id: int):
	try:
		return await bot.get_chat_member(chat_id=chat_id, user_id=bot.id)
	except (TelegramBadRequest, TelegramForbiddenError) as exc:
		logger.warning("Bot membership probe failed for %s: %s", chat_id, exc)
		return None
	except TelegramAPIError as exc:  # pragma: no cover - network failure
		logger.warning("Bot membership probe errored for %s: %s", chat_id, exc)
		return None


async def test_channel(bot: Bot, channel: TelegramChannel) -> ChannelTestResult:
	"""Verify bot access, posting rights and membership visibility."""
	try:
		chat = await bot.get_chat(channel.chat_id)
	except (TelegramBadRequest, TelegramForbiddenError) as exc:
		result = ChannelTestResult(
			channel=channel,
			ok=False,
			message="Bot kanalga qo'shilmagan yoki chat ID xato.",
			error=str(exc),
		)
		return await persist_result(result)
	except TelegramAPIError as exc:  # pragma: no cover - network failure
		result = ChannelTestResult(
			channel=channel, ok=False, message="Telegram bilan aloqa xatosi.", error=str(exc)
		)
		return await persist_result(result)

	member = await _bot_membership(bot, chat.id)
	can_post = bool(getattr(member, "can_post_messages", False))
	can_check = getattr(member, "status", "") in ADMIN_STATUSES
	chat_type = getattr(chat, "type", "") or ""

	if channel.purpose == TelegramChannel.Purpose.REQUIRED:
		ok = can_check
		message = (
			"Bot administrator va a'zolikni tekshira oladi."
			if ok
			else "Bot administrator emas: majburiy obunani tekshirib bo'lmaydi."
		)
	else:
		ok = can_post or chat_type == "private"
		message = (
			"Bot xabar yubora oladi."
			if ok
			else "Botda post yuborish huquqi yo'q. Administrator qilib tayinlang."
		)

	result = ChannelTestResult(
		channel=channel,
		ok=ok,
		title=getattr(chat, "title", None) or channel.title,
		chat_type=chat_type,
		can_post=can_post,
		can_check=can_check,
		message=message,
	)
	return await persist_result(result)


async def persist_result(result: ChannelTestResult) -> ChannelTestResult:
	channel = result.channel
	channel.last_checked_at = timezone.now()
	channel.last_check_ok = result.ok
	channel.check_details = {
		"ok": result.ok,
		"can_post": result.can_post,
		"can_check": result.can_check,
		"chat_type": result.chat_type,
		"message": result.message,
		"error": result.error,
	}
	await to_async(channel.save)(
		update_fields=[
			"last_checked_at",
			"last_check_ok",
			"check_details",
			"is_public",
		]
	)
	return result


async def test_channels(bot: Bot, channels: Optional[Iterable[TelegramChannel]] = None) -> List[ChannelTestResult]:
	if channels is None:
		channels = await all_channels()
	results = []
	for channel in channels:
		results.append(await test_channel(bot, channel))
	return results


async def default_required_channels() -> Sequence[TelegramChannel]:
	return await to_async(required_channels_sync)()
