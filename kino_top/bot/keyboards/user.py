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
* ``subchk`` — re-check mandatory subscription

The parts navigator attached under a delivered part reuses ``watch:<part_pk>``,
so every number and both arrows simply request that part's media again.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence
from urllib.parse import quote

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .. import callbacks as cb
from ..config import game_url, webapp_url
from ..utils import chunked
from .common import btn, keyboard, pagination_row

# The parts navigator under a delivered part: five numbers per row, two rows a
# page. Both values are part of the requested layout, so they stay local rather
# than following the generic ``BOT_PAGE_SIZE`` used by the list screens.
PARTS_PER_ROW = 5
PARTS_PER_PAGE = PARTS_PER_ROW * 2

# Mini App screen that authenticates through Telegram and lets a new visitor
# create a profile (see the website's /telegram-auth route).
AUTH_WEBAPP_PATH = "/telegram-auth"


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


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
	rows = [
		[btn("🔍 Qidirish", cb.SEARCH), btn("📚 Katalog", cb.CATALOG_MENU)],
		[btn("🎼 Janrlar", f"{cb.GENRES}:1"), btn("💖 Sevimlilar", f"{cb.FAVORITES}:1")],
		[btn("👤 Profil", cb.PROFILE), btn("👥 Do'stlar", cb.REF)],
		[btn("🎫 Obuna", cb.SUBSCRIPTION), btn("🎟 Kupon", cb.COUPON)],
		[btn("ℹ️ Yordam", cb.HELP)],
	]
	# The rating game lives on the website; the button appears only when a
	# public site URL is configured so it is never broken.
	game = game_url()
	if game:
		rows.insert(3, [btn("🎮 O'yin (reyting)", url=game)])
	# The Mini App's Telegram-native screen covers sign-in and sign-up.
	app = webapp_row("🔐 Kirish / Ro'yxatdan o'tish", path=AUTH_WEBAPP_PATH)
	if app:
		rows.append(app)
	if is_admin:
		rows.append([btn("🛠 Administrator paneli", cb.ADM_STATS)])
	return keyboard(*rows)


def search_keyboard() -> InlineKeyboardMarkup:
	"""The search screen: filter by media type or genre, or list everything."""
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
