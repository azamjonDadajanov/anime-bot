"""Publishing announcements and new episodes to public channels."""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup

from movies.models import MediaPart, MediaTitle, TelegramChannel

from ..texts import COUPON_POST, GIVEAWAY_POST, GIVEAWAY_POST_NO_CONDITIONS
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


def _genres_text_sync(title: MediaTitle) -> str:
	"""Comma-joined genre names; runs off the event loop through ``to_async``."""
	return ", ".join(title.genres.values_list("name", flat=True)) or "—"


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


def _deep_link_keyboard(
	bot_username_value: str, title: MediaTitle, *, text: Optional[str] = None
) -> Optional[InlineKeyboardMarkup]:
	link = deep_link(bot_username_value, deep_link_payload(title))
	if not link:
		return None
	label = text or ("📖 O'qish" if title.type == MediaTitle.MediaType.MANGA else "▶️ Tomosha qilish")
	return InlineKeyboardMarkup(
		inline_keyboard=[[InlineKeyboardButton(text=label, url=link)]]
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


async def resolve_target_channel(
	title: MediaTitle,
	*,
	is_completed: bool = False,
	channel: Optional[TelegramChannel] = None,
) -> Optional[TelegramChannel]:
	"""Select destination channel based on content type (media vs manga) and status (ongoing vs completed)."""
	if channel is not None:
		return channel
	settings = await get_settings()
	from .channels import get_channel

	is_manga = (title.type == MediaTitle.MediaType.MANGA)
	target_id = None
	if is_manga:
		if is_completed:
			target_id = (
				getattr(settings, "manga_completed_channel_id", None)
				or getattr(settings, "manga_channel_id", None)
				or getattr(settings, "completed_channel_id", None)
				or settings.publish_channel_id
			)
		else:
			target_id = (
				getattr(settings, "manga_channel_id", None)
				or getattr(settings, "ongoing_channel_id", None)
				or settings.publish_channel_id
			)
	else:
		if is_completed:
			target_id = (
				getattr(settings, "completed_channel_id", None)
				or settings.publish_channel_id
			)
		else:
			target_id = (
				getattr(settings, "ongoing_channel_id", None)
				or settings.publish_channel_id
			)

	if not target_id:
		return None
	return await get_channel(target_id)


async def _send_to_channel(
	bot: Bot,
	target: TelegramChannel,
	title: MediaTitle,
	caption: str,
	*,
	button_text: Optional[str] = None,
) -> Optional[int]:
	username = await bot_username(bot)
	keyboard = _deep_link_keyboard(username, title, text=button_text)
	cover = _cover_file(title)

	try:
		if cover is not None:
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
		return message.message_id
	except (TelegramBadRequest, TelegramForbiddenError) as exc:
		logger.warning("Publishing to channel %s failed: %s", target.chat_id, exc)
		return None
	except TelegramAPIError as exc:  # pragma: no cover - network failure
		logger.warning("Publishing to channel %s errored: %s", target.chat_id, exc)
		return None


async def publish_title(
	bot: Bot,
	title: MediaTitle,
	*,
	channel: Optional[TelegramChannel] = None,
	part: Optional[MediaPart] = None,
	genres: str = "",
) -> Optional[int]:
	"""Post a title (or a new episode) to the appropriate channel."""
	if part is not None:
		return await publish_parts_by_rules(bot, title, [part], channel=channel)

	is_completed = (
		title.status == MediaTitle.Status.COMPLETED or title.type == MediaTitle.MediaType.MOVIE
	)
	if is_completed:
		return await publish_completed_title(bot, title, channel=channel, genres=genres)

	target = await resolve_target_channel(title, is_completed=False, channel=channel)
	if target is None:
		logger.info("Auto-publish skipped for %s: no channel selected.", title.pk)
		return None

	if not genres:
		genres = await to_async(_genres_text_sync)(title)
	caption = announcement_text(title, part=None, genres=genres)
	btn_label = "📖 O'qish" if title.type == MediaTitle.MediaType.MANGA else "▶️ Ko'rish"
	message_id = await _send_to_channel(bot, target, title, caption, button_text=btn_label)
	if message_id is not None:
		title.metadata_channel = target
		title.metadata_message_id = message_id
		await to_async(title.save)(
			update_fields=["metadata_channel", "metadata_message_id", "updated_at"]
		)
	return message_id


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


def giveaway_post_text(giveaway) -> str:
	"""Channel announcement for an administrator-run raffle."""
	conditions = []
	if giveaway.min_bot_views:
		conditions.append(f"botda ≥ {giveaway.min_bot_views} anime")
	if giveaway.require_channels:
		conditions.append("homiy kanallarga obuna")
	if giveaway.require_bio_ref:
		conditions.append("bio'da referral havola")
	conditions_text = (
		"📌 Shartlar: " + ", ".join(conditions)
		if conditions
		else GIVEAWAY_POST_NO_CONDITIONS
	)
	return GIVEAWAY_POST.format(
		title=escape_html(giveaway.title),
		days=giveaway.reward_days,
		winners=giveaway.winner_count,
		conditions=conditions_text,
	)


async def publish_giveaway(bot: Bot, giveaway, *, channel: Optional[TelegramChannel] = None) -> Optional[int]:
	"""Post a giveaway to the public channel and return the message id."""
	target = await resolve_publish_channel(channel)
	if target is None:
		logger.info("Giveaway %s was not published: no public channel selected.", giveaway.pk)
		return None

	username = await bot_username(bot)
	keyboard = None
	if username:
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[InlineKeyboardButton(text="🎁 Qatnashish", url=f"https://t.me/{username}")]
			]
		)
	text = giveaway_post_text(giveaway)
	try:
		message = await bot.send_message(
			chat_id=target.chat_id,
			text=text,
			reply_markup=keyboard,
			disable_web_page_preview=True,
		)
	except (TelegramBadRequest, TelegramForbiddenError) as exc:
		logger.warning("Publishing giveaway %s to %s failed: %s", giveaway.pk, target.chat_id, exc)
		return None
	except TelegramAPIError as exc:  # pragma: no cover - network failure
		logger.warning("Publishing giveaway %s to %s errored: %s", giveaway.pk, target.chat_id, exc)
		return None
	return message.message_id


async def maybe_auto_publish_coupon(bot: Bot, coupon) -> Optional[int]:
	"""Post a coupon to the public channel when auto-publishing is on."""
	settings = await get_settings()
	if not settings.auto_publish_new_content:
		return None
	return await publish_coupon(bot, coupon)


async def maybe_auto_publish_giveaway(bot: Bot, giveaway) -> Optional[int]:
	"""Post a giveaway to the public channel when auto-publishing is on."""
	settings = await get_settings()
	if not settings.auto_publish_new_content:
		return None
	return await publish_giveaway(bot, giveaway)


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


def completed_announcement_text(title: MediaTitle, *, genres: str = "") -> str:
	genres = genres or "—"
	type_emoji = {
		"anime": "🎌",
		"movie": "🎬",
		"series": "📺",
		"manga": "📖",
		"podcast": "🎙",
	}.get(title.type, "🎬")
	action_text = "Mutolaa qilish" if title.type == MediaTitle.MediaType.MANGA else "Ko'rish"

	lines: List[str] = [
		f"✅ <b>{escape_html(title.title)}</b> (Tugallandi)",
		"",
		f"🆔 Kod: <code>{title.code}</code>",
		f"{type_emoji} Turi: {title.get_type_display()}",
		f"🎭 Janr: {escape_html(genres)}",
		f"🌐 Til: {escape_html(title.language)}",
		f"⭐ Reyting: {title.rating}/10",
		f"📊 Holat: {title.get_status_display()}",
	]
	if title.episode_count:
		unit = "bob" if title.type == MediaTitle.MediaType.MANGA else "qism"
		lines.append(f"🔢 Jami: {title.episode_count} {unit}")
	if title.synopsis:
		lines.append("")
		lines.append(escape_html(title.synopsis)[:300])
	lines.append("")
	lines.append(f"▶️ {action_text} uchun pastdagi tugmani bosing.")
	return "\n".join(lines)


def ongoing_announcement_text(
	title: MediaTitle, parts: Sequence[MediaPart], *, genres: str = ""
) -> str:
	genres = genres or "—"
	type_emoji = {
		"anime": "🎌",
		"movie": "🎬",
		"series": "📺",
		"manga": "📖",
		"podcast": "🎙",
	}.get(title.type, "🎬")
	action_text = "Mutolaa qilish" if title.type == MediaTitle.MediaType.MANGA else "Ko'rish"
	range_label = parts_range_label(parts) if parts else ""

	lines: List[str] = [
		f"🆕 <b>{escape_html(title.title)}</b>",
	]
	if range_label:
		lines.append(f"🎞 {escape_html(range_label)}")
	lines.extend([
		"",
		f"🆔 Kod: <code>{title.code}</code>",
		f"{type_emoji} Turi: {title.get_type_display()}",
		f"🎭 Janr: {escape_html(genres)}",
		f"🌐 Til: {escape_html(title.language)}",
		f"⭐ Reyting: {title.rating}/10",
		f"📊 Holat: {title.get_status_display()}",
	])
	if title.synopsis:
		lines.append("")
		lines.append(escape_html(title.synopsis)[:300])
	lines.append("")
	lines.append(f"▶️ {action_text} uchun pastdagi tugmani bosing.")
	return "\n".join(lines)


def batch_announcement_text(title: MediaTitle, parts: Sequence[MediaPart]) -> str:
	return ongoing_announcement_text(title, parts)


async def publish_completed_title(
	bot: Bot,
	title: MediaTitle,
	*,
	channel: Optional[TelegramChannel] = None,
	genres: str = "",
) -> Optional[int]:
	"""Tugallangan media (anime/kino/serial/manga) uchun tugallanganlar kanaliga e'lon berish."""
	target = await resolve_target_channel(title, is_completed=True, channel=channel)
	if target is None:
		logger.info("Publish completed skipped for %s: no channel selected.", title.pk)
		return None

	if not genres:
		genres = await to_async(_genres_text_sync)(title)
	caption = completed_announcement_text(title, genres=genres)
	btn_label = "📖 O'qish" if title.type == MediaTitle.MediaType.MANGA else "▶️ Ko'rish"

	message_id = await _send_to_channel(bot, target, title, caption, button_text=btn_label)
	if message_id is not None:
		title.metadata_channel = target
		title.metadata_message_id = message_id
		await to_async(title.save)(
			update_fields=["metadata_channel", "metadata_message_id", "updated_at"]
		)
	return message_id


async def publish_ongoing_parts(
	bot: Bot,
	title: MediaTitle,
	parts: Sequence[MediaPart],
	*,
	channel: Optional[TelegramChannel] = None,
	genres: str = "",
) -> Optional[int]:
	"""Ongoing media (anime/serial/manga) yangi qismlari uchun ongoing kanalga e'lon berish."""
	parts = [p for p in parts if p is not None]
	if not parts:
		return None
	target = await resolve_target_channel(title, is_completed=False, channel=channel)
	if target is None:
		logger.info("Publish ongoing skipped for %s: no channel selected.", title.pk)
		return None

	if not genres:
		genres = await to_async(_genres_text_sync)(title)
	caption = ongoing_announcement_text(title, parts, genres=genres)
	btn_label = "📖 O'qish" if title.type == MediaTitle.MediaType.MANGA else "▶️ Ko'rish"

	return await _send_to_channel(bot, target, title, caption, button_text=btn_label)


async def publish_parts_by_rules(
	bot: Bot,
	title: MediaTitle,
	parts: Sequence[MediaPart],
	*,
	channel: Optional[TelegramChannel] = None,
) -> Optional[int]:
	"""Medialarga qism qo'shilgandagi e'lon logikasi:
	1. Tugallangan media yoki kinoga qism qo'shilganda:
	   media fayllar uni qismlariga teng bo'lganda tugallanganlar kanaliga yuboriladi.
	2. Ongoing medialar tugallanganda (qismlari to'lganda):
	   tugallanganlar kanaliga cover image, ozgincha ma'lumot va ko'rish tugmasi bilan joylanadi.
	3. Ongoing medialarda har bir qism qo'shilgandan so'ng:
	   ongoing medialar kanaliga joylanadi.
	4. Mangalar esa mangalar kanaliga joylanadi (ongoing va tugallangan).
	"""
	parts = [p for p in parts if p is not None]
	if not parts:
		return None

	# Reload title from DB to get fresh status and values
	title = await to_async(MediaTitle.objects.get)(pk=title.pk)
	total_parts = await to_async(title.parts.count)()

	is_movie = (title.type == MediaTitle.MediaType.MOVIE)
	is_completed_initially = (title.status == MediaTitle.Status.COMPLETED)

	expected_count = title.episode_count
	if is_movie and (expected_count is None or expected_count == 0):
		expected_count = 1

	if is_movie or is_completed_initially:
		# Tugallangan media yoki kino
		if expected_count is not None:
			if total_parts >= expected_count:
				return await publish_completed_title(bot, title, channel=channel)
			else:
				logger.info(
					"Title %s (%s) parts count (%s) < expected (%s). Post skipped until complete.",
					title.pk, title.title, total_parts, expected_count
				)
				return None
		else:
			return await publish_completed_title(bot, title, channel=channel)

	# Ongoing yoki upcoming
	if expected_count is not None and total_parts >= expected_count:
		# Ongoing media tugallandi!
		title.status = MediaTitle.Status.COMPLETED
		await to_async(title.save)(update_fields=["status", "updated_at"])
		return await publish_completed_title(bot, title, channel=channel)
	else:
		return await publish_ongoing_parts(bot, title, parts, channel=channel)


async def publish_parts(
	bot: Bot,
	title: MediaTitle,
	parts: Sequence[MediaPart],
	*,
	channel: Optional[TelegramChannel] = None,
) -> Optional[int]:
	"""Announce freshly added episode(s) respecting completion and media type rules."""
	return await publish_parts_by_rules(bot, title, parts, channel=channel)


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
