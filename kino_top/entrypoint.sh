#!/bin/sh
# Container entrypoint for the Django image.
#
# The deploy steps run only when RUN_SETUP=1 (set for the `web` service), so the
# bot container reuses the same image without racing the migration. `docker
# compose up -d --build` therefore provisions an empty host by itself.
set -e

if [ "${RUN_SETUP:-0}" = "1" ]; then
    echo "[entrypoint] applying database migrations"
    python manage.py migrate --noinput

    echo "[entrypoint] collecting static files"
    # Hashed, compressed files land in STATIC_ROOT, which nginx serves from the
    # shared volume at /var/www/static.
    python manage.py collectstatic --noinput

    echo "[entrypoint] repairing legacy base64 covers"
    # Idempotent: turns whatever the base64 era left behind (payload text in an
    # already written file, or a payload still sitting in `cover_blob`) into a
    # real image under media/covers/ that nginx can serve. It only reports rows
    # it cannot repair, and `||` keeps a cover problem from blocking the boot.
    python manage.py fix_covers || echo "[entrypoint] fix_covers reported problems (see above)"
fi

exec "$@"
