# syntax=docker/dockerfile:1

# --------------------------------------------------------------------------
# Build the SPA
# --------------------------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app

# nginx serves the SPA on anichopar.uz while the API lives on api.anichopar.uz
# (see ../docker-compose.yml), so production passes a scheme-relative base URL.
# The /api default only fits a same-origin setup without that split.
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

# The reverse proxy lives in this file: anichopar.uz gets the SPA, /static,
# /media and /django-admin, admin.anichopar.uz gets the panel SPA as its
# document, api.anichopar.uz gets /api. anichopar.uz/admin and
# anichopar.uz/api are refused (the panel route in App.jsx is dev-only).
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
