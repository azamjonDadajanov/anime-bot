"""Paid plan (subscription) purchase flow.

Website and bot share the same ``SubscriptionRequest`` rows: the bot shows the
plan catalogue with live database counters, the card number from ``.env`` and a
short guide, then waits for the payment screenshot. The screenshot creates the
request and notifies every administrator, who approve or reject it with inline
buttons.
"""

from __future__ import annotations

import logging
import math

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from django.utils import timezone
from users.models import SubscriptionRequest

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
from ...utils import escape_html, human_datetime, to_async
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
	return subscription_state_sync(profile)["plan"]


def subscription_state_sync(profile) -> dict:
	"""``{plan, label, active, expires_at}`` for the catalogue header."""
	user = getattr(profile, "auth_user", None)
	subscription = getattr(user, "subscription", None) if user else None
	if subscription is None:
		return {"plan": "free", "label": "Bepul", "active": False, "expires_at": None}
	return {
		"plan": subscription.plan or "free",
		"label": subscription.get_plan_display(),
		"active": subscription.is_active,
		"expires_at": subscription.expires_at,
	}


def has_pending_sync(user, plan: str) -> bool:
	return SubscriptionRequest.objects.filter(
		user=user, plan=plan, status=SubscriptionRequest.Status.PENDING
	).exists()


load_plans = to_async(all_plans_sync)
load_plan_details = to_async(plan_details_sync)
load_state = to_async(subscription_state_sync)
check_pending = to_async(has_pending_sync)


def _status_line(state: dict) -> str:
	if state["active"]:
		expires = state["expires_at"]
		days_left = max(0, math.ceil((expires - timezone.now()).total_seconds() / 86400))
		return f"✅ Faol · {human_datetime(expires)} gacha ({days_left} kun qoldi)"
	if state["plan"] == "free":
		return "⚪ Bepul tarif — faqat bepul kontent ochiq"
	return "⏳ Muddati o'tgan"


def _plan_rows(plans) -> str:
	lines = []
	for plan in plans:
		features = "  ".join(
			f"{item['display']} {item['label']}" for item in plan.get("features", [])
		)
		price = int(plan.get("price") or 0)
		days = int(plan.get("days") or 0)
		per_day = int(plan.get("price_per_day") or 0)
		meta = "Bepul" if price <= 0 else f"{price:,} so'm"
		if days:
			meta += f" · {days} kun"
			if per_day:
				meta += f" · kuniga {per_day:,} so'm"
		lines.append(
			f"🔸 <b>{escape_html(plan['label'])}</b> — {meta}\n"
			f"   {escape_html(features)}"
		)
	return "\n".join(lines)


async def send_subscription_page(target, profile, *, edit: bool = False) -> None:
	plans, card = await load_plans()
	state = await load_state(profile)
	text = (
		"🎫 <b>Obunalar</b>\n\n"
		f"{_plan_rows(plans)}\n\n"
		"Joriy tarif: <b>{}</b>\n"
		"Holat: {}\n\n"
		"Tarifni tanlash orqali to'lov yo'riqnomasini olasiz.".format(
			escape_html(state["label"]), _status_line(state)
		)
	)
	await render(
		target,
		text,
		markup=subscription_keyboard(plans, state["plan"], current_active=state["active"]),
		edit=edit,
	)


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

	current_state = await load_state(profile)
	current = current_state["plan"]
	if plan == current and current_state["active"]:
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
		days=int(details.get("days") or 0),
		price=price_text,
		card=escape_html(card or "-"),
	)
	text += f"\n\nTarifga kiradigan kontent:\n🔸 {escape_html(features)}"
	await render(
		callback,
		text,
		markup=subscription_keyboard(
			plans, current, current_active=current_state["active"]
		),
		edit=True,
	)


@router.message(UserSubscriptionStates.awaiting_screenshot, F.photo)
async def receive_screenshot(message: Message, state: FSMContext, profile) -> None:
	data = await state.get_data()
	plan = data.get("plan") or ""
	user = getattr(profile, "auth_user", None)
	from users.plans import PLAN_ORDER

	if user is None or plan not in PLAN_ORDER:
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
