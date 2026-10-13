# syntax=docker/dockerfile:1

# --------------------------------------------------------------------------
# Build the SPA
# --------------------------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app

# nginx serves the SPA and proxies the Django API on the same origin, so the
# client only needs a relative base URL (no CORS in production). Override the
# build arg to point the bundle at another host.
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# --------------------------------------------------------------------------
# Serve it
# --------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# The reverse proxy for /api, /admin, /static and /media lives in this file, so
# the SPA and the API are always the same origin.
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
