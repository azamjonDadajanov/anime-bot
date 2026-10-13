"""Content (anime/movie/series/manga) management for administrators."""

from __future__ import annotations

import logging
from io import BytesIO

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from movies.models import MediaTitle

from ... import callbacks as cb
from ...bot_logging import record_event
from ...config import page_size
from ...keyboards.admin import (
	confirm,
	admin_panel,
	media_actions,
	media_list,
	media_menu,
	media_types,
	value_choice_keyboard,
)
from ...keyboards.common import btn, cancel_keyboard, keyboard
from ...services.stats import dashboard
from ...services.media import (
	all_genres,
	all_titles,
	create_title,
	delete_title,
	get_title_by_pk,
	search_titles,
	title_stats,
	update_title,
)
from ...services.publishing import maybe_auto_publish_title
from ...states import AdminMediaStates
from ...texts import (
	ADMIN_INVALID_INPUT,
	ADMIN_MEDIA_ASK_COVER,
	ADMIN_MEDIA_ASK_GENRES,
	ADMIN_MEDIA_ASK_LANGUAGE,
	ADMIN_MEDIA_ASK_PLAN,
	ADMIN_MEDIA_ASK_QUALITY,
	ADMIN_MEDIA_ASK_RATING,
	ADMIN_MEDIA_ASK_STATUS,
	ADMIN_MEDIA_ASK_SYNOPSIS,
	ADMIN_MEDIA_ASK_TITLE,
	ADMIN_MEDIA_CREATE_TYPE,
	ADMIN_MEDIA_DELETE_CONFIRM,
	ADMIN_MEDIA_DELETED,
	ADMIN_MEDIA_EMPTY,
	ADMIN_MEDIA_LIST,
	ADMIN_MEDIA_MENU,
	ADMIN_MEDIA_PREVIEW,
	ADMIN_MEDIA_SAVED,
	ADMIN_MEDIA_SEARCH,
	EDIT_PROMPT,
	NOT_FOUND,
)
from ...utils import (
	escape_html,
	paginate,
	parse_int,
	to_async,
)
from ..common import render
from .panel import dashboard_text

logger = logging.getLogger(__name__)

router = Router(name="admin-media")

LANGUAGES = (
	("uz", "🇺🇿 O'zbekcha"),
	("ru", "🇷🇺 Ruscha"),
	("en", "🇬🇧 Inglizcha"),
)
LANGUAGE_LABELS = {"uz": "O'zbekcha", "ru": "Ruscha", "en": "Inglizcha"}
PLAN_OPTIONS = (("free", "🆓 Free"), ("plus", "💠 Plus"), ("pro", "💎 Pro"))
STATUS_OPTIONS = (
	("upcoming", "🕓 Kutilmoqda"),
	("ongoing", "▶️ Davom etmoqda"),
	("completed", "✅ Tugallangan"),
)
TYPE_OPTIONS = (
	("anime", "🎌 Anime"),
	("series", "📺 Serial"),
	("manga", "📖 Manga"),
	("movie", "🎬 Kino"),
)
CHOICE_FIELDS = {"required_plan": PLAN_OPTIONS, "status": STATUS_OPTIONS, "type": TYPE_OPTIONS}


def genres_text_sync(title) -> str:
	return ", ".join(title.genres.values_list("name", flat=True)) or "—"


_genres_text = to_async(genres_text_sync)


async def draft(state: FSMContext) -> dict:
	data = await state.get_data()
	return dict(data.get("draft") or {})


async def update_draft(state: FSMContext, **values) -> dict:
	current = await draft(state)
	current.update(values)
	await state.update_data(draft=current)
	return current


async def admin_card_text(title) -> str:
	genres = await _genres_text(title)
	stats = await title_stats(title)
	return (
		f"🎬 <b>{escape_html(title.title)}</b>\n"
		f"🆔 Kod: <code>{title.code}</code>\n"
		f"🔗 Slug: <code>{title.slug}</code>\n"
		f"📺 Turi: {title.get_type_display()}\n"
		f"🎭 Janr: {escape_html(genres)}\n"
		f"🌐 Til: {escape_html(title.language)}\n"
		f"💎 Sifat: {escape_html(', '.join(title.quality_options or []) or title.default_quality)}\n"
		f"🔒 Tarif: {title.get_required_plan_display()}\n"
		f"📊 Holat: {title.get_status_display()}\n"
		f"⭐ Reyting: {title.rating}/10\n"
		f"🎞 Qismlar: {stats['parts']} · 📦 Fayllar: {stats['media']}"
	)


def preview_text(draft_data: dict) -> str:
	cover = "✅ bor" if draft_data.get("cover_file_id") else "—"
	return ADMIN_MEDIA_PREVIEW.format(
		title=escape_html(draft_data.get("title") or "—"),
		type=dict(TYPE_OPTIONS).get(draft_data.get("type"), draft_data.get("type")),
		genres=escape_html(", ".join(draft_data.get("genres") or []) or "—"),
		language=escape_html(draft_data.get("language") or "O'zbekcha"),
		quality=escape_html(", ".join(draft_data.get("quality_options") or []) or "—"),
		plan=escape_html(draft_data.get("required_plan") or "free"),
		status=escape_html(draft_data.get("status") or "upcoming"),
		rating=draft_data.get("rating") or 5,
		cover=cover,
		synopsis=escape_html(draft_data.get("synopsis") or "—"),
	)


async def show_genre_step(target, state: FSMContext, *, edit: bool = False) -> None:
	genres = await all_genres()
	selected = set((await draft(state)).get("genres") or [])
	rows = [
		[btn(f"➕ {genre.name}", f"{cb.ADM_MEDIA}:genre:{genre.pk}")]
		for genre in genres
		if genre.name not in selected
	][:20]
	if selected:
		rows.append([btn("✅ Tayyor", f"{cb.ADM_MEDIA}:genredone")])
	rows.append([btn("❌ Bekor qilish", cb.CANCEL)])
	text = ADMIN_MEDIA_ASK_GENRES
	if selected:
		text += "\n\nTanlangan: <b>" + escape_html(", ".join(sorted(selected))) + "</b>"
	await render(target, text, markup=keyboard(*rows), edit=edit)


async def show_language_step(target) -> None:
	await render(
		target,
		ADMIN_MEDIA_ASK_LANGUAGE,
		markup=value_choice_keyboard(f"{cb.ADM_MEDIA}:lang", LANGUAGES, back=cb.CANCEL),
	)


async def show_plan_step(target) -> None:
	await render(
		target,
		ADMIN_MEDIA_ASK_PLAN,
		markup=value_choice_keyboard(f"{cb.ADM_MEDIA}:plan", PLAN_OPTIONS, back=cb.CANCEL),
	)


async def show_status_step(target) -> None:
	await render(
		target,
		ADMIN_MEDIA_ASK_STATUS,
		markup=value_choice_keyboard(f"{cb.ADM_MEDIA}:status", STATUS_OPTIONS, back=cb.CANCEL),
	)


# ------------------------------------------------------------------ navigation
@router.callback_query(F.data == cb.ADM_MEDIA)
async def show_menu(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	await render(callback, ADMIN_MEDIA_MENU, markup=media_menu(), edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_MEDIA}:list:"))
async def list_titles(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	page = parse_int(args[0] if args else None, minimum=1) or 1
	titles = await all_titles()
	items, page, pages = paginate(titles, page, page_size())
	if not items:
		await render(callback, ADMIN_MEDIA_EMPTY, markup=media_menu(), edit=True)
		return
	await render(
		callback,
		ADMIN_MEDIA_LIST.format(page=page, pages=pages),
		markup=media_list(items, page, pages),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_MEDIA}:view:"))
async def view_title(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	args = cb.section_args(callback.data)
	title_pk = parse_int(args[0] if args else None, minimum=1)
	title = await get_title_by_pk(title_pk) if title_pk else None
	if title is None:
		await render(callback, NOT_FOUND, markup=media_menu(), edit=True)
		return
	await render(
		callback,
		await admin_card_text(title),
		markup=media_actions(title, page=1),
		edit=True,
	)


@router.callback_query(F.data == f"{cb.ADM_MEDIA}:search")
async def ask_search(callback: CallbackQuery, state: FSMContext) -> None:
	await state.set_state(AdminMediaStates.search)
	await render(callback, ADMIN_MEDIA_SEARCH, markup=cancel_keyboard(), edit=True)


@router.message(AdminMediaStates.search)
async def do_search(message: Message, state: FSMContext) -> None:
	query = (message.text or "").strip()
	await state.clear()
	if not query:
		await message.answer(ADMIN_INVALID_INPUT)
		return
	titles = await search_titles(query, limit=50)
	if not titles:
		await message.answer(ADMIN_MEDIA_EMPTY, reply_markup=media_menu())
		return
	items, page, pages = paginate(titles, 1, page_size())
	await message.answer(
		ADMIN_MEDIA_LIST.format(page=page, pages=pages),
		reply_markup=media_list(items, page, pages),
	)


# --------------------------------------------------------------------- creation
@router.callback_query(F.data == f"{cb.ADM_MEDIA}:new")
async def start_creation(callback: CallbackQuery, state: FSMContext) -> None:
	await state.clear()
	await render(callback, ADMIN_MEDIA_CREATE_TYPE, markup=media_types(), edit=True)


@router.callback_query(F.data.startswith(f"{cb.ADM_MEDIA}:typ:"))
async def choose_type(callback: CallbackQuery, state: FSMContext) -> None:
	args = cb.section_args(callback.data)
	media_type = args[0] if args else ""
	if media_type not in MediaTitle.MediaType.values:
		await render(callback, ADMIN_INVALID_INPUT, markup=media_types(), edit=True)
		return
	await state.clear()
	await state.set_state(AdminMediaStates.title)
	await update_draft(state, type=media_type, genres=[])
	await render(callback, ADMIN_MEDIA_ASK_TITLE, markup=cancel_keyboard(), edit=True)


@router.message(AdminMediaStates.title)
async def draft_title(message: Message, state: FSMContext) -> None:
	title = (message.text or "").strip()
	if not title or len(title) > 200:
		await message.answer(ADMIN_INVALID_INPUT)
		return
	await update_draft(state, title=title)
	await state.set_state(AdminMediaStates.synopsis)
	await message.answer(ADMIN_MEDIA_ASK_SYNOPSIS, reply_markup=cancel_keyboard())


@router.message(AdminMediaStates.synopsis)
async def draft_synopsis(message: Message, state: FSMContext) -> None:
	text = (message.text or "").strip()
	await update_draft(state, synopsis="" if text == "-" else text[:2000])
	await state.set_state(AdminMediaStates.cover)
	await message.answer(ADMIN_MEDIA_ASK_COVER, reply_markup=cancel_keyboard())


@router.message(AdminMediaStates.cover, F.photo)
async def draft_cover(message: Message, state: FSMContext) -> None:
	await update_draft(state, cover_file_id=message.photo[-1].file_id)
	await state.set_state(AdminMediaStates.genres)
	await show_genre_step(message, state)


@router.message(AdminMediaStates.cover)
async def draft_cover_skip(message: Message, state: FSMContext) -> None:
	await state.set_state(AdminMediaStates.genres)
	await message.answer(ADMIN_MEDIA_ASK_GENRES, reply_markup=cancel_keyboard())
	await show_genre_step(message, state)


@router.callback_query(F.data.startswith(f"{cb.ADM_MEDIA}:genre:"))
async def add_genre(callback: CallbackQuery, state: FSMContext) -> None:
	from movies.models import Genre

	args = cb.section_args(callback.data)
	genre_id = parse_int(args[0] if args else None, minimum=1)
	genre = await to_async(lambda: Genre.objects.filter(pk=genre_id).first())()
	if genre is None:
		await callback.answer(NOT_FOUND)
		return
	selected = list((await draft(state)).get("genres") or [])
	if genre.name not in selected:
		selected.append(genre.name)
	await update_draft(state, genres=selected)
	await callback.answer(f"➕ {genre.name}")
	await show_genre_step(callback, state, edit=True)


@router.callback_query(F.data == f"{cb.ADM_MEDIA}:genredone")
async def genres_done(callback: CallbackQuery, state: FSMContext) -> None:
	await state.set_state(AdminMediaStates.language)
	await show_language_step(callback)


@router.message(AdminMediaStates.genres)
async def genres_from_text(message: Message, state: FSMContext) -> None:
	names = [item.strip() for item in (message.text or "").split(",") if item.strip()]
	existing = list((await draft(state)).get("genres") or [])
	for name in names:
		if name not in existing:
			existing.append(name[:50])
	await update_draft(state, genres=existing)
	await state.set_state(AdminMediaStates.language)
	await message.answer(ADMIN_MEDIA_ASK_LANGUAGE, reply_markup=cancel_keyboard())
	await show_language_step(message)


@router.callback_query(F.data.startswith(f"{cb.ADM_MEDIA}:lang:"))
async def set_language(callback: CallbackQuery, state: FSMContext) -> None:
	args = cb.section_args(callback.data)
	code = args[0] if args else ""
	await update_draft(state, language=LANGUAGE_LABELS.get(code, "O'zbekcha"))
	await state.set_state(AdminMediaStates.quality)
	await render(callback, ADMIN_MEDIA_ASK_QUALITY, markup=cancel_keyboard(), edit=True)


@router.message(AdminMediaStates.language)
async def language_from_text(message: Message, state: FSMContext) -> None:
	text = (message.text or "").strip()
	await update_draft(state, language=(text or "O'zbekcha")[:40])
	await state.set_state(AdminMediaStates.quality)
	await message.answer(ADMIN_MEDIA_ASK_QUALITY, reply_markup=cancel_keyboard())


@router.message(AdminMediaStates.quality)
async def draft_quality(message: Message, state: FSMContext) -> None:
	qualities = [item.strip() for item in (message.text or "").replace(" ", ",").split(",") if item.strip()]
	qualities = [item for item in qualities if item.isdigit() and 144 <= int(item) <= 4320]
	if not qualities:
		await message.answer(ADMIN_INVALID_INPUT)
		return
	await update_draft(state, quality_options=qualities, default_quality=qualities[0])
	await state.set_state(AdminMediaStates.plan)
	await show_plan_step(message)


@router.callback_query(F.data.startswith(f"{cb.ADM_MEDIA}:plan:"))
async def set_plan(callback: CallbackQuery, state: FSMContext) -> None:
	args = cb.section_args(callback.data)
	plan = args[0] if args else ""
	if plan not in MediaTitle.AccessPlan.values:
		await callback.answer(ADMIN_INVALID_INPUT)
		return
	await update_draft(state, required_plan=plan)
	await state.set_state(AdminMediaStates.status)
	await show_status_step(callback)


@router.callback_query(F.data.startswith(f"{cb.ADM_MEDIA}:status:"))
async def set_status(callback: CallbackQuery, state: FSMContext) -> None:
	args = cb.section_args(callback.data)
	status = args[0] if args else ""
	if status not in MediaTitle.Status.values:
		await callback.answer(ADMIN_INVALID_INPUT)
		return
	await update_draft(state, status=status)
	await state.set_state(AdminMediaStates.rating)
	await render(callback, ADMIN_MEDIA_ASK_RATING, markup=cancel_keyboard(), edit=True)


@router.message(AdminMediaStates.rating)
async def draft_rating(message: Message, state: FSMContext) -> None:
	rating = parse_int((message.text or "").strip(), minimum=1, maximum=10)
	if rating is None:
		await message.answer(ADMIN_INVALID_INPUT)
		return
	await update_draft(state, rating=rating)
	await state.set_state(AdminMediaStates.preview)
	data = await draft(state)
	await message.answer(
		preview_text(data),
		reply_markup=confirm(f"{cb.ADM_MEDIA}:confirm", cb.CANCEL),
	)


@router.callback_query(F.data == f"{cb.ADM_MEDIA}:confirm")
async def commit_creation(callback: CallbackQuery, state: FSMContext, bot) -> None:
	data = await draft(state)
	if not data.get("title") or data.get("type") not in MediaTitle.MediaType.values:
		await render(callback, ADMIN_INVALID_INPUT, markup=media_menu(), edit=True)
		await state.clear()
		return

	cover = None
	if data.get("cover_file_id"):
		buffer = BytesIO()
		try:
			await bot.download(data["cover_file_id"], destination=buffer)
			cover = buffer.getvalue()
		except Exception:  # noqa: BLE001 - cover is optional
			logger.warning("Could not download the cover for the new title.")

	title = await create_title(
		media_type=data["type"],
		title=data["title"],
		synopsis=data.get("synopsis") or "",
		required_plan=data.get("required_plan") or MediaTitle.AccessPlan.FREE,
		language=data.get("language") or "O'zbekcha",
		quality_options=data.get("quality_options") or [],
		default_quality=data.get("default_quality") or "1080",
		status=data.get("status") or MediaTitle.Status.UPCOMING,
		rating=data.get("rating") or 5,
		genres=data.get("genres") or [],
		cover=cover,
		cover_content_type="image/jpeg" if cover else "",
	)
	await state.clear()
	await render(
		callback,
		ADMIN_MEDIA_SAVED.format(title=escape_html(title.title), code=title.code, slug=title.slug),
		markup=media_actions(title, page=1),
		edit=True,
	)
	await to_async(record_event)(
		"INFO", f"Content created: {title.title} ({title.code})", telegram_id=callback.from_user.id
	)
	await maybe_auto_publish_title(bot, title)


# ---------------------------------------------------------------------- editing
@router.callback_query(F.data == cb.CANCEL)
async def cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
	"""Shared ❌ button: leave any wizard and return to the panel dashboard."""
	await state.clear()
	stats = await dashboard()
	await render(callback, dashboard_text(stats), markup=admin_panel(), edit=True)


def _edit_target(callback: CallbackQuery):
	args = cb.section_args(callback.data)
	title_pk = parse_int(args[0] if args else None, minimum=1)
	field = args[1] if len(args) > 1 else ""
	return title_pk, field


@router.callback_query(F.data.startswith(f"{cb.ADM_MEDIA}:edit:"))
async def start_edit(callback: CallbackQuery, state: FSMContext) -> None:
	title_pk, field = _edit_target(callback)
	title = await get_title_by_pk(title_pk) if title_pk else None
	if title is None or not field:
		await render(callback, NOT_FOUND, markup=media_menu(), edit=True)
		return

	if field in CHOICE_FIELDS:
		await state.update_data(edit_title_id=title.pk, edit_field=field)
		await render(
			callback,
			f"✏️ <b>{field}</b> uchun yangi qiymat:",
			markup=value_choice_keyboard(
				f"{cb.ADM_MEDIA}:set:{title.pk}:{field}",
				CHOICE_FIELDS[field],
				back=f"{cb.ADM_MEDIA}:view:{title.pk}",
			),
			edit=True,
		)
		return

	await state.set_state(AdminMediaStates.edit_value)
	await state.update_data(edit_title_id=title.pk, edit_field=field)
	await render(
		callback,
		EDIT_PROMPT.format(cancel_hint="Bekor qilish uchun ❌ tugmasini bosing."),
		markup=keyboard(
			[btn("⬅️ Orqaga", f"{cb.ADM_MEDIA}:view:{title.pk}")],
			[btn("❌ Bekor qilish", cb.CANCEL)],
		),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_MEDIA}:set:"))
async def apply_choice(callback: CallbackQuery, state: FSMContext) -> None:
	args = cb.section_args(callback.data)
	title_pk = parse_int(args[0] if args else None, minimum=1)
	field = args[1] if len(args) > 1 else ""
	value = args[2] if len(args) > 2 else ""
	title = await get_title_by_pk(title_pk) if title_pk else None
	if title is None or field not in CHOICE_FIELDS:
		await render(callback, NOT_FOUND, markup=media_menu(), edit=True)
		return
	if value not in {option[0] for option in CHOICE_FIELDS[field]}:
		await callback.answer(ADMIN_INVALID_INPUT)
		return
	await update_title(title, **{field: value})
	await state.update_data(edit_title_id=None, edit_field="")
	await render(callback, await admin_card_text(title), markup=media_actions(title), edit=True)


@router.message(AdminMediaStates.edit_value, F.photo)
async def edit_cover(message: Message, state: FSMContext, bot) -> None:
	data = await state.get_data()
	title = await get_title_by_pk(data.get("edit_title_id"))
	if title is None:
		await state.clear()
		await message.answer(NOT_FOUND, reply_markup=media_menu())
		return
	buffer = BytesIO()
	await bot.download(message.photo[-1], destination=buffer)
	await update_title(title, cover=buffer.getvalue(), cover_content_type="image/jpeg")
	await state.update_data(edit_title_id=None, edit_field="")
	await state.set_state(None)
	await message.answer(await admin_card_text(title), reply_markup=media_actions(title))


@router.message(AdminMediaStates.edit_value)
async def apply_edit_value(message: Message, state: FSMContext) -> None:
	data = await state.get_data()
	title = await get_title_by_pk(data.get("edit_title_id"))
	field = data.get("edit_field") or ""
	raw = (message.text or "").strip()
	payload: dict = {}

	if title is None or not field:
		await state.clear()
		await message.answer(NOT_FOUND, reply_markup=media_menu())
		return

	if field == "quality_options":
		values = [item.strip() for item in raw.replace(" ", ",").split(",") if item.strip()]
		if not values:
			await message.answer(ADMIN_INVALID_INPUT)
			return
		payload[field] = values
	elif field == "rating":
		rating = parse_int(raw, minimum=1, maximum=10)
		if rating is None:
			await message.answer(ADMIN_INVALID_INPUT)
			return
		payload[field] = rating
	elif field == "release_year":
		if raw in {"", "-"}:
			payload[field] = None
		else:
			year = parse_int(raw, minimum=1900, maximum=2100)
			if year is None:
				await message.answer(ADMIN_INVALID_INPUT)
				return
			payload[field] = year
	elif field == "episode_count":
		if raw in {"", "-"}:
			payload[field] = None
		else:
			count = parse_int(raw, minimum=0, maximum=10000)
			if count is None:
				await message.answer(ADMIN_INVALID_INPUT)
				return
			payload[field] = count
	elif field in {"title", "synopsis", "language", "default_quality"}:
		if not raw:
			await message.answer(ADMIN_INVALID_INPUT)
			return
		payload[field] = raw[:2000] if field == "synopsis" else raw[:200]
	else:
		await message.answer(ADMIN_INVALID_INPUT)
		return

	await update_title(title, **payload)
	await state.update_data(edit_title_id=None, edit_field="")
	await state.set_state(None)
	await message.answer(await admin_card_text(title), reply_markup=media_actions(title))


# --------------------------------------------------------------------- deleting
@router.callback_query(F.data.startswith(f"{cb.ADM_MEDIA}:del:"))
async def confirm_delete(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	title_pk = parse_int(args[0] if args else None, minimum=1)
	page = parse_int(args[1] if len(args) > 1 else None, minimum=1) or 1
	title = await get_title_by_pk(title_pk) if title_pk else None
	if title is None:
		await render(callback, NOT_FOUND, markup=media_menu(), edit=True)
		return
	await render(
		callback,
		ADMIN_MEDIA_DELETE_CONFIRM.format(title=escape_html(title.title)),
		markup=confirm(f"{cb.ADM_MEDIA}:delok:{title.pk}:{page}", f"{cb.ADM_MEDIA}:view:{title.pk}"),
		edit=True,
	)


@router.callback_query(F.data.startswith(f"{cb.ADM_MEDIA}:delok:"))
async def do_delete(callback: CallbackQuery) -> None:
	args = cb.section_args(callback.data)
	title_pk = parse_int(args[0] if args else None, minimum=1)
	page = parse_int(args[1] if len(args) > 1 else None, minimum=1) or 1
	title = await get_title_by_pk(title_pk) if title_pk else None
	if title is None:
		await render(callback, NOT_FOUND, markup=media_menu(), edit=True)
		return
	name = title.title
	await delete_title(title)
	await to_async(record_event)(
		"WARNING", f"Content deleted: {name} (#{title_pk})", telegram_id=callback.from_user.id
	)
	titles = await all_titles()
	items, page, pages = paginate(titles, page, page_size())
	await render(
		callback,
		ADMIN_MEDIA_DELETED
		+ "\n\n"
		+ (ADMIN_MEDIA_LIST.format(page=page, pages=pages) if items else ADMIN_MEDIA_EMPTY),
		markup=media_list(items, page, pages) if items else media_menu(),
		edit=True,
	)


# Re-exported helpers used by other admin modules.
__all__ = ["router", "admin_card_text", "update_draft", "draft"]
