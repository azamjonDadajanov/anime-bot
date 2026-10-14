"""Giveaway administration: build a raffle with conditions, draw the winners.

The builder asks for the name, the reward in days, how many winners to pick and
an optional "watched N anime via the bot" condition; the two live-verified
conditions (sponsor channels, referral link in the bio) are toggled on the last
step. Drawing re-verifies every candidate through the Bot API, then grants the
reward to the randomly picked winners and DMs them.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from users.giveaways import (
	GiveawayValidationError,
	all_giveaways_sync,
	create_giveaway_sync,
	delete_giveaway_sync,
	giveaway_count_sync,
	get_giveaway_sync,
	set_giveaway_status_sync,
)
from users.models import Giveaway

from ... import callbacks as cb
from ...bot_logging import record_event
from ...config import page_size
from ...keyboards.admin import (
	giveaway_actions,
	giveaway_confirm_delete,
	giveaway_confirm_draw,
	giveaway_flags_keyboard,
	giveaways_list,
	giveaways_menu,
)
from ...keyboards.common import cancel_keyboard
from ...services.giveaways import run_draw_async
from ...states import AdminGiveawayStates
from ...texts import (
	ADMIN_GIVEAWAY_ASK_DAYS,
	ADMIN_GIVEAWAY_ASK_MIN_VIEWS,
	ADMIN_GIVEAWAY_ASK_TITLE,
	ADMIN_GIVEAWAY_ASK_WINNERS,
	ADMIN_GIVEAWAY_ALREADY_DRAWN,
	ADMIN_GIVEAWAY_CARD,
	ADMIN_GIVEAWAY_CREATED,
	ADMIN_GIVEAWAY_DELETE_CONFIRM,
	ADMIN_GIVEAWAY_DELETED,
	ADMIN_GIVEAWAY_DRAWN,
	ADMIN_GIVEAWAY_DRAW_EMPTY,
	ADMIN_GIVEAWAY_DRAW_CONFIRM,
	ADMIN_GIVEAWAY_EMPTY,
	ADMIN_GIVEAWAY_INVALID,
	ADMIN_GIVEAWAY_LIST,
	ADMIN_GIVEAWAY_NOT_OPEN,
	ADMIN_GIVEAWAY_STATUS_LABELS,
	ADMIN_GIVEAWAYS_MENU,
	NOT_FOUND,
)
from ...utils import escape_html, paginate, parse_int, to_async
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="admin-giveaways")

all_giveaways = to_async(all_giveaways_sync)
giveaway_count = to_async(giveaway_count_sync)
create_giveaway = to_async(create_giveaway_sync)
get_giveaway = to_async(get_giveaway_sync)
set_giveaway_status = to_async(set_giveaway_status_sync)
delete_giveaway = to_async(delete_giveaway_sync)
# ``run_draw_async`` is already async (it awaits Bot API calls), so it is
# awaited directly — never wrapped with ``to_async``.

CANCEL_TARGET = f"{cb.ADM_GIVEAWAY}:cancel"


def _admin_user_sync(telegram_id: int):
	from django.contrib.auth import get_user_model

	return get_user_model().objects.filter(telegram_profile__telegram_id=telegram_id).first()


admin_user = to_async(_admin_user_sync)


def _status_label(giveaway) -> str:
	return ADMIN_GIVEAWAY_STATUS_LABELS.get(giveaway.status, giveaway.status)


def _giveaway_card_sync(giveaway) -> str:
	"""Card text; reads the winners relation (must run via ``to_async``)."""
	conditions = []
	if giveaway.min_bot_views > 0:
		conditions.append(f"🎬 botda ≥ {giveaway.min_bot_views} anime")
	if giveaway.require_channels:
		conditions.append("📡 homiy kanallar")
	if giveaway.require_bio_ref:
		conditions.append("🔗 bio'da havola")
	if not conditions:
		conditions.append("— (shart yo'q, faqat faol obuna)")

	winners = list(giveaway.winners.all())
	winners_line = "—"
	if winners:
		winners_line = "\n".join(
			f"• <code>{winner.telegram_id}</code> — {winner.days} kun"
			for winner in winners
		)

	return ADMIN_GIVEAWAY_CARD.format(
		title=escape_html(giveaway.title),
		days=giveaway.reward_days,
		winners_count=giveaway.winner_count,
		conditions=escape_html("; ".join(conditions)),
		status=escape_html(_status_label(giveaway)),
		winners=winners_line,
	)


giveaway_card = to_async(_giveaway_card_sync)


async def _render_menu(target, *, edit: bool = False) -> None:
	total = await giveaway_count()
	await render(
		target,
		ADMIN_GIVEAWAYS_MENU.format(total=total),
		markup=giveaways_menu(),
		edit=edit,
	)


async def _load(callback: CallbackQuery, index: int):
	"""Resolve a giveaway pk from ``a:ga:<action>:<pk>[:<page>]``."""
	args = cb.section_args(callback.data)
	value = args[index] if len(args) > index else None
	pk = parse_int(value, minimum=1)
	giveaway = await get_giveaway(pk) if pk else None
	if giveaway is None:
		await callback.answer(NOT_FOUND[:200], show_alert=True)
	return giveaway


async def _flags_text(data: dict) -> str:
	channels = "✅" if data.get("ga_channels") else "❌"
	bio = "✅" if data.get("ga_bio") else "❌"
	return (
		"⚙️ <b>Qo'shimcha shartlar</b>\n\n"
		f"📡 Homiy kanallarga obuna: <b>{channels}</b>\n"
		f"🔗 Bio'da referral havolasi: <b>{bio}</b>\n\n"
		"Bu shartlar g'olib aniqlashda <b>qayta tekshiriladi</b>.\n"
		"Tanlab bo'lgach «✅ Yaratish» ni bosing."
	)


@router.callback_query(F.data == cb.ADM_GIVEAWAY)
async def open_menu(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	await _render_menu(callback, edit=True)


@router.callback_query(F.data == CANCEL_TARGET)
async def cancel_builder(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	await _render_menu(callback, edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_GIVEAWAY}:list:"))
async def list_giveaways(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	args = cb.section_args(callback.data)
	page = parse_int(args[0] if args else None, minimum=1) or 1
	items = await all_giveaways()
	shown, page, pages = paginate(items, page, page_size())
	if not shown:
		await render(callback, ADMIN_GIVEAWAY_EMPTY, markup=giveaways_menu(), edit=True)
		return
	await render(
		callback,
		ADMIN_GIVEAWAY_LIST.format(page=page, pages=pages),
		markup=giveaways_list(shown, page, pages),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_GIVEAWAY}:view:"))
async def show_giveaway(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	giveaway = await _load(callback, 0)
	if giveaway is None:
		return
	await render(
		callback, await giveaway_card(giveaway), markup=giveaway_actions(giveaway), edit=True
	)


@router.callback_query(F.data == f"{cb.ADM_GIVEAWAY}:new")
async def start_builder(callback: CallbackQuery, state: FSMContext) -> None:
	await state.set_state(AdminGiveawayStates.ask_title)
	await state.update_data(
		ga_title=None,
		ga_days=None,
		ga_winners=3,
		ga_min_views=0,
		ga_channels=False,
		ga_bio=False,
	)
	await render(
		callback,
		ADMIN_GIVEAWAY_ASK_TITLE,
		markup=cancel_keyboard(CANCEL_TARGET),
		edit=True,
	)


@router.message(AdminGiveawayStates.ask_title)
async def receive_title(message: Message, state: FSMContext) -> None:
	title = (message.text or "").strip()
	if not title:
		await message.answer(ADMIN_GIVEAWAY_INVALID)
		return
	await state.update_data(ga_title=title[:200])
	await state.set_state(AdminGiveawayStates.ask_days)
	await message.answer(ADMIN_GIVEAWAY_ASK_DAYS, reply_markup=cancel_keyboard(CANCEL_TARGET))


@router.message(AdminGiveawayStates.ask_days)
async def receive_days(message: Message, state: FSMContext) -> None:
	days = parse_int(message.text, minimum=1, maximum=3650)
	if days is None:
		await message.answer(ADMIN_GIVEAWAY_INVALID)
		return
	await state.update_data(ga_days=days)
	await state.set_state(AdminGiveawayStates.ask_winners)
	await message.answer(ADMIN_GIVEAWAY_ASK_WINNERS, reply_markup=cancel_keyboard(CANCEL_TARGET))


@router.message(AdminGiveawayStates.ask_winners)
async def receive_winners(message: Message, state: FSMContext) -> None:
	winners = parse_int(message.text, minimum=1, maximum=50)
	if winners is None:
		await message.answer(ADMIN_GIVEAWAY_INVALID)
		return
	await state.update_data(ga_winners=winners)
	await state.set_state(AdminGiveawayStates.ask_min_views)
	await message.answer(
		ADMIN_GIVEAWAY_ASK_MIN_VIEWS, reply_markup=cancel_keyboard(CANCEL_TARGET)
	)


@router.message(AdminGiveawayStates.ask_min_views)
async def receive_min_views(message: Message, state: FSMContext) -> None:
	min_views = parse_int(message.text, minimum=0, maximum=100000)
	if min_views is None:
		await message.answer(ADMIN_GIVEAWAY_INVALID)
		return
	await state.update_data(ga_min_views=min_views)
	await state.set_state(AdminGiveawayStates.flags)
	data = await state.get_data()
	await message.answer(
		await _flags_text(data),
		reply_markup=giveaway_flags_keyboard(
			require_channels=bool(data.get("ga_channels")),
			require_bio_ref=bool(data.get("ga_bio")),
		),
	)


@router.callback_query(AdminGiveawayStates.flags, F.data == f"{cb.ADM_GIVEAWAY}:fch")
async def toggle_channels(callback: CallbackQuery, state: FSMContext) -> None:
	data = await state.get_data()
	value = not bool(data.get("ga_channels"))
	await state.update_data(ga_channels=value)
	await render(
		callback,
		await _flags_text({**data, "ga_channels": value}),
		markup=giveaway_flags_keyboard(
			require_channels=value, require_bio_ref=bool(data.get("ga_bio"))
		),
		edit=True,
	)


@router.callback_query(AdminGiveawayStates.flags, F.data == f"{cb.ADM_GIVEAWAY}:fbio")
async def toggle_bio(callback: CallbackQuery, state: FSMContext) -> None:
	data = await state.get_data()
	value = not bool(data.get("ga_bio"))
	await state.update_data(ga_bio=value)
	await render(
		callback,
		await _flags_text({**data, "ga_bio": value}),
		markup=giveaway_flags_keyboard(
			require_channels=bool(data.get("ga_channels")), require_bio_ref=value
		),
		edit=True,
	)


@router.callback_query(AdminGiveawayStates.flags, F.data == f"{cb.ADM_GIVEAWAY}:create")
async def finalize_builder(callback: CallbackQuery, state: FSMContext) -> None:
	data = await state.get_data()
	try:
		giveaway = await create_giveaway(
			title=data.get("ga_title") or "",
			reward_days=data.get("ga_days") or 0,
			winner_count=data.get("ga_winners") or 3,
			min_bot_views=data.get("ga_min_views") or 0,
			require_channels=bool(data.get("ga_channels")),
			require_bio_ref=bool(data.get("ga_bio")),
			created_by=await admin_user(callback.from_user.id),
		)
	except GiveawayValidationError:
		await callback.answer(ADMIN_GIVEAWAY_INVALID[:200], show_alert=True)
		return

	await state.clear()
	await to_async(record_event)(
		"INFO",
		f"Giveaway '{giveaway.title}' created by {callback.from_user.id} "
		f"({giveaway.reward_days} days, {giveaway.winner_count} winners).",
		telegram_id=callback.from_user.id,
	)
	await render(
		callback,
		ADMIN_GIVEAWAY_CREATED.format(card=await giveaway_card(giveaway)),
		markup=giveaway_actions(giveaway),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_GIVEAWAY}:open:"))
async def reopen(callback: CallbackQuery) -> None:
	giveaway = await _load(callback, 0)
	if giveaway is None:
		return
	updated = await set_giveaway_status(giveaway.pk, Giveaway.Status.OPEN)
	await render(
		callback, await giveaway_card(updated or giveaway), markup=giveaway_actions(updated or giveaway), edit=True
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_GIVEAWAY}:close:"))
async def close(callback: CallbackQuery) -> None:
	giveaway = await _load(callback, 0)
	if giveaway is None:
		return
	updated = await set_giveaway_status(giveaway.pk, Giveaway.Status.CLOSED)
	await render(
		callback, await giveaway_card(updated or giveaway), markup=giveaway_actions(updated or giveaway), edit=True
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_GIVEAWAY}:draw:"))
async def ask_draw(callback: CallbackQuery) -> None:
	giveaway = await _load(callback, 0)
	if giveaway is None:
		return
	if giveaway.status == Giveaway.Status.DRAWN:
		await callback.answer(ADMIN_GIVEAWAY_ALREADY_DRAWN[:200], show_alert=True)
		return
	if giveaway.status not in (Giveaway.Status.OPEN, Giveaway.Status.DRAFT):
		await callback.answer(ADMIN_GIVEAWAY_NOT_OPEN[:200], show_alert=True)
		return
	await render(
		callback,
		ADMIN_GIVEAWAY_DRAW_CONFIRM.format(
			title=escape_html(giveaway.title),
			winners=giveaway.winner_count,
			days=giveaway.reward_days,
		),
		markup=giveaway_confirm_draw(giveaway),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_GIVEAWAY}:yes:"))
async def confirm_draw(callback: CallbackQuery, bot) -> None:
	args = cb.section_args(callback.data)
	pk = parse_int(args[0] if args else None, minimum=1)
	if pk is None:
		await callback.answer(NOT_FOUND[:200], show_alert=True)
		return
	await callback.answer("🎲 Tekshirilmoqda...")

	report = await run_draw_async(bot, pk, admin_telegram_id=callback.from_user.id)
	giveaway = report.giveaway
	if giveaway is None:
		await callback.answer(NOT_FOUND[:200], show_alert=True)
		return

	await to_async(record_event)(
		"INFO",
		f"Giveaway '{giveaway.title}' drawn by {callback.from_user.id}: "
		f"status={report.status}, eligible={report.eligible_count}, "
		f"winners={len(report.winners)}.",
		telegram_id=callback.from_user.id,
	)

	if report.status == "already_drawn":
		await render(
			callback,
			ADMIN_GIVEAWAY_ALREADY_DRAWN,
			markup=giveaway_actions(giveaway),
			edit=True,
		)
		return
	if report.status == "not_open":
		await render(
			callback,
			ADMIN_GIVEAWAY_NOT_OPEN,
			markup=giveaway_actions(giveaway),
			edit=True,
		)
		return
	if not report.winners:
		await render(
			callback,
			ADMIN_GIVEAWAY_DRAW_EMPTY.format(
				title=escape_html(giveaway.title), candidates=report.candidate_count
			),
			markup=giveaway_actions(giveaway),
			edit=True,
		)
		return

	lines = "\n".join(
		f"• <code>{winner.telegram_id}</code> — {winner.days} kun"
		for winner in report.winners
	)
	await render(
		callback,
		ADMIN_GIVEAWAY_DRAWN.format(
			title=escape_html(giveaway.title),
			eligible=report.eligible_count,
			won=len(report.winners),
			winners=lines,
		),
		markup=giveaway_actions(giveaway),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_GIVEAWAY}:del:"))
async def ask_delete(callback: CallbackQuery) -> None:
	giveaway = await _load(callback, 0)
	if giveaway is None:
		return
	await render(
		callback,
		ADMIN_GIVEAWAY_DELETE_CONFIRM.format(title=escape_html(giveaway.title)),
		markup=giveaway_confirm_delete(giveaway),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_GIVEAWAY}:dyes:"))
async def confirm_delete(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	pk = parse_int(args[0] if args else None, minimum=1)
	if pk is None:
		await callback.answer(NOT_FOUND[:200], show_alert=True)
		return
	await delete_giveaway(pk)
	await callback.answer(ADMIN_GIVEAWAY_DELETED[:200])
	await _render_menu(callback, edit=True)
