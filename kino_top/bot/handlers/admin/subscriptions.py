"""Approve or reject paid subscription requests sent from the website or bot.

The screenshot and the two buttons are delivered by
``users.telegram_notify``; this module handles the button presses, flips the
``SubscriptionRequest`` status, activates the plan and tells the user.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery
from django.contrib.auth import get_user_model
from django.db import transaction
from users.models import Subscription, SubscriptionRequest

from ... import callbacks as cb
from ...bot_logging import record_event
from ...texts import (
	ADMIN_SUBREQ_APPROVED,
	ADMIN_SUBREQ_REJECTED,
	SUBREQ_ALREADY_PROCESSED,
	SUBREQ_APPROVED,
	SUBREQ_NOT_FOUND,
	SUBREQ_REJECTED,
)
from ...utils import escape_html, to_async
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="admin-subscriptions")


def _user_telegram_id(request) -> int | None:
	profile = getattr(request.user, "telegram_profile", None)
	return int(profile.telegram_id) if profile is not None else None


def _details(request) -> str:
	profile = getattr(request.user, "telegram_profile", None)
	name = profile.first_name or profile.username or str(request.user) if profile else str(request.user)
	return (
		f"👤 {escape_html(name)}\n"
		f"💳 Tarif: <b>{escape_html(_plan_display(request.plan))}</b>\n"
		f"💰 Summa: <b>{request.amount:g}</b>"
	)


def process_request_sync(request_pk: int, *, approved: bool, admin_telegram_id: int):
	"""Flip the status, activate the plan (on approval) and return ``(row, changed)``."""
	User = get_user_model()
	try:
		request = SubscriptionRequest.objects.select_related("user", "user__telegram_profile").get(
			pk=request_pk
		)
	except SubscriptionRequest.DoesNotExist:
		return None, False
	if request.status != SubscriptionRequest.Status.PENDING:
		return request, False

	admin = User.objects.filter(telegram_profile__telegram_id=admin_telegram_id).first()
	request.status = (
		SubscriptionRequest.Status.APPROVED
		if approved
		else SubscriptionRequest.Status.REJECTED
	)
	request.processed_by = admin
	request.save(update_fields=["status", "processed_by", "updated_at"])

	if approved:
		with transaction.atomic():
			subscription, _ = Subscription.objects.get_or_create(user=request.user)
			subscription.activate(request.plan)
		# Any other pending request for this user is now moot.
		SubscriptionRequest.objects.filter(
			user=request.user,
			status=SubscriptionRequest.Status.PENDING,
		).exclude(pk=request.pk).update(status=SubscriptionRequest.Status.CANCELLED)
	return request, True


process_request = to_async(process_request_sync)


def _plan_display(plan: str) -> str:
	from users.plans import plan_label

	return plan_label(plan)


def _plan_days(plan: str) -> int:
	from users.plans import plan_days

	return plan_days(plan)


async def _notify_user(bot, request, *, approved: bool) -> None:
	telegram_id = _user_telegram_id(request)
	if not telegram_id:
		return
	template = SUBREQ_APPROVED if approved else SUBREQ_REJECTED
	if approved:
		text = template.format(
			plan=escape_html(_plan_display(request.plan)),
			days=_plan_days(request.plan),
		)
	else:
		text = template.format(plan=escape_html(_plan_display(request.plan)))
	try:
		await bot.send_message(telegram_id, text)
	except TelegramAPIError as exc:  # pragma: no cover - blocked user etc.
		logger.info("Could not notify user %s: %s", telegram_id, exc)


async def _handle(callback: CallbackQuery, *, approved: bool) -> None:
	args = cb.section_args(callback.data)
	try:
		request_pk = int(args[0])
	except (IndexError, TypeError, ValueError):
		await callback.answer(SUBREQ_NOT_FOUND[:200], show_alert=True)
		return

	admin_id = callback.from_user.id if callback.from_user else 0
	request, changed = await process_request(
		request_pk, approved=approved, admin_telegram_id=admin_id
	)
	if request is None:
		await callback.answer(SUBREQ_NOT_FOUND[:200], show_alert=True)
		return
	if not changed:
		await callback.answer(SUBREQ_ALREADY_PROCESSED[:200], show_alert=True)
		return

	await to_async(record_event)(
		"INFO",
		f"Subscription request {request.pk} "
		f"{'approved' if approved else 'rejected'} by {admin_id}.",
		telegram_id=admin_id,
	)

	await _notify_user(callback.bot, request, approved=approved)

	template = ADMIN_SUBREQ_APPROVED if approved else ADMIN_SUBREQ_REJECTED
	await render(
		callback,
		template.format(details=_details(request)),
		edit=True,
	)
	await callback.answer(
		"✅ Tasdiqlandi" if approved else "❌ Rad etildi"
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_SUBREQ_OK}:"))
async def approve_request(callback: CallbackQuery) -> None:
	await _handle(callback, approved=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_SUBREQ_NO}:"))
async def reject_request(callback: CallbackQuery) -> None:
	await _handle(callback, approved=False)
