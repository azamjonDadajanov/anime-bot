"""Shared rendering of title/part cards and protected media delivery."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from movies.models import MediaTitle
from users.models import FavoriteContent

from ...config import manga_url
from ...keyboards.user import (
	manga_keyboard,
	origin_callback,
	part_keyboard,
	title_detail_keyboard,
	watch_parts_keyboard,
)
from ...services.access import AccessDenied, ensure_access
from ...services.media import (
	MediaUnavailable,
	deliver_part,
	record_media_view,
	title_parts,
)
from ...texts import (
	MANGA_ON_SITE,
	MEDIA_BLOCKED,
	MEDIA_SENDING,
	MEDIA_UNAVAILABLE,
	PART_CARD,
	TITLE_CARD,
)
from ...utils import escape_html, to_async
from ..common import render, render_access_denial

logger = logging.getLogger(__name__)


def _genres_text_sync(title) -> str:
	return ", ".join(title.genres.values_list("name", flat=True)) or "—"


def _is_favorite_sync(profile, title) -> bool:
	return FavoriteContent.objects.filter(user=profile, content=title).exists()


_genres_text = to_async(_genres_text_sync)
_is_favorite = to_async(_is_favorite_sync)


def title_card_text(title, genres_text: str, parts_count: int) -> str:
	qualities = ", ".join(title.quality_options or []) or title.default_quality
	return TITLE_CARD.format(
		title=escape_html(title.title),
		code=title.code,
		type=title.get_type_display(),
		genres=escape_html(genres_text),
		language=escape_html(title.language),
		quality=escape_html(qualities),
		plan=title.get_required_plan_display(),
		rating=title.rating,
		year=title.release_year or "—",
		status=title.get_status_display(),
		parts=parts_count,
		synopsis=escape_html(title.synopsis) or "—",
	)


async def send_title_card(
	target: Any,
	title,
	*,
	profile,
	bot,
	page: int = 1,
	origin: str = "cat",
	edit: bool = False,
) -> None:
	"""Render a title card, honouring subscription and plan restrictions."""
	try:
		await ensure_access(bot, profile, title)
	except AccessDenied as denial:
		await render_access_denial(target, denial, edit=edit)
		return

	genres_text, is_favorite, parts = await asyncio.gather(
		_genres_text(title),
		_is_favorite(profile, title),
		title_parts(title),
	)
	read_url = manga_url(title.slug) if title.type == MediaTitle.MediaType.MANGA else ""
	markup = title_detail_keyboard(
		title.pk,
		is_favorite=is_favorite,
		origin=origin,
		page=page,
		back=origin_callback(origin, page),
		media_type=title.type,
		manga_url=read_url,
	)
	await render(target, title_card_text(title, genres_text, len(parts)), markup=markup, edit=edit)


async def send_part_card(
	target: Any,
	part,
	*,
	profile,
	bot,
	origin: str = "cat",
	edit: bool = False,
) -> None:
	title = part.content
	try:
		await ensure_access(bot, profile, title)
	except AccessDenied as denial:
		await render_access_denial(target, denial, edit=edit)
		return

	qualities = list(title.quality_options or [])
	season = f"{part.season_number}" if part.season_number else "—"
	text = PART_CARD.format(
		title=escape_html(title.title),
		season=season,
		number=part.number,
		qualities=escape_html(", ".join(qualities) or title.default_quality),
	)
	await render(
		target,
		text,
		markup=part_keyboard(part.pk, qualities, title.pk, origin=origin),
		edit=edit,
	)


async def deliver_media_for_part(
	target: Any,
	part,
	*,
	profile,
	bot,
	quality: Optional[str] = None,
	state: Any = None,
	edit: bool = False,
) -> bool:
	"""Verify access and deliver a part's media. Returns ``True`` when sent."""
	title = part.content
	try:
		await ensure_access(bot, profile, title)
	except AccessDenied as denial:
		if state is not None and denial.is_subscription:
			# Remember what the user wanted so the "check subscription" button can
			# resume the exact action after they subscribe.
			await state.update_data(pending_part_id=part.pk, pending_quality=quality or "")
		await render_access_denial(target, denial, edit=edit)
		return False

	if state is not None:
		await state.update_data(pending_part_id=None, pending_quality="")

	# Manga has no Telegram files to stream: send the reader link instead.
	if title.type == MediaTitle.MediaType.MANGA:
		read_url = manga_url(title.slug)
		if read_url:
			await render(
				target,
				MANGA_ON_SITE.format(title=escape_html(title.title)),
				markup=manga_keyboard(read_url),
				edit=edit,
				preview=True,
			)
			await record_media_view(profile.auth_user_id, part.content_id, part.pk)
			return False

	# The parts navigator rides on the delivered media so the user can hop to
	# another episode (or the next season) without leaving the player.
	parts = await title_parts(title)
	markup = watch_parts_keyboard(parts, part) if len(parts) > 1 else None

	await render(target, MEDIA_SENDING)
	try:
		await deliver_part(
			bot,
			profile.telegram_id,
			part,
			quality=quality,
			# Delivered media is always personal: forwarding and saving are blocked.
			protect_content=True,
			reply_markup=markup,
		)
	except MediaUnavailable:
		logger.warning("No deliverable file for part %s.", part.pk)
		await render(target, MEDIA_UNAVAILABLE)
		return False
	except (TelegramForbiddenError, TelegramAPIError) as exc:
		logger.warning("Delivery failed for part %s: %s", part.pk, exc)
		await render(target, MEDIA_BLOCKED)
		return False
	await record_media_view(profile.auth_user_id, part.content_id, part.pk)
	return True


async def deliver_title_media(
	target: Any,
	title,
	parts,
	*,
	profile,
	bot,
	state: Any = None,
	edit: bool = False,
) -> bool:
	"""Deliver every part of a movie/single-part title in one tap."""
	try:
		await ensure_access(bot, profile, title)
	except AccessDenied as denial:
		if state is not None and denial.is_subscription and parts:
			await state.update_data(pending_part_id=parts[0].pk, pending_quality="")
		await render_access_denial(target, denial, edit=edit)
		return False

	if state is not None:
		await state.update_data(pending_part_id=None, pending_quality="")

	await render(target, MEDIA_SENDING)
	sent = False
	for part in parts:
		try:
			await deliver_part(
				bot,
				profile.telegram_id,
				part,
				protect_content=True,
			)
		except MediaUnavailable:
			logger.warning("No deliverable file for part %s.", part.pk)
			continue
		except (TelegramForbiddenError, TelegramAPIError) as exc:
			logger.warning("Delivery failed for part %s: %s", part.pk, exc)
			await render(target, MEDIA_BLOCKED)
			return False
		await record_media_view(profile.auth_user_id, title.pk, part.pk)
		sent = True
	if not sent:
		await render(target, MEDIA_UNAVAILABLE)
		return False
	return True
