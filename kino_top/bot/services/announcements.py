"""One-off announcements of a title.

Both administrator panels (the website panel and the in-bot panel) post the
same message when the operator presses «📢 E'lon qilish»: a cover image with

    title
    qismlar (the announced episode(s))
    reyting
    davomiyligi
    qism/umumiy qism
    sifat

and one button that opens the bot on that very title's ``/start`` deep link.

The message may go to the channel, to every bot user, or to both at once;
:func:`send_announcement` is the single entry point for all three. The channel
rules are the publishing ones (:func:`resolve_target_channels`), so an ongoing
title lands in its section's Ongoing channel, a finished one in Tugagan and a
paid one in VIP without the operator picking anything.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.enums import ParseMode
from movies.models import MediaPart, MediaTitle

from ..utils import chunked, deep_link, escape_html, to_async
from .broadcast import RateLimiter
from .bot_settings import get_settings
from .media import title_parts_sync
from .publishing import (
	bot_username,
	cover_input_file,
	deep_link_payload,
	parts_range_label,
	resolve_target_channels,
)
from .users import recipients_sync

logger = logging.getLogger(__name__)

# ``last`` announces only the newest episode (the ongoing case), ``all``
# announces the whole run at once (a finished title, or a full re-announce).
SCOPE_LAST = "last"
SCOPE_ALL = "all"
SCOPES = (SCOPE_LAST, SCOPE_ALL)

WATCH_LABEL = "▶️ Tomosha qilish"
READ_LABEL = "📖 O'qish"

# Four Telegram requests in flight per concurrency slot, like the broadcast
# engine: enough to keep the rate limiter busy without a huge gather().
BATCH_MULTIPLIER = 4


@dataclass
class AnnouncementResult:
	"""What the announcement actually did (read by both panels)."""

	channel_message_id: Optional[int] = None
	channel_error: str = ""
	users_total: int = 0
	users_sent: int = 0
	users_failed: int = 0

	@property
	def channel_sent(self) -> bool:
		return self.channel_message_id is not None


def watch_label(title: MediaTitle) -> str:
	return READ_LABEL if title.type == MediaTitle.MediaType.MANGA else WATCH_LABEL


# ------------------------------------------------------------------- selection
def announcement_parts_sync(title: MediaTitle, scope: str = SCOPE_LAST) -> Tuple[List[MediaPart], int]:
	"""``(announced parts, total parts)`` for ``scope``.

	``last`` keeps only the newest episode; ``all`` keeps the whole run. The
	total is always the number of episodes that exist, so «12/24» stays honest
	even when only the last episode is announced.
	"""
	parts = title_parts_sync(title)
	if scope == SCOPE_ALL:
		return parts, len(parts)
	return parts[-1:], len(parts)


# -------------------------------------------------------------------- message
def announcement_caption(
	title: MediaTitle,
	parts: Sequence[MediaPart],
	*,
	total_parts: Optional[int] = None,
) -> str:
	"""The announcement body: the fields the operators asked for, in order."""
	announced = [part for part in parts if part is not None]
	total = total_parts if total_parts is not None else (title.episode_count or len(announced))

	lines: List[str] = [f"🎬 <b>{escape_html(title.title)}</b>"]
	if announced:
		lines.append(f"🎞 Qismlar: {escape_html(parts_range_label(announced))}")
	lines.append(f"⭐ Reyting: {title.rating}/10")
	if title.duration_minutes:
		lines.append(f"⏱ Davomiyligi: {title.duration_minutes} daqiqa")
	else:
		lines.append("⏱ Davomiyligi: —")
	numbers = sorted({part.number for part in announced})
	if numbers and total:
		lines.append(f"🔢 Qism: {numbers[-1]}/{total}")
	quality = ", ".join(title.quality_options or []) or title.default_quality
	if quality:
		lines.append(f"💎 Sifat: {escape_html(quality)}")
	lines.append("")
	lines.append(f"{watch_label(title)} uchun pastdagi tugmani bosing.")
	return "\n".join(lines)


def announcement_keyboard(
	bot_username_value: str, title: MediaTitle
) -> Optional[InlineKeyboardMarkup]:
	"""The single «Tomosha qilish» button opening the bot on this title.

	The URL is the bot's own ``?start=`` deep link, exactly like the channel
	posts in :mod:`bot.services.publishing`; without a resolvable username the
	message simply goes out without a button.
	"""
	link = deep_link(bot_username_value, deep_link_payload(title))
	if not link:
		return None
	return InlineKeyboardMarkup(
		inline_keyboard=[[InlineKeyboardButton(text=watch_label(title), url=link)]]
	)


async def _send_message(
	bot: Bot,
	chat_id: int,
	caption: str,
	keyboard: Optional[InlineKeyboardMarkup],
	cover: Optional[BufferedInputFile],
) -> Optional[int]:
	"""Send one announcement; ``None`` means Telegram refused it."""
	try:
		if cover is not None:
			message = await bot.send_photo(
				chat_id=chat_id,
				photo=cover,
				caption=caption,
				reply_markup=keyboard,
				parse_mode=ParseMode.HTML
			)
		else:
			message = await bot.send_message(
				chat_id=chat_id,
				text=caption,
				reply_markup=keyboard,
				disable_web_page_preview=True,
			)
		return message.message_id
	except (TelegramBadRequest, TelegramForbiddenError) as exc:
		logger.warning("Announcement to %s was refused: %s", chat_id, exc)
		return None
	except TelegramAPIError as exc:  # pragma: no cover - network failure
		logger.warning("Announcement to %s errored: %s", chat_id, exc)
		return None


async def send_to_channel(
	bot: Bot,
	title: MediaTitle,
	*,
	caption: str,
	keyboard: Optional[InlineKeyboardMarkup],
	cover: Optional[BufferedInputFile],
	channel=None,
) -> Tuple[Optional[int], str]:
	"""Post to every channel the publishing rules point at; ``(id, error)``."""
	is_completed = (
		title.status == MediaTitle.Status.COMPLETED
		or title.type == MediaTitle.MediaType.MOVIE
	)
	targets = await resolve_target_channels(
		title, is_completed=is_completed, channel=channel
	)
	if not targets:
		return None, (
			"E'lon kanali tanlanmagan. «Kanallar» bo'limida shu turdagi kanalni "
			"qo'shing yoki asosiy e'lon kanalini belgilang."
		)

	first_message_id: Optional[int] = None
	first_target = None
	for target in targets:
		message_id = await _send_message(bot, target.chat_id, caption, keyboard, cover)
		if message_id is None:
			continue
		if first_message_id is None:
			first_message_id, first_target = message_id, target
	if first_message_id is None:
		titles = ", ".join(f"«{target.title}»" for target in targets)
		return None, (
			f"Telegram {titles} kanaliga e'lonni qabul qilmadi. "
			"Bot kanalda administrator ekanini tekshiring."
		)
	# Remember where the title was announced, like the existing publisher does.
	title.metadata_channel = first_target
	title.metadata_message_id = first_message_id
	await to_async(title.save)(
		update_fields=["metadata_channel", "metadata_message_id", "updated_at"]
	)
	return first_message_id, ""


async def send_to_users(
	bot: Bot,
	*,
	caption: str,
	keyboard: Optional[InlineKeyboardMarkup],
	cover: Optional[BufferedInputFile],
	recipients: Optional[Sequence[int]] = None,
	rate: Optional[int] = None,
	concurrency: Optional[int] = None,
) -> Tuple[int, int]:
	"""Deliver the announcement to every bot user; ``(sent, failed)``."""
	settings = await get_settings()
	rate_value = int(rate or settings.broadcast_rate_per_second or 25)
	concurrency_value = max(1, int(concurrency or settings.broadcast_concurrency or 5))

	if recipients is None:
		recipients = await to_async(recipients_sync)(include_blocked=False)
	telegram_ids = [int(value) for value in recipients]
	if not telegram_ids:
		return 0, 0

	limiter = RateLimiter(rate_value)
	semaphore = asyncio.Semaphore(concurrency_value)

	async def handle(chat_id: int) -> bool:
		async with semaphore:
			await limiter.acquire()
			return await _send_message(bot, chat_id, caption, keyboard, cover) is not None

	sent = failed = 0
	for batch in chunked(telegram_ids, max(1, concurrency_value * BATCH_MULTIPLIER)):
		results = await asyncio.gather(*(handle(chat_id) for chat_id in batch))
		for delivered in results:
			if delivered:
				sent += 1
			else:
				failed += 1
	logger.info(
		"Announcement finished: sent=%s failed=%s of %s users.",
		sent,
		failed,
		len(telegram_ids),
	)
	return sent, failed


async def send_announcement(
	bot: Bot,
	title: MediaTitle,
	*,
	scope: str = SCOPE_LAST,
	to_channel: bool = False,
	to_users: bool = False,
	parts: Optional[Sequence[MediaPart]] = None,
	total_parts: Optional[int] = None,
	channel=None,
	recipients: Optional[Sequence[int]] = None,
	rate: Optional[int] = None,
	concurrency: Optional[int] = None,
) -> AnnouncementResult:
	"""Announce ``title`` to the public channel and/or every bot user."""
	scope = scope if scope in SCOPES else SCOPE_LAST
	if parts is None or total_parts is None:
		selected, total = await to_async(announcement_parts_sync)(title, scope)
		parts = selected if parts is None else parts
		total_parts = total if total_parts is None else total_parts

	caption = announcement_caption(title, parts, total_parts=total_parts)
	keyboard = announcement_keyboard(await bot_username(bot), title)
	cover = cover_input_file(title)

	result = AnnouncementResult()
	if to_channel:
		message_id, error = await send_to_channel(
			bot,
			title,
			caption=caption,
			keyboard=keyboard,
			cover=cover,
			channel=channel,
			
		)
		result.channel_message_id = message_id
		result.channel_error = error
	if to_users:
		# Resolve the audience once: the counter and the delivery must see the
		# same list, even when users register while the announcement runs.
		if recipients is None:
			recipients = await to_async(recipients_sync)(include_blocked=False)
		result.users_total = len(recipients)
		result.users_sent, result.users_failed = await send_to_users(
			bot,
			caption=caption,
			keyboard=keyboard,
			cover=cover,
			recipients=recipients,
			rate=rate,
			concurrency=concurrency,
		)
	return result
