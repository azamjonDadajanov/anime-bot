"""Logs and reports screens."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ... import callbacks as cb
from ...keyboards.admin import logs_menu
from ...models import BotLogEntry
from ...services.logs import level_icon, purge_logs, recent_logs
from ...services.stats import reports
from ...texts import ADMIN_LOGS_ENTRY, ADMIN_LOGS_EMPTY, ADMIN_LOGS_MENU, ADMIN_REPORTS
from ...utils import escape_html, to_async, truncate
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="admin-logs")

LOG_LIMIT = 12


def format_entries(entries) -> str:
	if not entries:
		return ADMIN_LOGS_EMPTY
	lines = []
	for entry in entries:
		lines.append(
			ADMIN_LOGS_ENTRY.format(
				time=entry.created_at.strftime("%d.%m %H:%M"),
				level=f"{level_icon(entry.level)} {entry.level}",
				message=escape_html(truncate(entry.message, 160)),
			)
		)
	return ADMIN_LOGS_MENU + "\n\n" + "\n".join(lines)


@router.callback_query(F.data == cb.ADM_LOGS)
async def show_menu(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	await render(callback, ADMIN_LOGS_MENU, markup=logs_menu(), edit=True)


@router.callback_query(F.data == f"{cb.ADM_LOGS}:all")
async def show_all(callback: CallbackQuery) -> None:
	entries = await recent_logs(LOG_LIMIT)
	await render(callback, format_entries(entries), markup=logs_menu(), edit=True)


@router.callback_query(F.data == f"{cb.ADM_LOGS}:errors")
async def show_errors(callback: CallbackQuery) -> None:
	entries = await recent_logs(LOG_LIMIT, level=BotLogEntry.Level.ERROR)
	critical = await recent_logs(LOG_LIMIT, level=BotLogEntry.Level.CRITICAL)
	merged = sorted(entries + critical, key=lambda item: item.created_at, reverse=True)[:LOG_LIMIT]
	await render(callback, format_entries(merged), markup=logs_menu(), edit=True)


@router.callback_query(F.data == f"{cb.ADM_LOGS}:reports")
async def show_reports(callback: CallbackQuery) -> None:
	data = await reports(days=30)
	await render(
		callback,
		ADMIN_REPORTS.format(
			broadcasts=data["broadcasts"],
			sent=data["sent"],
			blocked=data["blocked"],
			failed=data["failed"],
			logs=data["logs"],
		)
		+ f"\n\n⚠️ Xatolar (30 kun): <b>{data['errors']}</b>",
		markup=logs_menu(),
		edit=True,
	)


@router.callback_query(F.data == f"{cb.ADM_LOGS}:purge")
async def purge(callback: CallbackQuery) -> None:
	deleted = await purge_logs(days=30)
	await callback.answer(f"🧹 {deleted} ta yozuv o'chirildi.")
	entries = await recent_logs(LOG_LIMIT)
	await render(callback, format_entries(entries), markup=logs_menu(), edit=True)
