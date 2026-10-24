"""Episode (MediaPart) and Telegram media file management.

Administrator upload flow — the bot's "one part, one file" rule:

1. pick the content;
2. type the season number;
3. send any number of media messages: every message is copied to the Cloud
   channel with a *separate* ``copy_message`` and becomes its own part holding
   a single file, numbered automatically (parts already in that season + 1);
4. press the ``💾 Saqlash`` reply button to finish, which announces the new
   episodes in the public channel with a deep link so users can ``/start`` and
   watch.

The old wizard (ask part number -> ask part title -> preview -> confirm) is
gone: nothing is asked per part, and a part is stored as soon as its file
arrives so the next part's file can be sent immediately.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from ... import callbacks as cb
from ...bot_logging import record_event
from ...config import page_size
from ...keyboards.admin import (
	EPISODE_CANCEL_LABEL,
	EPISODE_SAVE_LABEL,
	channel_picker,
	confirm,
	episode_upload_reply_keyboard,
	episodes_menu,
	part_actions,
	parts_list,
	title_picker,
)
from ...keyboards.common import cancel_keyboard
from ...services.channels import get_channel, storage_channels
from ...services.media import (
	create_part_with_media,
	delete_media,
	delete_part,
	get_part_by_pk,
	get_title_by_pk,
	part_media,
	title_parts,
)
from ...services.publishing import publish_parts
from ...states import AdminEpisodeStates
from ...texts import (
	ADMIN_EPISODE_ASK_FILES,
	ADMIN_EPISODE_ASK_SEASON,
	ADMIN_EPISODE_CLOUD_FAILED,
	ADMIN_EPISODE_DELETE_CONFIRM,
	ADMIN_EPISODE_DELETED,
	ADMIN_EPISODE_FILE_SAVED,
	ADMIN_EPISODE_FILES_READY,
	ADMIN_EPISODE_LIST,
	ADMIN_EPISODE_NO_CHANNELS,
	ADMIN_EPISODE_NO_FILES,
	ADMIN_EPISODE_NOT_PUBLISHED,
	ADMIN_EPISODE_PUBLISHED,
	ADMIN_EPISODE_SELECT_CHANNEL,
	ADMIN_EPISODE_SELECT_TITLE,
	ADMIN_EPISODE_SESSION_SAVED,
	ADMIN_EPISODES_MENU,
	ADMIN_INVALID_INPUT,
	CANCELLED,
	NOT_FOUND,
)
from ...utils import escape_html, paginate, parse_int, to_async
from ..common import render
from .media import admin_card_text

logger = logging.getLogger(__name__)

router = Router(name="admin-episodes")


def part_scope_label(season: Optional[int], number: int) -> str:
	"""Human label such as ``3-mavsum · 12-`` or ``12-`` (ready for "qism")."""
	return f"{season}-mavsum · {number}-" if season else f"{number}-"


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


async def enter_media_step(callback: CallbackQuery, state: FSMContext) -> None:
	"""Switch to the bulk-upload step and show the 💾 Saqlash reply keyboard."""
	await state.set_state(AdminEpisodeStates.media)
	await render(callback, ADMIN_EPISODE_ASK_FILES, edit=True)
	if callback.message is not None:
		await callback.message.answer(
			ADMIN_EPISODE_FILES_READY, reply_markup=episode_upload_reply_keyboard()
		)


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
	items, page, pages = paginate(titles, page, 30)
	if not items:
		await render(callback, NOT_FOUND, markup=episodes_menu(), edit=True)
		return
	await render(callback, ADMIN_EPISODE_SELECT_TITLE, markup=title_picker(items, page, pages), edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_EPISODES}:add:"))
async def start_episode(callback: CallbackQuery, state: FSMContext) -> None:
	args = cb.section_args(callback.data)
	title_pk = parse_int(args[0] if args else None, minimum=1)
	title = await get_title_by_pk(title_pk) if title_pk else None
	if title is None:
		await render(callback, NOT_FOUND, markup=episodes_menu(), edit=True)
		return
	await state.clear()
	await state.set_state(AdminEpisodeStates.season)
	await state.update_data(episode={"title_id": title.pk}, added=[])
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
	await state.update_data(episode=episode, added=[])

	channels = await storage_channels()
	if not channels:
		await state.clear()
		await message.answer(ADMIN_EPISODE_NO_CHANNELS, reply_markup=episodes_menu())
		return
	if len(channels) == 1:
		# A single Cloud channel needs no question — just start the upload.
		episode["channel_id"] = channels[0].pk
		await state.update_data(episode=episode)
		await state.set_state(AdminEpisodeStates.media)
		await message.answer(ADMIN_EPISODE_ASK_FILES, reply_markup=episode_upload_reply_keyboard())
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
	await state.update_data(episode=episode, added=[])
	await enter_media_step(callback, state)


# ------------------------------------------------------------------- uploading
@router.message(AdminEpisodeStates.media, F.video | F.photo | F.document)
async def store_media(message: Message, state: FSMContext, bot) -> None:
	"""Copy the message to the Cloud channel and store it as a new part."""
	data = await state.get_data()
	episode = dict(data.get("episode") or {})
	title = await get_title_by_pk(episode.get("title_id"))
	channel = await get_channel(episode.get("channel_id")) if episode.get("channel_id") else None
	if title is None or channel is None:
		await state.clear()
		await message.answer(ADMIN_INVALID_INPUT, reply_markup=ReplyKeyboardRemove())
		return

	entry = extract_media_entry(message, channel.chat_id)
	if entry is None:
		await message.answer(ADMIN_INVALID_INPUT, reply_markup=episode_upload_reply_keyboard())
		return

	# The rule: every file is copied to the Cloud channel as its own message.
	try:
		copied = await bot.copy_message(
			chat_id=channel.chat_id,
			from_chat_id=message.chat.id,
			message_id=message.message_id,
		)
	except TelegramAPIError as exc:
		logger.warning("Could not copy the uploaded file to the cloud channel: %s", exc)
		await message.answer(ADMIN_EPISODE_CLOUD_FAILED, reply_markup=episode_upload_reply_keyboard())
		return

	part = await create_part_with_media(
		title,
		season_number=episode.get("season"),
		file_id=entry["file_id"],
		media_type=entry["media_type"],
		channel=channel,
		source_message_id=getattr(copied, "message_id", None),
		caption=entry["caption"],
	)
	added = list(data.get("added") or [])
	added.append({"part_id": part.pk, "season": part.season_number, "number": part.number})
	await state.update_data(added=added)
	await to_async(record_event)(
		"INFO",
		f"Episode file copied to the cloud channel: part #{part.pk} of {title.title}.",
		telegram_id=getattr(message.from_user, "id", None),
	)
	await message.answer(
		ADMIN_EPISODE_FILE_SAVED.format(
			label=part_scope_label(part.season_number, part.number)
		),
		reply_markup=episode_upload_reply_keyboard(),
	)


@router.message(AdminEpisodeStates.media, F.text == EPISODE_SAVE_LABEL)
async def finish_upload(message: Message, state: FSMContext, bot) -> None:
	"""💾 Saqlash: close the upload and announce the new episodes publicly."""
	data = await state.get_data()
	episode = dict(data.get("episode") or {})
	added = list(data.get("added") or [])
	await state.clear()

	title = await get_title_by_pk(episode.get("title_id"))
	if title is None:
		await message.answer(NOT_FOUND, reply_markup=ReplyKeyboardRemove())
		return
	if not added:
		await message.answer(ADMIN_EPISODE_NO_FILES, reply_markup=ReplyKeyboardRemove())
		return

	parts = []
	for item in added:
		part = await get_part_by_pk(item.get("part_id"))
		if part is not None:
			parts.append(part)

	message_id = await publish_parts(bot, title, parts)
	seasons = sorted({part.season_number for part in parts if part.season_number is not None})
	label = f"{seasons[-1]}-mavsum" if len(seasons) == 1 else "Qismlar"
	summary = ADMIN_EPISODE_SESSION_SAVED.format(
		title=escape_html(title.title), count=len(parts), label=label
	)
	if message_id:
		status_msg = ADMIN_EPISODE_PUBLISHED
	else:
		total_parts = await to_async(title.parts.count)()
		expected = title.episode_count or (1 if title.type == "movie" else None)
		if (title.type == "movie" or title.status == "completed") and expected and total_parts < expected:
			status_msg = f"⏳ Barcha qismlar ({total_parts}/{expected}) to'lgach, tugallanganlar kanaliga avtomatik joylanadi."
		else:
			status_msg = ADMIN_EPISODE_NOT_PUBLISHED
	summary += "\n\n" + status_msg
	await message.answer(summary, reply_markup=ReplyKeyboardRemove())

	await to_async(record_event)(
		"INFO",
		f"Episode batch saved for {title.title}: {len(parts)} parts.",
		telegram_id=getattr(message.from_user, "id", None),
	)
	last = parts[-1] if parts else None
	if last is not None:
		await message.answer(
			await admin_card_text(title),
			reply_markup=part_actions(
				last, title_pk=title.pk, media_items=await part_media(last)
			),
		)


@router.message(AdminEpisodeStates.media, F.text == EPISODE_CANCEL_LABEL)
async def cancel_upload(message: Message, state: FSMContext) -> None:
	await state.clear()
	await message.answer(CANCELLED, reply_markup=ReplyKeyboardRemove())
	await message.answer(ADMIN_EPISODES_MENU, reply_markup=episodes_menu())


@router.message(AdminEpisodeStates.media)
async def invalid_media(message: Message) -> None:
	await message.answer(ADMIN_INVALID_INPUT, reply_markup=episode_upload_reply_keyboard())


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
		await render(callback, NOT_FOUND, markup=episodes_menu(), edit=True)
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
		+ f"\n\n🎞 {part_scope_label(part.season_number, part.number).rstrip('-')}\n📦 Fayl: {len(media)}",
		markup=part_actions(part, title_pk=part.content_id, media_items=media),
		edit=True,
	)


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
		ADMIN_EPISODE_DELETE_CONFIRM.format(
			label=part_scope_label(part.season_number, part.number)
		),
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
		markup=parts_list(items, title.pk, page, pages) if items else episodes_menu(),
		edit=True,
	)
