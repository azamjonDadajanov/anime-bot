"""``/start`` registration, deep links, help and profile."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from django.utils import timezone
from users.referrals import parse_referral_payload, register_referral_sync

from ... import callbacks as cb
from ...keyboards.common import btn, keyboard
from ...keyboards.user import main_menu, profile_keyboard
from ...services.bot_settings import get_settings
from ...services.media import get_part_by_pk, get_title_by_code, get_title_by_slug
from ...services.users import (
	check_link_by_username,
	link_account_by_username,
	plan_expiry_text,
	user_card,
)
from ...texts import (
	ACCOUNT_ALREADY_LINKED,
	ACCOUNT_LINK_CANCELLED,
	ACCOUNT_LINK_CONFIRM,
	ACCOUNT_LINK_CONFLICT,
	ACCOUNT_LINKED,
	ACCOUNT_USERNAME_INACTIVE,
	ACCOUNT_USERNAME_TAKEN,
	BRAND,
	HELP_TEXT,
	MAIN_MENU,
	NOT_FOUND,
	PROFILE,
	REFERRAL_JOINED,
	WELCOME_BACK,
	WELCOME_NEW,
)
from ...utils import escape_html, human_datetime, to_async
from ..common import render
from .cards import send_part_card, send_title_card

logger = logging.getLogger(__name__)

router = Router(name="user-start")

DEEP_PREFIXES = ("anime", "series", "manga", "movie", "code", "title", "part", "ref")


def parse_deep_link(payload: str) -> tuple[str, str]:
	"""Parse a ``/start`` payload into ``(kind, value)``.

	Supported forms: ``anime_1234``, ``series_1234``, ``code_1234``, a bare
	4-digit code, or a slug.
	"""
	text = (payload or "").strip()
	if not text:
		return ("", "")
	lowered = text.lower()
	for prefix in DEEP_PREFIXES:
		marker = f"{prefix}_"
		if lowered.startswith(marker):
			return (prefix, text[len(marker):])
	if text.isdigit():
		return ("code", text)
	return ("slug", text)


def is_new_profile(profile) -> bool:
	"""Fallback heuristic used when the middleware flag is unavailable."""
	return (timezone.now() - profile.created_at).total_seconds() < 60


async def send_welcome(
	message: Message,
	profile,
	is_admin: bool,
	*,
	is_new_user: bool | None = None,
) -> None:
	card = await to_async(user_card)(profile)
	name = escape_html(card["name"])
	if is_new_user is None:
		is_new_user = is_new_profile(profile)
	template = WELCOME_NEW if is_new_user else WELCOME_BACK
	text = template.format(brand=BRAND, name=name)
	try:
		settings = await get_settings()
		custom = (settings.welcome_text or "").strip()
		if custom:
			text = f"{custom}\n\n{text}"
	except Exception:  # noqa: BLE001 - a settings failure must not block /start
		logger.warning("Could not load welcome_text settings.", exc_info=True)
	await message.answer(
		text,
		reply_markup=main_menu(is_admin, profile),
	)


async def open_payload(target, payload: str, *, bot, profile) -> bool:
	"""Open content addressed by a deep link, still enforcing access rules."""
	kind, value = parse_deep_link(payload)
	if not kind:
		return False

	if kind == "part":
		part_id = int(value) if value.isdigit() else 0
		part = await get_part_by_pk(part_id) if part_id else None
		if part is None:
			await render(target, NOT_FOUND)
			return True
		await send_part_card(target, part, profile=profile, bot=bot, origin="cat")
		return True

	if kind == "slug":
		title = await get_title_by_slug(value)
	else:
		title = await get_title_by_code(value)

	if title is None:
		await render(target, NOT_FOUND)
		return True
	await send_title_card(target, title, profile=profile, bot=bot, page=1, origin="cat")
	return True


LINK_MESSAGES = {
	"linked": ACCOUNT_LINKED,
	"already": ACCOUNT_ALREADY_LINKED,
	"taken": ACCOUNT_USERNAME_TAKEN,
	"conflict": ACCOUNT_LINK_CONFLICT,
	"inactive": ACCOUNT_USERNAME_INACTIVE,
}


async def link_account(target, payload: str, profile, state: FSMContext | None = None) -> bool:
	"""Offer to bind the Telegram profile to the site account in ``payload``.

	Nothing is written yet: the status is read first (``ready`` → a confirm
	card with inline buttons), and the real link only happens in the
	``alink:<username>`` callback. Negative outcomes (unknown name, taken,
	conflict, already) still answer immediately. Returns ``False`` when the
	payload is not a registered username so the caller can fall back to the
	content deep link.
	"""
	username = (payload or "").strip().lstrip("@")
	status = await check_link_by_username(profile, username)
	if status == "not_found":
		return False
	if status == "ready":
		if state is not None:
			await state.update_data(pending_link=username)
		await render(
			target,
			ACCOUNT_LINK_CONFIRM.format(username=escape_html(username)),
			markup=keyboard(
				[btn("✅ Ha, ulash", cb.join(cb.LINK_CONFIRM, username))],
				[btn("↩️ Bekor qilish", cb.LINK_CANCEL)],
			),
		)
		return True
	message = LINK_MESSAGES.get(status)
	if message is None:
		return False
	await render(target, message.format(username=escape_html(username)))
	return True


@router.callback_query(F.data.startswith(f"{cb.LINK_CONFIRM}:"))
async def confirm_link_account(
	callback: CallbackQuery, state: FSMContext, profile
) -> None:
	"""«✅ Ha, ulash»: actually bind the profile to the named account."""
	args = cb.split_data(callback.data)
	username = args[1] if len(args) > 1 else ""
	if not username:
		await callback.answer(NOT_FOUND[:200], show_alert=True)
		return
	await state.update_data(pending_link=None)
	status = await link_account_by_username(profile, username)
	message = LINK_MESSAGES.get(status) or NOT_FOUND
	await render(callback, message.format(username=escape_html(username)), edit=True)


@router.callback_query(F.data == cb.LINK_CANCEL)
async def cancel_link_account(callback: CallbackQuery, state: FSMContext, profile) -> None:
	"""«↩️ Bekor qilish»: leave the profile exactly as it was."""
	await state.update_data(pending_link=None)
	await render(callback, ACCOUNT_LINK_CANCELLED, edit=True)


@router.message(CommandStart(deep_link=True))
async def start_with_payload(
	message: Message,
	command,
	state: FSMContext,
	profile,
	is_admin: bool,
	bot,
	is_new_user: bool = True,
) -> None:
	await state.clear()
	await send_welcome(message, profile, is_admin, is_new_user=is_new_user)
	payload = command.args or ""
	# Referral deep link (``ref_<telegram_id>``): attribute the invitee once and
	# stop — there is no content to open for this payload form.
	if parse_deep_link(payload)[0] == "ref":
		inviter_id = parse_referral_payload(payload)
		if inviter_id is not None:
			await to_async(register_referral_sync)(invitee=profile, inviter_tg_id=inviter_id)
		await message.answer(REFERRAL_JOINED, reply_markup=main_menu(is_admin, profile))
		return
	# A bare payload (the website profile link) names a site account first and
	# only falls back to a title slug when no such account exists. The link
	# itself happens only after the inline confirm card is pressed.
	if parse_deep_link(payload)[0] == "slug" and await link_account(
		message, payload, profile, state
	):
		return
	await open_payload(message, payload, bot=bot, profile=profile)


@router.message(CommandStart())
async def start_plain(
	message: Message,
	state: FSMContext,
	profile,
	is_admin: bool,
	is_new_user: bool = True,
) -> None:
	await state.clear()
	await send_welcome(message, profile, is_admin, is_new_user=is_new_user)


@router.message(Command("help", "yordam"))
async def help_command(message: Message, profile, is_admin: bool) -> None:
	await message.answer(HELP_TEXT.format(brand=BRAND), reply_markup=main_menu(is_admin, profile))


@router.callback_query(F.data == cb.MENU)
async def show_menu(callback: CallbackQuery, state: FSMContext, profile, is_admin: bool) -> None:
	await state.clear()
	await render(
		callback,
		MAIN_MENU.format(brand=BRAND),
		markup=main_menu(is_admin, profile),
		edit=True,
	)


@router.callback_query(F.data == cb.HELP)
async def show_help(callback: CallbackQuery, profile, is_admin: bool) -> None:
	await render(callback, HELP_TEXT.format(brand=BRAND), markup=main_menu(is_admin, profile), edit=True)


@router.callback_query(F.data == cb.PROFILE)
async def show_profile(callback: CallbackQuery, profile) -> None:
	card = await to_async(user_card)(profile)
	text = PROFILE.format(
		telegram_id=profile.telegram_id,
		name=escape_html(card["name"]),
		username=escape_html(card["username"]),
		plan=card["plan_display"],
		expires=plan_expiry_text(card),
		favorites=card["favorites"],
		created=human_datetime(card["created"]),
	)
	await render(callback, text, markup=profile_keyboard(), edit=True)
