"""Channel management for the three channel types."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from movies.models import TelegramChannel

from ... import callbacks as cb
from ...bot_logging import record_event
from ...config import page_size
from ...keyboards.admin import (
	channel_actions,
	channel_edit_fields,
	channel_purposes,
	channels_list,
	channels_menu,
	confirm,
)
from ...keyboards.common import btn, cancel_keyboard, keyboard
from ...services.bot_settings import update_settings
from ...services.channels import (
	add_channel,
	channels_by_purpose_sync,
	counts_by_purpose,
	delete_channel,
	get_channel,
	purpose_label,
	resolve_chat,
	ChatResolutionError,
	test_channel,
	test_channels,
	toggle_active,
	update_channel,
)
from ...services.channels import all_channels
from ...states import AdminChannelStates
from ...texts import (
	ADMIN_CHANNEL_ASK_CHAT,
	ADMIN_CHANNEL_ASK_PURPOSE,
	ADMIN_CHANNEL_ASK_TITLE,
	ADMIN_CHANNEL_ASK_USERNAME,
	ADMIN_CHANNEL_DELETE_CONFIRM,
	ADMIN_CHANNEL_DELETED,
	ADMIN_CHANNEL_EMPTY,
	ADMIN_CHANNEL_LIST,
	ADMIN_CHANNEL_PREVIEW,
	ADMIN_CHANNEL_PUBLISH_SET,
	ADMIN_CHANNEL_SAVED,
	ADMIN_CHANNEL_TESTING,
	ADMIN_CHANNEL_TEST_RESULT,
	ADMIN_CHANNEL_TOGGLED,
	ADMIN_CHANNEL_UNREACHABLE,
	ADMIN_CHANNELS_MENU,
	ADMIN_INVALID_INPUT,
	EDIT_PROMPT,
	NOT_FOUND,
)
from ...utils import escape_html, paginate, parse_int, to_async
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="admin-channels")


def _context(callback: CallbackQuery, *, purpose: str, page: int) -> str:
	return f"{cb.ADM_CHANNELS}:list:{purpose}:{page}"


async def channels_menu_text() -> str:
	counts = await counts_by_purpose()
	return (
		ADMIN_CHANNELS_MENU
		+ f"\n\n🔒 Majburiy: <b>{counts.get('required', 0)}</b>"
		+ f"\n☁️ Saqlash: <b>{counts.get('storage', 0)}</b>"
		+ f"\n📢 Ommaviy: <b>{counts.get('public', 0)}</b>"
	)


@router.callback_query(F.data == cb.ADM_CHANNELS)
async def show_menu(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	await render(callback, await channels_menu_text(), markup=channels_menu(), edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_CHANNELS}:list:"))
async def list_channels(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	purpose = args[0] if args else ""
	page = parse_int(args[1] if len(args) > 1 else None, minimum=1) or 1
	if purpose not in TelegramChannel.Purpose.values:
		await render(callback, ADMIN_INVALID_INPUT, markup=channels_menu(), edit=True)
		return
	channels = await to_async(channels_by_purpose_sync)(purpose)
	items, page, pages = paginate(channels, page, page_size())
	if not items:
		await render(
			callback,
			ADMIN_CHANNEL_EMPTY,
			markup=channels_list([], purpose, 1, 1),
			edit=True,
		)
		return
	await render(
		callback,
		ADMIN_CHANNEL_LIST.format(label=purpose_label(purpose), page=page, pages=pages),
		markup=channels_list(items, purpose, page, pages),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_CHANNELS}:view:"))
async def view_channel(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	args = cb.section_args(callback.data)
	channel_pk = parse_int(args[0] if args else None, minimum=1)
	purpose = args[1] if len(args) > 1 else TelegramChannel.Purpose.STORAGE
	page = parse_int(args[2] if len(args) > 2 else None, minimum=1) or 1
	channel = await get_channel(channel_pk) if channel_pk else None
	if channel is None:
		await render(callback, NOT_FOUND, markup=channels_menu(), edit=True)
		return
	await render(
		callback,
		channel_card_text(channel),
		markup=channel_actions(channel, purpose=purpose, page=page),
		edit=True,
	)


def channel_card_text(channel) -> str:
	health = "✅" if channel.last_check_ok else ("❌" if channel.last_checked_at else "⚪️")
	return (
		f"📡 <b>{escape_html(channel.title)}</b>\n"
		f"🆔 Chat ID: <code>{channel.chat_id}</code>\n"
		f"🔗 Username: {escape_html(channel.username) or '—'}\n"
		f"🧷 Havola: {escape_html(channel.invite_link) or '—'}\n"
		f"📌 Turi: {purpose_label(channel.purpose)}\n"
		f"🟢 Holati: {'faol' if channel.is_active else 'o‘chirilgan'}\n"
		f"{health} Oxirgi tekshiruv: {'ok' if channel.last_check_ok else 'muammo'}"
	)


# -------------------------------------------------------------------- creation
@router.callback_query(F.data.startswith(f"{cb.ADM_CHANNELS}:new:"))
async def start_creation(callback: CallbackQuery, state: FSMContext) -> None:
	args = cb.section_args(callback.data)
	purpose = args[0] if args else ""
	if purpose not in TelegramChannel.Purpose.values:
		await render(callback, ADMIN_CHANNEL_ASK_PURPOSE, markup=channel_purposes(f"{cb.ADM_CHANNELS}:new"), edit=True)
		return
	await state.clear()
	await state.set_state(AdminChannelStates.chat)
	await state.update_data(channel_draft={"purpose": purpose})
	await render(callback, ADMIN_CHANNEL_ASK_CHAT, markup=cancel_keyboard(), edit=True)


@router.message(AdminChannelStates.chat)
async def draft_chat(message: Message, state: FSMContext, bot) -> None:
	try:
		chat = await resolve_chat(bot, message.text or "")
	except ChatResolutionError as exc:
		await message.answer(f"{ADMIN_CHANNEL_UNREACHABLE}\n\n{escape_html(exc)}", reply_markup=cancel_keyboard())
		return
	data = await state.get_data()
	draft = dict(data.get("channel_draft") or {})
	draft.update(
		chat_id=chat.id,
		chat_title=getattr(chat, "title", None) or getattr(chat, "full_name", "") or str(chat.id),
		username=getattr(chat, "username", "") or "",
		invite_link=getattr(chat, "invite_link", "") or "",
	)
	await state.update_data(channel_draft=draft)
	await state.set_state(AdminChannelStates.title)
	await message.answer(
		f"{ADMIN_CHANNEL_ASK_TITLE}\n\nAniqlangan nom: <b>{escape_html(draft['chat_title'])}</b>\n"
		"Shu nomni ishlatish uchun <code>-</code> yuboring.",
		reply_markup=cancel_keyboard(),
	)


@router.message(AdminChannelStates.title)
async def draft_title(message: Message, state: FSMContext) -> None:
	raw = (message.text or "").strip()
	data = await state.get_data()
	draft = dict(data.get("channel_draft") or {})
	draft["title"] = draft.get("chat_title") if raw == "-" else raw[:200]
	if not draft.get("title"):
		await message.answer(ADMIN_INVALID_INPUT)
		return
	await state.update_data(channel_draft=draft)
	await state.set_state(AdminChannelStates.username)
	await message.answer(
		f"{ADMIN_CHANNEL_ASK_USERNAME}\n\nAniqlangan username: <b>{escape_html(draft.get('username') or '—')}</b>",
		reply_markup=cancel_keyboard(),
	)


@router.message(AdminChannelStates.username)
async def draft_username(message: Message, state: FSMContext) -> None:
	raw = (message.text or "").strip()
	data = await state.get_data()
	draft = dict(data.get("channel_draft") or {})
	if raw and raw != "-":
		draft["username"] = raw.lstrip("@")[:64]
	await state.update_data(channel_draft=draft)
	await message.answer(
		ADMIN_CHANNEL_PREVIEW.format(
			title=escape_html(draft.get("title") or "—"),
			chat_id=draft.get("chat_id"),
			username=escape_html(draft.get("username") or "—"),
			purpose=purpose_label(draft.get("purpose") or ""),
		),
		reply_markup=confirm(f"{cb.ADM_CHANNELS}:save", cb.CANCEL),
	)


@router.callback_query(F.data == f"{cb.ADM_CHANNELS}:save")
async def save_channel(callback: CallbackQuery, state: FSMContext, bot) -> None:
	data = await state.get_data()
	draft = dict(data.get("channel_draft") or {})
	if not draft.get("chat_id"):
		await render(callback, ADMIN_INVALID_INPUT, markup=channels_menu(), edit=True)
		return
	channel = await add_channel(
		int(draft["chat_id"]),
		draft.get("title") or str(draft["chat_id"]),
		purpose=draft.get("purpose") or TelegramChannel.Purpose.STORAGE,
		username=draft.get("username") or "",
		invite_link=draft.get("invite_link") or "",
	)
	await state.clear()
	result = await test_channel(bot, channel)
	await to_async(record_event)(
		"INFO",
		f"Channel saved: {channel.title} ({channel.chat_id}) as {channel.purpose}",
		telegram_id=callback.from_user.id,
	)
	await render(
		callback,
		ADMIN_CHANNEL_SAVED.format(title=escape_html(channel.title))
		+ "\n\n"
		+ ADMIN_CHANNEL_TEST_RESULT.format(
			title=escape_html(result.title or channel.title),
			status=result.status_text,
			chat_type=result.chat_type or "—",
			can_post="✅" if result.can_post else "❌",
			can_check="✅" if result.can_check else "❌",
			message=escape_html(result.message),
		),
		markup=channel_actions(channel, purpose=channel.purpose, page=1),
		edit=True,
	)


# --------------------------------------------------------------------- testing
@router.callback_query(F.data == f"{cb.ADM_CHANNELS}:testall")
async def test_all(callback: CallbackQuery, bot) -> None:
	await callback.answer(ADMIN_CHANNEL_TESTING)
	results = await test_channels(bot)
	if not results:
		await render(callback, ADMIN_CHANNEL_EMPTY, markup=channels_menu(), edit=True)
		return
	lines = [ADMIN_CHANNEL_TESTING.replace("⏳ ", "") + "\n"]
	for result in results:
		lines.append(
			f"{'✅' if result.ok else '❌'} <b>{escape_html(result.channel.title)}</b> "
			f"({purpose_label(result.channel.purpose)})\n"
			f"   post: {'✅' if result.can_post else '❌'} · check: {'✅' if result.can_check else '❌'}\n"
			f"   {escape_html(result.message)}"
		)
	await render(callback, "\n".join(lines), markup=channels_menu(), edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_CHANNELS}:test:"))
async def test_one(callback: CallbackQuery, bot) -> None:
	args = cb.section_args(callback.data)
	channel_pk = parse_int(args[0] if args else None, minimum=1)
	channel = await get_channel(channel_pk) if channel_pk else None
	if channel is None:
		await render(callback, NOT_FOUND, markup=channels_menu(), edit=True)
		return
	result = await test_channel(bot, channel)
	await render(
		callback,
		ADMIN_CHANNEL_TEST_RESULT.format(
			title=escape_html(result.title or channel.title),
			status=result.status_text,
			chat_type=result.chat_type or "—",
			can_post="✅" if result.can_post else "❌",
			can_check="✅" if result.can_check else "❌",
			message=escape_html(result.message or result.error or "—"),
		),
		markup=channel_actions(channel, purpose=channel.purpose, page=1),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_CHANNELS}:tog:"))
async def toggle_channel(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	channel_pk = parse_int(args[0] if args else None, minimum=1)
	purpose = args[1] if len(args) > 1 else TelegramChannel.Purpose.STORAGE
	page = parse_int(args[2] if len(args) > 2 else None, minimum=1) or 1
	channel = await get_channel(channel_pk) if channel_pk else None
	if channel is None:
		await render(callback, NOT_FOUND, markup=channels_menu(), edit=True)
		return
	active = await toggle_active(channel)
	await callback.answer(ADMIN_CHANNEL_TOGGLED.format(state="faol" if active else "o'chirilgan"))
	await render(
		callback,
		channel_card_text(channel),
		markup=channel_actions(channel, purpose=purpose, page=page),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_CHANNELS}:pub:"))
async def set_publish_channel(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	channel_pk = parse_int(args[0] if args else None, minimum=1)
	channel = await get_channel(channel_pk) if channel_pk else None
	if channel is None:
		await render(callback, NOT_FOUND, markup=channels_menu(), edit=True)
		return
	if channel.purpose == TelegramChannel.Purpose.STORAGE:
		await update_channel(channel, purpose=TelegramChannel.Purpose.PUBLIC)
	await update_settings(publish_channel=channel)
	await render(
		callback,
		ADMIN_CHANNEL_PUBLISH_SET.format(title=escape_html(channel.title)),
		markup=channel_actions(channel, purpose=channel.purpose, page=1),
		edit=True,
	)


# --------------------------------------------------------------------- editing
@router.callback_query(F.data.startswith(f"{cb.ADM_CHANNELS}:edit:"))
async def start_edit(callback: CallbackQuery, state: FSMContext) -> None:
	args = cb.section_args(callback.data)
	channel_pk = parse_int(args[0] if args else None, minimum=1)
	field = args[1] if len(args) > 1 else ""
	channel = await get_channel(channel_pk) if channel_pk else None
	if channel is None or not field:
		await render(callback, NOT_FOUND, markup=channels_menu(), edit=True)
		return
	if field == "purpose":
		await render(
			callback,
			ADMIN_CHANNEL_ASK_PURPOSE,
			markup=channel_purposes(f"{cb.ADM_CHANNELS}:setp:{channel.pk}"),
			edit=True,
		)
		return
	await state.set_state(AdminChannelStates.edit_value)
	await state.update_data(channel_id=channel.pk, channel_field=field)
	await render(
		callback,
		EDIT_PROMPT.format(cancel_hint="Bekor qilish uchun ❌ tugmasini bosing."),
		markup=keyboard(
			[btn("⬅️ Orqaga", f"{cb.ADM_CHANNELS}:view:{channel.pk}:{channel.purpose}:1")],
			[btn("❌ Bekor qilish", cb.CANCEL)],
		),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_CHANNELS}:setp:"))
async def set_purpose(callback: CallbackQuery, state: FSMContext) -> None:
	args = cb.section_args(callback.data)
	channel_pk = parse_int(args[0] if args else None, minimum=1)
	purpose = args[1] if len(args) > 1 else ""
	channel = await get_channel(channel_pk) if channel_pk else None
	if channel is None or purpose not in TelegramChannel.Purpose.values:
		await render(callback, NOT_FOUND, markup=channels_menu(), edit=True)
		return
	await update_channel(channel, purpose=purpose)
	await state.update_data(channel_id=None, channel_field="")
	await render(
		callback,
		channel_card_text(channel),
		markup=channel_actions(channel, purpose=purpose, page=1),
		edit=True,
	)


@router.message(AdminChannelStates.edit_value)
async def apply_edit(message: Message, state: FSMContext) -> None:
	data = await state.get_data()
	channel = await get_channel(data.get("channel_id"))
	field = data.get("channel_field") or ""
	raw = (message.text or "").strip()
	if channel is None or field not in {"title", "username", "invite_link"} or not raw:
		await state.clear()
		await message.answer(ADMIN_INVALID_INPUT, reply_markup=channels_menu())
		return
	value = raw.lstrip("@") if field == "username" else raw[:255]
	await update_channel(channel, **{field: value})
	await state.update_data(channel_id=None, channel_field="")
	await state.set_state(None)
	await message.answer(
		channel_card_text(channel),
		reply_markup=channel_actions(channel, purpose=channel.purpose, page=1),
	)


# -------------------------------------------------------------------- deleting
@router.callback_query(F.data.startswith(f"{cb.ADM_CHANNELS}:del:"))
async def confirm_delete(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	channel_pk = parse_int(args[0] if args else None, minimum=1)
	purpose = args[1] if len(args) > 1 else TelegramChannel.Purpose.STORAGE
	page = parse_int(args[2] if len(args) > 2 else None, minimum=1) or 1
	channel = await get_channel(channel_pk) if channel_pk else None
	if channel is None:
		await render(callback, NOT_FOUND, markup=channels_menu(), edit=True)
		return
	await render(
		callback,
		ADMIN_CHANNEL_DELETE_CONFIRM.format(title=escape_html(channel.title)),
		markup=confirm(
			f"{cb.ADM_CHANNELS}:delok:{channel.pk}:{purpose}:{page}",
			f"{cb.ADM_CHANNELS}:view:{channel.pk}:{purpose}:{page}",
		),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_CHANNELS}:delok:"))
async def do_delete(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	channel_pk = parse_int(args[0] if args else None, minimum=1)
	purpose = args[1] if len(args) > 1 else TelegramChannel.Purpose.STORAGE
	page = parse_int(args[2] if len(args) > 2 else None, minimum=1) or 1
	channel = await get_channel(channel_pk) if channel_pk else None
	if channel is None:
		await render(callback, NOT_FOUND, markup=channels_menu(), edit=True)
		return
	title = channel.title
	await delete_channel(channel)
	await to_async(record_event)(
		"WARNING", f"Channel deleted: {title} (#{channel_pk})", telegram_id=callback.from_user.id
	)
	channels = await to_async(channels_by_purpose_sync)(purpose)
	items, page, pages = paginate(channels, page, page_size())
	await render(
		callback,
		ADMIN_CHANNEL_DELETED
		+ "\n\n"
		+ (ADMIN_CHANNEL_LIST.format(label=purpose_label(purpose), page=page, pages=pages) if items else ADMIN_CHANNEL_EMPTY),
		markup=channels_list(items, purpose, page, pages) if items else channels_menu(),
		edit=True,
	)
