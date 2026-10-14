"""Web API orqali qo'shilgan Telegram media faylini Cloud kanalga ko'chirish.

Admin panel'dan ``file_id`` kiritingda:
1. Avval fayl mavjudligi tekshiriladi (getFile)
2. Fayl bo'lmasa xatolik qaytariladi
3. Fayl bo'lsa Cloud kanalga yuboriladi
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Tuple

from django.conf import settings

logger = logging.getLogger(__name__)


def _send_to_channel(bot, channel_chat_id: int, file_id: str, media_type: str, caption: str):
	if media_type == "video":
		return bot.send_video(chat_id=channel_chat_id, video=file_id, caption=caption or None)
	if media_type == "photo":
		return bot.send_photo(chat_id=channel_chat_id, photo=file_id, caption=caption or None)
	return bot.send_document(chat_id=channel_chat_id, document=file_id, caption=caption or None)


def copy_file_to_storage_sync(
	file_id: str,
	media_type: str,
	caption: str = "",
) -> Tuple[Optional[int], Optional[int], Optional[str], str]:
	"""Faylni tekshirib, birinchi faol STORAGE kanalga yuboradi.

	Returns:
		(channel_pk, source_message_id, new_file_id, error_message)
		Xatolik bo'lsa error_message to'ldiriladi.
	"""
	from movies.models import TelegramChannel
	from movies.telegram_files import TelegramFileError, resolve_file_path

	# 1. Fayl mavjudligini tekshirish
	try:
		resolve_file_path(file_id)
	except TelegramFileError as exc:
		return None, None, None, f"Fayl topilmadi yoki yaroqsiz: {exc}"

	# 2. STORAGE kanalni topish
	channel = (
		TelegramChannel.objects.filter(
			purpose=TelegramChannel.Purpose.STORAGE,
			is_active=True,
		)
		.order_by("pk")
		.first()
	)
	if channel is None:
		return None, None, None, "Faol Cloud (storage) kanal topilmadi. Kanallar sahifasidan STORAGE kanal qo'shing."

	# 3. BOT_TOKEN tekshirish
	token = getattr(settings, "BOT_TOKEN", "") or getattr(settings, "TELEGRAM_BOT_TOKEN", "")
	if not token:
		return None, None, None, "BOT_TOKEN sozlanmagan."

	# 4. Kanalga yuborish
	async def _inner() -> Tuple[Optional[int], Optional[int], Optional[str], str]:
		from aiogram import Bot
		from aiogram.exceptions import TelegramAPIError

		bot = Bot(token=token)
		try:
			sent = await _send_to_channel(bot, channel.chat_id, file_id, media_type, caption)
			new_file_id = file_id
			if media_type == "video" and sent.video:
				new_file_id = sent.video.file_id
			elif media_type == "photo" and sent.photo:
				new_file_id = sent.photo[-1].file_id
			elif sent.document:
				new_file_id = sent.document.file_id
			return channel.pk, sent.message_id, new_file_id, ""
		except TelegramAPIError as exc:
			return None, None, None, f"Kanalga yuborishda xatolik: {exc}"
		finally:
			await bot.session.close()

	try:
		channel_pk, message_id, new_file_id, error = asyncio.run(_inner())
	except Exception as exc:  # noqa: BLE001
		logger.exception("Storage channel copy failed for file_id=%s", file_id[:64])
		return None, None, None, f"Kanalga yuborishda xatolik: {exc}"

	if error:
		return None, None, None, error
	return channel_pk, message_id, new_file_id, ""


def copy_file_to_storage(
	media_id: int,
	file_id: str,
	media_type: str,
	caption: str = "",
) -> Tuple[bool, str]:
	"""TelegramMedia yozuvini Cloud kanalga ko'chiradi va yangilaydi.

	Returns:
		(success, error_message)
	"""
	from movies.models import TelegramMedia

	channel_pk, message_id, new_file_id, error = copy_file_to_storage_sync(
		file_id, media_type, caption
	)
	if error:
		return False, error

	media = TelegramMedia.objects.get(pk=media_id)
	media.channel_id = channel_pk
	media.source_message_id = message_id
	if new_file_id:
		media.file_id = new_file_id[:512]
	media.save(update_fields=["channel", "source_message_id", "file_id"])
	return True, ""
