"""Administrator panel inline keyboards.

Callback convention: ``a:<section>:<action>[:<args>]``. Every builder keeps the
payload short enough for Telegram's 64 byte callback limit.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from aiogram.types import (
	InlineKeyboardButton,
	InlineKeyboardMarkup,
	KeyboardButton,
	ReplyKeyboardMarkup,
)
from movies.models import MediaTitle, TelegramChannel
from users.models import Giveaway

from .. import callbacks as cb
from ..services.channels import (
	CHANNEL_GROUPS,
	group_purposes,
	purpose_label,
	purpose_short_label,
)
from .common import btn, confirm_keyboard, keyboard, pagination_row

FIELD_LABELS = {
	"title": "📌 Nomi",
	"synopsis": "📝 Tavsif",
	"cover": "🖼 Muqova",
	"language": "🌐 Til",
	"quality_options": "💎 Sifatlar",
	"default_quality": "🎯 Asosiy sifat",
	"required_plan": "🔒 Tarif",
	"status": "📊 Holat",
	"rating": "⭐ Reyting",
	"release_year": "📅 Yil",
	"episode_count": "🎞 Qismlar soni",
	"duration_minutes": "⏱ Davomiylik (daqiqa)",
	"type": "📺 Turi",
}

CHANNEL_FIELD_LABELS = {
	"title": "📌 Nomi",
	"username": "🔗 Username",
	"invite_link": "🧷 Havola",
	"purpose": "📡 Turi",
}


def panel_home() -> InlineKeyboardMarkup:
	return keyboard([btn("🏠 Asosiy menyu", cb.ADM_STATS)])


def admin_panel() -> InlineKeyboardMarkup:
	return keyboard(
		[btn("🎬 Kontent", cb.ADM_MEDIA), btn("🎞 Qismlar", cb.ADM_EPISODES)],
		[btn("📡 Kanallar", cb.ADM_CHANNELS), btn("📣 Broadcast", cb.ADM_BROADCAST)],
		[btn("👥 Foydalanuvchilar", cb.ADM_USERS), btn("⚙️ Sozlamalar", cb.ADM_SETTINGS)],
		[btn("🎟 Kuponlar", cb.ADM_COUPONS), btn("🎁 Sovg'alar", cb.ADM_GIVEAWAY)],
		[btn("📜 Jurnallar", cb.ADM_LOGS), btn("🔄 Yangilash", cb.ADM_STATS)],
		[btn("🏠 Asosiy menyu", cb.MENU)],
	)


def media_menu() -> InlineKeyboardMarkup:
	return keyboard(
		[btn("➕ Yangi kontent", f"{cb.ADM_MEDIA}:new")],
		[btn("📃 Ro'yxat", f"{cb.ADM_MEDIA}:list:1"), btn("🔍 Qidirish", f"{cb.ADM_MEDIA}:search")],
		[btn("🏠 Panel", cb.ADM_STATS)],
	)


def media_types() -> InlineKeyboardMarkup:
	rows = [
		[
			btn("🎌 Anime", f"{cb.ADM_MEDIA}:typ:{MediaTitle.MediaType.ANIME}"),
			btn("📺 Serial", f"{cb.ADM_MEDIA}:typ:{MediaTitle.MediaType.SERIES}"),
		],
		[
			btn("📖 Manga", f"{cb.ADM_MEDIA}:typ:{MediaTitle.MediaType.MANGA}"),
			btn("🎬 Kino", f"{cb.ADM_MEDIA}:typ:{MediaTitle.MediaType.MOVIE}"),
		],
		[btn("⬅️ Orqaga", cb.ADM_MEDIA)],
	]
	return keyboard(*rows)


def media_list(items: Sequence, page: int, pages: int) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	for item in items:
		rows.append([btn(f"{item.title} · {item.code}", f"{cb.ADM_MEDIA}:view:{item.pk}")])
	rows.append(pagination_row(f"{cb.ADM_MEDIA}:list:", page, pages))
	rows.append([btn("⬅️ Orqaga", cb.ADM_MEDIA)])
	return keyboard(*rows)


def media_actions(title, *, page: int = 1) -> InlineKeyboardMarkup:
	return keyboard(
		[btn("🎞 Qismlar", f"{cb.ADM_EPISODES}:list:{title.pk}:1")],
		[btn("📢 E'lon qilish", f"{cb.ADM_MEDIA}:ann:{title.pk}")],
		[btn("✏️ Tahrirlash", f"{cb.ADM_MEDIA}:edit:{title.pk}:title")],
		[btn("🗑 O'chirish", f"{cb.ADM_MEDIA}:del:{title.pk}:{page}")],
		[btn("⬅️ Ro'yxat", f"{cb.ADM_MEDIA}:list:{page}")],
	)


def media_announce_scopes(title, *, page: int = 1) -> InlineKeyboardMarkup:
	"""Ask an ongoing title's operator how much to announce.

	A finished title never sees this keyboard: its whole run is announced.
	"""
	return keyboard(
		[btn("🆕 Faqat oxirgi qism", f"{cb.ADM_MEDIA}:annok:{title.pk}:last")],
		[btn("📚 Barcha qismlar", f"{cb.ADM_MEDIA}:annok:{title.pk}:all")],
		[btn("⬅️ Orqaga", f"{cb.ADM_MEDIA}:view:{title.pk}")],
	)


def media_edit_fields(title, *, page: int = 1) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	fields = ["title", "synopsis", "cover", "language", "quality_options", "required_plan", "status", "rating", "release_year", "episode_count", "duration_minutes", "type"]
	for index in range(0, len(fields), 2):
		rows.append(
			[
				btn(FIELD_LABELS[field], f"{cb.ADM_MEDIA}:edit:{title.pk}:{field}")
				for field in fields[index:index + 2]
			]
		)
	rows.append([btn("⬅️ Orqaga", f"{cb.ADM_MEDIA}:view:{title.pk}")])
	return keyboard(*rows)


def value_choice_keyboard(prefix: str, options: Sequence[tuple], *, back: str) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	for value, label in options:
		rows.append([btn(label, f"{prefix}:{value}")])
	rows.append([btn("⬅️ Orqaga", back)])
	return keyboard(*rows)


def episodes_menu() -> InlineKeyboardMarkup:
	return keyboard(
		[btn("➕ Qism qo'shish", f"{cb.ADM_EPISODES}:pick:1")],
		[btn("📃 Kontentlar", f"{cb.ADM_MEDIA}:list:1")],
		[btn("🏠 Panel", cb.ADM_STATS)],
	)


def title_picker(items: Sequence, page: int, pages: int) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	for item in items:
		rows.append([btn(f"{item.title} · {item.code}", f"{cb.ADM_EPISODES}:add:{item.pk}")])
	rows.append(pagination_row(f"{cb.ADM_EPISODES}:pick:", page, pages))
	rows.append([btn("⬅️ Orqaga", cb.ADM_EPISODES)])
	return keyboard(*rows)


# Reply-keyboard labels used by the episode uploader. The text arrives as an
# ordinary message, so handlers compare against these exact strings.
EPISODE_SAVE_LABEL = "💾 Saqlash"
EPISODE_CANCEL_LABEL = "❌ Bekor qilish"


def episode_upload_reply_keyboard() -> ReplyKeyboardMarkup:
	"""Keyboard shown while an administrator streams episode files.

	The files are sent as normal messages; ``💾 Saqlash`` finishes the upload
	and publishes the batch, ``❌ Bekor qilish`` abandons it.
	"""
	return ReplyKeyboardMarkup(
		keyboard=[
			[KeyboardButton(text=EPISODE_SAVE_LABEL)],
			[KeyboardButton(text=EPISODE_CANCEL_LABEL)],
		],
		resize_keyboard=True,
		input_field_placeholder="Video yoki fayl yuboring...",
	)


def channel_picker(channels: Sequence[TelegramChannel], prefix: str) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	for channel in channels:
		rows.append([btn(f"☁️ {channel.title}", f"{prefix}:{channel.pk}")])
	rows.append([btn("❌ Bekor qilish", cb.CANCEL)])
	return keyboard(*rows)


def parts_list(parts: Sequence, title_pk: int, page: int, pages: int) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	for part in parts:
		season = f"{part.season_number}-m " if part.season_number else ""
		rows.append([btn(f"{season}{part.number}-qism", f"{cb.ADM_EPISODES}:view:{part.pk}")])
	rows.append(pagination_row(f"{cb.ADM_EPISODES}:list:{title_pk}:", page, pages))
	rows.append([btn("⬅️ Orqaga", f"{cb.ADM_MEDIA}:view:{title_pk}")])
	return keyboard(*rows)


def part_actions(part, *, title_pk: int, page: int = 1, media_items: Sequence = ()) -> InlineKeyboardMarkup:
	# A part stores exactly one file, so there is nothing to reorder or append.
	# ``media_items`` is fetched by the caller inside the async ORM bridge; the
	# keyboard builder must never touch the database from an async context.
	rows: List[List[InlineKeyboardButton]] = []
	for media in sorted(media_items, key=lambda item: item.order):
		rows.append([btn(f"📦 {media.get_media_type_display()}", cb.NOOP)])
	rows.append([btn("🗑 Qismni o'chirish", f"{cb.ADM_EPISODES}:del:{part.pk}:{title_pk}:{page}")])
	rows.append([btn("⬅️ Orqaga", f"{cb.ADM_EPISODES}:list:{title_pk}:{page}")])
	return keyboard(*rows)


def _channel_back_payload(purpose: str) -> str:
	"""Back target for a channel list: its catalogue section or the main menu."""
	for key, _label, purposes in CHANNEL_GROUPS:
		if purpose in purposes:
			return f"{cb.ADM_CHANNELS}:group:{key}"
	return cb.ADM_CHANNELS


def channels_menu() -> InlineKeyboardMarkup:
	rows = [
		[btn(label, f"{cb.ADM_CHANNELS}:group:{key}")] for key, label, _purposes in CHANNEL_GROUPS
	]
	rows.append([btn("🔒 Majburiy obuna", f"{cb.ADM_CHANNELS}:list:required:1")])
	rows.append([btn("☁️ Cloud saqlash", f"{cb.ADM_CHANNELS}:list:storage:1")])
	rows.append([btn("📢 Ommaviy kanallar", f"{cb.ADM_CHANNELS}:list:public:1")])
	rows.append([btn("🧪 Hammasini tekshirish", f"{cb.ADM_CHANNELS}:testall")])
	rows.append([btn("🏠 Panel", cb.ADM_STATS)])
	return keyboard(*rows)


def channels_group(group_key: str) -> InlineKeyboardMarkup:
	"""One catalogue section: its ongoing/completed/VIP channel buckets."""
	rows = [
		[btn(purpose_short_label(purpose), f"{cb.ADM_CHANNELS}:list:{purpose}:1")]
		for purpose in group_purposes(group_key)
	]
	rows.append([btn("⬅️ Orqaga", cb.ADM_CHANNELS)])
	return keyboard(*rows)


def channel_purposes(prefix: str) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	for _key, label, purposes in CHANNEL_GROUPS:
		rows.append([btn(label, cb.NOOP)])
		for purpose in purposes:
			rows.append([btn(f"  {purpose_label(purpose)}", f"{prefix}:{purpose}")])
	rows.append([btn("🔒 Majburiy obuna", f"{prefix}:required")])
	rows.append([btn("☁️ Cloud saqlash", f"{prefix}:storage")])
	rows.append([btn("📢 Ommaviy kanal", f"{prefix}:public")])
	rows.append([btn("❌ Bekor qilish", cb.CANCEL)])
	return keyboard(*rows)


def channels_list(channels: Sequence[TelegramChannel], purpose: str, page: int, pages: int) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	for channel in channels:
		mark = "🟢" if channel.is_active else "🔴"
		rows.append(
			[btn(f"{mark} {channel.title}", f"{cb.ADM_CHANNELS}:view:{channel.pk}:{purpose}:{page}")]
		)
	rows.append(pagination_row(f"{cb.ADM_CHANNELS}:list:{purpose}:", page, pages))
	rows.append([btn("➕ Qo'shish", f"{cb.ADM_CHANNELS}:new:{purpose}")])
	rows.append([btn("⬅️ Orqaga", _channel_back_payload(purpose))])
	return keyboard(*rows)


def channel_actions(channel, *, purpose: str, page: int = 1) -> InlineKeyboardMarkup:
	state = "🔴 O'chirish" if channel.is_active else "🟢 Yoqish"
	return keyboard(
		[btn("🧪 Tekshirish", f"{cb.ADM_CHANNELS}:test:{channel.pk}")],
		[btn(state, f"{cb.ADM_CHANNELS}:tog:{channel.pk}:{purpose}:{page}")],
		[btn("✏️ Tahrirlash", f"{cb.ADM_CHANNELS}:edit:{channel.pk}:title")],
		[btn("📌 Asosiy e'lon kanali qilish", f"{cb.ADM_CHANNELS}:pub:{channel.pk}")],
		[btn("🗑 O'chirish", f"{cb.ADM_CHANNELS}:del:{channel.pk}:{purpose}:{page}")],
		[btn("⬅️ Orqaga", f"{cb.ADM_CHANNELS}:list:{purpose}:{page}")],
	)


def channel_edit_fields(channel, *, purpose: str, page: int = 1) -> InlineKeyboardMarkup:
	rows = [
		[btn(label, f"{cb.ADM_CHANNELS}:edit:{channel.pk}:{field}")]
		for field, label in CHANNEL_FIELD_LABELS.items()
	]
	rows.append([btn("⬅️ Orqaga", f"{cb.ADM_CHANNELS}:view:{channel.pk}:{purpose}:{page}")])
	return keyboard(*rows)


def broadcast_menu() -> InlineKeyboardMarkup:
	return keyboard(
		[btn("✍️ Matn", f"{cb.ADM_BROADCAST}:new:text")],
		[btn("🖼 Rasm", f"{cb.ADM_BROADCAST}:new:photo"), btn("🎬 Video", f"{cb.ADM_BROADCAST}:new:video")],
		[btn("📄 Fayl", f"{cb.ADM_BROADCAST}:new:document"), btn("📎 Forward", f"{cb.ADM_BROADCAST}:new:forward")],
		[btn("📃 Tarix", f"{cb.ADM_BROADCAST}:list:1")],
		[btn("🏠 Panel", cb.ADM_STATS)],
	)


def broadcast_preview(pk: int) -> InlineKeyboardMarkup:
	return keyboard(
		[btn("🚀 Yuborish", f"{cb.ADM_BROADCAST}:send:{pk}")],
		[btn("🔕 Sessiz rejim", f"{cb.ADM_BROADCAST}:silent:{pk}")],
		[btn("❌ Bekor qilish", f"{cb.ADM_BROADCAST}:drop:{pk}")],
	)


def broadcast_running(pk: int) -> InlineKeyboardMarkup:
	return keyboard(
		[btn("🛑 Bekor qilish", f"{cb.ADM_BROADCAST}:cancel:{pk}")],
		[btn("🏠 Panel", cb.ADM_STATS)],
	)


def broadcast_history(items: Sequence, page: int, pages: int) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	for item in items:
		label = f"#{item.pk} · {item.get_kind_display()} · {item.get_status_display()}"
		rows.append([btn(label, f"{cb.ADM_BROADCAST}:view:{item.pk}")])
	rows.append(pagination_row(f"{cb.ADM_BROADCAST}:list:", page, pages))
	rows.append([btn("⬅️ Orqaga", cb.ADM_BROADCAST)])
	return keyboard(*rows)


def broadcast_actions(item) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	if item.status in (item.Status.PAUSED, item.Status.CANCELLED, item.Status.FAILED):
		rows.append([btn("▶️ Davom ettirish", f"{cb.ADM_BROADCAST}:resume:{item.pk}")])
	if item.status == item.Status.RUNNING:
		rows.append([btn("🛑 Bekor qilish", f"{cb.ADM_BROADCAST}:cancel:{item.pk}")])
	rows.append([btn("📃 Tarix", f"{cb.ADM_BROADCAST}:list:1")])
	return keyboard(*rows)


def users_menu() -> InlineKeyboardMarkup:
	return keyboard(
		[btn("🔍 Qidirish", f"{cb.ADM_USERS}:search")],
		[btn("🏠 Panel", cb.ADM_STATS)],
	)


def user_results(items) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	for profile in items:
		name = profile.username and f"@{profile.username}" or profile.first_name or str(profile.telegram_id)
		mark = "🚫" if profile.is_blocked else "🟢"
		rows.append([btn(f"{mark} {name}", f"{cb.ADM_USERS}:view:{profile.telegram_id}")])
	rows.append([btn("⬅️ Orqaga", cb.ADM_USERS)])
	return keyboard(*rows)


def user_actions(profile) -> InlineKeyboardMarkup:
	state = "✅ Blokdan chiqarish" if profile.is_blocked else "🚫 Bloklash"
	return keyboard(
		[btn(f"{state}", f"{cb.ADM_USERS}:block:{profile.telegram_id}")],
		[btn("💎 Tarifni o'zgartirish", f"{cb.ADM_USERS}:plan:{profile.telegram_id}")],
		[btn("⬅️ Orqaga", cb.ADM_USERS)],
	)


def plan_picker(telegram_id: int) -> InlineKeyboardMarkup:
	from users.plans import ALL_PLANS, PLAN_LABELS

	rows = [
		[btn(PLAN_LABELS[plan_id], f"{cb.ADM_USERS}:setplan:{telegram_id}:{plan_id}")]
		for plan_id in ALL_PLANS
	]
	rows.append([btn("⬅️ Orqaga", f"{cb.ADM_USERS}:view:{telegram_id}")])
	return keyboard(*rows)


def settings_menu(settings) -> InlineKeyboardMarkup:
	def toggle(field: str) -> str:
		return f"{cb.ADM_SETTINGS}:tog:{field}"

	def state(value: bool) -> str:
		return "✅" if value else "❌"

	return keyboard(
		[btn(f"{state(settings.require_subscription)} Majburiy obuna", toggle("require_subscription"))],
		[btn(f"{state(settings.auto_publish_new_content)} Avtomatik e'lon", toggle("auto_publish_new_content"))],
		[btn(f"{state(settings.protect_content)} Kontent himoyasi", toggle("protect_content"))],
		[btn(f"{state(settings.maintenance_mode)} Texnik rejim", toggle("maintenance_mode"))],
		[btn("📣 Broadcast tezligi", f"{cb.ADM_SETTINGS}:rate")],
		[btn("⚡ Parallel yuborish", f"{cb.ADM_SETTINGS}:conc")],
		[btn("📡 Asosiy e'lon kanali", f"{cb.ADM_SETTINGS}:chan:publish_channel")],
		[btn("📡 Kanallar bo'limi", cb.ADM_CHANNELS)],
		[btn("📝 Salomlashuv matni", f"{cb.ADM_SETTINGS}:welcome"), btn("🚫 Taqiq matni", f"{cb.ADM_SETTINGS}:denied")],
		[btn("🏠 Panel", cb.ADM_STATS)],
	)


def settings_channel_picker(
	channels: Sequence[TelegramChannel], field: str = "publish_channel"
) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = [
		[btn(f"📢 {channel.title}", f"{cb.ADM_SETTINGS}:setchan:{field}:{channel.pk}")]
		for channel in channels
	]
	rows.append([btn("🚫 Kanalsiz", f"{cb.ADM_SETTINGS}:setchan:{field}:0")])
	rows.append([btn("⬅️ Orqaga", cb.ADM_SETTINGS)])
	return keyboard(*rows)


def logs_menu() -> InlineKeyboardMarkup:
	return keyboard(
		[btn("📜 Barcha jurnallar", f"{cb.ADM_LOGS}:all"), btn("⚠️ Xatolar", f"{cb.ADM_LOGS}:errors")],
		[btn("📊 Hisobotlar", f"{cb.ADM_LOGS}:reports")],
		[btn("🧹 Eski yozuvlarni tozalash", f"{cb.ADM_LOGS}:purge")],
		[btn("🏠 Panel", cb.ADM_STATS)],
	)


def coupons_menu() -> InlineKeyboardMarkup:
	return keyboard(
		[btn("➕ Yangi kupon", f"{cb.ADM_COUPONS}:new")],
		[btn("📃 Ro'yxat", f"{cb.ADM_COUPONS}:list:1")],
		[btn("🏠 Panel", cb.ADM_STATS)],
	)


def coupons_list(items: Sequence, page: int, pages: int) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	for item in items:
		mark = "⌛️" if item.is_expired else "✅"
		label = f"{mark} {item.code} · {item.days} kun · {item.used_count}/{item.max_uses}"
		rows.append([btn(label, f"{cb.ADM_COUPONS}:view:{item.pk}")])
	rows.append(pagination_row(f"{cb.ADM_COUPONS}:list:", page, pages))
	rows.append([btn("⬅️ Orqaga", cb.ADM_COUPONS)])
	return keyboard(*rows)


def coupon_actions(coupon, *, page: int = 1) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = [
		[btn("📢 Kanalga joylash", f"{cb.ADM_COUPONS}:pub:{coupon.pk}")],
	]
	toggle_label = "⏸ To'xtatish" if coupon.is_active else "▶️ Faollashtirish"
	rows.append([btn(toggle_label, f"{cb.ADM_COUPONS}:tog:{coupon.pk}")])
	rows.append([btn("🗑 O'chirish", f"{cb.ADM_COUPONS}:del:{coupon.pk}")])
	rows.append([btn("⬅️ Ro'yxat", f"{cb.ADM_COUPONS}:list:{page}")])
	return keyboard(*rows)


def coupon_confirm_delete(coupon, *, page: int = 1) -> InlineKeyboardMarkup:
	return confirm_keyboard(
		f"{cb.ADM_COUPONS}:yes:{coupon.pk}:{page}",
		f"{cb.ADM_COUPONS}:view:{coupon.pk}",
	)


def giveaways_menu() -> InlineKeyboardMarkup:
	return keyboard(
		[btn("➕ Yangi sovg'a", f"{cb.ADM_GIVEAWAY}:new")],
		[btn("📃 Ro'yxat", f"{cb.ADM_GIVEAWAY}:list:1")],
		[btn("🏠 Panel", cb.ADM_STATS)],
	)


def giveaways_list(items: Sequence, page: int, pages: int) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = []
	for item in items:
		mark = {"open": "🟢", "drawn": "🏆", "closed": "🔒", "draft": "📝"}.get(
			item.status, "🎁"
		)
		label = f"{mark} {item.title} · {item.reward_days} kun"
		rows.append([btn(label, f"{cb.ADM_GIVEAWAY}:view:{item.pk}")])
	rows.append(pagination_row(f"{cb.ADM_GIVEAWAY}:list:", page, pages))
	rows.append([btn("⬅️ Orqaga", cb.ADM_GIVEAWAY)])
	return keyboard(*rows)


def giveaway_actions(giveaway, *, page: int = 1) -> InlineKeyboardMarkup:
	rows: List[List[InlineKeyboardButton]] = [
		[btn("📢 Kanalga joylash", f"{cb.ADM_GIVEAWAY}:pub:{giveaway.pk}")],
	]
	if giveaway.status in (Giveaway.Status.OPEN, Giveaway.Status.DRAFT):
		rows.append([btn("🎲 O'tkazish (g'olib aniqlash)", f"{cb.ADM_GIVEAWAY}:draw:{giveaway.pk}")])
	if giveaway.status == Giveaway.Status.OPEN:
		rows.append([btn("🔒 Yopish", f"{cb.ADM_GIVEAWAY}:close:{giveaway.pk}")])
	elif giveaway.status == Giveaway.Status.CLOSED:
		rows.append([btn("▶️ Qayta ochish", f"{cb.ADM_GIVEAWAY}:open:{giveaway.pk}")])
	rows.append([btn("🗑 O'chirish", f"{cb.ADM_GIVEAWAY}:del:{giveaway.pk}")])
	rows.append([btn("⬅️ Ro'yxat", f"{cb.ADM_GIVEAWAY}:list:{page}")])
	return keyboard(*rows)


def giveaway_confirm_draw(giveaway, *, page: int = 1) -> InlineKeyboardMarkup:
	return confirm_keyboard(
		f"{cb.ADM_GIVEAWAY}:yes:{giveaway.pk}:{page}",
		f"{cb.ADM_GIVEAWAY}:view:{giveaway.pk}",
	)


def giveaway_confirm_delete(giveaway, *, page: int = 1) -> InlineKeyboardMarkup:
	return confirm_keyboard(
		f"{cb.ADM_GIVEAWAY}:dyes:{giveaway.pk}:{page}",
		f"{cb.ADM_GIVEAWAY}:view:{giveaway.pk}",
	)


def giveaway_flags_keyboard(*, require_channels: bool, require_bio_ref: bool) -> InlineKeyboardMarkup:
	"""Wizard step: toggle the live-verified conditions, then create."""
	ch_mark = "✅" if require_channels else "☐️"
	bio_mark = "✅" if require_bio_ref else "☐️"
	return keyboard(
		[btn(f"{ch_mark} Homiy kanallarga obuna", f"{cb.ADM_GIVEAWAY}:fch")],
		[btn(f"{bio_mark} Bio'da referral havolasi", f"{cb.ADM_GIVEAWAY}:fbio")],
		[btn("✅ Yaratish", f"{cb.ADM_GIVEAWAY}:create")],
		[btn("⬅️ Orqaga", f"{cb.ADM_GIVEAWAY}:cancel")],
	)


def confirm(yes_callback: str, no_callback: str) -> InlineKeyboardMarkup:
	return confirm_keyboard(yes_callback, no_callback)
