# syntax=docker/dockerfile:1
# Production image for the Django project (API, admin and the bot process).
# The SPA is built and served by the nginx image in ../frontend/Dockerfile.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Every dependency (psycopg[binary], aiogram, DRF, whitenoise, gunicorn) ships
# wheels, so no compiler or libpq headers are needed in the image.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# There is no offline model to ship: the AI assistant is an online chat model
# with catalogue tools (movies.ai_assistant), so the image stays small and the
# provider keys live in .env / the AI providers table.

# Named volumes are seeded from the image, so the upload and static directories
# must exist and be writable by the unprivileged user that runs the containers.
# The sed strips CRs so the script also works when the repo is checked out on
# Windows (autocrlf turns the shebang into "/bin/sh^M").
RUN useradd --create-home --uid 10001 app \
    && sed -i 's/\r$//' /app/entrypoint.sh \
    && chmod +x /app/entrypoint.sh \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R app:app /app

USER app

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "kino_top.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
