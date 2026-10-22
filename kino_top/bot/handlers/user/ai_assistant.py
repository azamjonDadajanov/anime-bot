"""``🤖 AI yordamchi``: AniVoy, the platform's own assistant.

The work lives in ``movies.ai_assistant``: an online chat model that is handed
catalogue functions and calls the ones it needs (search, title details, parts,
genres, popular content, and — only with the user's opt-in — their favourites).
This handler gates the feature on an active subscription, runs the work off the
event loop, shows a "thinking" placeholder, and renders the answer: the model's
words (markdown turned into the HTML tags Telegram allows), then the linked
titles its functions actually returned.

It is intentionally *not* part of the search screen: subscribers open it from
the ``🤖 AI yordamchi`` button on the main menu, everyone else never sees it.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Sequence

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from movies import ai_actions, ai_assistant

from ... import callbacks as cb
from ...keyboards.common import btn, keyboard
from ...keyboards.user import (
	assistant_action_keyboard,
	assistant_keyboard,
	assistant_locked_keyboard,
	assistant_results_keyboard,
	main_menu,
)
from ...markdown import to_telegram_html
from ...services.media import assistant_answer, assistant_user_context
from ...states import UserAssistantStates, UserSubscriptionStates
from ...texts import (
	AI_ACTION_CANCELLED,
	AI_ACTION_DONE,
	AI_ACTION_EDIT_ASK,
	AI_ACTION_HEADER,
	AI_ACTION_FIELD,
	AI_ACTION_INVALID,
	AI_ACTION_LINKED,
	AI_ACTION_LINK_TIP,
	AI_ACTION_PENDING,
	AI_ACTION_UNLINKED,
	AI_ASSISTANT_EMPTY,
	AI_ASSISTANT_ERROR,
	AI_ASSISTANT_PERSONAL_OFF,
	AI_ASSISTANT_PERSONAL_ON,
	AI_ASSISTANT_PROMPT,
	AI_ASSISTANT_REQUIRED,
	AI_ASSISTANT_RESULTS,
	AI_ASSISTANT_THINKING,
	AI_ASSISTANT_UNAVAILABLE,
	AI_ASSISTANT_UNAVAILABLE_ADMIN,
	NOT_FOUND,
	SEARCH_EMPTY_QUERY,
	SUBREQ_CARD_HINT,
	SUBREQ_PENDING_NOTICE,
)
from ...utils import escape_html, to_async
from ..common import render
from .subscription import check_pending, load_plan_details, load_plans

logger = logging.getLogger(__name__)

router = Router(name="user-ai-assistant")

META_SEPARATOR = " · "


def is_subscriber(profile) -> bool:
	"""The assistant is a paid feature: a paid, unexpired plan is required."""
	return ai_assistant.user_can_use(getattr(profile, "auth_user", None))


def render_hits(items: Sequence[Dict[str, Any]]) -> str:
	"""The titles the assistant found: a link, its metadata, its summary."""
	lines = []
	for index, item in enumerate(items, start=1):
		title = escape_html(item.get("title"))
		url = str(item.get("url") or "")
		# With ``BOT_SITE_URL`` configured the title itself is the link; without
		# it the bot still offers the numbered buttons of the keyboard below.
		heading = f'<a href="{escape_html(url)}">{title}</a>' if url.startswith("http") else title
		meta = META_SEPARATOR.join(
			part
			for part in (
				escape_html(item.get("type_display")),
				escape_html(item.get("release_year")) if item.get("release_year") else "",
				f"⭐ {item.get('rating')}/10" if item.get("rating") else "",
			)
			if part
		)
		lines.append(f"<b>{index}.</b> {heading}")
		if meta:
			lines.append(f"     <i>{meta}</i>")
		lines.append(f"     {escape_html(item.get('summary'))}")
		lines.append("")
	return "\n".join(lines).rstrip()


def render_answer(query: str, text: str, items: Sequence[Dict[str, Any]]) -> str:
	"""The assistant's words above the list of titles it looked up."""
	blocks = []
	if text:
		blocks.append(
			AI_ASSISTANT_RESULTS.format(query=escape_html(query))
			# The model writes markdown; the bot sends HTML, so only the tags
			# Telegram documents are rebuilt and the rest is escaped.
			+ f"\n\n{to_telegram_html(text)}"
		)
	if items:
		blocks.append(render_hits(items))
	return "\n\n".join(blocks)


def render_chat(text: str) -> str:
	"""A conversational reply: the assistant's words, without a result list."""
	return to_telegram_html(text)


def _display_value(field: Dict[str, Any]) -> str:
	"""How one card field reads inside the Telegram message."""
	field_type = field.get("type")
	value = field.get("value")
	if field_type == "select":
		for option in field.get("options") or []:
			if option.get("value") == value:
				return str(option.get("label") or "")
		return str(value or "—")
	if field_type == "bool":
		return "yoqilgan" if value else "o'chirilgan"
	if field_type == "file":
		return "tasdiqda yuboriladi"
	if field_type == "int":
		if value in (None, ""):
			return "—"
		upper = field.get("max")
		return f"{value}/{upper}" if upper else str(value)
	if value in (None, ""):
		return "—"
	return str(value)


def render_action_card(action: Dict[str, Any]) -> str:
	"""The card body: header, every value, and what to do next."""
	blocks = [AI_ACTION_HEADER.format(label=escape_html(action.get("label")))]
	lines = [
		AI_ACTION_FIELD.format(
			label=escape_html(field.get("label")),
			value=escape_html(_display_value(field)),
		)
		for field in action.get("fields") or []
	]
	if lines:
		blocks.append("\n".join(lines))
	if action.get("kind") == "link":
		linked = bool((action.get("link") or {}).get("linked"))
		blocks.append(AI_ACTION_LINKED if linked else AI_ACTION_LINK_TIP)
	else:
		blocks.append(AI_ACTION_PENDING)
	return "\n\n".join(blocks)


async def _compose(state: FSMContext, action: Dict[str, Any]) -> str:
	"""The model's words (if any) above the card, for every re-render."""
	data = await state.get_data()
	text = str(data.get("ai_action_text") or "")
	body = render_action_card(action)
	if text:
		return f"{to_telegram_html(text)}\n\n{body}"
	return body


async def _link_url(profile, bot, action: Dict[str, Any]) -> str:
	"""The ``/start <site username>`` deep link for an unlinked account.

	In practice the bot only ever shows a link card *already* linked (the
	assistant itself requires the link), so this is the defensive path.
	"""
	if action.get("kind") != "link" or (action.get("link") or {}).get("linked"):
		return ""
	user = getattr(profile, "auth_user", None)
	username = str(getattr(user, "username", "") or "")
	if not username:
		return ""
	from ...services.publishing import bot_username
	from ...utils import deep_link

	return deep_link(await bot_username(bot), username)


def _find_field(action: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
	for field in action.get("fields") or []:
		if str(field.get("key") or "") == key:
			return field
	return None


def _card_values(action: Dict[str, Any]) -> Dict[str, Any]:
	"""The edited values the confirm sends (file fields are excluded)."""
	return {
		str(field.get("key")): field.get("value")
		for field in action.get("fields") or []
		if field.get("editable") and field.get("type") != "file"
	}


def _link_status_sync(user) -> bool:
	from users.models import TelegramUser

	return TelegramUser.objects.filter(auth_user=user).exists()


link_status = to_async(_link_status_sync)


async def _replace(message: Message, text: str, *, markup: Optional[InlineKeyboardMarkup]) -> None:
	"""Turn the "thinking" placeholder into the final answer.

	Editing keeps the chat clean; if Telegram refuses (a message older than 48
	hours, an unchanged body) the same content is sent as a new message so the
	user is never left without an answer.
	"""
	try:
		await message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
	except TelegramBadRequest as exc:
		if "message is not modified" in str(exc):
			return
		logger.debug("Could not edit the AI answer (%s); sending a new message.", exc)
		await message.answer(text, reply_markup=markup, disable_web_page_preview=True)


async def _personal_enabled(state: FSMContext) -> bool:
	"""Whether the user opted in to giving the assistant their taste."""
	data = await state.get_data()
	return bool(data.get("ai_personal"))


@router.callback_query(F.data == cb.AI_ASSISTANT)
async def open_assistant(
	callback: CallbackQuery, state: FSMContext, profile, is_admin: bool
) -> None:
	"""Open the assistant prompt, or explain why the visitor cannot use it."""
	if not is_subscriber(profile):
		await render(callback, AI_ASSISTANT_REQUIRED, markup=assistant_locked_keyboard(), edit=True)
		return
	await state.set_state(UserAssistantStates.query)
	personal = await _personal_enabled(state)
	await render(
		callback,
		AI_ASSISTANT_PROMPT,
		markup=assistant_keyboard(personal=personal),
		edit=True,
	)


@router.callback_query(F.data == cb.AI_PERSONAL)
async def toggle_personal(
	callback: CallbackQuery, state: FSMContext, profile, is_admin: bool
) -> None:
	"""Turn "let the assistant read my favourites" on or off.

	The choice lives in the FSM data of this conversation (no DB column): it
	only matters while the user is inside the assistant screen, and off means
	the ``personal_taste`` tool is never even offered to the model.
	"""
	if not is_subscriber(profile):
		await render(callback, AI_ASSISTANT_REQUIRED, markup=assistant_locked_keyboard(), edit=True)
		return
	personal = not await _personal_enabled(state)
	await state.set_state(UserAssistantStates.query)
	await state.update_data(ai_personal=personal)
	await render(
		callback,
		AI_ASSISTANT_PERSONAL_ON if personal else AI_ASSISTANT_PERSONAL_OFF,
		markup=assistant_keyboard(personal=personal),
		edit=True,
	)


@router.message(UserAssistantStates.query)
async def ask_assistant(
	message: Message, state: FSMContext, profile, is_admin: bool
) -> None:
	query = (message.text or "").strip()
	personal = await _personal_enabled(state)
	if not query:
		await message.answer(
			SEARCH_EMPTY_QUERY, reply_markup=assistant_keyboard(personal=personal)
		)
		return
	if not is_subscriber(profile):
		# The plan may have expired between the prompt and this message.
		await state.clear()
		await message.answer(
			AI_ASSISTANT_REQUIRED, reply_markup=assistant_locked_keyboard()
		)
		return

	context = await assistant_user_context(profile) if personal else ""

	# The online model (and its tool calls) takes a few seconds, so the user
	# gets visible progress immediately; that message is edited into the answer.
	placeholder = await message.answer(AI_ASSISTANT_THINKING)
	try:
		result = await assistant_answer(query, context=context, profile=profile)
	except Exception:  # noqa: BLE001 - the user always gets an answer
		logger.exception("AI assistant failed for %r", query)
		await _replace(
			placeholder,
			AI_ASSISTANT_ERROR,
			markup=assistant_keyboard(personal=personal),
		)
		return

	if not result["available"]:
		# Only the online model can answer: with no key, a cooldown or an
		# outage there is no offline fallback to hide behind.
		logger.warning("AI assistant is unavailable: %s", result.get("error") or "")
		await state.clear()
		text = AI_ASSISTANT_UNAVAILABLE
		if is_admin:
			# The administrator gets the reason as well: a dead model and an
			# exhausted quota need different fixes.
			reason = str(result.get("error") or "").strip()
			if reason:
				text = AI_ASSISTANT_UNAVAILABLE_ADMIN.format(
					reason=escape_html(reason[:400])
				)
		await _replace(placeholder, text, markup=main_menu(is_admin, profile))
		return

	# Stay in the query state: asking a follow-up question is the natural next
	# step, and the keyboard offers the way out.
	await state.set_state(UserAssistantStates.query)
	action = result.get("action")
	if action:
		# The model proposed an account action: the card (with its signed
		# token) replaces the answer list, and the user confirms or edits it.
		await state.update_data(
			ai_action=action, ai_action_text=result.get("text") or ""
		)
		await _replace(
			placeholder,
			await _compose(state, action),
			markup=assistant_action_keyboard(
				action, link_url=await _link_url(profile, message.bot, action)
			),
		)
		return
	items = result["items"]
	if not items:
		# The assistant answered a conversational question (no titles): show its
		# words alone. With nothing to say either, report that nothing matched.
		if result.get("conversational") and result.get("text"):
			await _replace(
				placeholder,
				render_chat(result["text"]),
				markup=assistant_keyboard(personal=personal),
			)
			return
		blocks = [AI_ASSISTANT_EMPTY.format(query=escape_html(query))]
		if result.get("text"):
			blocks.append(to_telegram_html(result["text"]))
		await _replace(
			placeholder,
			"\n\n".join(blocks),
			markup=assistant_keyboard(personal=personal),
		)
		return
	await _replace(
		placeholder,
		render_answer(query, result["text"], items),
		markup=assistant_results_keyboard(items),
	)


# --------------------------------------------------------------------------- #
# The amal (action) card: confirm, cancel, edit one field, re-check the link
# --------------------------------------------------------------------------- #
async def _stored_action(state: FSMContext) -> Optional[Dict[str, Any]]:
	action = (await state.get_data()).get("ai_action")
	return action if isinstance(action, dict) and action.get("token") else None


async def _rerender(callback: CallbackQuery, state: FSMContext, profile) -> Optional[Dict[str, Any]]:
	"""Re-draw the message under the card after a value changed."""
	action = await _stored_action(state)
	if action is None:
		await callback.answer(AI_ACTION_INVALID.format(detail="Karta topilmadi.")[:200], show_alert=True)
		return None
	await render(
		callback,
		await _compose(state, action),
		markup=assistant_action_keyboard(
			action, link_url=await _link_url(profile, callback.bot, action)
		),
		edit=True,
	)
	return action


async def _confirm_subscription(
	callback: CallbackQuery, state: FSMContext, profile, action: Dict[str, Any], is_admin: bool
) -> None:
	"""Obuna: no file can ride the token, so the shared screenshot state opens.

	Exactly the flow «🎫 Obuna → tarif → skrinshot» uses: the plan from the
	card lands in the FSM and ``receive_screenshot`` waits for the photo.
	"""
	plan = str(_card_values(action).get("plan") or "")
	plans, card = await load_plans()
	known = {item["id"] for item in plans}
	if plan not in known:
		await callback.answer(AI_ACTION_INVALID.format(detail="Tarifni tanlang.")[:200], show_alert=True)
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
	await state.update_data(ai_action=None, ai_action_text=None, plan=plan)
	await state.set_state(UserSubscriptionStates.awaiting_screenshot)
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
		markup=main_menu(is_admin, profile),
		edit=True,
	)


@router.callback_query(F.data == cb.AI_ACTION_OK)
async def confirm_action(
	callback: CallbackQuery, state: FSMContext, profile, is_admin: bool
) -> None:
	"""«✅ Tasdiqlash»: run the signed action through ``ai_actions.execute``."""
	action = await _stored_action(state)
	if action is None:
		await callback.answer(
			AI_ACTION_INVALID.format(detail="Karta topilmadi.")[:200], show_alert=True
		)
		return
	if action.get("kind") == "link":
		await callback.answer(
			AI_ACTION_INVALID.format(detail="Ulash tugmalardan bajariladi.")[:200],
			show_alert=True,
		)
		return
	if str(action.get("action")) == "subscription_request":
		await _confirm_subscription(callback, state, profile, action, is_admin)
		return
	user = getattr(profile, "auth_user", None)
	if user is None:
		await callback.answer(NOT_FOUND[:200], show_alert=True)
		return
	try:
		result = await to_async(ai_actions.execute)(
			user,
			str(action.get("token") or ""),
			values=_card_values(action),
			source="bot",
		)
	except ai_actions.ActionError as exc:
		await callback.answer(AI_ACTION_INVALID.format(detail=exc.detail)[:200], show_alert=True)
		return
	await state.update_data(ai_action=None, ai_action_text=None)
	await state.set_state(UserAssistantStates.query)
	personal = await _personal_enabled(state)
	await render(
		callback,
		AI_ACTION_DONE.format(
			label=escape_html(result["label"]),
			message=escape_html(result["message"]),
		),
		markup=assistant_keyboard(personal=personal),
		edit=True,
	)


@router.callback_query(F.data == cb.AI_ACTION_NO)
async def cancel_action(callback: CallbackQuery, state: FSMContext, profile, is_admin: bool) -> None:
	"""«❌ Bekor qilish»: drop the proposal, nothing is written."""
	await state.update_data(ai_action=None, ai_action_text=None)
	await state.set_state(UserAssistantStates.query)
	personal = await _personal_enabled(state)
	await render(
		callback,
		AI_ACTION_CANCELLED,
		markup=assistant_keyboard(personal=personal),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.AI_ACTION_ADJ}:"))
async def adjust_field(callback: CallbackQuery, state: FSMContext, profile) -> None:
	"""``aiad:<field>:<±1>`` — nudge an int value inside its min/max."""
	action = await _stored_action(state)
	parts = cb.split_data(callback.data)
	field = _find_field(action or {}, parts[1] if len(parts) > 1 else "")
	if action is None or field is None or field.get("type") != "int":
		await callback.answer(AI_ACTION_INVALID.format(detail="O'zgartirib bo'lmaydi.")[:200], show_alert=True)
		return
	try:
		delta = int(parts[2]) if len(parts) > 2 else 0
	except (TypeError, ValueError):
		delta = 0
	try:
		current = int(field.get("value"))
	except (TypeError, ValueError):
		current = int(field.get("min") or 0)
	low = field.get("min")
	high = field.get("max")
	updated = current + delta
	if low is not None:
		updated = max(int(low), updated)
	if high is not None:
		updated = min(int(high), updated)
	field["value"] = updated
	await state.update_data(ai_action=action)
	await _rerender(callback, state, profile)


@router.callback_query(F.data.startswith(f"{cb.AI_ACTION_CYCLE}:"))
async def cycle_field(callback: CallbackQuery, state: FSMContext, profile) -> None:
	"""``aic:<field>`` — move a select to its next option."""
	action = await _stored_action(state)
	parts = cb.split_data(callback.data)
	field = _find_field(action or {}, parts[1] if len(parts) > 1 else "")
	options = (field or {}).get("options") or []
	if action is None or field is None or field.get("type") != "select" or not options:
		await callback.answer(AI_ACTION_INVALID.format(detail="O'zgartirib bo'lmaydi.")[:200], show_alert=True)
		return
	values = [option.get("value") for option in options]
	try:
		index = values.index(field.get("value"))
	except ValueError:
		index = -1
	field["value"] = values[(index + 1) % len(values)]
	await state.update_data(ai_action=action)
	await _rerender(callback, state, profile)


@router.callback_query(F.data.startswith(f"{cb.AI_ACTION_TOGGLE}:"))
async def toggle_field(callback: CallbackQuery, state: FSMContext, profile) -> None:
	"""``ait:<field>`` — flip a bool value."""
	action = await _stored_action(state)
	parts = cb.split_data(callback.data)
	field = _find_field(action or {}, parts[1] if len(parts) > 1 else "")
	if action is None or field is None or field.get("type") != "bool":
		await callback.answer(AI_ACTION_INVALID.format(detail="O'zgartirib bo'lmaydi.")[:200], show_alert=True)
		return
	field["value"] = not bool(field.get("value"))
	await state.update_data(ai_action=action)
	await _rerender(callback, state, profile)


@router.callback_query(F.data.startswith(f"{cb.AI_ACTION_EDIT}:"))
async def start_field_edit(callback: CallbackQuery, state: FSMContext, profile) -> None:
	"""``aied:<field>`` — ask for a new text value (FSM ``action_edit``)."""
	action = await _stored_action(state)
	parts = cb.split_data(callback.data)
	key = parts[1] if len(parts) > 1 else ""
	field = _find_field(action or {}, key)
	if action is None or field is None or field.get("type") not in ("text", "textarea"):
		await callback.answer(AI_ACTION_INVALID.format(detail="O'zgartirib bo'lmaydi.")[:200], show_alert=True)
		return
	await state.set_state(UserAssistantStates.action_edit)
	await state.update_data(ai_edit_field=key)
	await render(
		callback,
		AI_ACTION_EDIT_ASK.format(label=escape_html(field.get("label"))),
		markup=keyboard([btn("⬅️ Ortga", cb.AI_ACTION_BACK)]),
		edit=True,
	)


@router.callback_query(F.data == cb.AI_ACTION_BACK)
async def back_to_card(callback: CallbackQuery, state: FSMContext, profile) -> None:
	"""Leave the text editor without changing anything."""
	await state.set_state(UserAssistantStates.query)
	await state.update_data(ai_edit_field=None)
	await _rerender(callback, state, profile)


@router.callback_query(F.data == cb.AI_ACTION_CHECK)
async def check_link(callback: CallbackQuery, state: FSMContext, profile) -> None:
	"""«🔄 Tekshirish»: has the /start confirm landed yet?"""
	action = await _stored_action(state)
	user = getattr(profile, "auth_user", None)
	linked = await link_status(user) if user is not None else False
	if action is None:
		await callback.answer(
			AI_ACTION_INVALID.format(detail="Karta topilmadi.")[:200], show_alert=True
		)
		return
	action.setdefault("link", {})
	action["link"]["linked"] = linked
	action["link"]["username"] = (
		str(getattr(profile, "username", "") or "") if linked else ""
	)
	await state.update_data(ai_action=action)
	await _rerender(callback, state, profile)
	await callback.answer("✅ Ulandi" if linked else AI_ACTION_UNLINKED, show_alert=True)


@router.message(UserAssistantStates.action_edit)
async def apply_field_edit(
	message: Message, state: FSMContext, profile, is_admin: bool
) -> None:
	"""Store the new text value and show the card again."""
	data = await state.get_data()
	action = data.get("ai_action") if isinstance(data.get("ai_action"), dict) else None
	key = str(data.get("ai_edit_field") or "")
	field = _find_field(action or {}, key)
	await state.set_state(UserAssistantStates.query)
	await state.update_data(ai_edit_field=None)
	if action is None or field is None:
		await message.answer(
			AI_ACTION_INVALID.format(detail="Karta topilmadi."),
			reply_markup=assistant_keyboard(personal=await _personal_enabled(state)),
		)
		return
	text = (message.text or "").strip()
	max_length = int(field.get("max_length") or 0)
	if max_length:
		text = text[:max_length]
	if not text and field.get("required"):
		await message.answer(
			AI_ACTION_INVALID.format(detail="Qiymat bo'sh bo'lmasligi kerak."),
			reply_markup=keyboard([btn("⬅️ Ortga", cb.AI_ACTION_BACK)]),
		)
		await state.set_state(UserAssistantStates.action_edit)
		await state.update_data(ai_edit_field=key)
		return
	field["value"] = text
	await state.update_data(ai_action=action)
	personal = await _personal_enabled(state)
	await message.answer(
		await _compose(state, action),
		reply_markup=assistant_action_keyboard(
			action, link_url=await _link_url(profile, message.bot, action)
		),
	)
