"""Catalog management and Telegram media delivery.

``MediaTitle`` holds anime/movies, ``MediaPart`` holds episodes/chapters and
``TelegramMedia`` holds the Telegram ``file_id`` references. This module is the
only place that reads or writes them, so the REST API, the bot handlers and the
tests all share the same behaviour.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InputMediaDocument, InputMediaPhoto, InputMediaVideo
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.template.defaultfilters import slugify
from django.utils import timezone

from movies.models import Genre, MediaPart, MediaTitle, MediaView, TelegramChannel, TelegramMedia

from ..texts import WATCH_PARTS_HINT
from ..utils import to_async

logger = logging.getLogger(__name__)

PHOTO_LIMIT = 10


class MediaUnavailable(Exception):
	"""Raised when no stored file reference can be delivered."""


class MediaNotEditable(Exception):
	"""Raised when an already-sent message cannot show a part (see
	:func:`edit_part_media`). The caller falls back to a fresh message."""


# --------------------------------------------------------------------- reading
def title_by_code_sync(code: str) -> Optional[MediaTitle]:
	code = str(code or "").strip()
	if not code.isdigit():
		return None
	return MediaTitle.objects.filter(code=code).first()


def title_by_pk_sync(pk: int) -> Optional[MediaTitle]:
	return MediaTitle.objects.filter(pk=pk).first()


def title_by_slug_sync(slug: str) -> Optional[MediaTitle]:
	return MediaTitle.objects.filter(slug=slug).first()


def part_by_pk_sync(pk: int) -> Optional[MediaPart]:
	return MediaPart.objects.select_related("content").filter(pk=pk).first()


def media_by_pk_sync(pk: int) -> Optional[TelegramMedia]:
	return TelegramMedia.objects.select_related("part", "part__content", "channel").filter(pk=pk).first()


get_title_by_code = to_async(title_by_code_sync)
get_title_by_pk = to_async(title_by_pk_sync)


def record_media_view_sync(
	user_id: Optional[int],
	title_id: int,
	part_id: Optional[int] = None,
) -> None:
	"""Store a bot-side watch/read event for the website profile pages."""
	if not user_id:
		return
	from django.contrib.auth import get_user_model

	user = get_user_model().objects.filter(pk=user_id).first()
	title = title_by_pk_sync(title_id)
	if user is None or title is None:
		return
	part = MediaPart.objects.filter(pk=part_id).first() if part_id else None
	MediaView.record(user, title, part=part, source=MediaView.Source.BOT)


record_media_view = to_async(record_media_view_sync)
get_title_by_slug = to_async(title_by_slug_sync)
get_part_by_pk = to_async(part_by_pk_sync)
get_media_by_pk = to_async(media_by_pk_sync)


def search_titles_sync(
	query: str = "",
	*,
	media_type: str = "",
	genre: str = "",
	status: str = "",
	limit: Optional[int] = None,
) -> List[MediaTitle]:
	queryset = MediaTitle.objects.prefetch_related("genres")
	query = (query or "").strip()
	if query:
		if query.isdigit():
			queryset = queryset.filter(Q(code=query) | Q(title__icontains=query))
		else:
			queryset = queryset.filter(title__icontains=query)
	if media_type:
		queryset = queryset.filter(type=media_type)
	if genre:
		queryset = queryset.filter(genres__name__iexact=genre)
	if status:
		queryset = queryset.filter(status=status)
	queryset = queryset.order_by("title").distinct()
	if limit:
		queryset = queryset[:limit]
	return list(queryset)


search_titles = to_async(search_titles_sync)


# The AI search lives in ``movies.ai_search`` (shared with the website) and is
# exposed here so handlers keep talking to the service layer only.
AI_SEARCH_LIMIT = 10
# How much of the user's taste the AI context may carry. The context rides on
# two model calls, so it stays a few short lines — enough for "oxshashini ayt",
# not enough to bloat every request.
AI_CONTEXT_FAVORITES_LIMIT = 8
AI_CONTEXT_VIEWS_LIMIT = 5


def _context_line(title: MediaTitle) -> str:
	genres = ", ".join(genre.name for genre in title.genres.all()[:3])
	parts = [title.get_type_display().lower()]
	if genres:
		parts.append(genres)
	return "(" + ", ".join(parts) + ")"


def ai_user_context_sync(profile: Any) -> str:
	"""A compact block about the user's taste for the AI (empty when unknown).

	Favourites first (newest), then the last watched/read titles. Both are
	opt-in: the caller only builds this when the user asked for it.
	"""
	if profile is None:
		return ""
	lines: List[str] = []
	favorites = list(
		profile.content_favorites.select_related("content")
		.prefetch_related("content__genres")
		.order_by("-created_at")[:AI_CONTEXT_FAVORITES_LIMIT]
	)
	if favorites:
		items = ", ".join(
			f"{row.content.title[:40]} {_context_line(row.content)}"
			for row in favorites
		)
		lines.append(f"Sevimlilar: {items}")
	auth_user = getattr(profile, "auth_user", None)
	if auth_user is not None:
		views = list(
			auth_user.media_views.select_related("title")
			.prefetch_related("title__genres")
			.order_by("-updated_at")[:AI_CONTEXT_VIEWS_LIMIT]
		)
		if views:
			seen = {row.content_id for row in favorites}
			items = ", ".join(
				f"{row.title.title[:40]} {_context_line(row.title)}"
				for row in views
				if row.title_id not in seen
			)
			if items:
				lines.append(f"Oxirgi ko'rganlari: {items}")
	return "\n".join(lines)


ai_user_context = to_async(ai_user_context_sync)


def ai_search_answer_sync(
	query: str, *, limit: int = AI_SEARCH_LIMIT, context: str = ""
) -> Dict[str, Any]:
	"""Find titles by meaning and explain the picks (raises EmbeddingUnavailable).

	Returns everything the handler renders: the ranked hits, how many titles
	matched in total, and the reasoning model's answer (empty when no model is
	configured or the call failed — the search still has an answer then).
	``context`` is the optional user-taste block (see :func:`ai_user_context_sync`).
	"""
	from movies import ai_reasoning

	from ..config import site_url

	answer = ai_reasoning.answer_search(query, limit=limit, context=context)
	return {
		"query": answer.query,
		"items": [hit.as_dict(site_url=site_url()) for hit in answer.hits],
		"total": answer.total,
		"text": answer.answer,
		"thinking": answer.thinking,
		"reasoning": answer.used_llm,
		"conversational": answer.conversational,
	}


ai_search_answer = to_async(ai_search_answer_sync)


def titles_by_type_sync(media_type: str, *, limit: Optional[int] = None) -> List[MediaTitle]:
	return search_titles_sync(media_type=media_type, limit=limit)


titles_by_type = to_async(titles_by_type_sync)


def all_titles_sync(*, limit: Optional[int] = None) -> List[MediaTitle]:
	return search_titles_sync(limit=limit)


all_titles = to_async(all_titles_sync)


def all_genres_sync() -> List[Genre]:
	return list(Genre.objects.order_by("name"))


all_genres = to_async(all_genres_sync)


def genre_by_pk_sync(pk: int) -> Optional[Genre]:
	return Genre.objects.filter(pk=pk).first()


get_genre_by_pk = to_async(genre_by_pk_sync)


def title_parts_sync(title: MediaTitle) -> List[MediaPart]:
	return list(
		MediaPart.objects.filter(content=title).order_by("season_number", "number")
	)


title_parts = to_async(title_parts_sync)


def part_media_sync(part: MediaPart) -> List[TelegramMedia]:
	return list(
		TelegramMedia.objects.filter(part=part).select_related("channel").order_by("order")
	)


part_media = to_async(part_media_sync)


def seasons_sync(title: MediaTitle) -> List[Optional[int]]:
	values = (
		MediaPart.objects.filter(content=title)
		.values_list("season_number", flat=True)
		.distinct()
	)
	return sorted(values, key=lambda value: (value is None, value or 0))


seasons = to_async(seasons_sync)


def next_media_order_sync(part: MediaPart) -> int:
	last = TelegramMedia.objects.filter(part=part).order_by("-order").values_list("order", flat=True).first()
	return int(last or 0) + 1


next_media_order = to_async(next_media_order_sync)


# --------------------------------------------------------------------- writing
def _unique_slug_sync(title: str, media_type: str) -> str:
	base = slugify(f"{title}-{media_type}") or f"media-{timezone.now().timestamp():.0f}"
	candidate = base[:200]
	suffix = 2
	while MediaTitle.objects.filter(slug=candidate).exists():
		candidate = f"{base[:195]}-{suffix}"
		suffix += 1
	return candidate


def assign_genres_sync(title: MediaTitle, names: Sequence[str]) -> List[str]:
	cleaned: List[str] = []
	for raw in names:
		name = str(raw or "").strip()[:50]
		if name and name.lower() not in {item.lower() for item in cleaned}:
			cleaned.append(name)
	genres = []
	for name in cleaned:
		genre, _ = Genre.objects.get_or_create(name=name)
		genres.append(genre)
	title.genres.set(genres)
	return [genre.name for genre in genres]


assign_genres = to_async(assign_genres_sync)


def create_title_sync(
	*,
	media_type: str,
	title: str,
	synopsis: str = "",
	required_plan: str = MediaTitle.AccessPlan.FREE,
	language: str = "O'zbekcha",
	quality_options: Optional[Sequence[str]] = None,
	default_quality: str = "1080",
	status: str = MediaTitle.Status.UPCOMING,
	rating: int = 5,
	release_year: Optional[int] = None,
	episode_count: Optional[int] = None,
	genres: Optional[Sequence[str]] = None,
	cover: Optional[bytes] = None,
	cover_content_type: str = "",
) -> MediaTitle:
	if media_type not in MediaTitle.MediaType.values:
		raise ValueError(f"Unknown media type: {media_type!r}")
	if required_plan not in MediaTitle.AccessPlan.values:
		raise ValueError(f"Unknown access plan: {required_plan!r}")
	if status not in MediaTitle.Status.values:
		raise ValueError(f"Unknown status: {status!r}")

	qualities = [str(item).strip() for item in (quality_options or []) if str(item).strip()]
	payload: Dict[str, Any] = {
		"type": media_type,
		"title": title[:200],
		"slug": _unique_slug_sync(title, media_type),
		"synopsis": synopsis or "",
		"required_plan": required_plan,
		"language": (language or "O'zbekcha")[:40],
		"quality_options": qualities,
		"default_quality": (default_quality or (qualities[0] if qualities else "1080"))[:20],
		"status": status,
		"rating": max(1, min(10, int(rating or 5))),
		"release_year": release_year,
		"episode_count": episode_count,
	}
	if cover:
		payload["cover"] = bytes(cover)
		payload["cover_content_type"] = cover_content_type[:50]
	media = MediaTitle(**payload)
	media.save()
	if genres:
		assign_genres_sync(media, genres)
	return media


create_title = to_async(create_title_sync)

CONTENT_EDITABLE_FIELDS = {
	"title",
	"synopsis",
	"language",
	"default_quality",
	"quality_options",
	"required_plan",
	"status",
	"rating",
	"release_year",
	"episode_count",
	"cover",
	"cover_content_type",
	"type",
}


def update_title_sync(title: MediaTitle, **fields: Any) -> MediaTitle:
	changed = []
	for name, value in fields.items():
		if name not in CONTENT_EDITABLE_FIELDS:
			continue
		if name == "required_plan" and value not in MediaTitle.AccessPlan.values:
			raise ValueError(f"Unknown access plan: {value!r}")
		if name == "status" and value not in MediaTitle.Status.values:
			raise ValueError(f"Unknown status: {value!r}")
		if name == "type" and value not in MediaTitle.MediaType.values:
			raise ValueError(f"Unknown media type: {value!r}")
		if name == "rating" and value is not None:
			value = max(1, min(10, int(value)))
		if name == "quality_options" and value is not None:
			value = [str(item).strip() for item in value if str(item).strip()]
		if name == "cover" and value is not None:
			value = bytes(value)
		if getattr(title, name) != value:
			setattr(title, name, value)
			changed.append(name)
	if changed:
		title.save(update_fields=changed + ["updated_at"])
	return title


update_title = to_async(update_title_sync)


def delete_title_sync(title: MediaTitle) -> None:
	title.delete()


delete_title = to_async(delete_title_sync)


def upsert_part_sync(
	content: MediaTitle,
	*,
	season_number: Optional[int],
	number: int,
	title: str = "",
) -> Tuple[MediaPart, bool]:
	part, created = MediaPart.objects.get_or_create(
		content=content,
		season_number=season_number,
		number=number,
		defaults={"title": title[:200]},
	)
	if not created and title and part.title != title[:200]:
		part.title = title[:200]
		part.save(update_fields=["title"])
	return part, created


upsert_part = to_async(upsert_part_sync)


def delete_part_sync(part: MediaPart) -> None:
	part.delete()


delete_part = to_async(delete_part_sync)


def add_media_sync(
	part: MediaPart,
	*,
	file_id: str,
	media_type: str,
	channel: Optional[TelegramChannel] = None,
	source_message_id: Optional[int] = None,
	caption: str = "",
	order: Optional[int] = None,
) -> TelegramMedia:
	if media_type not in TelegramMedia.MediaType.values:
		raise ValueError(f"Unknown media type: {media_type!r}")
	if order is None:
		order = next_media_order_sync(part)
	for attempt in range(5):
		try:
			with transaction.atomic():
				return TelegramMedia.objects.create(
					part=part,
					channel=channel,
					source_message_id=source_message_id,
					file_id=file_id[:512],
					media_type=media_type,
					order=order,
					caption=(caption or "")[:1024],
				)
		except IntegrityError:
			# Another writer took this order/source message; retry with the next one.
			order = next_media_order_sync(part)
			if attempt == 4:
				raise
	return TelegramMedia.objects.filter(part=part).order_by("order").last()  # pragma: no cover


add_media = to_async(add_media_sync)


def create_part_with_media_sync(
	content: MediaTitle,
	*,
	season_number: Optional[int],
	file_id: str,
	media_type: str,
	channel: Optional[TelegramChannel] = None,
	source_message_id: Optional[int] = None,
	caption: str = "",
) -> MediaPart:
	"""Create a fresh part holding exactly one media file.

	The bot's episode uploader follows a strict rule: one part, one video/file.
	The part number is derived automatically from the parts already stored in
	``season_number`` — the current count plus one, skipping numbers that a
	previous deletion may have left as a gap — so the administrator never has to
	type a part number.
	"""
	if media_type not in TelegramMedia.MediaType.values:
		raise ValueError(f"Unknown media type: {media_type!r}")
	with transaction.atomic():
		taken = set(
			MediaPart.objects.filter(content=content, season_number=season_number).values_list(
				"number", flat=True
			)
		)
		number = len(taken) + 1
		while number in taken:
			number += 1
		part = MediaPart.objects.create(
			content=content, season_number=season_number, number=number
		)
		TelegramMedia.objects.create(
			part=part,
			channel=channel,
			source_message_id=source_message_id,
			file_id=str(file_id)[:512],
			media_type=media_type,
			order=1,
			caption=(caption or "")[:1024],
		)
	return part


create_part_with_media = to_async(create_part_with_media_sync)


def replace_part_media_sync(part: MediaPart, entries: Sequence[Dict[str, Any]]) -> int:
	"""Replace every stored file of ``part`` with ``entries``."""
	with transaction.atomic():
		TelegramMedia.objects.filter(part=part).delete()
		created = 0
		for index, entry in enumerate(entries, start=1):
			TelegramMedia.objects.create(
				part=part,
				channel=entry.get("channel"),
				source_message_id=entry.get("source_message_id"),
				file_id=str(entry["file_id"])[:512],
				media_type=entry["media_type"],
				order=entry.get("order") or index,
				caption=str(entry.get("caption") or "")[:1024],
			)
			created += 1
	return created


replace_part_media = to_async(replace_part_media_sync)


def delete_media_sync(media: TelegramMedia) -> None:
	media.delete()


delete_media = to_async(delete_media_sync)


def swap_media_order_sync(first: TelegramMedia, second: TelegramMedia) -> None:
	"""Swap the ``order`` of two media rows without violating the constraint."""
	if first.pk == second.pk:
		return
	with transaction.atomic():
		first_order, second_order = first.order, second.order
		# Move one out of the way first to dodge the unique(part, order) index.
		TelegramMedia.objects.filter(pk=first.pk).update(order=0)
		TelegramMedia.objects.filter(pk=second.pk).update(order=first_order)
		TelegramMedia.objects.filter(pk=first.pk).update(order=second_order)


swap_media_order = to_async(swap_media_order_sync)


# ------------------------------------------------------------------- delivery
def select_media_for_delivery_sync(
	part: MediaPart, quality: Optional[str] = None
) -> List[TelegramMedia]:
	"""Pick the delivery candidates for ``part``, best match first.

	* A photo-only part (manga chapter) returns every page in order.
	* Otherwise every video/document copy is returned, with the requested
	  quality moved to the front. ``deliver_part`` sends the first copy that
	  Telegram still accepts, which is what makes a stale ``file_id`` harmless.
	"""
	records = part_media_sync(part)
	if not records:
		return []
	photos = [row for row in records if row.media_type == TelegramMedia.MediaType.PHOTO]
	videos = [
		row
		for row in records
		if row.media_type in (TelegramMedia.MediaType.VIDEO, TelegramMedia.MediaType.DOCUMENT)
	]
	if photos and not videos:
		return photos
	if not videos:
		return records[:1]
	if quality:
		needle = str(quality).lower()
		videos.sort(key=lambda row: 0 if needle in (row.caption or "").lower() else 1)
	return videos


select_media_for_delivery = to_async(select_media_for_delivery_sync)


def _reply_markup(reply_markup: Any) -> Any:
	return reply_markup


async def send_media(
	bot: Bot,
	chat_id: int,
	media: TelegramMedia,
	*,
	protect_content: bool = True,
	caption: Optional[str] = None,
	reply_markup: Any = None,
) -> Any:
	"""Send a single stored media item using its Telegram ``file_id``."""
	text = caption if caption is not None else (media.caption or None)
	if media.media_type == TelegramMedia.MediaType.VIDEO:
		return await bot.send_video(
			chat_id=chat_id,
			video=media.file_id,
			caption=text,
			supports_streaming=True,
			protect_content=protect_content,
			reply_markup=_reply_markup(reply_markup),
		)
	if media.media_type == TelegramMedia.MediaType.PHOTO:
		return await bot.send_photo(
			chat_id=chat_id,
			photo=media.file_id,
			caption=text,
			protect_content=protect_content,
			reply_markup=_reply_markup(reply_markup),
		)
	return await bot.send_document(
		chat_id=chat_id,
		document=media.file_id,
		caption=text,
		protect_content=protect_content,
		reply_markup=_reply_markup(reply_markup),
	)


async def _deliver_photo_pages(
	bot: Bot,
	chat_id: int,
	records: List[TelegramMedia],
	*,
	protect_content: bool,
	caption: Optional[str],
	reply_markup: Any = None,
) -> List[int]:
	"""Send every manga page, preferring a single media group.

	A media group cannot carry a keyboard, so ``reply_markup`` is attached to
	the single page itself or, for a group, sent as a short follow-up message.
	"""
	pages = records[:PHOTO_LIMIT]
	if len(pages) > 1:
		try:
			messages = await bot.send_media_group(
				chat_id=chat_id,
				media=[
					InputMediaPhoto(
						media=row.file_id,
						caption=caption if index == 0 else (row.caption or None),
					)
					for index, row in enumerate(pages)
				],
				protect_content=protect_content,
			)
			if reply_markup is not None:
				await send_parts_keyboard(bot, chat_id, reply_markup, protect_content=protect_content)
			return [message.message_id for message in messages]
		except (TelegramBadRequest, TelegramForbiddenError) as exc:
			logger.warning("Media group failed for part %s: %s; sending pages one by one.", pages[0].part_id, exc)

	sent: List[int] = []
	last = len(pages) - 1
	for index, media in enumerate(pages):
		try:
			message = await send_media(
				bot,
				chat_id,
				media,
				protect_content=protect_content,
				caption=caption,
				reply_markup=reply_markup if index == last else None,
			)
		except (TelegramBadRequest, TelegramForbiddenError, TelegramAPIError) as exc:
			logger.warning("Manga page %s could not be sent: %s", media.pk, exc)
			continue
		sent.append(message.message_id)
	if not sent:
		raise MediaUnavailable("Sahifalarni yuborib bo'lmadi.")
	return sent


async def send_parts_keyboard(
	bot: Bot,
	chat_id: int,
	reply_markup: Any,
	*,
	protect_content: bool = True,
) -> None:
	"""Send the parts navigator on its own when it cannot ride on the media."""
	await bot.send_message(
		chat_id=chat_id,
		text=WATCH_PARTS_HINT,
		reply_markup=reply_markup,
		protect_content=protect_content,
	)


async def deliver_part(
	bot: Bot,
	chat_id: int,
	part: MediaPart,
	*,
	quality: Optional[str] = None,
	protect_content: bool = True,
	caption: Optional[str] = None,
	reply_markup: Any = None,
) -> List[int]:
	"""Deliver a part, falling back to the next stored copy when one is stale."""
	records = await select_media_for_delivery(part, quality)
	if not records:
		raise MediaUnavailable("Bu qism uchun media fayl saqlanmagan.")

	if all(row.media_type == TelegramMedia.MediaType.PHOTO for row in records):
		return await _deliver_photo_pages(
			bot,
			chat_id,
			records,
			protect_content=protect_content,
			caption=caption,
			reply_markup=reply_markup,
		)

	# Video/document variants: send the first copy Telegram still accepts.
	last_error: Optional[Exception] = None
	for media in records:
		try:
			message = await send_media(
				bot,
				chat_id,
				media,
				protect_content=protect_content,
				caption=caption,
				reply_markup=reply_markup,
			)
		except (TelegramBadRequest, TelegramForbiddenError) as exc:
			logger.warning("Stored file for media %s is unavailable: %s", media.pk, exc)
			last_error = exc
			continue
		except TelegramAPIError as exc:  # pragma: no cover - network failure
			last_error = exc
			logger.warning("Failed to send media %s: %s", media.pk, exc)
			continue
		return [message.message_id]

	raise MediaUnavailable(str(last_error or "Media yuborilmadi."))


# Telegram answers "message is not modified" when an edit would change nothing;
# that is a success for us (the requested part is already on screen).
ALREADY_CURRENT = "message is not modified"


def build_input_media(media: TelegramMedia, caption: Optional[str] = None) -> Any:
	"""``InputMedia`` for one stored row, or ``None`` for types we never edit.

	Telegram's ``editMessageMedia`` needs the file *type* to match the id, so a
	stored photo id can only ever be declared as ``InputMediaPhoto`` and so on.
	"""
	text = caption if caption is not None else (media.caption or None)
	if media.media_type == TelegramMedia.MediaType.VIDEO:
		return InputMediaVideo(media=media.file_id, caption=text, supports_streaming=True)
	if media.media_type == TelegramMedia.MediaType.PHOTO:
		return InputMediaPhoto(media=media.file_id, caption=text)
	if media.media_type == TelegramMedia.MediaType.DOCUMENT:
		return InputMediaDocument(media=media.file_id, caption=text)
	return None


async def edit_part_media(
	bot: Bot,
	chat_id: int,
	message_id: int,
	part: MediaPart,
	*,
	current_kind: str,
	quality: Optional[str] = None,
	caption: Optional[str] = None,
	reply_markup: Any = None,
) -> bool:
	"""Swap the file inside an already-sent message, keeping the message itself.

	This is what lets the parts navigator hop between episodes inside one bubble:
	nothing is deleted and no new message is sent — only the media and the inline
	keyboard are replaced. ``current_kind`` is the media type of the message being
	edited (``video``/``photo``/``document``); only a copy of that same type is
	ever offered, because Telegram cannot change a message's media type reliably.

	Returns ``True`` when the message now shows ``part``. Raises
	:class:`MediaNotEditable` when the swap is impossible (no file of the same
	kind, a multi-page part) or Telegram refused it, and :class:`MediaUnavailable`
	when the part stores no file at all.
	"""
	records = await select_media_for_delivery(part, quality)
	if not records:
		raise MediaUnavailable("Bu qism uchun media fayl saqlanmagan.")

	candidates = [row for row in records if row.media_type == current_kind]
	if not candidates:
		raise MediaNotEditable("Bu qismning fayl turi hozirgi xabarnikidan farq qiladi.")
	if current_kind == TelegramMedia.MediaType.PHOTO and len(candidates) > 1:
		# Several pages/prints cannot live in one editable message.
		raise MediaNotEditable("Ko'p sahifali qismni bitta xabarda almashtirib bo'lmaydi.")

	last_error: Optional[Exception] = None
	for media in candidates:
		try:
			await bot.edit_message_media(
				chat_id=chat_id,
				message_id=message_id,
				media=build_input_media(media, caption),
				reply_markup=reply_markup,
			)
			return True
		except TelegramBadRequest as exc:
			if ALREADY_CURRENT in str(exc):
				# Telegram only answers this when both the file *and* the keyboard
				# already match, i.e. the user tapped the part they are watching.
				return True
			logger.warning("Could not swap media in message %s: %s", message_id, exc)
			last_error = exc
		except (TelegramForbiddenError, TelegramAPIError) as exc:
			logger.warning("Could not swap media in message %s: %s", message_id, exc)
			last_error = exc

	raise MediaNotEditable(str(last_error or "Media almashtirilmadi."))


def title_stats_sync(title: MediaTitle) -> Dict[str, Any]:
	parts = MediaPart.objects.filter(content=title)
	media_count = TelegramMedia.objects.filter(part__content=title).count()
	return {
		"parts": parts.count(),
		"media": media_count,
		"seasons": len(seasons_sync(title)),
	}


title_stats = to_async(title_stats_sync)


def count_media_sync() -> Dict[str, int]:
	return {
		"titles": MediaTitle.objects.count(),
		"parts": MediaPart.objects.count(),
		"files": TelegramMedia.objects.count(),
	}


count_media = to_async(count_media_sync)


def part_label(part: MediaPart) -> str:
	season = f"{part.season_number}-mavsum " if part.season_number else ""
	return f"{season}{part.number}-qism" + (f" · {part.title}" if part.title else "")


def media_kind_label(media_type: str) -> str:
	return dict(TelegramMedia.MediaType.choices).get(media_type, media_type)
