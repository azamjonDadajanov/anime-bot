# Production deploy (Docker + nginx)

Bitta `docker compose` steki to'rt xizmatdan iborat:

| Xizmat  | Vazifasi                                                                 |
| ------- | ------------------------------------------------------------------------ |
| `db`    | PostgreSQL 17 (ma'lumotlar `pgdata` volume'da)                            |
| `web`   | Django + gunicorn (`:8000`), konteyner ishga tushishida migratsiya + `collectstatic` + muqovalarni tuzatish (`fix_covers`) |
| `bot`   | `python manage.py runbot` — aiogram long-polling (faqat bitta replika!)   |
| `nginx` | Uch hostni bitta konteynerda beradi: `anichopar.uz` → SPA + `/static` + `/media` + `/django-admin` (`/admin` va `/api` **404**), `admin.anichopar.uz` → React panel o'z boshiga document sifatida, `api.anichopar.uz` → `/api` ni `web` ga proxy qiladi. **TLS shu yerda**: 80 va 443 bir xil kontent beradi, sertifikat `/etc/letsencrypt` dan (certbot) olinadi |

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

## 3. Domen, sertifikat va HTTPS

TLS **nginx konteynerida** tugatiladi: `certbot` host'da bitta sertifikat oladi
(barcha besh nom uchun), compose esa `/etc/letsencrypt` ni read-only konteynerga
ulaydi va `frontend/nginx.conf` uni 443 da ishlatadi. Shuning uchun `docker
compose up` dan **oldin** ikki shart bajarilishi kerak:

1. **Sertifikat olingan bo'lishi** (yo'q bo'lsa nginx konteyneri ishga
   tushmaydi — bu ataylab qilingan):

   ```bash
   sudo certbot --nginx -d anichopar.uz -d www.anichopar.uz -d admin.anichopar.uz -d bot.anichopar.uz -d api.anichopar.uz
   ```

2. **Host nginx 80/443 ni egallamasligi** — portlar konteynerga tegishli.
   Certbot `--nginx` installer'i bilan yozgan konfiguratsiyasi keyin aralashmasligi
   uchun host xizmatini o'chirib qo'ying (portni faqat shu bilan bo'shatish
   mumkin, `ai_agent` sudo'siz `systemctl` ishlatolmaydi):

   ```bash
   sudo systemctl disable --now nginx
   ```

   Host nginx ishlab turgan bo'lsa, konteyner `port is already in use` bilan
   tinmaydi va sayt umuman ochilmaydi.

DNS recordlari (barchasi bir xil serverga, Cloudflare proxy **yoqilgan** holda):

```text
anichopar.uz   A  37.60.237.72
www            A  37.60.237.72
bot            A  37.60.237.72
admin          A  37.60.237.72   # panel: admin.anichopar.uz/
api            A  37.60.237.72   # REST API: api.anichopar.uz/api/...
```

`api` recordi shart: SPA `//api.anichopar.uz/api` ga chaqiradi va
`anichopar.uz/api` nginx'da 404.

Edge'ning SSL mode'i ikkala holatda ham ishlaydi:

- **Flexible** (edge → origin oddiy http:80): konteyner 80-urinishga ham 443-dagi
  kontentni beradi va **hech qayerga redirect qilmaydi**. Redirect shu mode'da
  cheksiz loopga aylanadi: https so'rov edge orqali yana origin:80 ga tushadi va
  `301 https://…` ni qayta oladi (sayt ochilmaydigan holat — aynan shu bo'lib
  turgan edi).
- **Full / Full (strict)** (edge → origin https:443): shu sertifikat
  ko'rsatiladi, Strict'da ham Let's Encrypt zanjiri to'g'ri keladi. Origin TLS'ni
  haqiqatan ishlatmoqchi bo'lsangiz shu mode'ga o'ting.

Har qanday proxy holatida `X-Forwarded-Proto` uzatiladi; Django uni
`SECURE_PROXY_SSL_HEADER` orqali o'qiydi, shuning uchun `/django-admin/` CSRF
tekshiruvi va absolute havolalar to'g'ri sxemada bo'lib qoladi. To'g'ridan-to'g'ri
443 ga urilgan so'rovda header bo'lmaydi, lekin `frontend/nginx.conf` dagi
`$anichopar_proto` xaritasi `$scheme` ga tushadi — yana https.

Port band bo'lsa `.env` da `HTTP_PORT` / `HTTPS_PORT` ni o'zgartiring
(Cloudflare'da record ham shu portga qarab ishlaydi — odatda 80/443 ni
o'zgartirmang).

### Sertifikatni yangilash

Renewal host'dagi `certbot.timer` tomonidan avtomatik bajariladi
(~30 kun qolganda), lekin `nginx` authenticator o'rniga **webroot** ishlatiladi —
host nginx o'chirilgani uchun challenge'ni u portda bera olmaydi. Bu ikki fayl
konfiguratsiyada (root, bir marta qo'yiladi):

```text
/etc/letsencrypt/renewal/anichopar.uz.conf
    [renewalparams]
    authenticator = webroot
    webroot_path = /home/ai_agent/anime-bot/certbot-www

/etc/letsencrypt/renewal-hooks/deploy/reload-anichopar-nginx   # 0755
    # sertifikat yangilangandan keyin konteyner nginx'ini qayta yuklaydi
```

`certbot-www` xostda yaratiladi, compose uni `/var/www/certbot` ga read-only
ulaydi va `/.well-known/acme-challenge/` shu yerdan o'qiladi (to'liq oqim:
edge → origin:80 → konteyner → token fayli). Tekshirish:

```bash
sudo certbot renew --dry-run
```

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
curl -I http://localhost/admin/game-ratings   # 404 — panel endi admin.anichopar.uz da
curl -I -H 'Host: admin.anichopar.uz' http://localhost/login  # 200, panel SPA login
curl -I http://localhost/django-admin/    # 302, Django admin login
curl -I -H 'Host: api.anichopar.uz' http://localhost/api/schema/  # 200, DRF sxema
curl -I http://localhost/api/schema/      # 404 — API faqat api.anichopar.uz da
curl -I http://localhost/static/admin/css/base.css   # nginx beradi, DEBUG=false da ham
curl -I http://localhost/media/tlhxlgfj   # 200, SPA media sahifasi (deep link)

# TLS konteynerda: 80 ham, 443 ham bir xil kontent beradi (80 da redirect
# bo'lmasligi kerak — Flexible'da u loopga aylanadi)
curl -skI -H 'Host: anichopar.uz' https://localhost/                  # 200
curl -skI -H 'Host: api.anichopar.uz' https://localhost/api/schema/   # 200
curl -sI  -H 'Host: anichopar.uz' http://localhost/                   # 200 (redirect yo'q)
curl -svo /dev/null -H 'Host: anichopar.uz' https://localhost/ 2>&1 | grep -E 'subject:|expire date'   # Let's Encrypt

docker compose exec web python manage.py check --deploy

# tashqaridan (DNS+Cloudflare sozlangan bo'lsa):
curl -sI https://anichopar.uz/            # 200
curl -sI https://admin.anichopar.uz/login # 200
curl -s  https://api.anichopar.uz/api/schema/ | head -c 200
# oldin: infinite 301 loop edi (origin:80 redirect qilardi, edge esa Flexible
# bilan yana origin:80 ga kelardi) — endi 200 bo'lishi shart
```

## Eslatmalar

- `bot` xizmatini hech qachon bir nechta replikada ishga tushirmang
  (`--scale bot=2` Telegram'da `Conflict` xatosiga olib keladi).
- `DJANGO_DEBUG=false` bo'lganda Django static/media'ni o'zi bermaydi; ularni
  nginx uzatadi, shuning uchun `collectstatic` har deploy'da ishlashi shart
  (`web` konteynerining entrypoint'i buni bajaradi).
- Media yuklash hajmi `DATA_UPLOAD_MAX_MEMORY_SIZE` (512 MB) bilan cheklangan,
  nginx tomonida `client_max_body_size 512m` bilan moslashtirilgan.
- **Muqovalar** (`media/covers/`) va **manga sahifalari** (`media/manga/pages/`)
  nginx tomonidan 1 yillik `immutable` kech bilan uzatiladi. PDF qayta
  yuklanganda `?v=` tokeni o'zgaradi, shuning uchun brauzer eski faylni qayta
  olmaydi — qayta render uchun `mediaApi.partPagesMeta` ni invalidate qilish
  yetarli.
- Eski `cover` BinaryField'ida base64 matn ko'rinishida turgan muqovalar
  `migrate` (0019) da faylga aylanadi, keyin har bir deploy'da
  `python manage.py fix_covers` qoldiq payloadlarni ham tuzatadi:
  idempotent, qatorlarni alohida ko'radi va hech qachon boot'ni to'xtatmaydi.
  Qo'lda ishga tushirish: `--dry-run` (faqat hisobot), `--slug <x>` (bitta
  sarlavha), `--strict` (tuzatilmagan qator qolsa xato kod).
- PDF sahifalari birinchi so'rovda serverda render qilinadi (`pages` API
  `ensure_pages` chaqiradi), keyin brauzer faqat nginx'dan rasm oladi. PDF'ni
  brauzerda yuklab olish (pdf.js) olib tashlangan; API dagi `page_image`
  endpointi nginx faylni topa olgandagina fallback sifatida qolgan.
- `media/manga/render/` ishchi katalogi (xom PDF'lar) nginx'dan yashirin —
  `/media/manga/` yo'nalishi to'g'ridan-to'g'ri `return 404` qiladi, faqat
  `pages/` `^~` qoidalari orqali ochiladi.
- Himoya qatlami: auth endpointlari 5 r/m (`anichopar_auth`), API 25 r/s +
  64 bir vaqtdagi ulanish (`limit_conn`), skaner agentlari (sqlmap, masscan
  va h.k.) 403, `/wp-admin` kabi tez-tez uriladigan yo'llar `444`, `.env` kabi
  nuqtali fayllar `404`. Cheklovlar Cloudflare proxied so'rovlarda ham
  haqiqiy mijoz bo'yicha ishlaydi (`CF-Connecting-IP` map'i), aks holda butun
  sayt bitta edge IP bilan umumiy byudjetda bo'lib qolardi. Sarlavha/CSP
  nginx'da `location = /index.html` da (SPA yo'llari `try_files` orqali shu
  yerga kiradi), `connect-src` da API hosti ham bor (http varianti ham qoldirilgan —
  edge Flexible'da yoki to'g'ridan-to'g'ri kirilganda ham ishlaydi). TLS konteynerda
  (3-bosqich qarang); `DJANGO_SECURE_*` o'zgaruvchilarini esa faqat edge Full'ga
  o'tganda `.env.production.example` dagi izohlarga qarab yoqing.
- **Oylik o'yin mukofoti** uchun cron qo'ying (har oyining 1-si, 06:00 da oldingi
  oy g'olibini e'lon qiladi; bir xil oy uchun ikki marta ishga tushirsa ham
  mukofot takrorlanmaydi):

  ```cron
  0 6 1 * * cd /app && python manage.py award_game_monthly_prize
  ```

  Qo'lda boshqa oy uchun: `python manage.py award_game_monthly_prize --year 2026 --month 9`.
- **AI yordamchi (AniVoy, obunachilar uchun)**: offline model ham, indeks ham
  yo'q — yordamchi faqat online chat modeli bilan ishlaydi va kerakli
  ma'lumotni katalog funksiyalarini chaqirib oladi (`movies.ai_assistant`).
  Shuning uchun deploy'da yuklab olinadigan ~470MB model, `aimodels` volume va
  indekslash cron'i yo'q.

  Bitta provayder — bitta nosozlik nuqtasi (bepul limit tugaydi, kalit
  bloklanadi, endpoint javob bermaydi). Shuning uchun model bitta kalitga emas,
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
  ham, kutmaydi ham. Zanjir to'liq kutishda bo'lsa, yordamchi tarmoqqa umuman
  murojaat qilmasdan darhol "hozircha javob bera olmaydi" deb xabar qaytaradi —
  offline zaxira yo'l yo'q (ataylab).

  Jadval bo'sh bo'lsa, oddiy `.env` usuli ishlayveradi (zaxira variant):

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
  python manage.py ai_status          # zanjir, kalit, kutish holati
  python manage.py ai_status --test   # bitta real so'rov va chaqirilgan funksiyalar
  ```

  `--test` haqiqiy so'rov yuboradi va qaysi provayder javob berganini, qancha
  vaqt ketganini va qaysi biri o'tkazib yuborilganini ko'rsatadi.

  Vaqt byudjeti qat'iy: `AI_LLM_TIMEOUT` (standart 8 s) — bitta provayder uchun,
  `AI_LLM_DEADLINE` (standart 12 s) — butun zanjir uchun, shuning uchun o'lik
  provayderlar ketma-ket javob kutishni cho'zib yubormaydi. Bitta so'rov uchun
  sarf kichik: funksiya natijalari (eng ko'pi 8-10 sarlavha) yuboriladi, bir xil
  savol 2 daqiqa keshlanadi, javob uzunligi ~900 tokenga cheklangan. Model
  katalogda yo'q nom yoki qism sonini o'ylab topmasligi uchun javob ostidagi
  havolalar faqat funksiyalar qaytargan qatorlardan olinadi.

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
- `manage.py check --deploy` qolgan ogohlantirishlar kodda standart holicha
  qoldirilgan; `.env` dagi `DJANGO_SECURE_*` bilan yoqiladi — lekin faqat
  **har bir** tashrif https orqali kelganda: `DJANGO_SECURE_SSL_REDIRECT=true`,
  `DJANGO_SECURE_COOKIES=true`, `DJANGO_SECURE_HSTS_SECONDS=31536000`
  (+`SECURE_HSTS_INCLUDE_SUBDOMAINS` avtomat). Cloudflare **Flexible** ishlab
  turganda SSL redirect loopga, Secure cookie esa http:// orqali kirgan
  foydalanuvchining `/django-admin/` kirishini buzadi. HSTS'ni eng oxirida
  yoqing — uni bekor qilish qiyin (edge'da o'chirsangiz ham brauzer eslab
  qoladi).
