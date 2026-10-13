"""Paid plan (subscription) purchase flow.

Website and bot share the same ``SubscriptionRequest`` rows: the bot shows the
plan catalogue with live database counters, the card number from ``.env`` and a
short guide, then waits for the payment screenshot. The screenshot creates the
request and notifies every administrator, who approve or reject it with inline
buttons.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from users.models import Subscription, SubscriptionRequest

from ... import callbacks as cb
from ...keyboards.user import (
	profile_keyboard,
	subscription_keyboard,
)
from ...states import UserSubscriptionStates
from ...texts import (
	NOT_FOUND,
	SUBREQ_ALREADY_PLAN,
	SUBREQ_AWAITING_SCREENSHOT,
	SUBREQ_CARD_HINT,
	SUBREQ_PENDING_NOTICE,
	SUBREQ_SAVED,
)
from ...utils import escape_html, to_async
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="user-subscription")


def plan_details_sync(plan: str):
	from users.plans import plan_details as build_plan_details

	return build_plan_details(plan)


def all_plans_sync():
	from users.plans import all_plan_details, card_number

	return all_plan_details(), card_number()


def current_plan_sync(profile) -> str:
	user = getattr(profile, "auth_user", None)
	subscription = getattr(user, "subscription", None) if user else None
	return (subscription.plan if subscription else "free") or "free"


def has_pending_sync(user, plan: str) -> bool:
	return SubscriptionRequest.objects.filter(
		user=user, plan=plan, status=SubscriptionRequest.Status.PENDING
	).exists()


load_plans = to_async(all_plans_sync)
load_plan_details = to_async(plan_details_sync)
load_current_plan = to_async(current_plan_sync)
check_pending = to_async(has_pending_sync)


def _plan_rows(plans) -> str:
	lines = []
	for plan in plans:
		features = "  ".join(
			f"{item['display']} {item['label']}" for item in plan.get("features", [])
		)
		price = int(plan.get("price") or 0)
		price_text = "Bepul" if price <= 0 else f"{price:,} so'm"
		lines.append(
			f"🔸 <b>{escape_html(plan['label'])}</b> — {price_text}\n"
			f"   {escape_html(features)}"
		)
	return "\n".join(lines)


async def send_subscription_page(target, profile, *, edit: bool = False) -> None:
	plans, card = await load_plans()
	current = await load_current_plan(profile)
	text = (
		"🎫 <b>Obunalar</b>\n\n"
		f"{_plan_rows(plans)}\n\n"
		"Joriy tarif: <b>{}</b>\n\n"
		"Tarifni o'zgartirmoqchi bo'lsangiz, kerakli tarifni tanlang — "
		"to'lov yo'riqnomasi ko'rsatiladi.".format(escape_html(current.upper()))
	)
	await render(target, text, markup=subscription_keyboard(plans, current), edit=edit)


@router.callback_query(F.data == cb.SUBSCRIPTION)
async def show_subscriptions(callback: CallbackQuery, profile) -> None:
	await send_subscription_page(callback, profile, edit=True)


@router.callback_query(F.data.startswith(f"{cb.SUBSCRIPTION_BUY}:"))
async def start_purchase(callback: CallbackQuery, state: FSMContext, profile) -> None:
	args = callback.data.split(":")
	plan = args[2] if len(args) > 2 else ""
	plans, card = await load_plans()
	known = {item["id"] for item in plans}
	if plan not in known:
		await callback.answer(NOT_FOUND[:200], show_alert=True)
		return

	current = await load_current_plan(profile)
	if plan == current:
		await callback.answer(SUBREQ_ALREADY_PLAN[:200], show_alert=True)
		return

	user = getattr(profile, "auth_user", None)
	if user is None:
		await callback.answer(NOT_FOUND[:200], show_alert=True)
		return
	if await check_pending(user, plan):
		await callback.answer(SUBREQ_PENDING_NOTICE[:200], show_alert=True)
		return

	details = await load_plan_details(plan)
	price = int(details.get("price") or 0)
	price_text = "Bepul" if price <= 0 else f"{price:,} so'm"
	await state.set_state(UserSubscriptionStates.awaiting_screenshot)
	await state.update_data(plan=plan)

	features = "  ".join(
		f"{item['display']} {item['label']}" for item in details.get("features", [])
	)
	text = SUBREQ_CARD_HINT.format(
		plan=escape_html(details["label"]),
		price=price_text,
		card=escape_html(card or "-"),
	)
	text += f"\n\nTarifga kiradigan kontent:\n🔸 {escape_html(features)}"
	await render(
		callback,
		text,
		markup=subscription_keyboard(plans, current),
		edit=True,
	)


@router.message(UserSubscriptionStates.awaiting_screenshot, F.photo)
async def receive_screenshot(message: Message, state: FSMContext, profile) -> None:
	data = await state.get_data()
	plan = data.get("plan") or ""
	user = getattr(profile, "auth_user", None)
	if user is None or plan not in Subscription.Plan.values:
		await state.clear()
		await message.answer(NOT_FOUND, reply_markup=profile_keyboard())
		return

	if await check_pending(user, plan):
		await state.clear()
		await message.answer(SUBREQ_PENDING_NOTICE, reply_markup=profile_keyboard())
		return

	photo = message.photo[-1]
	from users.plans import card_number, plan_price

	instance = await to_async(_create_request)(
		user=user,
		plan=plan,
		photo_file_id=photo.file_id,
		amount=plan_price(plan),
		card=card_number(),
	)
	await state.clear()
	await message.answer(SUBREQ_SAVED, reply_markup=profile_keyboard())

	from users.telegram_notify import notify_admins_new_request

	try:
		await to_async(notify_admins_new_request)(instance)
	except Exception:  # noqa: BLE001 - a delivery failure must not lose the request
		logger.warning("Could not notify admins about request %s.", instance.pk, exc_info=True)


@router.message(UserSubscriptionStates.awaiting_screenshot)
async def screenshot_expected(message: Message) -> None:
	await message.answer(SUBREQ_AWAITING_SCREENSHOT)


def _create_request(*, user, plan, photo_file_id, amount, card):
	"""Persist the request; the Telegram photo is forwarded by the notifier."""
	request = SubscriptionRequest.objects.create(
		user=user,
		plan=plan,
		amount=amount,
		card_number=card,
		status=SubscriptionRequest.Status.PENDING,
		notes=f"telegram_photo:{photo_file_id}",
	)
	return request
