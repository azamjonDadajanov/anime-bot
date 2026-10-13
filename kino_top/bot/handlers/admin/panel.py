"""``/admin`` entry point and the statistics dashboard."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ... import callbacks as cb
from ...bot_logging import record_event
from ...keyboards.admin import admin_panel
from ...services.stats import dashboard
from ...texts import ADMIN_PANEL
from ...utils import to_async
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="admin-panel")


def dashboard_text(stats) -> str:
	return ADMIN_PANEL.format(
		users=stats["users"],
		active=stats["active_users"],
		media=stats["media"]["titles"],
		episodes=stats["media"]["episodes"],
		channels=stats["channels"]["total"],
		favorites=stats["favorites"],
	)


@router.message(Command("admin", "panel", "boshqaruv"))
async def open_panel(message: Message, profile) -> None:
	stats = await dashboard()
	await to_async(record_event)(
		"INFO",
		f"Administrator {profile.telegram_id} opened the panel.",
		telegram_id=profile.telegram_id,
	)
	await message.answer(dashboard_text(stats), reply_markup=admin_panel())


@router.callback_query(F.data == cb.ADM_STATS)
async def show_dashboard(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	stats = await dashboard()
	await render(callback, dashboard_text(stats), markup=admin_panel(), edit=True)
