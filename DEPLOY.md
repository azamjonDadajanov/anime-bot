# Production deploy (Docker + nginx)

Bitta `docker compose` steki to'rt xizmatdan iborat:

| Xizmat  | Vazifasi                                                                 |
| ------- | ------------------------------------------------------------------------ |
| `db`    | PostgreSQL 17 (ma'lumotlar `pgdata` volume'da)                            |
| `web`   | Django + gunicorn (`:8000`), konteyner ishga tushishida migratsiya + `collectstatic` |
| `bot`   | `python manage.py runbot` — aiogram long-polling (faqat bitta replika!)   |
| `nginx` | Qurilgan SPA'ni beradi (`/admin` — React panel), `/api` va `/django-admin` ni `web` ga proxy qiladi, `/static` va `/media` ni to'g'ridan-to'g'ri volume'dan uzatadi |

## 1. Sozlash

```bash
cp .env.production.example .env
# .env ichida kamida quyidagilarni to'ldiring:
#   DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS,
#   CORS_ALLOWED_ORIGINS, DB_PASSWORD, BOT_TOKEN, ADMIN_IDS, BOT_SITE_URL
```

`.env` fayl git'ga tushmaydi va image ichiga ham ko'chirilmaydi
(`.dockerignore`, `.gitignore`).

## 2. Ishga tushirish

```bash
docker compose up -d --build
docker compose logs -f web          # migratsiya tugaganini kuzatish
docker compose ps                   # barcha xizmatlar "healthy" bo'lishi kerak
```

`web` konteyneri healthcheck'i `/api/schema/` manzilini so'raydi; bot esa faqat
`web` sog'lom bo'lgach ishga tushadi, shuning uchun migratsiyasiz baza bilan
to'qnashmaydi.

Administrator hisobini yaratish:

```bash
docker compose exec web python manage.py createsuperuser
```

## 3. Domen va HTTPS

TLS'ni ikki yo'l bilan ulash mumkin:

1. **Tashqi proxy** (Caddy, Traefik, host nginx, Cloudflare) — 80-portni u yerga
   bering va shu stekni orqasiga qo'ying.
2. **Shu nginx ichida** — sertifikatni mount qilib, `frontend/nginx.conf` oxiridagi
   izohda ko'rsatilgan `443 ssl` blokini qo'shing.

Har ikki holatda `X-Forwarded-Proto` uzatiladi; Django uni
`SECURE_PROXY_SSL_HEADER` orqali o'qiydi, shuning uchun `/django-admin/` CSRF
tekshiruvi va absolute havolalar `https` bo'lib qoladi.

Port band bo'lsa `.env` da `HTTP_PORT=8080` qilib o'zgartiring.

## 4. Yangilash va zaxiralash

```bash
git pull
docker compose up -d --build        # web migratsiyani o'zi qo'llaydi
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > backup-$(date +%F).sql
docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < backup.sql
```

(Tirnoqlar muhim: `$POSTGRES_*` konteyner ichida emas, `sh` ichida kengaytiriladi.)

Fayllar: `media` (manga PDF'lari va muqovalar) va `static` (collectstatic
chiqishi) nomlangan volume'larda saqlanadi; ular `frontend` konteyneriga
faqat-o'qish uchun ulanadi.

## 5. Tekshirish

```bash
curl -I http://localhost/                 # 200, SPA index.html
curl -I http://localhost/admin/game-ratings   # 200, SPA (React panel) — Django admin EMAS
curl -I http://localhost/django-admin/    # 302, Django admin login
curl -I http://localhost/api/schema/      # 200, DRF sxema
curl -I http://localhost/static/admin/css/base.css   # nginx beradi, DEBUG=false da ham
docker compose exec web python manage.py check --deploy
```

## Eslatmalar

- `bot` xizmatini hech qachon bir nechta replikada ishga tushirmang
  (`--scale bot=2` Telegram'da `Conflict` xatosiga olib keladi).
- `DJANGO_DEBUG=false` bo'lganda Django static/media'ni o'zi bermaydi; ularni
  nginx uzatadi, shuning uchun `collectstatic` har deploy'da ishlashi shart
  (`web` konteynerining entrypoint'i buni bajaradi).
- Media yuklash hajmi `DATA_UPLOAD_MAX_MEMORY_SIZE` (512 MB) bilan cheklangan,
  nginx tomonida `client_max_body_size 512m` bilan moslashtirilgan.
- **Oylik o'yin mukofoti** uchun cron qo'ying (har oyining 1-si, 06:00 da oldingi
  oy g'olibini e'lon qiladi; bir xil oy uchun ikki marta ishga tushirsa ham
  mukofot takrorlanmaydi):

  ```cron
  0 6 1 * * cd /app && python manage.py award_game_monthly_prize
  ```

  Qo'lda boshqa oy uchun: `python manage.py award_game_monthly_prize --year 2026 --month 9`.
- **AI qidiruv** (semantic qidiruv, obunachilar uchun) model fayllarini va
  indeksni talab qiladi. Modelni bir marta yuklab oling (u `aimodels` volume'da
  saqlanadi va `web` bilan `bot` uni bo'lishadi):

  ```bash
  docker compose run --rm web python manage.py index_anime_embeddings --download-model
  docker compose run --rm web python manage.py index_anime_embeddings    # indeksni yig'ish
  docker compose exec web python manage.py index_anime_embeddings --status
  ```

  Modelni image ichiga "pishirish" ham mumkin (internetsiz deploy uchun):
  `docker build --build-arg AI_MODEL=1 ./kino_top` — bunda volume birinchi
  yaratilganda image'dagi fayllar undan nusxalanadi.

  Kunlik kontent qo'shilsa/tahrirlansa indeks avtomatik yangilanadi (signal'lar),
  shuning uchun cron shart emas. Faqat ommaviy import (masalan `import_kawaii`)
  paytida AI o'chirilgan bo'lsa, keyin bir marta indekslash foydali:

  ```cron
  0 4 * * * cd /app && python manage.py index_anime_embeddings
  ```

  Sozlamalar: `AI_SEARCH_ENABLED`, `AI_MODEL_DIR`, `AI_MODEL_FILE`,
  `AI_SEARCH_TOP_K`, `AI_SEARCH_MIN_SCORE`. Model ~470MB fp32 ONNX; kam resursli
  server uchun `AI_MODEL_FILE=onnx/model_quint8_avx2.onnx` (~118MB, x86 AVX2;
  ARM uchun `onnx/model_qint8_arm64.onnx`) va faylni `--download-model` bilan
  yuklab oling.

  **Fikrlash modeli ("fikrlash" qadami)**: encoder kontentni topadi, chat
  modeli esa mos keladiganlarini tanlaydi, tartibini aniqlaydi va o'zbekcha
  qisqa javob yozadi.

  Bir provayder — bitta nosozlik nuqtasi (bepul limit tugaydi, kalit bloklanadi,
  endpoint javob bermaydi). Shuning uchun fikrlash qadami bitta kalitga emas,
  **provayderlar zanjiriga** bog'langan; zanjir `.env`dan emas, **bazadan**
  o'qiladi (`/django-admin/` → *AI provayderlar*), ya'ni kalit qo'shish yoki
  tartibini o'zgartirish uchun qayta deploy kerak emas:

  ```text
  /django-admin/ → AI provayderlar
    1) Groq (asosiy)     priority=1   api_key=gsk_...   is_active=✓
    2) Gemini (zaxira)   priority=2   api_key=AIza...   is_active=✓
    3) OpenAI (oxirgi)   priority=3   api_key=sk-...    is_active=✓
  ```

  Xatti-harakat: so'rov **bittalab**, ustuvorlik tartibida yuboriladi (hech
  qachon ikkitasiga birdaniga emas); biri "limit" (402/429) yoki timeout
  qaytarsa, avtomatik keyingisiga o'tiladi va o'sha provayder kutishga
  qo'yiladi — buni butun zanjir ko'radi, keyingi so'rovlar uni qayta urinmaydi
  ham, kutmaydi ham. Zanjir to'liq kutishda bo'lsa, qidiruv darhol vektor
  natijalari bilan javob beradi (tarmoqqa umuman murojaat qilinmaydi).

  Jadval bo'sh bo'lsa, eski `.env` usuli ishlayveradi (zaxira variant):

  ```bash
  AI_LLM_PROVIDER=groq      # bepul developer tarifi, eng tez javob (~1-3 s)
  AI_LLM_API_KEY=gsk_...    # https://console.groq.com/keys
  # AI_LLM_PROVIDER=gemini | openai | custom (+ AI_LLM_BASE_URL)
  ```

  Standart modellar: `groq` → `qwen/qwen3.8-27b`, `gemini` →
  `gemini-3.5-flash-lite`, `openai` → `gpt-6-luna` (kerak bo'lsa `AI_LLM_MODEL`
  bilan almashtiriladi). Kalit `.env`da saqlanadi — repoga tushmaydi.
  Tekshirish:

  ```bash
  python manage.py index_anime_embeddings --status     # zanjir, kalit, kutish
  python manage.py index_anime_embeddings --test-llm   # bitta real so'rov
  ```

  `--test-llm` haqiqiy so'rov yuboradi va qaysi provayder javob berganini,
  qancha vaqt ketganini va qaysi biri o'tkazib yuborilganini ko'rsatadi.

  Diqqat: fikrlash qadami **ixtiyoriy**. Kalit bo'lmasa, hamma provayder
  limitda bo'lsa yoki zanjir javob bermasa, qidiruv vektor natijalari bilan
  qaytadi — foydalanuvchi bo'sh ekran ko'rmaydi. Vaqt byudjeti qat'iy:
  `AI_LLM_TIMEOUT` (standart 8 s) — bitta provayder uchun, `AI_LLM_DEADLINE`
  (standart 12 s) — butun zanjir uchun; shuning uchun o'lik provayderlar
  ketma-ket javob kutishni cho'zib yubormaydi. Bitta so'rov uchun sarf kichik:
  so'rov + eng ko'pi 20 nomzod yuboriladi, bir xil so'rov 2 daqiqa davomida
  keshlanadi, javob uzunligi ~900 tokenga cheklangan.

  **Chegarani tanlash (o'lchangan)**: 33 sarlavhali katalogda real model bilan
  o'lchandi — mavzuga oid so'rovlarda eng yaxshi natijalar 0.70-0.84, hech qanday
  aloqasi yo'q so'rovlarda esa eng yuqori ball 0.42 dan oshmadi ("bugungi ob-havo
  qanday" → 0.41, "zzz qqq xxx" → 0.42). Shu sababli standart
  `AI_SEARCH_MIN_SCORE=0.45` shu bo'shliqqa qo'yilgan: aloqasiz so'rov bo'sh
  qaytadi, mos kontent esa tashlab yuborilmaydi. Katalog kattalashgani sari
  ballar biroz pasayishi mumkin — yangi kontent qo'shgandan keyin bir marta
  tekshirib ko'ring (`index_anime_embeddings --status`) va kerak bo'lsa
  chegarani 0.40 ga tushiring. Javobda har doim jami nechta mos kontent
  topilgani ham qaytariladi (`total`), shuning uchun foydalanuvchi ro'yxat
  qisqartirilganini biladi.

  Model birinchi so'rovda xotiraga yuklanadi (~6 s), keyin bitta qidiruv
  ~10 ms (CPU); indeks bir marta yuklanib, o'zgargan taqdirdagina qayta
  o'qiladi.
- **Obuna eslatmalari** uchun kuniga bir marta cron qo'ying (obuna tugashiga 3 kun
  qolganda va muddati o'tgandan keyin 7 kun ichida foydalanuvchiga Telegramdan
  eslatma yuboradi; har bir bosqich faqat bir marta yuboriladi, shuning uchun bu
  buyruqni tez-tez ishga tushirish ham spam qilmaydi):

  ```cron
  0 9 * * * cd /app && python manage.py send_subscription_reminders
  ```

  Avval kimga yuborilishini ko'rish uchun: `python manage.py send_subscription_reminders --dry-run`.
  Eslatma yuborilmasa (masalan, Telegram xatosi) yozuv belgilanmaydi va keyingi
  ishga tushirishda qayta uriniladi. Eslatma matni va muddatlari
  `users/reminders.py` da (`REMIND_BEFORE_DAYS`, `REMIND_AFTER_DAYS`).
- `manage.py check --deploy` qolgan ogohlantirishlar HTTPS yoqilgandan keyin
  hal qilinadi (shuning uchun kodda standart holicha qoldirilgan):
  `SECURE_SSL_REDIRECT=True`, `SECURE_HSTS_SECONDS=31536000`
  (+`SECURE_HSTS_INCLUDE_SUBDOMAINS`), `SESSION_COOKIE_SECURE=True`,
  `CSRF_COOKIE_SECURE=True`. HSTS'ni ehtiyotkorlik bilan yoqing — uni bekor
  qilish qiyin.
