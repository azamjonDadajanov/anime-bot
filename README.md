# AniChopar — Telegram bot, REST API va veb-sayt

Anime, serial, manga va kinolar uchun to'liq platforma: **aiogram 3** bot, **Django REST** API
va **React** veb-ilova. Bot kontentni yopiq tarzda (himoyalangan fayllar bilan) yetkazadi,
sayt esa katalog, sevimlilar, profil va obuna bo'limlarini beradi.

## Imkoniyatlar

**Telegram bot**

- 4 xonali kod, nom yoki janr bo'yicha qidiruv; katalog, janrlar va turlar bo'limlari.
- **AI qidiruv** ("🤖 AI orqali qidirish" tugmasi, faqat faol obunachilar uchun):
  "menga sarguzasht va qo'rqinchli animelar ayt" kabi so'rovlarni tushunadi va
  mos kontentlarni havola + bir gaplik mazmun bilan ro'yxat qilib beradi.
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
- O'ng pastdagi **🤖 AI qidiruv** tugmasi — chat: savol matni botdagi bilan bir xil
  modeldan o'tadi, natijalar havola, bir gaplik mazmun va moslik foizi bilan
  chiqadi. Obuna bo'lmagan hisobga "Obunani tanlash" taklifi ko'rsatiladi.
- Obuna tugashiga 3 kun qolganda yoki muddati o'tgach `/subscription` sahifasida
  ogohlantirish ko'rsatiladi (botdagi eslatma bilan bir xil qoida).
- **Anime reyting o'yini** (`/game`): botda ≥3 qism ochilgan animelar bo'yicha
  5 savollik quiz. To'g'ri javoblar soniga qarab ball (jami ballar soniga proporsional),
  ≥4/5 bo'lsa animeni "tasdiqlangan" deb belgilaydi. Qayta urinish yo'q (bir marta),
  javoblar keyin ko'rsatilmaydi. Server tomonidan minimal javob vaqti va kunlik
  urinish limiti bilan anti-cheat. Oyning eng faol (obunasi bo'lmagan) o'yinchisi
  1 oylik obuna yutadi (`award_game_monthly_prize`, cron).
- JWT asosidagi autentifikatsiya: parol, Telegram login widget va Telegram Mini App.

## Texnologiyalar

| Qatlam    | Nima ishlatilgan                                                             |
| --------- | ---------------------------------------------------------------------------- |
| Bot       | aiogram 3, Django ORM bilan `sync_to_async` ko'prigi                          |
| AI qidiruv| `paraphrase-multilingual-MiniLM-L12-v2` ONNX eksporti + onnxruntime + numpy    |
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

### AI qidiruvni yoqish

AI qidiruv modelni talab qiladi (bir marta yuklanadi) va indeksni yig'ish kerak:

```bash
python manage.py index_anime_embeddings --download-model   # ~470MB ONNX + tokenizer
python manage.py index_anime_embeddings                    # katalogdagi hamma kontentni indekslaydi
python manage.py index_anime_embeddings --status           # holat va eskirgan yozuvlar
python manage.py index_anime_embeddings --check            # model ishlayaptimi
```

Keyin kontent qo'shilsa, tahrirlansa yoki o'chirilsa indeks o'zi yangilanadi
(signal'lar orqali, faqat o'zgargan sarlavha qayta hisoblanadi). Batafsil
ma'lumot va cheklovlar **[DEPLOY.md](DEPLOY.md)** da.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

Veb-ilova API manzilini `VITE_API_BASE_URL` dan oladi (standart:
`http://127.0.0.1:8000/api`). Sayt va botni bir-biriga ulash uchun `kino_top/.env` dagi
`BOT_SITE_URL` ni frontend manziliga moslang.

## Bot buyruqlari

| Buyruq                     | Vazifasi                                                       |
| -------------------------- | -------------------------------------------------------------- |
| `/start`                   | Ro'yxatdan o'tish va asosiy menyu                              |
| `/start anime_1234`        | Kod bo'yicha to'g'ridan-to'g'ri ochish (`anime_`, `series_`, `manga_`, `movie_`) |
| `/start part_42`           | Aniq qismni ochish                                              |
| `/help`, `/yordam`         | Yordam                                                          |
| `/admin`, `/panel`         | Administrator paneli (faqat `ADMIN_IDS` uchun)                  |

## API

JWT bilan himoyalangan REST API (`/api/`):

- `POST /api/auth/register/`, `POST /api/auth/token/`, `POST /api/auth/token/refresh/`
- `GET|PATCH /api/auth/me/`, `/api/auth/settings/`, `/api/auth/favorites/`
- `/api/auth/profile/`, `profile/activity/`, `profile/history/`, `profile/subscription/`
- `POST /api/auth/telegram/login/`, `POST /api/auth/telegram/mini-app/`
- `/api/auth/subscription/plans/`, `subscription/card/`, `subscription/request/`
- `POST /api/auth/support/` — Adminga xabar (barcha administratorlarga yetkaziladi)
- `POST /api/catalog/ai-search/` — AI qidiruv: `{"query": "..."}` → havola,
  bir gaplik mazmun va moslik bali bilan natijalar ro'yxati (faqat faol obuna;
  model yoki indeks tayyor bo'lmasa `503`, obuna bo'lmasa `403`)
- `/api/catalog/`, `/api/parts/`, `/api/reading/`, `/api/telegram-media/`, `/api/channels/`
- O'yin: `/api/game/status/`, `game/titles/`, `game/quiz/start/`, `game/quiz/submit/`,
  `game/leaderboard/`
- Sxema va hujjatlar: `/api/schema/`, `/api/docs/` (Swagger UI)

## Testlar va tekshiruvlar

```bash
cd kino_top && python manage.py test        # 443 ta test
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

`nginx` konteyneri SPA'ni beradi, `/api/` va `/django-admin/` ni gunicorn'ga proxy
qiladi, `/static/` va `/media/` ni esa to'g'ridan-to'g'ri volume'lardan uzatadi — barchasi
bitta origin bo'lgani uchun production'da CORS kerak emas.

`/admin` **React administrator paneliga** tegishli (SPA route), shuning uchun Django'ning
o'z admini `/django-admin/` ga ko'chirilgan (`kino_top/kino_top/urls.py`). Ilgari nginx
`/admin/` ni Django'ga proxy qilardi va panelning istalgan sahifasiga to'g'ridan-to'g'ri
kirish yoki sahifani yangilash Django admin loginiga olib kelardi.

## AI qidiruv (semantic search)

Katalogdagi sarlavhalar **`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`**
modelining ONNX eksporti bilan 384 o'lchamli vektorga aylantiriladi (bu rasmiy
eksport, shuning uchun natija PyTorch versiyasi bilan bir xil; bizda torch o'rniga
faqat `onnxruntime` ishlaydi). Foydalanuvchi so'rovi ham shu modeldan o'tadi va
natijalar kosinus o'xshashligi bo'yicha tartiblanadi — shuning uchun so'rovdagi
so'zlar sarlavhada umuman uchramasa ham mos kontent topiladi.

- **Obuna to'sig'i**: botda ham, saytda ham faqat `Subscription.is_active` bo'lgan
  (ya'ni to'langan va muddati o'tmagan) hisoblar foydalanadi.
- **Indeks**: `TitleEmbedding` jadvali (sarlavha ↔ vektor + matn hashi).
  Qo'shilgan/tahrirlangan/o'chirilgan sarlavha (va janr o'zgarishi) o'zgargan
  qatornigina qayta hisoblaydi; to'liq indeksni `index_anime_embeddings` yig'adi.
- **Matn**: nom, tur, janrlar, yil, holat va tavsifning bir qismi (model 128
  tokenda kesadi, shuning uchun tavsif qisqartiriladi).
- **Fikrlash (ixtiyoriy, lekin tavsiya etiladi)**: qidiruv ikki qadamda ishlaydi —
  avval encoder katalogdan nomzodlarni topadi, keyin chat modeli so'rovni tahlil
  qilib, mos keladiganlarini tanlaydi, tartibini aniqlaydi va o'zbekcha qisqa javob
  yozadi. Model bitta kalitga emas, **bazadagi provayderlar zanjiriga** bog'langan
  (`/django-admin/` → *AI provayderlar*; bo'sh bo'lsa `.env`dagi
  `AI_LLM_PROVIDER`/`AI_LLM_API_KEY` ishlaydi): so'rov ustuvorlik tartibida
  bittalab yuboriladi, biri limitga yetsa yoki javob bermasa avtomatik keyingisiga
  o'tiladi, o'sha provayder esa kutishga qo'yiladi — keyingi so'rovlar uni qayta
  urinmaydi (`AI_LLM_TIMEOUT`, `AI_LLM_DEADLINE`). Zanjir butunlay limitda bo'lsa,
  qidiruv tarmoqqa murojaat qilmasdan darhol vektor natijalarini qaytaradi. Botda
  «🤔 AI o'ylayapti…» xabari javobga aylanadi, saytda javob va yig'ilgan
  «Fikrlash jarayoni» ko'rsatiladi. Kalit o'rnatilmagan yoki provayder javob
  bermagan taqdirda qidiruv ishlashda davom etadi — faqat izohsiz, vektor
  tartibida qaytadi (`used_llm`/`reasoning` maydoni buni aytadi).
- **Natijalar**: har bir sarlavha havola (saytda `/media/<slug>`, botda bosiladigan
  tugma) va bir gapli qisqacha mazmun bilan chiqadi. Ro'yxat eng mos N tadan
  iborat, lekin javobda **jami nechta mos kontent topilgani** ham aytiladi
  ("Yana N tasini ko'rsatish" / "Jami N ta mos kontent topildi") — model butun
  bazani titkilaydi, ko'rsatiladigan qismi esa faqat o'qish uchun qulay bo'lgani
  uchun cheklanadi.
- **Choralar/cheklovlar**: o'lchov (33 sarlavhali katalog, real model) — mavzuga
  oid so'rovlarning eng yaxshi natijalari 0.70-0.84, aloqasi yo'q so'rovlarda esa
  eng yuqori ball 0.42 dan oshmadi; shu sababli standart chegara
  `AI_SEARCH_MIN_SCORE=0.45`. Model birinchi so'rovda xotiraga yuklanadi (~6 s),
  keyin bitta qidiruv ~10 ms. Batafsil: DEPLOY.md.

## Xavfsizlik

- `kino_top/.env` va `.env.production` repoga tushmaydi (`.gitignore`), image ichiga ham
  ko'chirilmaydi (`.dockerignore`).
- Mahalliy baza (`db.sqlite3`), yuklangan fayllar (`media/`) va yig'ilgan static
  (`staticfiles/`) versiyalanmaydi.
- Bot tokeni, `DJANGO_SECRET_KEY` va karta ma'lumotlari faqat muhit o'zgaruvchilari orqali
  beriladi.
