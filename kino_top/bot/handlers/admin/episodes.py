"""Episode (MediaPart) and Telegram media file management."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ... import callbacks as cb
from ...bot_logging import record_event
from ...config import page_size
from ...keyboards.admin import (
	channel_picker,
	confirm,
	episode_draft_keyboard,
	episodes_menu,
	media_upload_keyboard,
	part_actions,
	parts_list,
	title_picker,
)
from ...keyboards.common import cancel_keyboard
from ...services.channels import storage_channels, get_channel
from ...services.media import (
	add_media,
	delete_media,
	get_media_by_pk,
	get_part_by_pk,
	get_title_by_pk,
	part_media,
	replace_part_media,
	swap_media_order,
	title_parts,
	upsert_part,
)
from ...services.publishing import maybe_auto_publish_part
from ...states import AdminEpisodeStates
from ...texts import (
	ADMIN_EPISODE_ASK_MEDIA,
	ADMIN_EPISODE_ASK_NUMBER,
	ADMIN_EPISODE_ASK_SEASON,
	ADMIN_EPISODE_ASK_TITLE,
	ADMIN_EPISODE_DELETE_CONFIRM,
	ADMIN_EPISODE_DELETED,
	ADMIN_EPISODE_LIST,
	ADMIN_EPISODE_MEDIA_ADDED,
	ADMIN_EPISODE_NO_CHANNELS,
	ADMIN_EPISODE_PREVIEW,
	ADMIN_EPISODE_REPLACED,
	ADMIN_EPISODE_REPLACE_PROMPT,
	ADMIN_EPISODE_SAVED,
	ADMIN_EPISODE_SELECT_CHANNEL,
	ADMIN_EPISODE_SELECT_TITLE,
	ADMIN_EPISODES_MENU,
	ADMIN_INVALID_INPUT,
	NOT_FOUND,
)
from ...utils import escape_html, paginate, parse_int, to_async
from ..common import render
from .media import admin_card_text

logger = logging.getLogger(__name__)

router = Router(name="admin-episodes")


def extract_media_entry(message: Message, fallback_channel_id: Optional[int]) -> Optional[Dict[str, Any]]:
	"""Turn an uploaded or forwarded message into a storable file entry."""
	forward_chat = getattr(message, "forward_from_chat", None)
	source_channel_id = getattr(forward_chat, "id", None) or fallback_channel_id
	source_message_id = getattr(message, "forward_from_message_id", None)
	caption = (message.caption or "")[:1024]

	if message.video:
		return {
			"file_id": message.video.file_id,
			"media_type": "video",
			"channel_id": source_channel_id,
			"source_message_id": source_message_id,
			"caption": caption,
		}
	if message.photo:
		return {
			"file_id": message.photo[-1].file_id,
			"media_type": "photo",
			"channel_id": source_channel_id,
			"source_message_id": source_message_id,
			"caption": caption,
		}
	if message.document:
		return {
			"file_id": message.document.file_id,
			"media_type": "document",
			"channel_id": source_channel_id,
			"source_message_id": source_message_id,
			"caption": caption,
		}
	return None


async def resolve_entries(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
	"""Attach resolved ``TelegramChannel`` instances to raw file entries."""
	cache: Dict[int, Any] = {}
	resolved = []
	for entry in files:
		channel_id = entry.get("channel_id")
		channel = None
		if channel_id:
			if channel_id not in cache:
				cache[channel_id] = await get_channel(int(channel_id))
			channel = cache[channel_id]
		resolved.append(
			{
				"file_id": entry["file_id"],
				"media_type": entry["media_type"],
				"channel": channel,
				"source_message_id": entry.get("source_message_id"),
				"caption": entry.get("caption") or "",
			}
		)
	return resolved


# ------------------------------------------------------------------ navigation
@router.callback_query(F.data == cb.ADM_EPISODES)
async def show_menu(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	await render(callback, ADMIN_EPISODES_MENU, markup=episodes_menu(), edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_EPISODES}:pick:"))
async def pick_title(callback: CallbackQuery) -> None:
	from ...services.media import all_titles

	args = cb.section_args(callback.data)
	page = parse_int(args[0] if args else None, minimum=1) or 1
	titles = await all_titles()
	items, page, pages = paginate(titles, page, page_size())
	if not items:
		await render(callback, NOT_FOUND, markup=episode_draft_keyboard(), edit=True)
		return
	await render(callback, ADMIN_EPISODE_SELECT_TITLE, markup=title_picker(items, page, pages), edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_EPISODES}:add:"))
async def start_episode(callback: CallbackQuery, state: FSMContext) -> None:
	args = cb.section_args(callback.data)
	title_pk = parse_int(args[0] if args else None, minimum=1)
	title = await get_title_by_pk(title_pk) if title_pk else None
	if title is None:
		await render(callback, NOT_FOUND, markup=episode_draft_keyboard(), edit=True)
		return
	await state.clear()
	await state.set_state(AdminEpisodeStates.season)
	await state.update_data(episode={"title_id": title.pk}, files=[])
	await render(callback, ADMIN_EPISODE_ASK_SEASON, markup=cancel_keyboard(), edit=True)


@router.message(AdminEpisodeStates.season)
async def draft_season(message: Message, state: FSMContext) -> None:
	raw = (message.text or "").strip()
	season = None
	if raw not in {"", "-"}:
		season = parse_int(raw, minimum=1, maximum=999)
		if season is None:
			await message.answer(ADMIN_INVALID_INPUT)
			return
	data = await state.get_data()
	episode = dict(data.get("episode") or {})
	episode["season"] = season
	await state.update_data(episode=episode)
	await state.set_state(AdminEpisodeStates.number)
	await message.answer(ADMIN_EPISODE_ASK_NUMBER, reply_markup=cancel_keyboard())


@router.message(AdminEpisodeStates.number)
async def draft_number(message: Message, state: FSMContext) -> None:
	number = parse_int((message.text or "").strip(), minimum=1, maximum=10000)
	if number is None:
		await message.answer(ADMIN_INVALID_INPUT)
		return
	data = await state.get_data()
	episode = dict(data.get("episode") or {})
	episode["number"] = number
	await state.update_data(episode=episode)
	await state.set_state(AdminEpisodeStates.title)
	await message.answer(ADMIN_EPISODE_ASK_TITLE, reply_markup=cancel_keyboard())


@router.message(AdminEpisodeStates.title)
async def draft_part_title(message: Message, state: FSMContext) -> None:
	raw = (message.text or "").strip()
	data = await state.get_data()
	episode = dict(data.get("episode") or {})
	episode["part_title"] = "" if raw == "-" else raw[:200]
	await state.update_data(episode=episode)

	channels = await storage_channels()
	if not channels:
		await state.clear()
		await message.answer(ADMIN_EPISODE_NO_CHANNELS, reply_markup=episode_draft_keyboard())
		return
	await state.set_state(AdminEpisodeStates.channel)
	await message.answer(
		ADMIN_EPISODE_SELECT_CHANNEL,
		reply_markup=channel_picker(channels, f"{cb.ADM_EPISODES}:ch"),
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_EPISODES}:ch:"))
async def choose_channel(callback: CallbackQuery, state: FSMContext) -> None:
	args = cb.section_args(callback.data)
	channel_pk = parse_int(args[0] if args else None, minimum=1)
	channel = await get_channel(channel_pk) if channel_pk else None
	if channel is None:
		await render(callback, NOT_FOUND, edit=True)
		return
	data = await state.get_data()
	episode = dict(data.get("episode") or {})
	episode["channel_id"] = channel.pk
	await state.update_data(episode=episode)
	await state.set_state(AdminEpisodeStates.media)
	await render(
		callback,
		ADMIN_EPISODE_ASK_MEDIA,
		markup=media_upload_keyboard(),
		edit=True,
	)


@router.message(AdminEpisodeStates.media, F.video | F.photo | F.document)
async def collect_media(message: Message, state: FSMContext) -> None:
	data = await state.get_data()
	episode = dict(data.get("episode") or {})
	entry = extract_media_entry(message, episode.get("channel_id"))
	if entry is None:
		await message.answer(ADMIN_INVALID_INPUT)
		return
	files = list(data.get("files") or [])
	files.append(entry)
	await state.update_data(files=files)
	await message.answer(
		ADMIN_EPISODE_MEDIA_ADDED.format(count=len(files)),
		reply_markup=media_upload_keyboard(),
	)


@router.message(AdminEpisodeStates.media)
async def invalid_media(message: Message) -> None:
	await message.answer(ADMIN_INVALID_INPUT, reply_markup=media_upload_keyboard())


# ----------------------------------------------------------------------- saving
@router.callback_query(F.data == f"{cb.ADM_EPISODES}:save")
async def save_draft(callback: CallbackQuery, state: FSMContext) -> None:
	data = await state.get_data()
	files = list(data.get("files") or [])

	if data.get("replace_part_id"):
		part = await get_part_by_pk(data.get("replace_part_id"))
		if part is None or not files:
			await render(callback, ADMIN_INVALID_INPUT, markup=media_upload_keyboard(), edit=True)
			return
		count = await replace_part_media(part, await resolve_entries(files))
		await state.clear()
		await to_async(record_event)(
			"INFO",
			f"Episode files replaced for part #{part.pk} ({count} files).",
			telegram_id=callback.from_user.id,
		)
		await render(
			callback,
			ADMIN_EPISODE_REPLACED.format(count=count),
			markup=part_actions(part, title_pk=part.content_id, media_items=await part_media(part)),
			edit=True,
		)
		return

	if data.get("part_id"):
		part = await get_part_by_pk(data.get("part_id"))
		if part is None or not files:
			await render(callback, ADMIN_INVALID_INPUT, markup=media_upload_keyboard(), edit=True)
			return
		for entry in await resolve_entries(files):
			await add_media(
				part,
				file_id=entry["file_id"],
				media_type=entry["media_type"],
				channel=entry["channel"],
				source_message_id=entry["source_message_id"],
				caption=entry["caption"],
			)
		await state.clear()
		await render(
			callback,
			ADMIN_EPISODE_MEDIA_ADDED.format(count=len(files)),
			markup=part_actions(part, title_pk=part.content_id, media_items=await part_media(part)),
			edit=True,
		)
		return

	episode = dict(data.get("episode") or {})
	if not episode.get("number") or not episode.get("title_id"):
		await render(callback, ADMIN_INVALID_INPUT, markup=episode_draft_keyboard(), edit=True)
		return
	if not files:
		await render(callback, ADMIN_INVALID_INPUT, markup=media_upload_keyboard(), edit=True)
		return

	title = await get_title_by_pk(episode["title_id"])
	channel = await get_channel(episode.get("channel_id")) if episode.get("channel_id") else None
	if title is None:
		await render(callback, NOT_FOUND, edit=True)
		return
	await render(
		callback,
		ADMIN_EPISODE_PREVIEW.format(
			title=escape_html(title.title),
			season=episode.get("season") or "—",
			number=episode.get("number"),
			part_title=escape_html(episode.get("part_title") or "—"),
			channel=escape_html(channel.title if channel else "—"),
			files=len(files),
		),
		markup=confirm(f"{cb.ADM_EPISODES}:confirm", cb.CANCEL),
		edit=True,
	)


@router.callback_query(F.data == f"{cb.ADM_EPISODES}:confirm")
async def commit_episode(callback: CallbackQuery, state: FSMContext, bot) -> None:
	data = await state.get_data()
	episode = dict(data.get("episode") or {})
	files = list(data.get("files") or [])
	title = await get_title_by_pk(episode.get("title_id"))
	if title is None or not episode.get("number") or not files:
		await state.clear()
		await render(callback, ADMIN_INVALID_INPUT, markup=episode_draft_keyboard(), edit=True)
		return

	part, created = await upsert_part(
		title,
		season_number=episode.get("season"),
		number=episode["number"],
		title=episode.get("part_title") or "",
	)
	for entry in await resolve_entries(files):
		await add_media(
			part,
			file_id=entry["file_id"],
			media_type=entry["media_type"],
			channel=entry["channel"],
			source_message_id=entry["source_message_id"],
			caption=entry["caption"],
		)

	await state.clear()
	await to_async(record_event)(
		"INFO",
		f"Episode saved: {title.title} part #{part.pk} ({len(files)} files).",
		telegram_id=callback.from_user.id,
	)
	await render(
		callback,
		ADMIN_EPISODE_SAVED.format(
			season=part.season_number or "—", number=part.number, files=len(files)
		),
		markup=part_actions(part, title_pk=title.pk, media_items=await part_media(part)),
		edit=True,
	)
	await maybe_auto_publish_part(bot, part)


# ------------------------------------------------------------------ part lists
@router.callback_query(F.data.startswith(f"{cb.ADM_EPISODES}:list:"))
async def list_parts(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	title_pk = parse_int(args[0] if args else None, minimum=1)
	page = parse_int(args[1] if len(args) > 1 else None, minimum=1) or 1
	title = await get_title_by_pk(title_pk) if title_pk else None
	if title is None:
		await render(callback, NOT_FOUND, edit=True)
		return
	all_parts = await title_parts(title)
	items, page, pages = paginate(all_parts, page, page_size())
	if not items:
		await render(callback, NOT_FOUND, markup=episode_draft_keyboard(), edit=True)
		return
	await render(
		callback,
		ADMIN_EPISODE_LIST.format(title=escape_html(title.title), page=page, pages=pages),
		markup=parts_list(items, title.pk, page, pages),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_EPISODES}:view:"))
async def view_part(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	args = cb.section_args(callback.data)
	part_pk = parse_int(args[0] if args else None, minimum=1)
	part = await get_part_by_pk(part_pk) if part_pk else None
	if part is None:
		await render(callback, NOT_FOUND, edit=True)
		return
	media = await part_media(part)
	await render(
		callback,
		await admin_card_text(part.content)
		+ f"\n\n🎞 {part.season_number or '—'}-mavsum · {part.number}-qism\n📦 Fayllar: {len(media)}",
		markup=part_actions(part, title_pk=part.content_id, media_items=media),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_EPISODES}:up:"))
async def move_up(callback: CallbackQuery) -> None:
	await _swap(callback, direction=-1)


@router.callback_query(F.data.startswith(f"{cb.ADM_EPISODES}:down:"))
async def move_down(callback: CallbackQuery) -> None:
	await _swap(callback, direction=1)


async def _swap(callback: CallbackQuery, *, direction: int) -> None:
	args = cb.section_args(callback.data)
	media_pk = parse_int(args[0] if args else None, minimum=1)
	current = await get_media_by_pk(media_pk) if media_pk else None
	if current is None:
		await callback.answer(NOT_FOUND)
		return
	siblings = await part_media(current.part)
	orders = [row.order for row in siblings]
	try:
		index = orders.index(current.order)
	except ValueError:  # pragma: no cover - defensive
		await callback.answer(NOT_FOUND)
		return
	target_index = index + direction
	if target_index < 0 or target_index >= len(siblings):
		await callback.answer("↕️ Boshqa joyga o'tkazib bo'lmaydi.")
		return
	await swap_media_order(current, siblings[target_index])
	part = await get_part_by_pk(current.part_id)
	await render(
		callback,
		await admin_card_text(part.content)
		+ f"\n\n🎞 {part.season_number or '—'}-mavsum · {part.number}-qism",
		markup=part_actions(part, title_pk=part.content_id, media_items=await part_media(part)),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_EPISODES}:rep:"))
async def replace_media(callback: CallbackQuery, state: FSMContext) -> None:
	args = cb.section_args(callback.data)
	media_pk = parse_int(args[0] if args else None, minimum=1)
	media = await get_media_by_pk(media_pk) if media_pk else None
	if media is None:
		await callback.answer(NOT_FOUND)
		return
	await state.set_state(AdminEpisodeStates.media)
	await state.update_data(replace_part_id=media.part_id, files=[], episode={}, part_id=None)
	await render(
		callback,
		ADMIN_EPISODE_REPLACE_PROMPT,
		markup=media_upload_keyboard(),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_EPISODES}:addmore:"))
async def add_more_media(callback: CallbackQuery, state: FSMContext) -> None:
	args = cb.section_args(callback.data)
	part_pk = parse_int(args[0] if args else None, minimum=1)
	part = await get_part_by_pk(part_pk) if part_pk else None
	if part is None:
		await callback.answer(NOT_FOUND)
		return
	await state.set_state(AdminEpisodeStates.media)
	await state.update_data(part_id=part.pk, files=[], episode={}, replace_part_id=None)
	await render(callback, ADMIN_EPISODE_ASK_MEDIA, markup=media_upload_keyboard(), edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_EPISODES}:del:"))
async def confirm_delete(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	part_pk = parse_int(args[0] if args else None, minimum=1)
	title_pk = parse_int(args[1] if len(args) > 1 else None, minimum=1) or 0
	page = parse_int(args[2] if len(args) > 2 else None, minimum=1) or 1
	part = await get_part_by_pk(part_pk) if part_pk else None
	if part is None:
		await render(callback, NOT_FOUND, edit=True)
		return
	await render(
		callback,
		ADMIN_EPISODE_DELETE_CONFIRM.format(season=part.season_number or "—", number=part.number),
		markup=confirm(
			f"{cb.ADM_EPISODES}:delok:{part.pk}:{title_pk}:{page}",
			f"{cb.ADM_EPISODES}:view:{part.pk}",
		),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_EPISODES}:delok:"))
async def do_delete(callback: CallbackQuery, state: FSMContext) -> None:
	args = cb.section_args(callback.data)
	part_pk = parse_int(args[0] if args else None, minimum=1)
	title_pk = parse_int(args[1] if len(args) > 1 else None, minimum=1) or 0
	page = parse_int(args[2] if len(args) > 2 else None, minimum=1) or 1
	part = await get_part_by_pk(part_pk) if part_pk else None
	if part is None:
		await render(callback, NOT_FOUND, edit=True)
		return
	from ...services.media import delete_part

	for media_row in await part_media(part):
		await delete_media(media_row)
	await delete_part(part)
	await state.clear()
	await to_async(record_event)(
		"WARNING", f"Episode deleted: part #{part_pk}", telegram_id=callback.from_user.id
	)
	title = await get_title_by_pk(title_pk) if title_pk else None
	if title is None:
		await render(callback, ADMIN_EPISODE_DELETED, edit=True)
		return
	all_parts = await title_parts(title)
	items, page, pages = paginate(all_parts, page, page_size())
	await render(
		callback,
		ADMIN_EPISODE_DELETED
		+ "\n\n"
		+ ADMIN_EPISODE_LIST.format(title=escape_html(title.title), page=page, pages=pages),
		markup=parts_list(items, title.pk, page, pages) if items else episode_draft_keyboard(),
		edit=True,
	)
