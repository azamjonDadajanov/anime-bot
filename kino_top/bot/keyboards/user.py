"""User-facing inline keyboards.

Callback contract (kept short for Telegram's 64 byte limit):

* ``menu`` / ``help`` / ``prof`` / ``search``
* ``cat:<page>`` — all titles
* ``type:<type>:<page>`` — titles of one media type
* ``genres:<page>`` / ``g:<genre_id>:<page>``
* ``fav:<page>`` — favourites
* ``t:<title_pk>:<page>:<origin>`` — title card (``origin`` describes the list)
* ``p:list:<title_pk>:<page>`` / ``p:view:<part_pk>``
* ``watch:<part_pk>`` / ``wt:<title_pk>`` / ``q:<part_pk>:<quality>``
* manga titles use a plain ``url`` button to the website reader
* ``favt:<title_pk>:<page>:<origin>``
* ``favm:<title_pk>:<part_pk>`` — favourite toggle under a delivered file
* ``ai`` — the AI yordamchi chat (subscribers only)
* ``aiok`` / ``aino`` — the AI amal card's confirm/cancel; ``aiad:<f>:<±1>``,
  ``aic:<f>``, ``ait:<f>``, ``aied:<f>`` edit one field, ``aiacheck`` re-checks
  the Telegram link status
* ``alink:<username>`` / ``alinkno`` — /start account-link confirm
* ``qz:<title_pk>`` / ``qza:<attempt_pk>:<index>:<choice>`` — the in-bot quiz
* ``rt`` — the rating table (top players, the caller's own rank)
* ``subchk`` — re-check mandatory subscription
* ``support`` — write a message to the administrators

The parts navigator attached under a delivered part reuses ``watch:<part_pk>``,
so every number and both arrows simply request that part's media again.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from movies.ai_assistant import user_can_use

from .. import callbacks as cb
from ..config import game_url, webapp_url
from ..utils import chunked, truncate
from .common import btn, keyboard, pagination_row

# The parts navigator under a delivered part: five numbers per row, two rows a
# page. Both values are part of the requested layout, so they stay local rather
# than following the generic ``BOT_PAGE_SIZE`` used by the list screens.
PARTS_PER_ROW = 5
PARTS_PER_PAGE = PARTS_PER_ROW * 2

# Mini App screen that authenticates through Telegram and lets a new visitor
# create a profile (see the website's /telegram-auth route).
AUTH_WEBAPP_PATH = "/telegram-auth"

# Result lists produced by the AI yordamchi carry this origin, so the title
# card's back button returns to the assistant prompt (see
# :func:`origin_callback`).
ASSISTANT_ORIGIN = "ai"
# Telegram renders ten keycap emojis reliably; the label of the eleventh would
# wrap in a narrow client.
NUMBER_EMOJI = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟")


def origin_callback(origin: str, page: int) -> str:
	"""Map an ``origin`` slug back to the callback that re-opens its list."""
	origin = origin or "cat"
	if origin.startswith("type:"):
		return f"{cb.TYPE}:{origin.split(':', 1)[1]}:{page}"
	if origin.startswith("g:"):
		return f"{cb.GENRE}:{origin.split(':', 1)[1]}:{page}"
	if origin.startswith("fav"):
		return f"{cb.FAVORITES}:{page}"
	if origin.startswith("search"):
		return f"{cb.SEARCH_RESULTS}:{page}"
	if origin.startswith(ASSISTANT_ORIGIN):
		return cb.AI_ASSISTANT
	return f"{cb.CATALOG}:{page}"


def webapp_row(text: str = "📱 Ilova", path: str = "") -> Optional[List[InlineKeyboardButton]]:
	"""A Telegram Mini App button row, or ``None`` when no URL is configured.

	``path`` selects the Mini App screen (sign-in/sign-up live at
	``/telegram-auth``). These buttons stay absent (rather than broken) on a
	deployment without ``BOT_WEBAPP_URL``.
	"""
	url = webapp_url(path)
	if not url:
		return None
	return [btn(text, web_app=url)]


def main_menu(is_admin: bool = False, profile=None) -> InlineKeyboardMarkup:
	"""The main menu; the AI yordamchi button exists only for subscribers.

	``profile`` is the TelegramUser the context middleware injected. Without it
	the button is simply absent (an anonymous menu), which is also what an
	active-subscription check failure should look like rather than a broken
	button.
	"""
	rows = [
		[btn("🔍 Qidirish", cb.SEARCH), btn("📚 Katalog", cb.CATALOG_MENU)],
		[btn("🎼 Janrlar", f"{cb.GENRES}:1"), btn("💖 Sevimlilar", f"{cb.FAVORITES}:1")],
		[btn("👤 Profil", cb.PROFILE), btn("👥 Do'stlar", cb.REF)],
		[btn("🎫 Obuna", cb.SUBSCRIPTION), btn("🎟 Kupon", cb.COUPON)],
	]
	if user_can_use(getattr(profile, "auth_user", None)):
		# The assistant is a paid feature: an active subscription is required,
		# so a free account never sees the button at all.
		rows.append([btn("🤖 AI yordamchi", cb.AI_ASSISTANT)])
	rows.append([btn("ℹ️ Yordam", cb.HELP), btn("✉️ Adminga xabar", cb.SUPPORT)])
	# The rating table is public and lives right in the bot; playing the game
	# itself opens the website, so that half only appears with a site URL.
	game = game_url()
	if game:
		rows.insert(3, [btn("🎮 O'yin o'ynash", url=game), btn("🏆 Reyting", cb.RATING)])
	else:
		rows.insert(4, [btn("🏆 Reyting", cb.RATING)])
	# The Mini App's Telegram-native screen covers sign-in and sign-up.
	app = webapp_row("🔐 Kirish / Ro'yxatdan o'tish", path=AUTH_WEBAPP_PATH)
	if app:
		rows.append(app)
	if is_admin:
		rows.append([btn("🛠 Administrator paneli", cb.ADM_STATS)])
	return keyboard(*rows)


def search_keyboard() -> InlineKeyboardMarkup:
	"""The plain search screen: filter by media type or genre, or list everything.

	The AI yordamchi is deliberately not here: it has its own button on the main
	menu, shown to subscribers only, so the search screen stays the fast
	name/code/genre lookup it was.
	"""
	rows: List[List[InlineKeyboardButton]] = [
		[btn("🎌 Anime", f"{cb.S_TYPE}:anime:1"), btn("📺 Serial", f"{cb.S_TYPE}:series:1")],
		[btn("📖 Manga", f"{cb.S_TYPE}:manga:1"), btn("🎬 Kino", f"{cb.S_TYPE}:movie:1")],
		[btn("🎭 Janr bo'yicha", f"{cb.S_GENRES}:1")],
		[btn("📚 Barchasini ko'rish", cb.S_ALL)],
	]
	app = webapp_row("📱 Ilovada qidirish")
	if app:
		rows.append(app)
	rows.append([btn("⬅️ Asosiy menyu", cb.MENU)])
	return keyboard(*rows)


def search_genres_keyboard(genres: Sequence, page: int, pages: int) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = [
		[btn(genre.name, f"{cb.S_GENRE}:{genre.pk}:1")] for genre in genres
	]
	rows.append(pagination_row(f"{cb.S_GENRES}:", page, pages))
	rows.append([btn("⬅️ Qidiruvga qaytish", cb.SEARCH)])
	return keyboard(*rows)


def assistant_keyboard(*, personal: bool = False) -> InlineKeyboardMarkup:
	"""Shown while the AI yordamchi waits for the user's message.

	``personal`` reflects whether the user opted in to giving the assistant
	their favourites and recent activity ("agar user ozi hohlasa"): the toggle
	only changes what the assistant may read, the feature costs nothing when off.
	"""
	personal_label = "🎯 Sevimlilar: ✅" if personal else "🎯 Sevimlilar: ❌"
	return keyboard(
		[btn(personal_label, cb.AI_PERSONAL)],
		[btn("⬅️ Asosiy menyu", cb.MENU)],
	)


def assistant_locked_keyboard() -> InlineKeyboardMarkup:
	"""The way forward for a visitor without an active subscription."""
	return keyboard(
		[btn("🎫 Obuna", cb.SUBSCRIPTION)],
		[btn("⬅️ Asosiy menyu", cb.MENU)],
	)


def assistant_results_keyboard(
	items: Sequence[Dict[str, Any]], *, limit: int = len(NUMBER_EMOJI)
) -> InlineKeyboardMarkup:
	"""Numbered buttons that open each title the assistant found, in the bot.

	The message above already lists every hit with its link and one-line summary;
	these buttons are how the user opens one without leaving Telegram.
	"""
	rows: List[List[InlineKeyboardButton]] = []
	for index, item in enumerate(list(items)[: min(limit, len(NUMBER_EMOJI))]):
		rows.append(
			[
				btn(
					f"{NUMBER_EMOJI[index]} {truncate(item.get('title'), 40)}",
					f"{cb.TITLE}:{item.get('id')}:1:{ASSISTANT_ORIGIN}",
				)
			]
		)
	rows.append([btn("🔎 Yana so'rash", cb.AI_ASSISTANT)])
	rows.append([btn("⬅️ Asosiy menyu", cb.MENU)])
	return keyboard(*rows)


def assistant_action_keyboard(
	action: Dict[str, Any],
	*,
	link_url: str = "",
) -> InlineKeyboardMarkup:
	"""Confirm/cancel plus the per-field editors under a proposed amal card.

	The card body (built server-side by ``movies.ai_actions``) lists every
	value; these buttons only *edit* the values the action allows — an int
	with +/-, a select by cycling its options, a bool by flipping it, text by
	dropping into the ``action_edit`` FSM state. The signed token itself never
	rides in callback data: it lives in the FSM.
	"""
	rows: List[List[InlineKeyboardButton]] = []
	if action.get("kind") == "link":
		linked = bool((action.get("link") or {}).get("linked"))
		if linked:
			rows.append([btn("✅ Ulangan", cb.NOOP)])
		else:
			if link_url:
				rows.append([btn("🔗 Akountga ulash", url=link_url)])
			rows.append([btn("🔄 Tekshirish", cb.AI_ACTION_CHECK)])
		rows.append([btn("⬅️ Asosiy menyu", cb.MENU)])
		return keyboard(*rows)

	for field in action.get("fields") or []:
		if not field.get("editable"):
			continue
		key = str(field.get("key") or "")
		label = str(field.get("label") or key)
		field_type = field.get("type")
		if not key or field_type == "file":
			continue
		if field_type == "int":
			value = field.get("value")
			rows.append(
				[
					btn(f"➖ {label}", f"{cb.AI_ACTION_ADJ}:{key}:-1"),
					btn("—" if value in (None, "") else str(value), cb.NOOP),
					btn(f"➕ {label}", f"{cb.AI_ACTION_ADJ}:{key}:+1"),
				]
			)
		elif field_type == "select":
			value = field.get("value")
			options = field.get("options") or []
			current = next(
				(option.get("label") for option in options if option.get("value") == value),
				"",
			)
			rows.append([btn(f"🔄 {label}: {current or 'tanlang'}", f"{cb.AI_ACTION_CYCLE}:{key}")])
		elif field_type == "bool":
			mark = "✅" if field.get("value") else "❌"
			rows.append([btn(f"{mark} {label}", f"{cb.AI_ACTION_TOGGLE}:{key}")])
		elif field_type in ("text", "textarea"):
			rows.append([btn(f"✏️ {label}", f"{cb.AI_ACTION_EDIT}:{key}")])
	rows.append(
		[
			btn("✅ Tasdiqlash", cb.AI_ACTION_OK),
			btn("❌ Bekor qilish", cb.AI_ACTION_NO),
		]
	)
	rows.append([btn("⬅️ Asosiy menyu", cb.MENU)])
	return keyboard(*rows)


def catalog_menu() -> InlineKeyboardMarkup:
	return keyboard(
		[btn("🎌 Anime", f"{cb.TYPE}:anime:1"), btn("📺 Serial", f"{cb.TYPE}:series:1")],
		[btn("📖 Manga", f"{cb.TYPE}:manga:1"), btn("🎬 Kino", f"{cb.TYPE}:movie:1")],
		[btn("📚 Barchasi", f"{cb.CATALOG}:1"), btn("🎭 Janrlar", f"{cb.GENRES}:1")],
		[btn("⬅️ Asosiy menyu", cb.MENU)],
	)


def results_keyboard(
	items: Sequence,
	*,
	prefix: str,
	page: int,
	pages: int,
	origin: str,
	back: str = cb.MENU,
) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	for item in items:
		rows.append([btn(f"{item.title} · {item.code}", f"{cb.TITLE}:{item.pk}:{page}:{origin}")])
	rows.append(pagination_row(prefix, page, pages))
	rows.append([btn("⬅️ Orqaga", back)])
	return keyboard(*rows)


def genres_keyboard(genres: Sequence, page: int, pages: int) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = [
		[btn(genre.name, f"{cb.GENRE}:{genre.pk}:1")] for genre in genres
	]
	rows.append(pagination_row(f"{cb.GENRES}:", page, pages))
	rows.append([btn("⬅️ Orqaga", cb.MENU)])
	return keyboard(*rows)


def title_detail_keyboard(
	title_pk: int,
	*,
	is_favorite: bool,
	origin: str,
	page: int,
	back: str,
	media_type: str = "",
	manga_url: str = "",
) -> InlineKeyboardMarkup:
	# The "watch" button is always shown: with no parts yet the handler explains
	# that, and for manga it opens the website. This keeps every entry point
	# (deep link, search, code) consistent.
	rows: List[List[InlineKeyboardButton]] = []
	if media_type == "manga" and manga_url:
		# Manga is read on the website, so "watch" becomes a plain URL button.
		rows.append([btn("📖 Saytda o'qish", url=manga_url)])
	elif media_type == "movie":
		# A movie is delivered in a single tap, without an episode list.
		rows.append([btn("🎬 Kinoni ko'rish", f"{cb.WATCH_TITLE}:{title_pk}")])
	else:
		# Anime/series open the episode list, where every part can be watched.
		watch_label = "▶️ Animeni ko'rish" if media_type == "anime" else "🎬 Tomosha qilish"
		rows.append([btn(watch_label, f"{cb.PART}:list:{title_pk}:1:{origin}")])
	favorite_label = "💔 Sevimlilardan olib tashlash" if is_favorite else "⭐️ Sevimlilarga qo'shish"
	rows.append([btn(favorite_label, f"{cb.FAV_TOGGLE}:{title_pk}:{page}:{origin[:16]}")])
	# The comments live in one table shared with the website, so the bot shows
	# what others wrote there and can add its own.
	rows.append([btn("💬 Izohlar", f"{cb.COMMENT_LIST}:{title_pk}:1")])
	rows.append([btn("⬅️ Orqaga", back)])
	return keyboard(*rows)


def manga_keyboard(url: str) -> InlineKeyboardMarkup:
	"""Standalone \"read on the website\" keyboard used for manga titles."""
	return keyboard([btn("📖 Saytda o'qish", url=url)])


def parts_keyboard(
	parts: Sequence,
	title_pk: int,
	page: int,
	pages: int,
	*,
	origin: str = "cat",
	first_part_pk: Optional[int] = None,
) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	if first_part_pk:
		rows.append([btn("▶️ Tomosha qilish", f"{cb.WATCH}:{first_part_pk}")])
	for part in parts:
		season = f"{part.season_number}-mavsum " if part.season_number else ""
		rows.append(
			[
				btn(
					f"{season}{part.number}-qism" + (f" · {part.title}" if part.title else ""),
					f"{cb.PART}:view:{part.pk}:{origin}",
				)
			]
		)
	rows.append(pagination_row(f"{cb.PART}:list:{title_pk}:", page, pages))
	rows.append([btn("⬅️ Orqaga", f"{cb.TITLE}:{title_pk}:1:{origin}")])
	return keyboard(*rows)


def part_keyboard(
	part_pk: int,
	qualities: Sequence[str],
	title_pk: int,
	origin: str = "cat",
) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	if len(qualities) > 1:
		rows.append(
			[btn(f"💎 {quality}", f"{cb.QUALITY}:{part_pk}:{quality}") for quality in qualities[:4]]
		)
	rows.append([btn("▶️ Ko'rish", f"{cb.WATCH}:{part_pk}")])
	rows.append([btn("⬅️ Orqaga", f"{cb.PART}:list:{title_pk}:1:{origin}")])
	return keyboard(*rows)


def _part_sort_key(part):
	"""Season-and-number order; unseasoned parts come last."""
	return (part.season_number is None, part.season_number or 0, part.number)


def _season_label(part) -> str:
	if part.season_number:
		return f"{part.season_number}-mavsum"
	return "Qismlar"


def watch_parts_keyboard(parts: Sequence, current) -> InlineKeyboardMarkup:
	"""Navigator attached under a delivered part.

	The numbers of the *current season* are laid out five per row, ten per page;
	the page follows the part that was just delivered. The part being watched
	carries a green marker (Telegram buttons cannot be recoloured), and the
	bottom row walks to the previous/next part — crossing a season boundary
	switches to the neighbouring season's first (or last) part. The middle button
	names the season the user is currently in.

	Every number and both arrows request their part with ``watch:<part_pk>``, so
	the handler swaps the file inside the message the user is already looking at.
	"""
	ordered = sorted(parts, key=_part_sort_key)
	if not ordered:
		return keyboard()

	pks = [part.pk for part in ordered]
	index = pks.index(current.pk) if current.pk in pks else 0
	current = ordered[index]

	season_parts = [part for part in ordered if part.season_number == current.season_number]
	position = next(
		(i for i, part in enumerate(season_parts) if part.pk == current.pk), 0
	)
	pages = max(1, math.ceil(len(season_parts) / PARTS_PER_PAGE))
	page = position // PARTS_PER_PAGE + 1
	window = season_parts[(page - 1) * PARTS_PER_PAGE : page * PARTS_PER_PAGE]

	rows: List[List[InlineKeyboardButton]] = [
		[
			btn(
				f"🟢 {part.number}" if part.pk == current.pk else str(part.number),
				f"{cb.WATCH}:{part.pk}",
			)
			for part in row
		]
		for row in chunked(window, PARTS_PER_ROW)
	]

	label = _season_label(current)
	if pages > 1:
		label = f"{label} {page}/{pages}"
	nav = [btn("⬅️ Oldingi qism", cb.NOOP), btn(label, cb.NOOP), btn("Keyingi qism ➡️", cb.NOOP)]
	if index > 0:
		nav[0] = btn("⬅️ Oldingi qism", f"{cb.WATCH}:{ordered[index - 1].pk}")
	if index < len(ordered) - 1:
		nav[2] = btn("Keyingi qism ➡️", f"{cb.WATCH}:{ordered[index + 1].pk}")
	rows.append(nav)
	return keyboard(*rows)


def media_keyboard(
	title_pk: int,
	current,
	*,
	is_favorite: bool = False,
	has_quiz: bool = False,
	parts: Sequence = (),
	manga_url: str = "",
) -> InlineKeyboardMarkup:
	"""Keyboard that rides on every message delivering this title's media.

	Order (top to bottom): the website reader link for manga, the parts
	navigator when the title has more than one part, the favourite toggle, the
	quiz button (only while the title has active questions) and the main menu.
	The navigator keeps the exact layout of :func:`watch_parts_keyboard`, so
	the action rows simply follow it.
	"""
	rows: List[List[InlineKeyboardButton]] = []
	if manga_url:
		rows.append([btn("📖 Saytda o'qish", url=manga_url)])
	if current is not None and len(parts) > 1:
		rows.extend(watch_parts_keyboard(parts, current).inline_keyboard)
	favorite_label = (
		"💔 Sevimlilardan olib tashlash" if is_favorite else "⭐️ Sevimlilarga qo'shish"
	)
	rows.append(
		[btn(favorite_label, f"{cb.FAV_MEDIA}:{title_pk}:{getattr(current, 'pk', 0) or 0}")]
	)
	# Writing from here attaches the comment to the episode on screen, and the
	# bot re-sends that episode with its navigator once the comment is saved.
	rows.append(
		[
			btn(
				"💬 Izoh qoldirish",
				cb.join(cb.COMMENT, title_pk, getattr(current, "pk", None)),
			)
		]
	)
	if has_quiz:
		rows.append([btn("🧪 Testlarni ishlash", f"{cb.QUIZ}:{title_pk}")])
	rows.append([btn("⬅️ Asosiy menyu", cb.MENU)])
	return keyboard(*rows)


def quiz_keyboard(attempt_id: int, index: int, choices: Sequence[str]) -> InlineKeyboardMarkup:
	"""One button per shuffled answer choice of the current quiz question."""
	rows = [
		[btn(truncate(choice, 64), f"{cb.QUIZ_ANSWER}:{attempt_id}:{index}:{choice_index}")]
		for choice_index, choice in enumerate(choices)
	]
	return keyboard(*rows)


def rating_keyboard(site: str = "") -> InlineKeyboardMarkup:
	"""Under the rating table: play on the website, refresh, or go back."""
	rows: List[List[InlineKeyboardButton]] = []
	if site:
		rows.append([btn("🎮 O'yin o'ynash", url=site)])
	rows.append([btn("🔄 Yangilash", cb.RATING), btn("⬅️ Asosiy menyu", cb.MENU)])
	return keyboard(*rows)


def comment_prompt_keyboard() -> InlineKeyboardMarkup:
	"""While the bot waits for the comment text: only a way out."""
	return keyboard([btn("✖️ Bekor qilish", cb.COMMENT_CANCEL)])


def comment_rating_keyboard() -> InlineKeyboardMarkup:
	"""The 1-10 score picker: two rows of five, then skip and cancel.

	Each keycap posts its own score; picking one finishes the comment (the text
	is already in the FSM), so there is no second confirmation step.
	"""
	rows: List[List[InlineKeyboardButton]] = [
		[btn(NUMBER_EMOJI[index], f"{cb.COMMENT_RATE}:{index + 1}") for index in range(5)],
		[
			btn(NUMBER_EMOJI[index], f"{cb.COMMENT_RATE}:{index + 1}")
			for index in range(5, 10)
		],
	]
	rows.append([btn("⭐️ Bahosiz davom etish", cb.COMMENT_RATE_SKIP)])
	rows.append([btn("✖️ Bekor qilish", cb.COMMENT_CANCEL)])
	return keyboard(*rows)


def comment_list_keyboard(title_pk: int, page: int, pages: int) -> InlineKeyboardMarkup:
	"""Under a page of comments: write one, page through, or go back."""
	rows: List[List[InlineKeyboardButton]] = [
		[btn("💬 Izoh yozish", cb.join(cb.COMMENT, title_pk))]
	]
	rows.append(pagination_row(f"{cb.COMMENT_LIST}:{title_pk}:", page, pages))
	rows.append([btn("⬅️ Orqaga", f"{cb.TITLE}:{title_pk}:1:cat")])
	return keyboard(*rows)


def favorites_keyboard(items: Sequence, page: int, pages: int) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = [
		[btn(f"{item.title} · {item.code}", f"{cb.TITLE}:{item.pk}:{page}:fav")] for item in items
	]
	rows.append(pagination_row(f"{cb.FAVORITES}:", page, pages))
	rows.append([btn("⬅️ Asosiy menyu", cb.MENU)])
	return keyboard(*rows)


def coupon_keyboard() -> InlineKeyboardMarkup:
	return keyboard(
		[btn("🎫 Obuna", cb.SUBSCRIPTION)],
		[btn("🏠 Asosiy menyu", cb.MENU)],
	)


def referral_keyboard(*, invited: int, claimed, link: str) -> InlineKeyboardMarkup:
	"""Referral menu: share link plus one claim button per reachable milestone.

	A milestone already claimed shows as a static "olindi" label; one that is
	still out of reach is omitted (the invited counter in the text explains why).
	"""
	from users.referrals import REFERRAL_MILESTONES

	rows: List[List[InlineKeyboardButton]] = []
	target = (link or "").strip()
	if target:
		share = (
			"https://t.me/share/url?url="
			+ quote(target, safe="")
			+ "&text="
			+ quote("AniChopar botga qo'shil va animelarni tomosha qil!", safe="")
		)
		rows.append([btn("📤 Ulashish", url=share)])
	for milestone, days in sorted(REFERRAL_MILESTONES.items()):
		if milestone in claimed:
			rows.append([btn(f"✅ {days} kun olindi", cb.NOOP)])
		elif invited >= milestone:
			rows.append([btn(f"🎁 {days} kun olish", f"{cb.REF_CLAIM}:{milestone}")])
	rows.append([btn("🏠 Asosiy menyu", cb.MENU)])
	return keyboard(*rows)


def profile_keyboard() -> InlineKeyboardMarkup:
	return keyboard(
		[btn("🎫 Obuna", cb.SUBSCRIPTION)],
		[btn("💖 Sevimlilar", f"{cb.FAVORITES}:1")],
		[btn("🏠 Asosiy menyu", cb.MENU)],
	)


def subscription_keyboard(
	plans: Sequence, current_plan: str, *, current_active: bool = False
) -> InlineKeyboardMarkup:
	"""One row per plan; a *running* current plan is shown as a no-op label."""
	rows: List[List[InlineKeyboardButton]] = []
	for plan in plans:
		plan_id = plan["id"]
		price = plan.get("price") or 0
		price_text = "Bepul" if price <= 0 else f"{price:,} so'm"
		if plan_id == current_plan and current_active:
			label = f"✅ {plan['label']} (joriy)"
			rows.append([btn(label, cb.NOOP)])
		else:
			rows.append([btn(f"🔄 {plan['label']} — {price_text}", f"{cb.SUBSCRIPTION_BUY}:{plan_id}")])
	rows.append([btn("⬅️ Orqaga", cb.PROFILE)])
	return keyboard(*rows)
