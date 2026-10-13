"""Shared test helpers: environment overrides and entity factories."""

from __future__ import annotations

import os
from contextlib import contextmanager
from unittest import mock

from movies.models import Genre, MediaPart, MediaTitle, TelegramChannel, TelegramMedia

from ..config import reset_config_cache


@contextmanager
def bot_env(**values):
	"""Temporarily override environment variables and clear the config cache.

	``bot.config`` reads ``os.environ`` before Django settings, so tests must
	patch the environment (not ``override_settings``) and reset the cache for
	``ADMIN_IDS``/``BOT_TOKEN`` changes to take effect.
	"""
	patched = {key: ("" if value is None else str(value)) for key, value in values.items()}
	with mock.patch.dict(os.environ, patched, clear=False):
		reset_config_cache()
		try:
			yield
		finally:
			reset_config_cache()


def make_title(
	*,
	code: str = "1234",
	title: str = "Test Anime",
	media_type: str = MediaTitle.MediaType.ANIME,
	required_plan: str = MediaTitle.AccessPlan.FREE,
	quality_options=None,
	slug: str = "",
	status: str = MediaTitle.Status.ONGOING,
) -> MediaTitle:
	return MediaTitle.objects.create(
		type=media_type,
		title=title,
		slug=slug or f"{title.lower().replace(' ', '-')}-{code}",
		code=code,
		required_plan=required_plan,
		quality_options=list(quality_options or ["480", "720"]),
		status=status,
	)


def make_part(title: MediaTitle, *, number: int = 1, season: int | None = None, part_title: str = "") -> MediaPart:
	return MediaPart.objects.create(
		content=title, season_number=season, number=number, title=part_title
	)


def make_media(
	part: MediaPart,
	*,
	file_id: str = "file-id-1",
	media_type: str = TelegramMedia.MediaType.VIDEO,
	order: int = 1,
	caption: str = "",
	channel: TelegramChannel | None = None,
	source_message_id: int | None = None,
) -> TelegramMedia:
	return TelegramMedia.objects.create(
		part=part,
		channel=channel,
		source_message_id=source_message_id,
		file_id=file_id,
		media_type=media_type,
		order=order,
		caption=caption,
	)


def make_channel(
	*,
	chat_id: int = -1001234567890,
	title: str = "Storage Channel",
	purpose: str = TelegramChannel.Purpose.STORAGE,
	is_active: bool = True,
	username: str = "",
) -> TelegramChannel:
	return TelegramChannel.objects.create(
		chat_id=chat_id,
		title=title,
		purpose=purpose,
		is_active=is_active,
		username=username,
	)


def make_genre(name: str = "Action") -> Genre:
	return Genre.objects.create(name=name)
