"""Publishing announcements and new episodes to public channels."""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from movies.models import MediaPart, MediaTitle, TelegramChannel

from ..texts import COUPON_POST
from ..utils import deep_link, escape_html, to_async
from .bot_settings import get_settings
from .media import part_label, title_parts

logger = logging.getLogger(__name__)

_username_cache: dict[int, str] = {}


async def bot_username(bot: Bot) -> str:
	"""Return (and cache) the bot username used for deep links."""
	cached = _username_cache.get(bot.id)
	if cached:
		return cached
	try:
		me = await bot.get_me()
	except TelegramAPIError:  # pragma: no cover - network failure
		logger.warning("Could not resolve the bot username for deep links.")
		return ""
	_username_cache[bot.id] = me.username or ""
	return _username_cache[bot.id]


def deep_link_payload(title: MediaTitle) -> str:
	return f"{title.type}_{title.code}"


def announcement_text(
	title: MediaTitle, *, part: Optional[MediaPart] = None, genres: str = ""
) -> str:
	# ``genres`` is resolved by the caller through the async ORM bridge; reading
	# the M2M here would perform a synchronous query inside an async handler.
	genres = genres or "—"
	lines: List[str] = []
	if part is None:
		lines.append(f"🎬 <b>{escape_html(title.title)}</b>")
		lines.append(f"🆔 Kod: <code>{title.code}</code>")
		lines.append(f"📺 Turi: {title.get_type_display()}")
		lines.append(f"🎭 Janr: {escape_html(genres)}")
		lines.append(f"🌐 Til: {escape_html(title.language)}")
		lines.append(f"⭐ Reyting: {title.rating}/10")
		lines.append(f"📊 Holat: {title.get_status_display()}")
		if title.synopsis:
			lines.append("")
			lines.append(escape_html(title.synopsis)[:600])
	else:
		lines.append(f"🆕 <b>{escape_html(title.title)}</b>")
		lines.append(f"🎞 {escape_html(part_label(part))}")
		lines.append(f"🆔 Kod: <code>{title.code}</code>")
	lines.append("")
	lines.append("▶️ Tomosha qilish uchun pastdagi tugmani bosing.")
	return "\n".join(lines)


def _cover_file(title: MediaTitle) -> Optional[BufferedInputFile]:
	if not title.cover:
		return None
	try:
		data = bytes(title.cover)
	except TypeError:  # pragma: no cover - memoryview edge case
		data = title.cover
	return BufferedInputFile(data, filename=f"cover-{title.code}.jpg")


def _deep_link_keyboard(bot_username_value: str, title: MediaTitle) -> Optional[InlineKeyboardMarkup]:
	link = deep_link(bot_username_value, deep_link_payload(title))
	if not link:
		return None
	return InlineKeyboardMarkup(
		inline_keyboard=[[InlineKeyboardButton(text="▶️ Tomosha qilish", url=link)]]
	)


async def resolve_publish_channel(channel: Optional[TelegramChannel] = None) -> Optional[TelegramChannel]:
	if channel is not None:
		return channel
	settings = await get_settings()
	if not settings.publish_channel_id:
		return None
	# Resolve the FK through the async ORM bridge: touching ``settings.publish_channel``
	# here would run a query on the event loop and raise SynchronousOnlyOperation.
	from .channels import get_channel

	return await get_channel(settings.publish_channel_id)


async def publish_title(
	bot: Bot,
	title: MediaTitle,
	*,
	channel: Optional[TelegramChannel] = None,
	part: Optional[MediaPart] = None,
) -> Optional[int]:
	"""Post a title (or a new episode) to the selected public channel."""
	target = await resolve_publish_channel(channel)
	if target is None:
		logger.info("Auto-publish skipped for %s: no public channel selected.", title.pk)
		return None

	username = await bot_username(bot)
	caption = announcement_text(title, part=part)
	keyboard = _deep_link_keyboard(username, title)
	cover = _cover_file(title)

	try:
		if cover is not None and part is None:
			message = await bot.send_photo(
				chat_id=target.chat_id,
				photo=cover,
				caption=caption,
				reply_markup=keyboard,
			)
		else:
			message = await bot.send_message(
				chat_id=target.chat_id,
				text=caption,
				reply_markup=keyboard,
				disable_web_page_preview=True,
			)
	except (TelegramBadRequest, TelegramForbiddenError) as exc:
		logger.warning("Publishing to channel %s failed: %s", target.chat_id, exc)
		return None
	except TelegramAPIError as exc:  # pragma: no cover - network failure
		logger.warning("Publishing to channel %s errored: %s", target.chat_id, exc)
		return None

	title.metadata_channel = target
	title.metadata_message_id = message.message_id
	await to_async(title.save)(update_fields=["metadata_channel", "metadata_message_id", "updated_at"])
	return message.message_id


async def publish_coupon(bot: Bot, coupon, *, channel: Optional[TelegramChannel] = None) -> Optional[int]:
	"""Post a coupon promotion to the selected public channel.

	Returns the message id, or ``None`` when no channel is configured or the post
	is refused — the caller then tells the administrator what to fix.
	"""
	target = await resolve_publish_channel(channel)
	if target is None:
		logger.info("Coupon %s was not published: no public channel selected.", coupon.pk)
		return None

	username = await bot_username(bot)
	keyboard = None
	if username:
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[InlineKeyboardButton(text="🎟 Kuponni olish", url=f"https://t.me/{username}")]
			]
		)
	text = COUPON_POST.format(
		days=coupon.days,
		max_uses=coupon.max_uses,
		code=escape_html(coupon.code),
	)
	try:
		message = await bot.send_message(
			chat_id=target.chat_id,
			text=text,
			reply_markup=keyboard,
			disable_web_page_preview=True,
		)
	except (TelegramBadRequest, TelegramForbiddenError) as exc:
		logger.warning(
			"Publishing coupon %s to channel %s failed: %s", coupon.pk, target.chat_id, exc
		)
		return None
	except TelegramAPIError as exc:  # pragma: no cover - network failure
		logger.warning(
			"Publishing coupon %s to channel %s errored: %s", coupon.pk, target.chat_id, exc
		)
		return None

	coupon.posted_channel = target
	coupon.posted_message_id = message.message_id
	await to_async(coupon.save)(
		update_fields=["posted_channel", "posted_message_id", "updated_at"]
	)
	return message.message_id


async def maybe_auto_publish_title(bot: Bot, title: MediaTitle) -> Optional[int]:
	settings = await get_settings()
	if not settings.auto_publish_new_content:
		return None
	return await publish_title(bot, title)


async def maybe_auto_publish_part(bot: Bot, part: MediaPart) -> Optional[int]:
	settings = await get_settings()
	if not settings.auto_publish_new_content:
		return None
	return await publish_title(bot, part.content, part=part)


def parts_range_label(parts: Sequence[MediaPart]) -> str:
	"""A human label for a batch of new parts, e.g. ``3-mavsum · 12–14-qismlar``."""
	seasons = sorted({part.season_number for part in parts if part.season_number is not None})
	numbers = sorted({part.number for part in parts})
	prefix = ""
	if len(seasons) == 1 and all(part.season_number == seasons[0] for part in parts):
		prefix = f"{seasons[0]}-mavsum · "
	if len(numbers) == 1:
		return f"{prefix}{numbers[0]}-qism"
	if numbers == list(range(numbers[0], numbers[-1] + 1)):
		return f"{prefix}{numbers[0]}–{numbers[-1]}-qismlar"
	return prefix + "Yangi qismlar: " + ", ".join(str(number) for number in numbers)


def batch_announcement_text(title: MediaTitle, parts: Sequence[MediaPart]) -> str:
	lines: List[str] = [
		f"🆕 <b>{escape_html(title.title)}</b>",
		f"🎞 {escape_html(parts_range_label(parts))}",
		f"🆔 Kod: <code>{title.code}</code>",
		f"📺 Turi: {title.get_type_display()}",
		f"⭐ Reyting: {title.rating}/10",
	]
	lines.append("")
	lines.append("▶️ Tomosha qilish uchun pastdagi tugmani bosing.")
	return "\n".join(lines)


async def publish_parts(
	bot: Bot,
	title: MediaTitle,
	parts: Sequence[MediaPart],
	*,
	channel: Optional[TelegramChannel] = None,
) -> Optional[int]:
	"""Announce a batch of freshly added episodes with one tidy public post.

	A single post per save (instead of one per file) keeps the channel readable
	when an administrator uploads a whole season at once. The message carries a
	``?start=<type>_<code>`` deep link so anyone can tap it and watch from the
	bot.
	"""
	parts = [part for part in parts if part is not None]
	if not parts:
		return None
	target = await resolve_publish_channel(channel)
	if target is None:
		logger.info("Batch publish skipped for %s: no public channel selected.", title.pk)
		return None

	username = await bot_username(bot)
	caption = batch_announcement_text(title, parts)
	keyboard = _deep_link_keyboard(username, title)
	cover = _cover_file(title)

	try:
		if cover is not None:
			message = await bot.send_photo(
				chat_id=target.chat_id, photo=cover, caption=caption, reply_markup=keyboard
			)
		else:
			message = await bot.send_message(
				chat_id=target.chat_id,
				text=caption,
				reply_markup=keyboard,
				disable_web_page_preview=True,
			)
	except (TelegramBadRequest, TelegramForbiddenError) as exc:
		logger.warning("Batch publishing to channel %s failed: %s", target.chat_id, exc)
		return None
	except TelegramAPIError as exc:  # pragma: no cover - network failure
		logger.warning("Batch publishing to channel %s errored: %s", target.chat_id, exc)
		return None
	return message.message_id


async def publish_all_parts(bot: Bot, title: MediaTitle) -> int:
	"""Post one announcement per episode (used right after bulk episode import)."""
	settings = await get_settings()
	if not settings.auto_publish_new_content:
		return 0
	count = 0
	for part in await title_parts(title):
		if await publish_title(bot, title, part=part):
			count += 1
	return count
