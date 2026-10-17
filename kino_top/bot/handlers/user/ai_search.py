"""``🤖 AI orqali qidirish``: find titles by meaning instead of by name.

The work itself lives in ``movies.ai_search`` (the shared index, documents and
multilingual encoder, so the bot and the site always agree on what
"qo'rqinchli" matches) and in ``movies.ai_reasoning`` (the chat model that
explains the picks and re-orders them). This handler gates the feature on an
active subscription, runs the work off the event loop, shows a "thinking"
placeholder while it waits, and renders the answer the way the request asks
for: an explanation, then a list of linked titles each with a one-sentence
summary under it.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Sequence

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from movies import ai_search, embeddings

from ... import callbacks as cb
from ...keyboards.user import (
	ai_locked_keyboard,
	ai_prompt_keyboard,
	ai_results_keyboard,
	search_keyboard,
)
from ...services.media import ai_search_answer, ai_user_context
from ...states import UserAIStates
from ...texts import (
	AI_SEARCH_EMPTY,
	AI_SEARCH_ERROR,
	AI_SEARCH_FAVS_OFF,
	AI_SEARCH_FAVS_ON,
	AI_SEARCH_MORE,
	AI_SEARCH_PROMPT,
	AI_SEARCH_REQUIRED,
	AI_SEARCH_RESULTS,
	AI_SEARCH_THINKING,
	AI_SEARCH_UNAVAILABLE,
	SEARCH_EMPTY_QUERY,
)
from ...utils import escape_html
from ..common import render

logger = logging.getLogger(__name__)

router = Router(name="user-ai-search")

META_SEPARATOR = " · "


def is_subscriber(profile) -> bool:
	"""AI search is a paid feature: a paid, unexpired plan is required."""
	return ai_search.user_can_search(getattr(profile, "auth_user", None))


def render_hits(query: str, items: Sequence[Dict[str, Any]], *, total: int = 0) -> str:
	"""The result list: a linked title with its one-sentence summary below it.

	``total`` is how many titles matched in the whole catalogue; when the list is
	shorter than that (Telegram messages have a length limit, and a hundred hits
	would be unreadable anyway) the last line says so instead of letting the user
	believe the list is the whole answer.
	"""
	lines = [AI_SEARCH_RESULTS.format(query=escape_html(query)), ""]
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
	if total > len(items):
		lines.append(AI_SEARCH_MORE.format(total=total, shown=len(items)))
	return "\n".join(lines).rstrip()


def render_answer(text: str, thinking: str, query: str, items, *, total: int) -> str:
	"""The reasoning model's words above the list it reasoned about.

	When the model answered a conversational question (or found nothing that
	fits) there is no list to render — only its words are shown.
	"""
	blocks = []
	if text:
		blocks.append(f"✨ <b>{escape_html(query)}</b> bo'yicha AI javobi:\n\n{escape_html(text)}")
		if thinking:
			blocks.append(f"<i>Fikrlash: {escape_html(thinking)}</i>")
	if items:
		blocks.append(render_hits(query, items, total=total))
	return "\n\n".join(blocks)


def render_chat(text: str, thinking: str) -> str:
	"""A conversational reply: the model's own words, without a query header
	or a result list (the user asked the assistant something, not for titles)."""
	blocks = []
	if text:
		blocks.append(escape_html(text))
	if thinking:
		blocks.append(f"<i>Fikrlash: {escape_html(thinking)}</i>")
	return "\n\n".join(blocks)


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


async def _ai_favs_enabled(state: FSMContext) -> bool:
	"""Whether the user opted in to sending their taste to the model."""
	data = await state.get_data()
	return bool(data.get("ai_favs"))


@router.callback_query(F.data == cb.AI_SEARCH)
async def open_ai_search(
	callback: CallbackQuery, state: FSMContext, profile, is_admin: bool
) -> None:
	"""Open the AI prompt, or explain why the visitor cannot use it."""
	if not is_subscriber(profile):
		await render(callback, AI_SEARCH_REQUIRED, markup=ai_locked_keyboard(), edit=True)
		return
	await state.set_state(UserAIStates.query)
	favs = await _ai_favs_enabled(state)
	await render(
		callback,
		AI_SEARCH_PROMPT,
		markup=ai_prompt_keyboard(favs=favs),
		edit=True,
	)


@router.callback_query(F.data == cb.AI_FAV)
async def toggle_ai_favorites(
	callback: CallbackQuery, state: FSMContext, profile, is_admin: bool
) -> None:
	"""Turn the "send my favourites to the AI" opt-in on or off.

	The choice lives in the FSM data of this conversation (no DB column): it
	only matters while the user is inside the AI screen.
	"""
	if not is_subscriber(profile):
		await render(callback, AI_SEARCH_REQUIRED, markup=ai_locked_keyboard(), edit=True)
		return
	favs = not await _ai_favs_enabled(state)
	await state.set_state(UserAIStates.query)
	await state.update_data(ai_favs=favs)
	await render(
		callback,
		AI_SEARCH_FAVS_ON if favs else AI_SEARCH_FAVS_OFF,
		markup=ai_prompt_keyboard(favs=favs),
		edit=True,
	)


@router.message(UserAIStates.query)
async def search_by_meaning(
	message: Message, state: FSMContext, profile, is_admin: bool
) -> None:
	query = (message.text or "").strip()
	favs = await _ai_favs_enabled(state)
	if not query:
		await message.answer(
			SEARCH_EMPTY_QUERY, reply_markup=ai_prompt_keyboard(favs=favs)
		)
		return
	if not is_subscriber(profile):
		# The plan may have expired between the prompt and this answer.
		await state.clear()
		await message.answer(AI_SEARCH_REQUIRED, markup=ai_locked_keyboard())
		return

	context = await ai_user_context(profile) if favs else ""

	# The reasoning model takes a few seconds, so the user gets visible progress
	# immediately; that message is edited into the answer below. (Without a
	# configured model the search answers in milliseconds — the placeholder is
	# then simply replaced by the result.)
	placeholder = await message.answer(AI_SEARCH_THINKING)
	try:
		result = await ai_search_answer(query, context=context)
	except embeddings.EmbeddingUnavailable as exc:
		logger.warning("AI search is unavailable: %s", exc)
		await _replace(placeholder, AI_SEARCH_UNAVAILABLE, markup=search_keyboard())
		return
	except Exception:  # noqa: BLE001 - the user always gets an answer
		logger.exception("AI search failed for %r", query)
		await _replace(placeholder, AI_SEARCH_ERROR, markup=ai_prompt_keyboard(favs=favs))
		return

	# Stay in the query state: asking a follow-up question is the natural next
	# step, and the keyboard offers the way out.
	await state.set_state(UserAIStates.query)
	items = result["items"]
	if not items:
		# The model answered a conversational question (no titles): show its
		# words alone. With nothing to say either, report that nothing matched.
		if result.get("conversational") and result.get("text"):
			await _replace(
				placeholder,
				render_chat(result["text"], result["thinking"]),
				markup=ai_prompt_keyboard(favs=favs),
			)
			return
		await _replace(
			placeholder,
			AI_SEARCH_EMPTY.format(query=escape_html(query)),
			markup=ai_prompt_keyboard(favs=favs),
		)
		return
	await _replace(
		placeholder,
		render_answer(
			result["text"], result["thinking"], query, items, total=result["total"]
		),
		markup=ai_results_keyboard(items),
	)
