"""Uzbek-language message templates.

Keeping every string here makes the bot translatable and keeps handlers focused
on logic rather than copy.
"""

from __future__ import annotations

BRAND = "🎬 <b>AniChopar</b>"

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
	"🤖 <b>AI yordamchi</b> — AniVoy: savollarga javob beradi va kontent topadi "
	"(faol obunachilar uchun).\n"
	"📚 <b>Katalog</b> — anime, serial, manga va kinolar ro'yxati.\n"
	"⭐ <b>Sevimlilar</b> — saqlangan kontentlar.\n"
	"👤 <b>Profil</b> — hisobingiz va obuna tarifi.\n\n"
	"Kontent kodini bilgan bo'lsangiz, kodni to'g'ridan-to'g'ri yuboring."
)

SEARCH_PROMPT = (
	"🔍 <b>Qidiruv</b>\n\n"
	"Nomini, 4 xonali kodini yoki janr nomini yuboring.\n\n"
	"Turi yoki janri bo'yicha filtrlash uchun quyidagi tugmalardan foydalaning."
)

SEARCH_EMPTY_QUERY = "❌ Iltimos, matn yoki kod yuboring."
SEARCH_NOTHING_FOUND = "😔 <b>{query}</b> bo'yicha hech narsa topilmadi."
SEARCH_RESULTS = "🔍 <b>{query}</b> uchun natijalar:"
SEARCH_TYPE_TITLE = "🎬 <b>{label}</b> — {page}/{pages}"
SEARCH_GENRE_TITLE = "🎭 <b>{genre}</b> janri — {page}/{pages}"
SEARCH_ALL_TITLE = "📚 <b>Barcha kontent</b> — {page}/{pages}"
SEARCH_GENRE_LIST = "🎭 <b>Janr bo'yicha qidiruv</b>\n\nJanrni tanlang:"
SEARCH_EMPTY_RESULTS = "📭 Hozircha bu bo'limda kontent yo'q."

# --- AI yordamchi (AniVoy, subscribers only) ---------------------------------
AI_ASSISTANT_PROMPT = (
	"🤖 <b>AniVoy — AI yordamchi</b>\n\n"
	"Savolingizni yoki qidirayotgan kontentingizni o'z so'zingiz bilan yozing:\n"
	"<i>menga sarguzasht va qo'rqinchli animelar ayt</i>\n"
	"<i>Naruto nechta qismdan iborat?</i>\n"
	"<i>sevimlilarimga o'xshash nima bor?</i>\n\n"
	"Yordamchi katalogdan o'zi qidirib, kerakli ma'lumotni oladi va o'zbekcha "
	"javob beradi.\n"
	"«🎯 Sevimlilar» tugmasini yoqsangiz, sevimlilaringiz va oxirgi "
	"ko'rganlaringiz ham hisobga olinadi.\n"
	"Bekor qilish uchun «⬅️ Asosiy menyu» tugmasini bosing."
)
AI_ASSISTANT_PERSONAL_ON = (
	"✅ Endi sevimlilaringiz va oxirgi ko'rganlaringiz yordamchiga beriladi."
)
AI_ASSISTANT_PERSONAL_OFF = "❌ Sevimlilar yordamchiga berilmaydi."
AI_ASSISTANT_THINKING = (
	"🤔 <b>AniVoy o'ylayapti…</b>\n\n"
	"So'rovingizni tahlil qilib, kerakli ma'lumotni katalogdan qidiryapti."
)
AI_ASSISTANT_RESULTS = "🤖 <b>{query}</b> bo'yicha AniVoy javobi:"
AI_ASSISTANT_EMPTY = (
	"😔 <b>{query}</b> bo'yicha mos kontent topilmadi.\n"
	"So'rovni boshqacha yozib ko'ring (masalan, janr va kayfiyatni qo'shib)."
)
AI_ASSISTANT_REQUIRED = (
	"🔒 <b>AI yordamchi faqat obunachilar uchun</b>\n\n"
	"Yordamchi online AI modelida ishlaydi, shuning uchun faol obuna kerak.\n"
	"«🎫 Obuna» bo'limidan tarifni tanlang."
)
AI_ASSISTANT_UNAVAILABLE = (
	"🛠 AI yordamchi hozircha javob bera olmaydi: model sozlanmagan yoki "
	"barcha provayderlar limitda.\n"
	"Keyinroq qayta urinib ko'ring yoki oddiy qidiruvdan foydalaning."
)
AI_ASSISTANT_ERROR = "⚠️ AI yordamchida xatolik yuz berdi. Keyinroq qayta urinib ko'ring."

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

# Sent instead of a chapter that exists only as a PDF: Telegram documents are
# downloadable, so the bot links to the website reader (server-rendered pages)
# and never attaches the file itself.
PDF_READER_HINT = (
	"📖 Bu qism PDF ko'rinishida saqlangan va Telegram orqali yuborilmaydi.\n"
	"Saytda o'qish: {url}"
)

SUBSCRIPTION_REQUIRED = (
	"🔒 <b>Majburiy obuna</b>\n\n"
	"Kontentni olish uchun quyidagi kanallarga obuna bo'ling:\n{channels}\n\n"
	"Obuna bo'lgach, <b>✅ Tekshirish</b> tugmasini bosing."
)
SUBSCRIPTION_OK = "✅ Obuna tasdiqlandi!"
SUBSCRIPTION_STILL_MISSING = "❌ Siz hali quyidagi kanallarga obuna bo'lmagansiz:\n{channels}"

PREMIUM_REQUIRED = (
	"🔒 <b>Faol obuna kerak</b>\n\n"
	"Bu kontent <b>{plan}</b> uchun mo'ljallangan.\n"
	"Hisobingiz tarifi: <b>{current}</b>.\n\n"
	"Obunani «🎫 Obuna» bo'limidan tanlang."
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
	"📅 Obuna muddati: <b>{expires}</b>\n"
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

# --- in-bot quiz (the games questions, asked one message at a time) ---------
QUIZ_QUESTION = (
	"🧪 <b>Savol {index}/{total}</b> — {title}\n\n"
	"{text}\n\n"
	"⏱ {seconds} soniya · ✅ {pass_score} ta to'g'ri javob kerak"
)
# Appended to the first question only: it explains the speed bonus once.
QUIZ_FIRST_HINT = "⭐ Tez javob bersangiz, ko'proq ball olasiz."
QUIZ_TIME_UP = "⏳ Vaqt tugadi — bu savol ball keltirmadi."
QUIZ_STALE = "ℹ️ Bu savol allaqachon yopildi."
QUIZ_NO_QUESTIONS = "ℹ️ Bu kontent uchun savollar tayyor emas."
QUIZ_NO_ACCOUNT = "⚠️ O'yinda qatnashish uchun hisobingizni saytga ulang."
QUIZ_RESULT = (
	"🧪 <b>Test yakunlandi</b> — {title}\n\n"
	"✅ {correct} / {total} to'g'ri javob\n"
	"🏆 Ballar: <b>{points}</b>\n\n"
	"{outcome}"
)
QUIZ_PASSED = "🎉 Tabriklaymiz! Bu kontent tasdiqlandi."
QUIZ_FAILED = "😕 O'tib bo'lmadi. Qayta urinish mavjud emas."
QUIZ_SUSPICIOUS = "🚫 Javoblar shubhali darajada tez berilgani uchun ballar hisoblanmadi."
QUIZ_RANK = "🏆 Reytingdagi o'rningiz: <b>#{rank}</b> · {points} ball · Lv.{level}"

# --- rating table (the site's "Reyting" page, inside the bot) ---------------
RATING_TITLE = (
	"🏆 <b>Reyting jadvali</b>\n\n"
	"O'yinda ball to'plang, reytingda yuqoriga chiqing. Oyning eng faol "
	"o'yinchisi 1 oylik obuna yutadi."
)
RATING_OWN = (
	"👤 <b>Sizning o'rningiz:</b> #{rank} · {points} ball · Lv.{level} ({level_name})\n"
	"✅ Tasdiqlangan: {verified} ta · 🎯 Urinishlar: {attempts} ta"
)
# Shown when the Telegram visitor has not linked a website account yet: the
# table is public, only the "my rank" part needs an account.
RATING_GUEST = "👤 O'z o'rningizni ko'rish uchun hisobingizni saytga ulang."
RATING_TOP = "🔥 <b>Eng faol o'yinchilar:</b>"
RATING_ROW = "{mark} <b>{name}</b> — <b>{points}</b> ball · Lv.{level}"
RATING_ROW_SELF = "{mark} <b>{name}</b> — <b>{points}</b> ball · Lv.{level} ◀ siz"
RATING_EMPTY = (
	"🏆 <b>Reyting jadvali</b>\n\n"
	"Hali reyting yo'q — o'yinda birinchi bo'lib ball to'plang."
)

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
ADMIN_EPISODE_ASK_SEASON = (
	"📺 Nechanchi mavsum ekanini yuboring (mavsumsiz bo'lsa <code>-</code>).\n"
	"Qismlar raqami o'zi hisoblanadi."
)
ADMIN_EPISODE_SELECT_CHANNEL = "📡 Cloud (saqlash) kanalini tanlang:"
ADMIN_EPISODE_NO_CHANNELS = "⚠️ Cloud kanal yo'q. Avval «Kanallar» bo'limida qo'shing."
ADMIN_EPISODE_ASK_FILES = (
	"📤 Endi media fayllarni yuboring.\n\n"
	"Har bir xabar alohida qism bo'ladi — bitta qismda faqat bitta video yoki fayl.\n"
	"Har bir fayl Cloud kanalga alohida nusxalanadi.\n"
	"Qismlar raqami avtomatik beriladi.\n\n"
	"Tugagach <b>💾 Saqlash</b> tugmasini bosing."
)
ADMIN_EPISODE_FILES_READY = "📥 Fayllarni yuboring. Tugagach 💾 Saqlash tugmasini bosing."
ADMIN_EPISODE_FILE_SAVED = (
	"✅ {label}qism saqlandi (Cloud kanalga nusxalandi).\n"
	"Yana fayl yuboring yoki <b>💾 Saqlash</b> ni bosing."
)
ADMIN_EPISODE_CLOUD_FAILED = (
	"❌ Faylni Cloud kanalga nusxalab bo'lmadi. "
	"Bot kanalda administrator ekaniga ishonch hosil qilib, qayta yuboring."
)
ADMIN_EPISODE_SESSION_SAVED = "✅ <b>{title}</b> uchun {count} ta qism saqlandi.\n🎞 {label}"
ADMIN_EPISODE_PUBLISHED = "📢 Ommaviy kanalga e'lon joylandi."
ADMIN_EPISODE_NOT_PUBLISHED = (
	"⚠️ E'lon kanali tanlanmagani uchun ommaviy kanalga chiqarilmadi. "
	"«Sozlamalar → E'lon kanali» bo'limida tanlang."
)
ADMIN_EPISODE_NO_FILES = "📭 Hech qanday fayl yuborilmadi. Avval media yuboring."
ADMIN_EPISODE_LIST = "🎞 <b>{title}</b> qismlari — {page}/{pages}"
ADMIN_EPISODE_DELETE_CONFIRM = "🗑 {label}qismni o'chirmoqchimisiz?"
ADMIN_EPISODE_DELETED = "🗑 Qism o'chirildi."

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
	"📅 Muddat: <b>{expires}</b>\n"
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
Davomiylik: <b>{days} kun</b>
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

SUBREQ_ALREADY_PLAN = "Bu tarif allaqachon sizniki va faol."

SUBREQ_APPROVED = (
	"✅ <b>Obuna tasdiqlandi!</b>\n\n"
	"Tarif: <b>{plan}</b>\n"
	"Davomiylik: {days} kun\n"
	"Endi barcha imkoniyatlardan foydalanishingiz mumkin."
)

SUBREQ_REJECTED = "❌ <b>Obuna bekor qilindi.</b>\n\nTarif: <b>{plan}</b>\nSabab: to'lov tasdiqlanmadi."

SUBREQ_NOT_FOUND = "Ariza topilmadi."

SUBREQ_ALREADY_PROCESSED = "Bu ariza allaqachon ko'rib chiqilgan."

ADMIN_SUBREQ_APPROVED = "✅ Ariza tasdiqlandi.\n\n{details}"

ADMIN_SUBREQ_REJECTED = "❌ Ariza rad etildi.\n\n{details}"

# --- coupons ------------------------------------------------------------------
COUPON_PROMPT = (
	"🎟 <b>Kupon</b>\n\n"
	"Kupon kodini yuboring.\n"
	"Masalan: <code>ANICHOPAR</code>"
)
COUPON_REDEEMED = (
	"🎉 <b>Kupon qabul qilindi!</b>\n\n"
	"🎁 Sovg'a: <b>{days} kunlik obuna</b>\n"
	"📅 Amal qiladi: <b>{expires}</b>"
)
COUPON_ALREADY = "ℹ️ Siz bu kuponni allaqachon ishlatgansiz."
COUPON_EXPIRED = (
	"⌛️ Bu kupon eskirgan — ruxsat etilganlar soni tugagan."
)
COUPON_NOT_FOUND = "❌ Bunday kupon topilmadi. Kodni tekshirib qayta yuboring."
COUPON_NO_ACCOUNT = "⚠️ Hisobingiz topilmadi. Avval /start buyrug'ini yuboring."

# Posted to a public channel when the administrator publishes a coupon.
COUPON_POST = (
	"🎟 <b>KUPON SOVG'A</b>\n\n"
	"🎁 Sovg'a: <b>{days} kunlik obuna</b>\n"
	"👥 Kimga: birinchi <b>{max_uses}</b> kishi\n"
	"🔑 Kod: <code>{code}</code>\n\n"
	"Kodni botga yuborib obunani oling — son cheklangan!"
)

# --- admin coupons ------------------------------------------------------------
ADMIN_COUPONS_MENU = (
	"🎟 <b>Kuponlar</b>\n\n"
	"Kupon — cheklangan sonda beriladigan sovg'a kod: birinchi <b>N</b> kishi "
	"kodni kiritsa, <b>D</b> kunlik obuna oladi. Chegaradan oshgan kupon "
	"<b>eskirgan</b> hisoblanadi.\n\n"
	"Jami kuponlar: <b>{total}</b>"
)
ADMIN_COUPON_ASK_DAYS = "🎁 Necha kunlik obuna beriladi? Masalan: <code>7</code>"
ADMIN_COUPON_ASK_USES = "👥 Necha kishiga mo'ljallangan? Masalan: <code>50</code>"
ADMIN_COUPON_ASK_CODE = (
	"🔑 Kupon kodini yuboring (4–24 belgi, kamida bitta harf).\n"
	"Avtomatik kod uchun <code>-</code> yuboring."
)
ADMIN_COUPON_CARD = (
	"🔑 Kod: <code>{code}</code>\n"
	"🎁 Sovg'a: <b>{days} kunlik obuna</b>\n"
	"👥 Kimga: birinchi <b>{max_uses}</b> kishi\n"
	"✅ Ishlatilgan: <b>{used}</b> · Qoldi: <b>{remaining}</b>\n"
	"📊 Holat: <b>{status}</b>"
)
ADMIN_COUPON_CREATED = "✅ <b>Kupon yaratildi!</b>\n\n{card}"
ADMIN_COUPON_LIST = "🎟 <b>Kuponlar</b> — {page}/{pages}"
ADMIN_COUPON_EMPTY = "📭 Hozircha kupon yo'q. «➕ Yangi kupon» orqali yarating."
ADMIN_COUPON_INVALID = "❌ Noto'g'ri qiymat. Qayta yuboring."
ADMIN_COUPON_CODE_TAKEN = "⚠️ Bu kod band. Boshqa kod yuboring."
ADMIN_COUPON_DELETE_CONFIRM = "🗑 <b>{code}</b> kuponini o'chirmoqchimisiz?"
ADMIN_COUPON_DELETED = "🗑 Kupon o'chirildi."
ADMIN_COUPON_PUBLISHED = "📢 Kupon kanalga joylandi."
ADMIN_COUPON_NOT_PUBLISHED = (
	"⚠️ E'lon kanali tanlanmagan. «Sozlamalar → E'lon kanali» bo'limida tanlang."
)
ADMIN_COUPON_TOGGLED = "✅ Kupon holati: <b>{state}</b>"

# --- support (write to the administrators) ------------------------------------
SUPPORT_PROMPT = (
	"✉️ <b>Adminga xabar</b>\n\n"
	"Savol, taklif yoki muammoingizni yozib yuboring — xabar barcha "
	"administratorlarga yetib boradi.\n\n"
	"Bekor qilish uchun «🏠 Asosiy menyu» tugmasini bosing."
)
SUPPORT_SENT = (
	"✅ <b>Xabaringiz yuborildi!</b>\n\n"
	"Administratorlar tez orada javob berishadi."
)
SUPPORT_FAILED = (
	"⚠️ Xabaringiz saqlandi, lekin administratorlarga hozircha yuborilmadi.\n"
	"Iltimos, birozdan so'ng qayta yuboring."
)
SUPPORT_TOO_SOON = (
	"⏳ Oldingi xabaringiz endigina yuborildi.\n"
	"Iltimos, {seconds} soniyadan so'ng qayta yozing."
)
SUPPORT_EMPTY = (
	"❌ Bo'sh xabar yuborilmadi.\n"
	"Iltimos, savolingizni matn ko'rinishida yozing."
)

# --- referrals -----------------------------------------------------------------
REFERRAL_MENU = (
	"👥 <b>Do'stlarni taklif qilish</b>\n\n"
	"Har bir do'stingizni shu havola orqali botga taklif qiling — "
	"do'stlar soni oshgani sari bepul obuna yuting!\n\n"
	"🔗 Havolangiz: <code>{link}</code>\n"
	"👥 Taklif qilinganlar: <b>{invited}</b>\n\n"
	"🎁 10 ta do'st → <b>15 kunlik obuna</b>\n"
	"🎁 15 ta do'st → <b>1 oylik obuna</b>\n\n"
	"Mukofot avtomatik berilmaydi — yetarli do'st to'plangach, "
	"quyidagi tugma orqali o'zingiz tasdiqlaysiz."
)
REFERRAL_CLAIMED = (
	"🎉 <b>Mukofot olindi!</b>\n\n"
	"🎁 Sizga <b>{days} kunlik obuna</b> berildi.\n"
	"📅 Amal qiladi: <b>{expires}</b>"
)
REFERRAL_ALREADY = "ℹ️ Bu mukofotni allaqachon olgansiz."
REFERRAL_NOT_ENOUGH = (
	"⏳ Hali erta. Sizning mukofotingiz uchun <b>{needed}</b> ta do'st kerak, "
	"hozircha <b>{invited}</b> ta bor."
)
REFERRAL_NO_ACCOUNT = "⚠️ Hisobingiz topilmadi. Avval /start buyrug'ini yuboring."
REFERRAL_INVALID = "❌ Noto'g'ri mukofot turi."
REFERRAL_JOINED = (
	"👋 Do'stingiz orqali keldingiz!\n\n"
	"U sizni botga taklif qildi. Ko'rganingizdan keyin u mukofot oladi."
)

# --- giveaways -----------------------------------------------------------------
# Posted to a public channel so non-subscribers can join the raffle.
GIVEAWAY_POST = (
	"🎁 <b>{title}</b>\n\n"
	"🏆 Sovrin: <b>{days} kunlik obuna</b>\n"
	"👥 G'oliblar: <b>{winners}</b> ta\n"
	"{conditions}\n\n"
	"Qatnashish uchun pastdagi tugmani bosing — sovrin soni cheklangan!"
)
GIVEAWAY_POST_NO_CONDITIONS = "📌 Shartlar: faqat faol obunachilar uchun"
GIVEAWAY_WINNER_DM = (
	"🎉 <b>Sovg'a g'olibi!</b>\n\n"
	"«{title}» sovg'asida yutib oldingiz!\n"
	"🎁 Sizga <b>{days} kunlik obuna</b> berildi.\n"
	"📅 Amal qiladi: <b>{expires}</b>"
)

# --- admin giveaways -----------------------------------------------------------
ADMIN_GIVEAWAYS_MENU = (
	"🎁 <b>Sovg'alar</b>\n\n"
	"Admin sovg'asi: shartlarni o'zingiz belgilaysiz (masalan: botda anime "
	"ko'rgan, homiy kanallarga obuna, biosida referral havolasi). O'tkazilganda "
	"3 ta tasodifiy obunachi g'olib bo'ladi va har biri mukofot oladi.\n\n"
	"Jami sovg'alar: <b>{total}</b>"
)
ADMIN_GIVEAWAY_ASK_TITLE = "🎁 Sovg'a nomini yuboring.\nMasalan: <code>Yangi yil sovg'asi</code>"
ADMIN_GIVEAWAY_ASK_DAYS = "🎁 G'oliblarga necha kunlik obuna beriladi? Masalan: <code>30</code>"
ADMIN_GIVEAWAY_ASK_WINNERS = "👥 Nechta g'olib tanlanadi? Masalan: <code>3</code>"
ADMIN_GIVEAWAY_ASK_MIN_VIEWS = (
	"🎬 Nomzod kamida nechta anime ko'rgan bo'lishi kerak (botda ochilgan)?\n"
	"Shart bo'lmasa <code>0</code> yuboring."
)
ADMIN_GIVEAWAY_CREATED = "✅ <b>Sovg'a yaratildi!</b>\n\n{card}"
ADMIN_GIVEAWAY_PUBLISHED = "📢 Sovg'a ommaviy kanalga joylandi."
ADMIN_GIVEAWAY_NOT_PUBLISHED = (
	"⚠️ E'lon kanali tanlanmagan. «Sozlamalar → E'lon kanali» bo'limida tanlang."
)
ADMIN_GIVEAWAY_CARD = (
	"🎁 <b>{title}</b>\n\n"
	"🎁 Mukofot: <b>{days} kun</b>\n"
	"👥 G'oliblar: <b>{winners_count}</b> ta\n"
	"📌 Shartlar: {conditions}\n"
	"📊 Holat: <b>{status}</b>\n\n"
	"🏆 G'oliblar:\n{winners}"
)
ADMIN_GIVEAWAY_LIST = "🎁 <b>Sovg'alar</b> — {page}/{pages}"
ADMIN_GIVEAWAY_EMPTY = "📭 Hozircha sovg'a yo'q. «➕ Yangi sovg'a» orqali yarating."
ADMIN_GIVEAWAY_INVALID = "❌ Noto'g'ri qiymat. Qayta yuboring."
ADMIN_GIVEAWAY_DELETE_CONFIRM = "🗑 <b>{title}</b> sovg'asini o'chirmoqchimisiz?"
ADMIN_GIVEAWAY_DELETED = "🗑 Sovg'a o'chirildi."
ADMIN_GIVEAWAY_DRAW_CONFIRM = (
	"🎲 <b>{title}</b> sovg'asini o'tkazmoqchimisiz?\n\n"
	"Shartlar tekshiriladi (kanallar va bio qayta tekshiruvi bilan), "
	"keyin <b>{winners}</b> ta g'olib tanlanadi va har biriga "
	"<b>{days} kun</b> beriladi.\n\n"
	"⚠️ Bu amalni qaytarib bo'lmaydi."
)
ADMIN_GIVEAWAY_DRAWN = (
	"🎲 <b>Sovg'a yakunlandi!</b>\n\n"
	"🎁 {title}\n"
	"✅ Mos nomzodlar: <b>{eligible}</b>\n"
	"🏆 G'oliblar (<b>{won}</b> ta):\n{winners}"
)
ADMIN_GIVEAWAY_DRAW_EMPTY = (
	"⚠️ G'olib topilmadi — shartlarga mos nomzod yo'q.\n\n"
	"🎁 {title}\n"
	"Nomzodlar soni: <b>{candidates}</b>"
)
ADMIN_GIVEAWAY_ALREADY_DRAWN = "ℹ️ Bu sovg'a allaqachon o'tkazilgan."
ADMIN_GIVEAWAY_NOT_OPEN = "⚠️ Bu sovg'a o'tkazish uchun ochiq holatda bo'lishi kerak."
ADMIN_GIVEAWAY_STATUS_LABELS = {
	"draft": "Loyiha",
	"open": "Ochiq",
	"drawn": "E'lon qilingan",
	"closed": "Yopilgan",
}
