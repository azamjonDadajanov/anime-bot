# Production deploy (Docker + nginx)

Bitta `docker compose` steki to'rt xizmatdan iborat:

| Xizmat  | Vazifasi                                                                 |
| ------- | ------------------------------------------------------------------------ |
| `db`    | PostgreSQL 17 (ma'lumotlar `pgdata` volume'da)                            |
| `web`   | Django + gunicorn (`:8000`), konteyner ishga tushishida migratsiya + `collectstatic` |
| `bot`   | `python manage.py runbot` — aiogram long-polling (faqat bitta replika!)   |
| `nginx` | Qurilgan SPA'ni beradi, `/api`, `/admin` ni `web` ga proxy qiladi, `/static` va `/media` ni to'g'ridan-to'g'ri volume'dan uzatadi |

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
`SECURE_PROXY_SSL_HEADER` orqali o'qiydi, shuning uchun `/admin/` CSRF tekshiruvi
va absolute havolalar `https` bo'lib qoladi.

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
- `manage.py check --deploy` qolgan ogohlantirishlar HTTPS yoqilgandan keyin
  hal qilinadi (shuning uchun kodda standart holicha qoldirilgan):
  `SECURE_SSL_REDIRECT=True`, `SECURE_HSTS_SECONDS=31536000`
  (+`SECURE_HSTS_INCLUDE_SUBDOMAINS`), `SESSION_COOKIE_SECURE=True`,
  `CSRF_COOKIE_SECURE=True`. HSTS'ni ehtiyotkorlik bilan yoqing — uni bekor
  qilish qiyin.
