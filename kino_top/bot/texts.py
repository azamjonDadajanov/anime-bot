"""Uzbek-language message templates.

Keeping every string here makes the bot translatable and keeps handlers focused
on logic rather than copy.
"""

from __future__ import annotations

BRAND = "🎬 <b>Kino Top</b>"

WELCOME_NEW = (
	"{brand}\n\n"
	"Assalomu alaykum, <b>{name}</b>! 👋\n"
	"Anime, serial va kinolarni qulay ko'rinishda tomosha qiling.\n\n"
	"Kod bilan qidirish uchun shunchaki 4 xonali kodni yuboring.\n"
	"Masalan: <code>1234</code>"
)

WELCOME_BACK = "{brand}\n\nXush kelibsiz, <b>{name}</b>! 🎉\nQuyidagi bo'limlardan birini tanlang."

MAIN_MENU = "{brand}\n\nKerakli bo'limni tanlang:"

HELP_TEXT = (
	"{brand}\n\n"
	"<b>Yordam</b>\n\n"
	"🔍 <b>Qidirish</b> — nomi, kodi yoki janri bo'yicha qidirish.\n"
	"📚 <b>Katalog</b> — anime, serial, manga va kinolar ro'yxati.\n"
	"⭐ <b>Sevimlilar</b> — saqlangan kontentlar.\n"
	"👤 <b>Profil</b> — hisobingiz va obuna tarifi.\n\n"
	"Kontent kodini bilgan bo'lsangiz, kodni to'g'ridan-to'g'ri yuboring."
)

SEARCH_PROMPT = (
	"🔍 <b>Qidiruv</b>\n\n"
	"Anime nomini, 4 xonali kodini yoki janr nomini yuboring."
)

SEARCH_EMPTY_QUERY = "❌ Iltimos, matn yoki kod yuboring."
SEARCH_NOTHING_FOUND = "😔 <b>{query}</b> bo'yicha hech narsa topilmadi."
SEARCH_RESULTS = "🔍 <b>{query}</b> uchun natijalar:"

CATALOG_TITLE = "📚 <b>Katalog</b>\n\nKategoriyani tanlang:"
GENRE_LIST = "🎭 <b>Janrlar</b>\n\nJanrni tanlang:"
CATALOG_EMPTY = "📭 Hozircha bu bo'limda kontent yo'q."
CATALOG_PAGE = "📚 <b>{label}</b> — {page}/{pages} bet"

TITLE_CARD = (
	"🎬 <b>{title}</b>\n"
	"🆔 Kod: <code>{code}</code>\n"
	"📺 Turi: {type}\n"
	"🎭 Janr: {genres}\n"
	"🌐 Til: {language}\n"
	"💎 Sifat: {quality}\n"
	"🔒 Tarif: {plan}\n"
	"⭐ Reyting: {rating}/10\n"
	"📅 Yil: {year}\n"
	"📊 Holat: {status}\n"
	"🎞 Qismlar: {parts}\n\n"
	"📝 {synopsis}"
)

PARTS_LIST = "🎞 <b>{title}</b>\n\nQismni tanlang:"
PARTS_EMPTY = "📭 Bu kontent uchun hali qismlar qo'shilmagan."

PART_CARD = (
	"🎬 <b>{title}</b>\n"
	"📺 {season} mavsum · {number}-qism\n"
	"💎 Sifatlar: {qualities}\n\n"
	"Ko'rish uchun quyidagi tugmani bosing."
)

# Attached below a delivered part whose files are images only: a media group
# cannot carry a keyboard, so the navigator goes out as its own message.
WATCH_PARTS_HINT = "🎞 Qismni tanlang:"

MANGA_ON_SITE = (
	"📖 <b>{title}</b>\n\n"
	"Manga saytda o'qiladi. Quyidagi tugma orqali davom eting."
)

MEDIA_SENDING = "⏳ Media yuborilmoqda, biroz kuting..."
MEDIA_UNAVAILABLE = "😔 Kechirasiz, bu media hozircha mavjud emas.\nAdministrator fayl almashayotgan bo'lishi mumkin."
MEDIA_BLOCKED = "❌ Bu kontentni yuborishning imkoni bo'lmadi. Keyinroq qayta urinib ko'ring."

SUBSCRIPTION_REQUIRED = (
	"🔒 <b>Majburiy obuna</b>\n\n"
	"Kontentni olish uchun quyidagi kanallarga obuna bo'ling:\n{channels}\n\n"
	"Obuna bo'lgach, <b>✅ Tekshirish</b> tugmasini bosing."
)
SUBSCRIPTION_OK = "✅ Obuna tasdiqlandi!"
SUBSCRIPTION_STILL_MISSING = "❌ Siz hali quyidagi kanallarga obuna bo'lmagansiz:\n{channels}"

PREMIUM_REQUIRED = (
	"💎 <b>Premium tarif kerak</b>\n\n"
	"Bu kontent <b>{plan}</b> tarifiga mo'ljallangan.\n"
	"Hisobingiz tarifi: <b>{current}</b>.\n\n"
	"Tarifni oshirish uchun administrator bilan bog'laning."
)

FAVORITES_TITLE = "⭐ <b>Sevimlilar</b> — {page}/{pages}"
FAVORITES_EMPTY = "⭐ Hozircha sevimlilar bo'sh.\nKontent sahifasidagi ⭐ tugmasini bosib qo'shing."
FAVORITE_ADDED = "⭐️ Sevimlilarga qo'shildi."
FAVORITE_REMOVED = "💔 Sevimlilardan olib tashlandi."

PROFILE = (
	"👤 <b>Profil</b>\n\n"
	"🆔 Telegram ID: <code>{telegram_id}</code>\n"
	"👤 Ism: {name}\n"
	"🔗 Username: {username}\n"
	"💎 Tarif: <b>{plan}</b>\n"
	"⭐ Sevimlilar: {favorites}\n"
	"📅 Ro'yxatdan o'tgan: {created}"
)

# ``/start <username>`` — the payload sent by the website profile page.
ACCOUNT_LINKED = (
	"✅ Telegram akkaunt endi <b>{username}</b> sayt hisobiga ulandi.\n"
	"💎 Tarif va ⭐ sevimlilar sayt bilan endi birga."
)
ACCOUNT_ALREADY_LINKED = "ℹ️ Bu Telegram akkaunt allaqachon <b>{username}</b> hisobiga ulangan."
ACCOUNT_USERNAME_TAKEN = "⚠️ <code>{username}</code> hisobi boshqa Telegram akkauntga ulangan."
ACCOUNT_LINK_CONFLICT = (
	"⚠️ Bu Telegram akkaunt boshqa sayt hisobiga ulangan.\n"
	"Uni uzish uchun administratorga murojaat qiling."
)
ACCOUNT_USERNAME_INACTIVE = "⚠️ <code>{username}</code> hisobi faol emas."

ACCESS_DENIED_GENERIC = "🚫 Bu amalni bajarishga ruxsatingiz yo'q."
ADMIN_ONLY = "🚫 Bu bo'lim faqat administratorlar uchun."
BOT_BLOCKED = "🚫 Sizning hisobingiz bloklangan. Administrator bilan bog'laning."
MAINTENANCE = "🛠 Texnik ishlar davom etmoqda. Iltimos, keyinroq urinib ko'ring."
CANCELLED = "❌ Amal bekor qilindi."
OPERATION_FAILED = "⚠️ Xatolik yuz berdi. Keyinroq qayta urinib ko'ring."
NOT_FOUND = "🔍 Ma'lumot topilmadi."
EDIT_PROMPT = "✏️ Yangi qiymatni yuboring.\n\n{cancel_hint}"

# --- admin ------------------------------------------------------------------
ADMIN_PANEL = (
	"📊 <b>Statistika</b>\n"
	"🛠 <b>Administrator paneli</b>\n\n"
	"👥 Foydalanuvchilar: <b>{users}</b>\n"
	"🟢 Faol (30 kun): <b>{active}</b>\n"
	"🎬 Kontent: <b>{media}</b>\n"
	"🎞 Qismlar: <b>{episodes}</b>\n"
	"📡 Kanallar: <b>{channels}</b>\n"
	"⭐ Sevimlilar: <b>{favorites}</b>\n\n"
	"Kerakli bo'limni tanlang."
)

ADMIN_MEDIA_MENU = "🎬 <b>Kontent boshqaruvi</b>\n\nNima qilamiz?"
ADMIN_MEDIA_LIST = "🎬 <b>Kontentlar</b> — {page}/{pages}"
ADMIN_MEDIA_EMPTY = "📭 Kontent yo'q. Yangi kontent qo'shing."
ADMIN_MEDIA_CREATE_TYPE = "🎬 <b>Yangi kontent</b>\n\nKontent turini tanlang:"
ADMIN_MEDIA_ASK_TITLE = "📝 Kontent nomini yuboring:"
ADMIN_MEDIA_ASK_SYNOPSIS = "📝 Qisqa tavsifni yuboring (yoki <code>-</code> yuborib o'tkazib yuboring):"
ADMIN_MEDIA_ASK_COVER = "🖼 Muqova rasmini yuboring (yoki <code>-</code> yuborib o'tkazib yuboring):"
ADMIN_MEDIA_ASK_GENRES = (
	"🎭 Janrlarni tanlang.\n\n"
	"Ro'yxatdan tanlang yoki yangi janr nomini vergul bilan yuboring.\n"
	"Tayyor bo'lgach <b>✅ Saqlash</b> ni bosing."
)
ADMIN_MEDIA_ASK_LANGUAGE = "🌐 Tilni yuboring yoki pastdagilardan tanlang:"
ADMIN_MEDIA_ASK_QUALITY = (
	"💎 Sifatlarni vergul bilan yuboring (masalan: <code>480,720,1080</code>):"
)
ADMIN_MEDIA_ASK_PLAN = "🔒 Kontent qaysi tarif uchun ochiq bo'lsin?"
ADMIN_MEDIA_ASK_STATUS = "📊 Kontent holatini tanlang:"
ADMIN_MEDIA_ASK_RATING = "⭐ Reytingni 1 dan 10 gacha yuboring:"
ADMIN_MEDIA_PREVIEW = (
	"🧾 <b>Tekshirib ko'ring</b>\n\n"
	"📌 Nomi: <b>{title}</b>\n"
	"📺 Turi: {type}\n"
	"🎭 Janr: {genres}\n"
	"🌐 Til: {language}\n"
	"💎 Sifat: {quality}\n"
	"🔒 Tarif: {plan}\n"
	"📊 Holat: {status}\n"
	"⭐ Reyting: {rating}/10\n"
	"🖼 Muqova: {cover}\n"
	"📝 {synopsis}\n\n"
	"Saqlashni tasdiqlaysizmi?"
)
ADMIN_MEDIA_SAVED = (
	"✅ Kontent saqlandi!\n\n"
	"📌 <b>{title}</b>\n"
	"🆔 Kod: <code>{code}</code>\n"
	"🎬 Slug: <code>{slug}</code>\n\n"
	"Endi qismlar qo'shishingiz mumkin."
)
ADMIN_MEDIA_DELETE_CONFIRM = (
	"🗑 <b>{title}</b> ni o'chirmoqchimisiz?\n\n"
	"Diqqat: qismlar va Telegram fayl havolalari ham o'chadi."
)
ADMIN_MEDIA_DELETED = "🗑 Kontent o'chirildi."
ADMIN_MEDIA_SEARCH = "🔍 Nomi yoki kodini yuboring:"
ADMIN_INVALID_INPUT = "❌ Noto'g'ri qiymat. Qayta yuboring."

ADMIN_EPISODES_MENU = "🎞 <b>Qismlar boshqaruvi</b>"
ADMIN_EPISODE_SELECT_TITLE = "🎬 Qaysi kontentga qism qo'shamiz?"
ADMIN_EPISODE_ASK_SEASON = "📺 Mavsum raqamini yuboring (mavsumsiz bo'lsa <code>-</code>):"
ADMIN_EPISODE_ASK_NUMBER = "🔢 Qism raqamini yuboring:"
ADMIN_EPISODE_ASK_TITLE = "📝 Qism nomini yuboring (ixtiyoriy, <code>-</code> bilan o'tkazish):"
ADMIN_EPISODE_SELECT_CHANNEL = "📡 Cloud (saqlash) kanalini tanlang:"
ADMIN_EPISODE_NO_CHANNELS = "⚠️ Cloud kanal yo'q. Avval «Kanallar» bo'limida qo'shing."
ADMIN_EPISODE_ASK_MEDIA = (
	"📤 Endi mediani yuboring yoki kanaldan forward qiling.\n\n"
	"Video, rasm yoki fayl qabul qilinadi.\n"
	"Bir nechta faylni ketma-ket yuborishingiz mumkin."
)
ADMIN_EPISODE_MEDIA_ADDED = "✅ Fayl qo'shildi ({count} ta). Yana yuboring yoki <b>💾 Saqlash</b> ni bosing."
ADMIN_EPISODE_PREVIEW = (
	"🧾 <b>Qismni tekshirish</b>\n\n"
	"🎬 Kontent: <b>{title}</b>\n"
	"📺 Mavsum: {season}\n"
	"🔢 Qism: {number}\n"
	"📝 Nomi: {part_title}\n"
	"📡 Kanal: {channel}\n"
	"📦 Fayllar: {files}\n\n"
	"Saqlashni tasdiqlaysizmi?"
)
ADMIN_EPISODE_SAVED = "✅ Qism saqlandi: {season} mavsum · {number}-qism ({files} ta fayl)."
ADMIN_EPISODE_LIST = "🎞 <b>{title}</b> qismlari — {page}/{pages}"
ADMIN_EPISODE_DELETE_CONFIRM = "🗑 {season} mavsum {number}-qismni o'chirmoqchimisiz?"
ADMIN_EPISODE_DELETED = "🗑 Qism o'chirildi."
ADMIN_EPISODE_REPLACE_PROMPT = "🔄 Qism uchun yangi mediani yuboring (yoki forward qiling):"
ADMIN_EPISODE_REPLACED = "✅ Fayllar almashtirildi ({count} ta)."

ADMIN_CHANNELS_MENU = "📡 <b>Kanallar boshqaruvi</b>\n\nQaysi turdagi kanallar?"
ADMIN_CHANNEL_LIST = "📡 <b>{label}</b> — {page}/{pages}"
ADMIN_CHANNEL_EMPTY = "📭 Bu turdagi kanallar yo'q."
ADMIN_CHANNEL_ASK_PURPOSE = "📡 Kanal turini tanlang:"
ADMIN_CHANNEL_ASK_CHAT = (
	"📡 Kanalning <b>ID</b>, <b>@username</b> yoki <b>t.me</b> havolasini yuboring.\n\n"
	"Masalan: <code>-1001234567890</code> yoki <code>@mening_kanalim</code>"
)
ADMIN_CHANNEL_ASK_TITLE = "📝 Kanal nomini yuboring:"
ADMIN_CHANNEL_ASK_USERNAME = "🔗 Kanal username'ini yuboring (ixtiyoriy, <code>-</code>):"
ADMIN_CHANNEL_PREVIEW = (
	"🧾 <b>Kanalni tekshirish</b>\n\n"
	"📛 Nomi: <b>{title}</b>\n"
	"🆔 Chat ID: <code>{chat_id}</code>\n"
	"🔗 Username: {username}\n"
	"📡 Turi: {purpose}\n\n"
	"Saqlashni tasdiqlaysizmi?"
)
ADMIN_CHANNEL_SAVED = "✅ Kanal saqlandi: <b>{title}</b>"
ADMIN_CHANNEL_DELETE_CONFIRM = (
	"🗑 <b>{title}</b> kanalini o'chirmoqchimisiz?\n\n"
	"Diqqat: media havolalari kanal bilan bog'langan bo'lishi mumkin."
)
ADMIN_CHANNEL_DELETED = "🗑 Kanal o'chirildi."
ADMIN_CHANNEL_TOGGLED = "✅ Kanal holati: <b>{state}</b>"
ADMIN_CHANNEL_TESTING = "⏳ Kanal tekshirilmoqda..."
ADMIN_CHANNEL_TEST_RESULT = (
	"🧪 <b>{title}</b>\n\n"
	"Holat: {status}\n"
	"Tur: {chat_type}\n"
	"Post yuborish: {can_post}\n"
	"Membership tekshirish: {can_check}\n"
	"Xabar: {message}"
)
ADMIN_CHANNEL_UNREACHABLE = "❌ Kanalga ulanib bo'lmadi. Bot kanalda administrator ekanligiga ishonch hosil qiling."
ADMIN_CHANNEL_PUBLISH_SET = "✅ Yuborish kanali etib belgilandi: <b>{title}</b>"

ADMIN_BROADCAST_MENU = "📣 <b>Broadcast</b>\n\nNima yuboramiz?"
ADMIN_BROADCAST_COMPOSE = "✍️ Yuboriladigan matnni kiriting:"
ADMIN_BROADCAST_COMPOSE_MEDIA = "🖼 Media bilan birga caption yuboring (ixtiyoriy, <code>-</code>):"
ADMIN_BROADCAST_FORWARD = "📎 Kanaldan xabar forward qiling:"
ADMIN_BROADCAST_PREVIEW = (
	"🧾 <b>Broadcast tekshiruvi</b>\n\n"
	"📦 Turi: {kind}\n"
	"👥 Qabul qiluvchilar: <b>{recipients}</b>\n"
	"🔕 Sessiz: {silent}\n\n"
	"Yuborishni boshlaymizmi?"
)
ADMIN_BROADCAST_STARTED = "🚀 Broadcast boshlandi. Jarayon shu xabarda ko'rinadi."
ADMIN_BROADCAST_PROGRESS = (
	"📣 <b>Broadcast #{pk}</b>\n\n"
	"📊 Holat: <b>{status}</b>\n"
	"👥 Jami: {total}\n"
	"✅ Yuborildi: {sent}\n"
	"⚠️ Xato: {failed}\n"
	"🚫 Bloklagan: {blocked}\n"
	"📈 Jarayon: {processed}/{total} ({percent})"
)
ADMIN_BROADCAST_DONE = (
	"🏁 <b>Broadcast yakunlandi</b>\n\n"
	"✅ Yuborildi: {sent}\n"
	"⚠️ Xato: {failed}\n"
	"🚫 Bloklagan: {blocked}\n"
	"⏱ Davomiylik: {duration}"
)
ADMIN_BROADCAST_CANCELLED = "🛑 Broadcast bekor qilindi."
ADMIN_BROADCAST_CANCEL_REQUESTED = "🛑 Bekor qilish so'raldi, joriy yuborishlar tugagach to'xtaydi."
ADMIN_BROADCAST_EMPTY = "📭 Yuboriladigan foydalanuvchilar yo'q."
ADMIN_BROADCAST_ALREADY_RUNNING = "⚠️ Sizda davom etayotgan broadcast bor."
ADMIN_BROADCAST_RESUMED = "▶️ Broadcast davom ettirilmoqda."

ADMIN_USERS_MENU = "👥 <b>Foydalanuvchilar</b>\n\nID yoki username yuboring:"
ADMIN_USER_CARD = (
	"👤 <b>{name}</b>\n\n"
	"🆔 Telegram ID: <code>{telegram_id}</code>\n"
	"🔗 Username: {username}\n"
	"💎 Tarif: <b>{plan}</b>\n"
	"🚫 Bloklangan: <b>{blocked}</b>\n"
	"⭐ Sevimlilar: {favorites}\n"
	"📅 Ro'yxat: {created}\n"
	"🕒 Oxirgi faollik: {last_seen}"
)
ADMIN_USER_BLOCKED = "🚫 Foydalanuvchi bloklandi."
ADMIN_USER_UNBLOCKED = "✅ Foydalanuvchi blokdan chiqarildi."
ADMIN_USER_PLAN_UPDATED = "✅ Tarif yangilandi: <b>{plan}</b>"
ADMIN_USERS_EMPTY = "🔍 Foydalanuvchi topilmadi."

ADMIN_SETTINGS_MENU = (
	"⚙️ <b>Sozlamalar</b>\n\n"
	"🔒 Majburiy obuna: <b>{require_subscription}</b>\n"
	"🚀 Avtomatik e'lon: <b>{auto_publish}</b>\n"
	"📡 E'lon kanali: <b>{publish_channel}</b>\n"
	"🛡 Kontent himoyasi: <b>{protect_content}</b>\n"
	"🛠 Texnik rejim: <b>{maintenance}</b>\n"
	"📣 Broadcast tezligi: <b>{rate}/s</b>\n"
	"⚡ Parallel yuborish: <b>{concurrency}</b>"
)
ADMIN_SETTINGS_UPDATED = "✅ Sozlama yangilandi."
ADMIN_SETTINGS_ASK_VALUE = "✏️ Yangi qiymatni yuboring:"
ADMIN_SETTINGS_SELECT_CHANNEL = "📡 E'lon kanalini tanlang:"

ADMIN_LOGS_MENU = "📜 <b>Jurnallar va hisobotlar</b>"
ADMIN_LOGS_EMPTY = "📭 Jurnal yozuvlari yo'q."
ADMIN_LOGS_ENTRY = "• <code>{time}</code> [{level}] {message}"
ADMIN_REPORTS = (
	"📊 <b>Hisobotlar</b>\n\n"
	"📣 Broadcastlar: <b>{broadcasts}</b>\n"
	"✅ Yuborilgan xabarlar: <b>{sent}</b>\n"
	"🚫 Bloklaganlar: <b>{blocked}</b>\n"
	"⚠️ Xatolar: <b>{failed}</b>\n"
	"📜 Jurnal yozuvlari: <b>{logs}</b>"
)

CONFIRM_YES = "✅ Ha, tasdiqlayman"
CONFIRM_NO = "↩️ Bekor qilish"

# --- subscription payment requests -------------------------------------------
SUBREQ_CARD_HINT = (
    """
<b>Obuna to'lovi</b>

Tarif: <b>{plan}</b>
Narx: <b>{price}</b>
Karta raqami: <code>{card}</code>

Yo'riqnoma:
1. Karta raqamiga {price} miqdorda pul tashlang.
2. To'lov screenshotini oling.
3. Screenshotni shu yerga yuboring.

Arizangiz administratorga yuboriladi va tasdiqlanishini kuting.
"""
)

SUBREQ_AWAITING_SCREENSHOT = "Screenshot yuboring (rasm sifatida)."

SUBREQ_SAVED = "Screenshot qabul qilindi. Arizangiz administratorga yuborildi. Tasdiqlanishini kuting."

SUBREQ_PENDING_NOTICE = "Sizda allaqachon ko'rib chiqilayotgan ariza bor. Iltimos, kuting."

SUBREQ_ALREADY_PLAN = "Bu tarif allaqachon sizniki."

SUBREQ_APPROVED = "✅ <b>Obuna tasdiqlandi!</b>\n\nTarif: <b>{plan}</b>\nEndi barcha imkoniyatlardan foydalanishingiz mumkin."

SUBREQ_REJECTED = "❌ <b>Obuna bekor qilindi.</b>\n\nTarif: <b>{plan}</b>\nSabab: to'lov tasdiqlanmadi."

SUBREQ_NOT_FOUND = "Ariza topilmadi."

SUBREQ_ALREADY_PROCESSED = "Bu ariza allaqachon ko'rib chiqilgan."

ADMIN_SUBREQ_APPROVED = "✅ Ariza tasdiqlandi.\n\n{details}"

ADMIN_SUBREQ_REJECTED = "❌ Ariza rad etildi.\n\n{details}"
