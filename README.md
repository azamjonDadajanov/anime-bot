# AniChopar — Telegram bot, REST API va veb-sayt

Anime, serial, manga va kinolar uchun to'liq platforma: **aiogram 3** bot, **Django REST** API
va **React** veb-ilova. Bot kontentni yopiq tarzda (himoyalangan fayllar bilan) yetkazadi,
sayt esa katalog, sevimlilar, profil va obuna bo'limlarini beradi.

## Imkoniyatlar

**Telegram bot**

- 4 xonali kod, nom yoki janr bo'yicha qidiruv; katalog, janrlar va turlar bo'limlari.
- **AI yordamchi — AniVoy** ("🤖 AI yordamchi" tugmasi, faqat faol obunachilar
  uchun): online chat modeli katalog funksiyalarini (qidiruv, kontent ma'lumoti,
  qismlar, janrlar, mashhur/yangi kontent) o'zi chaqirib, savolga javob beradi va
  mos kontentlarni havola + bir gaplik mazmun bilan ro'yxat qilib beradi.
  Masalan: «qo'rqinchli anime ayt», «Naruto nechta qismdan iborat?»,
  «sevimlilarimga o'xshash nima bor?».
- Qism yuborilgach uning ostida **qismlar navigatori** chiqadi: qismlar 5 tadan qatorlarga
  joylashadi, tanlangani yashil belgi bilan ajratiladi, pastdagi `⬅️ fasl ➡️` tugmalari
  oldingi/keyingi qismni yuboradi va fasl tugaganda keyingi faslning birinchi qismiga o'tadi.
- Sevimlilar, manga uchun saytga havola, media himoyasi (`protect_content`).
- Majburiy obuna: ommaviy (public) kanallar ham avtomatik majburiy obuna bo'ladi;
  birorta kanalga obuna bo'lmagan foydalanuvchi botning **hech bir** imkoniyatidan
  foydalana olmaydi (faqat "✅ Tekshirish" tugmasi ishlaydi va obuna bo'lingan kanallar
  ro'yxatda takror ko'rsatilmaydi).
- Obuna tariflari: kunlik 6 000, 15 kunlik 10 000, 1 oylik 25 000, 3 oylik 64 000 va
  yillik 220 000 so'm (har keyingisi ~15% arzon). Bepul foydalanuvchi faqat `free`
  kontentni ko'radi, faol obunada hammasi ochiq (`free` / `paid` darajalari).
- Broadcast, kanallar, kontent/qismlar, foydalanuvchilar, jurnallar va sozlamalar uchun
  administrator paneli (`/admin`), to'lov arizalarini tasdiqlash.
- **Referral**: "👥 Do'stlar" bo'limi orqali havola; taklif qilingan har bir do'st
  uchun mukofot — 10 kishi → 15 kun, 15 kishi → 30 kun. Mukofot faqat "🎁 Olish"
  tugmasi bosilganda beriladi (avtomatik emas), har bir referral faqat bitta
  taklifchiga bir marta hisoblanadi.
- **Sovg'alar (giveaway)**: administrator panel orqali sovg'a yaratish — nom,
  mukofot kunlari, g'oliblar soni va shartlar (botda ≥ N anime ochilgan bo'lish,
  homiy kanallarga obuna, bio'da referral havolasi). Kanallar va bio yig'ish
  paytida Telegram Bot API orqali jonli tekshiriladi; g'oliblar tasodifiy tanlanadi
  va shaxsiy xabar oladi.
- **Adminga xabar** ("✉️" tugmasi): foydalanuvchi savoli/muammosi saqlanadi va barcha
  administratorlarga (`ADMIN_IDS`) Telegramga yuboriladi. Majburiy obuna bo'lmasa ham
  bu bo'lim ochiq qoladi, chunki aynan o'sha holatda odam adminga yozishi kerak bo'ladi.
- **Obuna eslatmalari**: `python manage.py send_subscription_reminders` (cron) obunasi
  tugab qolayotgan va yaqinda tugagan foydalanuvchilarga bir marta shaxsiy eslatma
  yuboradi.
- `python manage.py runbot` — long-polling rejimida ishlaydi.

**Veb-ilova**

- Katalog bo'limlari (yangi, mashhur, kutilmoqda, kino, anime, manga, serial), janrlar,
  sevimlilar va media sahifasi.
- Qidiruv (modal + `Ctrl K`), profil bo'limlari (ma'lumotlar, faollik, tarix, Telegram,
  obuna), tema va til sozlamalari.
- Manga o'quvchi (PDF va rasmlar), o'qish pozitsiyasini saqlash.
- Sarlavhadagi "✉️" tugmasi — **Adminga xabar** modali: matn serverda saqlanadi va
  administratorlarga yuboriladi (natija foydalanuvchiga darhol aytiladi).
- O'ng pastdagi **🤖 AI yordamchi** tugmasi (faqat faol obunachilarga ko'rinadi) —
  AniVoy bilan chat: botdagi bilan bir xil model va funksiyalar ishlaydi, natijalar
  havola va bir gaplik mazmun bilan chiqadi. Obuna bo'lmagan hisobga tugma
  ko'rsatilmaydi, API esa `403 subscription_required` qaytaradi.
- Obuna tugashiga 3 kun qolganda yoki muddati o'tgach `/subscription` sahifasida
  ogohlantirish ko'rsatiladi (botdagi eslatma bilan bir xil qoida).
- **Anime reyting o'yini** (`/game`): botda ≥3 qism ochilgan animelar bo'yicha
  5 savollik quiz. To'g'ri javoblar soniga qarab ball (jami ballar soniga proporsional),
  ≥4/5 bo'lsa animeni "tasdiqlangan" deb belgilaydi. Qayta urinish yo'q (bir marta),
  javoblar keyin ko'rsatilmaydi. Server tomonidan minimal javob vaqti va kunlik
  urinish limiti bilan anti-cheat. Oyning eng faol (obunasi bo'lmagan) o'yinchisi
  1 oylik obuna yutadi (`award_game_monthly_prize`, cron).
- **Reyting jadvali** ikkala joyda ham bir xil manbadan (`games.services.leaderboard`)
  olinadi: saytda `/rating` sahifasida, botda esa asosiy menyudagi **🏆 Reyting**
  tugmasida — top 10 o'yinchi, o'z o'rni, tasdiqlanganlar va urinishlar soni.
  Botda qiz tugagach natija ostida yangi o'rin ham ko'rsatiladi.
- **Admin panel — «📢 E'lon qilish»** (`/admin/media/<slug>`): kontentni muqova,
  nomi, qismlar, reyting, davomiyligi, qism/umumiy qism va sifat bilan e'lon qiladi;
  manzil sifatida kanal, barcha bot foydalanuvchilari yoki ikkalasi birdaniga
  tanlanadi. Xuddi shu tugma bot panelida ham bor: davom etayotgan media uchun
  «oxirgi qism / barcha qismlar» so'raladi, tugallangan media hammasini yuboradi.
- JWT asosidagi autentifikatsiya: parol, Telegram login widget va Telegram Mini App.

## Texnologiyalar

| Qatlam    | Nima ishlatilgan                                                             |
| --------- | ---------------------------------------------------------------------------- |
| Bot       | aiogram 3, Django ORM bilan `sync_to_async` ko'prigi                          |
| AI yordamchi| Online chat modeli (Groq/Gemini/OpenAI) + OpenAI-mos `tools` (function calling) |
| Backend   | Django 5.2, Django REST Framework, SimpleJWT, drf-spectacular, CORS, whitenoise |
| Baza      | SQLite (dev) yoki PostgreSQL (production)                                     |
| Frontend  | React 19, Vite, Mantine 9, React Router, axios, bootstrap-icons               |
| Production| Docker Compose, gunicorn, nginx, PostgreSQL 17                                 |

## Repo tuzilishi

```
.
├── kino_top/                  # Django loyihasi
│   ├── bot/                   # aiogram bot: handlerlar, klaviaturalar, servislar, testlar
│   ├── movies/                # katalog modellari, DRF API, manga/PDF
│   ├── users/                 # autentifikatsiya, profil, obuna, tariflar, sovg'alar
│   ├── games/                 # anime reyting o'yini (quiz, ball, oylik mukofot)
│   ├── adminpanel/            # website admin API (SPA /admin uchun)
│   ├── kino_top/              # settings, urls, wsgi
│   └── Dockerfile             # backend image (gunicorn + entrypoint)
├── frontend/                  # React SPA (Vite + Mantine)
│   ├── src/components/Header.jsx
│   ├── nginx.conf             # SPA + API proxy (production)
│   └── Dockerfile             # SPA build → nginx image
├── docker-compose.yml         # db + web + bot + nginx
├── DEPLOY.md                  # production deploy qo'llanmasi
├── .env.production.example    # compose uchun muhit namunasi
└── kino_top/.env.example      # mahalliy ishlab chiqish uchun namuna
```

## Tez boshlash (mahalliy)

### 1. Backend va bot

```bash
cd kino_top
python -m venv .venv
source .venv/Scripts/activate        # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt

cp .env.example .env                 # BOT_TOKEN, ADMIN_IDS va boshqalarni to'ldiring
python manage.py migrate
python manage.py createsuperuser     # admin panel uchun
python manage.py runserver           # API: http://127.0.0.1:8000
```

Botni alohida terminalda ishga tushiring (u `BOT_TOKEN` va `ADMIN_IDS` ni talab qiladi):

```bash
python manage.py runbot
python manage.py botcheck            # sozlamalarni tekshirish
```

Demo kontent kerak bo'lsa: `python manage.py seed_test_anime`.

### AI yordamchini yoqish

Offline model yuklab olish ham, indeks yig'ish ham kerak emas: yordamchi faqat
online model bilan ishlaydi. `kino_top/.env` da bitta kalit yetarli:

```bash
AI_LLM_PROVIDER=groq        # groq | gemini | openai | custom
AI_LLM_API_KEY=gsk_...      # https://console.groq.com/keys
```

Sozlamani tekshirish va bitta real so'rovni sinab ko'rish:

```bash
python manage.py ai_setup             # ishlaydigan modellar zanjiri (baza qatorlari)
python manage.py ai_status            # zanjir: provayderlar, model, kalit, kutish
python manage.py ai_status --test     # har bir model alohida sinanadi + bitta real savol
```

Bir nechta kalitni zanjir qilib qo'yish (`/django-admin/` → *AI provayderlar*)
batafsil **[DEPLOY.md](DEPLOY.md)** da.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

Veb-ilova API manzilini `VITE_API_BASE_URL` dan oladi (lokal standart:
`http://127.0.0.1:8000/api`; production build'i compose'da
`//api.anichopar.uz/api` bilan quriladi). Sayt va botni bir-biriga ulash uchun
`kino_top/.env` dagi `BOT_SITE_URL` ni frontend manziliga moslang.

## Bot buyruqlari

| Buyruq                     | Vazifasi                                                       |
| -------------------------- | -------------------------------------------------------------- |
| `/start`                   | Ro'yxatdan o'tish va asosiy menyu                              |
| `/start anime_1234`        | Kod bo'yicha to'g'ridan-to'g'ri ochish (`anime_`, `series_`, `manga_`, `movie_`) |
| `/start part_42`           | Aniq qismni ochish                                              |
| `/help`, `/yordam`         | Yordam                                                          |
| `/admin`, `/panel`         | Administrator paneli (faqat `ADMIN_IDS` uchun)                  |

## API

JWT bilan himoyalangan REST API (`/api/`; production'da
`api.anichopar.uz/api/`, `anichopar.uz/api` esa 404):

- `POST /api/auth/register/`, `POST /api/auth/token/`, `POST /api/auth/token/refresh/`
- `GET|PATCH /api/auth/me/`, `/api/auth/settings/`, `/api/auth/favorites/`
- `/api/auth/profile/`, `profile/activity/`, `profile/history/`, `profile/subscription/`
- `POST /api/auth/telegram/login/`, `POST /api/auth/telegram/mini-app/`
- `/api/auth/subscription/plans/`, `subscription/card/`, `subscription/request/`
- `POST /api/auth/support/` — Adminga xabar (barcha administratorlarga yetkaziladi)
- `POST /api/catalog/ai-assistant/` — AI yordamchi: `{"query": "..."}` (+ ixtiyoriy
  `history`, `taste`, `support`, `type`, `limit`) → modelning javobi, u chaqirgan
  funksiyalar ro'yxati va havola + bir gaplik mazmun bilan natijalar (faqat faol
  obuna; provayder bo'lmasa `503 ai_unavailable`, obuna bo'lmasa `403`)
- `GET|POST /api/admin/media/<slug>/announce/` — e'lon: `GET` tayyor matn va
  auditoriyani qaytaradi, `POST {"targets": ["channel", "users"], "scope": "last"|"all"}`
  yuboradi (kanal — so'rov ichida, foydalanuvchilar — fonda)
- `/api/catalog/`, `/api/parts/`, `/api/reading/`, `/api/telegram-media/`, `/api/channels/`
- O'yin: `/api/game/status/`, `game/titles/`, `game/quiz/start/`, `game/quiz/submit/`,
  `game/leaderboard/`
- Sxema va hujjatlar: `/api/schema/`, `/api/docs/` (Swagger UI)

## Testlar va tekshiruvlar

```bash
cd kino_top && python manage.py test        # 641 ta test
python manage.py check --deploy             # production sozlamalari bo'yicha ogohlantirishlar

cd frontend && npm run lint && npm run build
```

## Production

Docker Compose steki (PostgreSQL + gunicorn + bot + nginx) va HTTPS bo'yicha to'liq
qo'llanma: **[DEPLOY.md](DEPLOY.md)**.

```bash
cp .env.production.example .env      # sirlarni to'ldiring
docker compose up -d --build
```

`nginx` konteyneri uchta hostni bitta joydan beradi: `anichopar.uz` — SPA,
`/django-admin`, `/static`, `/media`; `admin.anichopar.uz` — React panel o'z
boshiga document sifatida; `api.anichopar.uz` — `/api/` gunicorn'ga proxy.
`anichopar.uz/api` va `anichopar.uz/admin` esa 404: ikkinchi kirish nuqtasi
qolmasligi uchun. API alohida hostga ko'chgani uchun production'da CORS
ishlaydi (`CORS_ALLOWED_ORIGINS`).

`/admin` **React administrator paneliga** tegishli (SPA route), shuning uchun Django'ning
o'z admini `/django-admin/` ga ko'chirilgan (`kino_top/kino_top/urls.py`). Ilgari nginx
`/admin/` ni Django'ga proxy qilardi va panelning istalgan sahifasiga to'g'ridan-to'g'ri
kirish yoki sahifani yangilash Django admin loginiga olib kelardi; hozir production'da
bu prefiks umuman yopiq, panel faqat `admin.anichopar.uz` da ochiladi.

## AI yordamchi (AniVoy)



AniVoy — bu qidiruv maydoni ustiga qo'yilgan model emas, balki **funksiyalar

bilan ishlaydigan online yordamchi**. Model senga berilgan funksiyalardan qaysi

biri kerakligini o'zi hal qiladi, natijani o'qiydi va shundan keyin o'zbekcha

javob yozadi (`movies.ai_assistant`):



| Funksiya | Nima qiladi |

| --- | --- |

| `search_catalog` | Nomi, tavsifi, janri, turi yoki yili bo'yicha kontent qidiradi |

| `title_details` | Bitta kontent haqida to'liq ma'lumot (janr, yil, reyting, tarif, tavsif) |

| `list_parts` | Qismlar/mavsumlar ro'yxati («nechta qism bor?» uchun aniq javob) |

| `list_genres` | Katalogdagi janrlar va ularning kontent soni |

| `popular_titles` | Mashhur, eng yangi yoki kutilayotgan kontent |

| `catalog_stats` | Turlar bo'yicha kontent soni |

| `personal_taste` | Sevimlilar va oxirgi ko'rganlar — faqat foydalanuvchi yoqsa |



- **Offline model yo'q**: vektor indeks, ONNX/model fayllari va `numpy`/

  `onnxruntime`/`tokenizers` bog'liqliklari butunlay olib tashlangan. Yordamchi

  faqat online model orqali ishlaydi; kalit bo'lmasa u javob bera olmasligini

  aytadi (botda «🛠 AI yordamchi hozircha javob bera olmaydi…», saytda `503`).

- **Obuna to'sig'i**: botda tugma faqat `Subscription.is_active` bo'lgan

  hisoblarga chiqadi, saytda esa launcher ham, API ham (`403`) shu qoidani

  qo'llaydi. Qidiruv ekranida AI tugmasi yo'q — yordamchi asosiy menyudagi

  alohida «🤖 AI yordamchi» tugmasi orqali ochiladi.

- **Provayder zanjiri**: model bitta kalitga emas, **bazadagi provayderlar

  zanjiriga** bog'langan (`/django-admin/` → *AI provayderlar*; bo'sh bo'lsa

  `.env`dagi `AI_LLM_PROVIDER`/`AI_LLM_API_KEY` ishlaydi). So'rov ustuvorlik

  tartibida bittalab yuboriladi, biri limitga yetsa avtomatik keyingisiga

  o'tiladi, o'sha provayder kutishga qo'yiladi (`AI_LLM_TIMEOUT`,

  `AI_LLM_DEADLINE`). Zanjir butunlay limitda bo'lsa yordamchi darhol

  «javob bera olmaydi» deb xabar qaytaradi — kutib qolmaydi.

- **O'lik model bilan bog'liq holatlar**: `404` (model eskirgan) — qator yarim

  soatga qo'yiladi, `429` (kvota) — 5 daqiqa, `5xx`/timeout — 1 daqiqa. Sabab

  faqat **administratorga** ko'rinadi: botda va saytda xabar o'zgarmaydi, lekin

  admin panelning *Loglar* sahifasida (`bot.ai`) va `ai_status --test`

  chiqishida aniq yoziladi. `manage.py ai_setup` esa ishlaydigan modellarning

  zanjirini bir buyruq bilan yozadi.

- **Grounded javob**: javob ostidagi har bir havola funksiya qaytargan haqiqiy

  katalog qatori; model katalogda yo'q nom, qism soni yoki yilni o'ylab topmaydi

  (promptda taqiqlangan, testlar buni tekshiradi).

- **Tarix va kontekst**: sayt va bot oxirgi suhbat turlarini (`history`) yuboradi,

  shuning uchun «nima aytgandingiz?» yoki «oldingisiga o'xshashini top» mazmunli

  bo'ladi. «Sevimlilar» rejimi yoqilsa, `personal_taste` funksiyasi ro'yxatga

  qo'shiladi — o'chirilgan bo'lsa model sevimlilarni umuman ko'rmaydi.

- **Kesh**: bir xil savol 2 daqiqa ichida qayta berilsa javob keshdan olinadi.



## Xavfsizlik

- `kino_top/.env` va `.env.production` repoga tushmaydi (`.gitignore`), image ichiga ham
  ko'chirilmaydi (`.dockerignore`).
- Mahalliy baza (`db.sqlite3`), yuklangan fayllar (`media/`) va yig'ilgan static
  (`staticfiles/`) versiyalanmaydi.
- Bot tokeni, `DJANGO_SECRET_KEY` va karta ma'lumotlari faqat muhit o'zgaruvchilari orqali
  beriladi.
