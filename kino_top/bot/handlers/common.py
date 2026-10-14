"""Render helpers shared by user and administrator handlers."""

from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from ..middlewares.context import inner_event
from ..services.access import AccessDenied
from ..texts import (
	ACCESS_DENIED_GENERIC,
	BOT_BLOCKED,
	PREMIUM_REQUIRED,
	SUBSCRIPTION_REQUIRED,
)
from ..keyboards.common import subscribe_keyboard

logger = logging.getLogger(__name__)


async def render(
	target: Any,
	text: str,
	*,
	markup: Optional[InlineKeyboardMarkup] = None,
	edit: bool = False,
	alert: bool = False,
	preview: bool = False,
) -> None:
	"""Show ``text`` to the user behind ``target`` (Message or CallbackQuery)."""
	payload = inner_event(target)
	if isinstance(payload, CallbackQuery):
		if alert:
			await payload.answer(text[:200], show_alert=True)
			return
		message = payload.message
		if edit and message is not None:
			try:
				await message.edit_text(
					text, reply_markup=markup, disable_web_page_preview=not preview
				)
				return
			except TelegramBadRequest as exc:
				if "message is not modified" in str(exc):
					return
				logger.debug("edit_text failed (%s); sending a new message instead.", exc)
		if message is not None:
			await message.answer(text, reply_markup=markup, disable_web_page_preview=not preview)
		else:  # pragma: no cover - inline mode edge case
			await payload.answer(text[:200], show_alert=True)
		return
	if isinstance(payload, Message):
		await payload.answer(text, reply_markup=markup, disable_web_page_preview=not preview)


def format_channels(channels: Sequence) -> str:
	return "\n".join(f"• {channel.title}" for channel in channels) or "—"


async def render_access_denial(target: Any, denial: AccessDenied, *, edit: bool = False) -> None:
	"""Explain why access was refused and offer the next step."""
	extra = ""
	try:
		from ..services.bot_settings import get_settings

		settings = await get_settings()
		extra = (settings.access_denied_text or "").strip()
		if extra:
			extra = f"\n\n{extra}"
	except Exception:  # noqa: BLE001 - denial must never fail on settings
		logger.warning("Could not load access_denied_text settings.", exc_info=True)
	if denial.is_subscription:
		await render(
			target,
			SUBSCRIPTION_REQUIRED.format(channels=format_channels(denial.channels)) + extra,
			markup=subscribe_keyboard(denial.channels),
			edit=edit,
		)
		return
	if denial.is_premium:
		await render(
			target,
			PREMIUM_REQUIRED.format(
				plan=access_label(denial.required_plan),
				current=access_label(denial.current_plan),
			)
			+ extra,
			edit=edit,
		)
		return
	if denial.is_blocked:
		await render(target, BOT_BLOCKED, alert=True, edit=edit)
		return
	await render(target, ACCESS_DENIED_GENERIC + extra, edit=edit)


def plan_label(plan: str) -> str:
	from users.plans import plan_label as catalogue_label

	return catalogue_label(plan)


def access_label(value: str) -> str:
	"""Human label for either a content gate (free/paid) or a plan id."""
	from movies.models import MediaTitle

	key = str(value or "free").lower()
	if key in MediaTitle.AccessPlan.values:
		return dict(MediaTitle.AccessPlan.choices)[key]
	return plan_label(key)
