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
from movies import ai_assistant

from ... import callbacks as cb
from ...keyboards.user import (
	assistant_keyboard,
	assistant_locked_keyboard,
	assistant_results_keyboard,
	main_menu,
)
from ...markdown import to_telegram_html
from ...services.media import assistant_answer, assistant_user_context
from ...states import UserAssistantStates
from ...texts import (
	AI_ASSISTANT_EMPTY,
	AI_ASSISTANT_ERROR,
	AI_ASSISTANT_PERSONAL_OFF,
	AI_ASSISTANT_PERSONAL_ON,
	AI_ASSISTANT_PROMPT,
	AI_ASSISTANT_REQUIRED,
	AI_ASSISTANT_RESULTS,
	AI_ASSISTANT_THINKING,
	AI_ASSISTANT_UNAVAILABLE,
	SEARCH_EMPTY_QUERY,
)
from ...utils import escape_html
from ..common import render

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
		result = await assistant_answer(query, context=context)
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
		await _replace(placeholder, AI_ASSISTANT_UNAVAILABLE, markup=main_menu(is_admin, profile))
		return

	# Stay in the query state: asking a follow-up question is the natural next
	# step, and the keyboard offers the way out.
	await state.set_state(UserAssistantStates.query)
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
