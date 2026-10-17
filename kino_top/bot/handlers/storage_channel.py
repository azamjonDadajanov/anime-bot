"""Storage channel listener: automatically ingest media uploaded directly to Cloud storage channels.

When an administrator drops a video/photo/document directly into a storage (Cloud)
channel with a caption containing a 4-digit code (e.g. `code: 8874` or `kod 8874`):
1. Resolve the MediaTitle by that 4-digit code.
2. Automatically create the next MediaPart and TelegramMedia.
3. Post a confirmation message in the storage channel ("qism qo'shildi").
4. Publish according to the catalogue rules:
   - If ongoing: post the new episode to the ongoing channel.
   - If completed or movie: wait until all expected parts are uploaded before posting to the completed channel.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from aiogram import F, Router
from aiogram.types import Message
from django.db import transaction

from movies.models import MediaPart, MediaTitle, TelegramChannel, TelegramMedia

from ..bot_logging import record_event
from ..services.media import title_by_code_sync
from ..services.publishing import publish_parts_by_rules
from ..utils import escape_html, to_async

logger = logging.getLogger(__name__)

router = Router(name="storage-channel")


def extract_media_entry(message: Message) -> Optional[Dict[str, Any]]:
	caption = (message.caption or message.text or "")[:1024]
	if message.video:
		return {
			"file_id": message.video.file_id,
			"media_type": TelegramMedia.MediaType.VIDEO,
			"caption": caption,
		}
	if message.photo:
		return {
			"file_id": message.photo[-1].file_id,
			"media_type": TelegramMedia.MediaType.PHOTO,
			"caption": caption,
		}
	if message.document:
		return {
			"file_id": message.document.file_id,
			"media_type": TelegramMedia.MediaType.DOCUMENT,
			"caption": caption,
		}
	return None


def extract_media_code(text: str) -> Optional[str]:
	"""Extract 4-digit media code from caption (e.g., 'code: 8874', 'kod 8874', or standalone '8874')."""
	if not text:
		return None
	# 1) Prefixed match: code: 8874, kod: 8874, code - 8874, code 8874
	match = re.search(r"(?:code|kod)\s*[:=\-]?\s*(\d{4})\b", text, re.IGNORECASE)
	if match:
		return match.group(1)
	# 2) Standalone 4-digit number: #8874 or 8874
	match = re.search(r"(?:#|\b)(\d{4})\b", text)
	if match:
		return match.group(1)
	return None


def extract_season_number(text: str) -> Optional[int]:
	"""Extract season number if specified in caption (e.g., 'season: 2', 'mavsum 1')."""
	if not text:
		return None
	match = re.search(r"(?:season|mavsum|sezon)\s*[:=\-]?\s*(\d{1,3})\b", text, re.IGNORECASE)
	if match:
		try:
			return int(match.group(1))
		except ValueError:
			return None
	return None


def create_part_from_channel_post_sync(
	channel: TelegramChannel,
	title: MediaTitle,
	entry: Dict[str, Any],
	message_id: int,
	season_number: Optional[int],
) -> MediaPart:
	"""Create a fresh MediaPart and TelegramMedia from the message already in the Cloud channel."""
	with transaction.atomic():
		if season_number is None:
			last_part = (
				MediaPart.objects.filter(content=title)
				.order_by("-season_number", "-number")
				.first()
			)
			if last_part and last_part.season_number is not None:
				season_number = last_part.season_number

		taken = set(
			MediaPart.objects.filter(content=title, season_number=season_number).values_list(
				"number", flat=True
			)
		)
		next_number = len(taken) + 1
		while next_number in taken:
			next_number += 1

		part = MediaPart.objects.create(
			content=title,
			season_number=season_number,
			number=next_number,
		)
		TelegramMedia.objects.create(
			part=part,
			channel=channel,
			source_message_id=message_id,
			file_id=str(entry["file_id"])[:512],
			media_type=entry["media_type"],
			order=1,
			caption=entry["caption"],
		)
	return part


create_part_from_channel_post = to_async(create_part_from_channel_post_sync)


async def _is_storage_channel(message: Message) -> bool:
	return await to_async(
		TelegramChannel.objects.filter(
			chat_id=message.chat.id,
			purpose=TelegramChannel.Purpose.STORAGE,
			is_active=True,
		).exists
	)()


@router.channel_post(_is_storage_channel, F.video | F.photo | F.document)
async def handle_storage_channel_post(message: Message, bot) -> None:
	"""Catch uploads to Cloud storage channels and register them as new parts."""
	chat_id = message.chat.id
	channel = await to_async(
		TelegramChannel.objects.filter(
			chat_id=chat_id,
			purpose=TelegramChannel.Purpose.STORAGE,
			is_active=True,
		).first
	)()
	if channel is None:
		return

	entry = extract_media_entry(message)
	if entry is None:
		return

	caption = entry.get("caption") or ""
	code = extract_media_code(caption)
	if not code:
		logger.debug("Storage post in %s had no 4-digit code in caption.", chat_id)
		return

	title = await to_async(title_by_code_sync)(code)
	if title is None:
		logger.warning("Storage post in %s referenced unknown code %s.", chat_id, code)
		error_text = f"⚠️ <code>{escape_html(code)}</code> kodli media topilmadi."
		try:
			await message.reply(error_text)
		except Exception:
			await bot.send_message(chat_id=chat_id, text=error_text)
		return

	season_number = extract_season_number(caption)
	part = await create_part_from_channel_post(
		channel=channel,
		title=title,
		entry=entry,
		message_id=message.message_id,
		season_number=season_number,
	)

	season_lbl = f"{part.season_number}-mavsum · " if part.season_number else ""
	confirm_text = (
		f"✅ <b>{escape_html(title.title)}</b>\n"
		f"🎞 {season_lbl}{part.number}-qism muvaffaqiyatli qo'shildi!"
	)
	try:
		await message.reply(confirm_text)
	except Exception:
		try:
			await bot.send_message(
				chat_id=chat_id, text=confirm_text, reply_to_message_id=message.message_id
			)
		except Exception:
			await bot.send_message(chat_id=chat_id, text=confirm_text)

	await to_async(record_event)(
		"INFO",
		f"Direct storage upload: {title.title} ({code}) part #{part.number} added via channel {channel.title}.",
	)

	# Ongoing bo'lsa ongoing kanalga tashlaydi, completed/movie bo'lsa barcha qismlari to'lishini kutadi
	await publish_parts_by_rules(bot, title, [part])
