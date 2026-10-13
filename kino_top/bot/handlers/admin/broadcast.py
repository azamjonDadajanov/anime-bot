"""Broadcast composition, execution, cancellation and history."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from typing import Dict

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ... import callbacks as cb
from ...bot_logging import record_event
from ...config import page_size
from ...keyboards.admin import (
	broadcast_actions,
	broadcast_history,
	broadcast_menu,
	broadcast_preview,
	broadcast_running,
)
from ...keyboards.common import cancel_keyboard
from ...models import Broadcast
from ...services.broadcast import (
	BroadcastProgress,
	active_broadcast,
	attach_panel,
	create_broadcast,
	get_broadcast,
	payload_from_message,
	recent_broadcasts,
	request_cancel,
	resume_broadcast,
	run_broadcast,
	set_silent,
	set_total,
)
from ...services.users import recipients
from ...states import AdminBroadcastStates
from ...texts import (
	ADMIN_BROADCAST_ALREADY_RUNNING,
	ADMIN_BROADCAST_CANCEL_REQUESTED,
	ADMIN_BROADCAST_COMPOSE,
	ADMIN_BROADCAST_COMPOSE_MEDIA,
	ADMIN_BROADCAST_DONE,
	ADMIN_BROADCAST_EMPTY,
	ADMIN_BROADCAST_FORWARD,
	ADMIN_BROADCAST_MENU,
	ADMIN_BROADCAST_PREVIEW,
	ADMIN_BROADCAST_PROGRESS,
	ADMIN_BROADCAST_STARTED,
	ADMIN_INVALID_INPUT,
	NOT_FOUND,
)
from ...utils import escape_html, human_timesince, paginate, parse_int, percent, to_async
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="admin-broadcast")

_tasks: Dict[int, asyncio.Task] = {}

PROMO_KINDS = {
	Broadcast.Kind.TEXT: ADMIN_BROADCAST_COMPOSE,
	Broadcast.Kind.PHOTO: ADMIN_BROADCAST_COMPOSE_MEDIA,
	Broadcast.Kind.VIDEO: ADMIN_BROADCAST_COMPOSE_MEDIA,
	Broadcast.Kind.DOCUMENT: ADMIN_BROADCAST_COMPOSE_MEDIA,
	Broadcast.Kind.FORWARD: ADMIN_BROADCAST_FORWARD,
}


def progress_text(progress: BroadcastProgress) -> str:
	return ADMIN_BROADCAST_PROGRESS.format(
		pk=progress.pk,
		status=Broadcast.Status(progress.status).label if progress.status in Broadcast.Status.values else progress.status,
		total=progress.total,
		sent=progress.sent,
		failed=progress.failed,
		blocked=progress.blocked,
		processed=progress.processed,
		percent=percent(progress.processed, progress.total),
	)


async def show_preview(target, broadcast: Broadcast) -> None:
	count = len(await recipients(include_blocked=broadcast.include_blocked))
	if not count:
		await render(target, ADMIN_BROADCAST_EMPTY, markup=broadcast_menu())
		return
	await set_total(broadcast.pk, count)
	await render(
		target,
		ADMIN_BROADCAST_PREVIEW.format(
			kind=broadcast.get_kind_display(),
			recipients=count,
			silent="✅" if broadcast.disable_notification else "❌",
		),
		markup=broadcast_preview(broadcast.pk),
	)


async def _run(bot, pk: int, chat_id: int, message_id: int) -> None:
	async def progress_callback(progress: BroadcastProgress) -> None:
		try:
			await bot.edit_message_text(
				chat_id=chat_id,
				message_id=message_id,
				text=progress_text(progress),
				reply_markup=broadcast_running(pk),
			)
		except (TelegramBadRequest, TelegramAPIError):
			# Editing the live panel is best-effort; delivery must continue.
			return

	broadcast = await get_broadcast(pk)
	if broadcast is None:
		return
	started = dt.datetime.now(dt.timezone.utc)
	try:
		final = await run_broadcast(bot, broadcast, progress=progress_callback)
	except asyncio.CancelledError:  # pragma: no cover - shutdown path
		raise
	except Exception:  # noqa: BLE001 - never kill the polling loop
		logger.exception("Broadcast %s crashed.", pk)
		final = await get_broadcast(pk)

	duration = dt.datetime.now(dt.timezone.utc) - started
	summary = (
		ADMIN_BROADCAST_DONE.format(
			sent=final.sent_count if final else "?",
			failed=final.failed_count if final else "?",
			blocked=final.blocked_count if final else "?",
			duration=str(duration).split(".")[0],
		)
		if final is not None
		else ADMIN_INVALID_INPUT
	)
	try:
		await bot.edit_message_text(
			chat_id=chat_id,
			message_id=message_id,
			text=summary,
			reply_markup=broadcast_actions(final) if final else None,
		)
	except (TelegramBadRequest, TelegramAPIError):
		pass
	await to_async(record_event)(
		"INFO",
		f"Broadcast #{pk} finished: sent={getattr(final, 'sent_count', '?')} "
		f"failed={getattr(final, 'failed_count', '?')} blocked={getattr(final, 'blocked_count', '?')}",
	)


# ------------------------------------------------------------------ navigation
@router.callback_query(F.data == cb.ADM_BROADCAST)
async def show_menu(callback: CallbackQuery, profile, state: FSMContext) -> None:
	await state.clear()
	active = await active_broadcast(profile.telegram_id)
	if active is not None:
		await render(
			callback,
			progress_text(
				BroadcastProgress(
					pk=active.pk,
					status=active.status,
					total=active.total,
					sent=active.sent_count,
					failed=active.failed_count,
					blocked=active.blocked_count,
				)
			),
			markup=broadcast_running(active.pk),
			edit=True,
		)
		return
	await render(callback, ADMIN_BROADCAST_MENU, markup=broadcast_menu(), edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_BROADCAST}:list:"))
async def show_history(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	page = parse_int(args[0] if args else None, minimum=1) or 1
	items_all = await recent_broadcasts(limit=200)
	items, page, pages = paginate(items_all, page, page_size())
	if not items:
		await render(callback, ADMIN_BROADCAST_MENU, markup=broadcast_menu(), edit=True)
		return
	await render(
		callback,
		"📃 <b>Broadcast tarixi</b>",
		markup=broadcast_history(items, page, pages),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_BROADCAST}:view:"))
async def view_broadcast(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	pk = parse_int(args[0] if args else None, minimum=1)
	broadcast = await get_broadcast(pk) if pk else None
	if broadcast is None:
		await render(callback, NOT_FOUND, markup=broadcast_menu(), edit=True)
		return
	await render(
		callback,
		progress_text(
			BroadcastProgress(
				pk=broadcast.pk,
				status=broadcast.status,
				total=broadcast.total,
				sent=broadcast.sent_count,
				failed=broadcast.failed_count,
				blocked=broadcast.blocked_count,
			)
		)
		+ f"\n\n🕒 {human_timesince(broadcast.created_at)}",
		markup=broadcast_actions(broadcast),
		edit=True,
	)


# ------------------------------------------------------------------- composing
@router.callback_query(F.data.startswith(f"{cb.ADM_BROADCAST}:new:"))
async def start_compose(callback: CallbackQuery, state: FSMContext, profile) -> None:
	args = cb.section_args(callback.data)
	kind = args[0] if args else ""
	if kind not in Broadcast.Kind.values:
		await render(callback, ADMIN_INVALID_INPUT, markup=broadcast_menu(), edit=True)
		return
	active = await active_broadcast(profile.telegram_id)
	if active is not None:
		await callback.answer(ADMIN_BROADCAST_ALREADY_RUNNING)
		return
	await state.clear()
	await state.update_data(broadcast_kind=kind)
	await state.set_state(
		AdminBroadcastStates.compose
		if kind == Broadcast.Kind.TEXT
		else AdminBroadcastStates.awaiting_forward
	)
	await render(callback, PROMO_KINDS[kind], markup=cancel_keyboard(), edit=True)


@router.message(AdminBroadcastStates.compose)
async def compose_text(message: Message, state: FSMContext, profile) -> None:
	text = message.html_text or message.text or ""
	if not text.strip():
		await message.answer(ADMIN_INVALID_INPUT, reply_markup=cancel_keyboard())
		return
	data = await state.get_data()
	broadcast = await create_broadcast(
		admin_telegram_id=profile.telegram_id,
		kind=Broadcast.Kind.TEXT,
		text=text[:4000],
		protect_content=True,
	)
	await state.clear()
	await show_preview(message, broadcast)
	logger.info("Draft broadcast %s prepared from %s.", broadcast.pk, data.get("broadcast_kind"))


@router.message(AdminBroadcastStates.awaiting_forward)
async def compose_media(message: Message, state: FSMContext, profile) -> None:
	kind = (await state.get_data()).get("broadcast_kind") or Broadcast.Kind.TEXT
	payload = payload_from_message(message)
	if kind != Broadcast.Kind.FORWARD and payload.get("kind") != kind:
		await message.answer(
			ADMIN_INVALID_INPUT + f"\n\nKutilgan tur: <b>{kind}</b>", reply_markup=cancel_keyboard()
		)
		return
	if kind == Broadcast.Kind.FORWARD and payload.get("kind") != Broadcast.Kind.FORWARD:
		await message.answer(ADMIN_BROADCAST_FORWARD, reply_markup=cancel_keyboard())
		return

	broadcast = await create_broadcast(
		admin_telegram_id=profile.telegram_id,
		protect_content=True,
		**payload,
	)
	await state.clear()
	await show_preview(message, broadcast)


# ------------------------------------------------------------------ execution
@router.callback_query(F.data.startswith(f"{cb.ADM_BROADCAST}:silent:"))
async def toggle_silent(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	pk = parse_int(args[0] if args else None, minimum=1)
	broadcast = await get_broadcast(pk) if pk else None
	if broadcast is None:
		await render(callback, NOT_FOUND, markup=broadcast_menu(), edit=True)
		return
	await set_silent(pk, not broadcast.disable_notification)
	broadcast.disable_notification = not broadcast.disable_notification
	await show_preview(callback, broadcast)


@router.callback_query(F.data.startswith(f"{cb.ADM_BROADCAST}:drop:"))
async def drop_broadcast(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	pk = parse_int(args[0] if args else None, minimum=1)
	broadcast = await get_broadcast(pk) if pk else None
	if broadcast is not None and broadcast.status == Broadcast.Status.DRAFT:
		await to_async(broadcast.delete)()
	await render(callback, ADMIN_BROADCAST_MENU, markup=broadcast_menu(), edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_BROADCAST}:send:"))
async def send_broadcast(callback: CallbackQuery, bot, profile) -> None:
	args = cb.section_args(callback.data)
	pk = parse_int(args[0] if args else None, minimum=1)
	broadcast = await get_broadcast(pk) if pk else None
	if broadcast is None:
		await render(callback, NOT_FOUND, markup=broadcast_menu(), edit=True)
		return
	existing = _tasks.get(pk)
	if existing is not None and not existing.done():
		await callback.answer(ADMIN_BROADCAST_ALREADY_RUNNING)
		return

	chat_id = callback.message.chat.id
	message_id = callback.message.message_id
	await attach_panel(pk, chat_id, message_id)
	await render(
		callback,
		ADMIN_BROADCAST_STARTED,
		markup=broadcast_running(pk),
		edit=True,
	)
	task = asyncio.create_task(_run(bot, pk, chat_id, message_id))
	_tasks[pk] = task
	task.add_done_callback(lambda finished, key=pk: _tasks.pop(key, None))


@router.callback_query(F.data.startswith(f"{cb.ADM_BROADCAST}:cancel:"))
async def cancel_broadcast(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	pk = parse_int(args[0] if args else None, minimum=1)
	if not pk or not await request_cancel(pk):
		await callback.answer(NOT_FOUND)
		return
	await callback.answer(ADMIN_BROADCAST_CANCEL_REQUESTED)
	await to_async(record_event)(
		"WARNING", f"Broadcast #{pk} cancellation requested.", telegram_id=callback.from_user.id
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_BROADCAST}:resume:"))
async def resume(callback: CallbackQuery, bot) -> None:
	args = cb.section_args(callback.data)
	pk = parse_int(args[0] if args else None, minimum=1)
	broadcast = await get_broadcast(pk) if pk else None
	if broadcast is None:
		await render(callback, NOT_FOUND, markup=broadcast_menu(), edit=True)
		return
	existing = _tasks.get(pk)
	if existing is not None and not existing.done():
		await callback.answer(ADMIN_BROADCAST_ALREADY_RUNNING)
		return

	chat_id = callback.message.chat.id
	message_id = callback.message.message_id
	await attach_panel(pk, chat_id, message_id)
	await render(callback, ADMIN_BROADCAST_STARTED, markup=broadcast_running(pk), edit=True)

	async def progress_callback(progress: BroadcastProgress) -> None:
		try:
			await bot.edit_message_text(
				chat_id=chat_id,
				message_id=message_id,
				text=progress_text(progress),
				reply_markup=broadcast_running(pk),
			)
		except (TelegramBadRequest, TelegramAPIError):
			return

	async def runner() -> None:
		started = dt.datetime.now(dt.timezone.utc)
		final = await resume_broadcast(bot, pk, progress=progress_callback)
		duration = dt.datetime.now(dt.timezone.utc) - started
		try:
			await bot.edit_message_text(
				chat_id=chat_id,
				message_id=message_id,
				text=ADMIN_BROADCAST_DONE.format(
					sent=getattr(final, "sent_count", "?"),
					failed=getattr(final, "failed_count", "?"),
					blocked=getattr(final, "blocked_count", "?"),
					duration=str(duration).split(".")[0],
				),
				reply_markup=broadcast_actions(final) if final else None,
			)
		except (TelegramBadRequest, TelegramAPIError):
			pass

	task = asyncio.create_task(runner())
	_tasks[pk] = task
	task.add_done_callback(lambda finished, key=pk: _tasks.pop(key, None))


__all__ = ["router", "progress_text", "escape_html"]
