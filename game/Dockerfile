# ── Build stage ─────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Dependencies first (layer cache)
COPY package.json package-lock.json ./
RUN npm ci --prefer-offline

# Source
COPY . .

# Production build (VITE_API_BASE_URL points to the Django API)
ARG VITE_API_BASE_URL=//api.anichopar.uz/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# ── Production stage ─────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Remove default nginx config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/game.conf

# Copy built SPA
COPY --from=builder /app/dist /usr/share/nginx/game

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
