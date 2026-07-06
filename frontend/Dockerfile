# syntax=docker/dockerfile:1.6
#
# ─── UBOS web (CRA build → nginx) ────────────────────────────────────────
#
# Stage 1 — build the React app.
# We build with REACT_APP_BACKEND_URL="" so axios uses a relative base and
# every /api/* call goes through the nginx in stage 2 (which reverse-proxies
# to the backend container). This keeps the deployment same-origin — no CORS.

FROM node:20-alpine AS build

WORKDIR /app/frontend

# Cache-friendly deps install.
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile

COPY . .

# Empty base → axios uses relative /api/* through nginx.
ARG REACT_APP_BACKEND_URL=""
ARG REACT_APP_ENABLE_SW="1"
ENV REACT_APP_BACKEND_URL=${REACT_APP_BACKEND_URL} \
    REACT_APP_ENABLE_SW=${REACT_APP_ENABLE_SW} \
    ENABLE_HEALTH_CHECK=false \
    NODE_OPTIONS=--openssl-legacy-provider \
    CI=false

RUN yarn build

# ─── Stage 2 — nginx runtime ─────────────────────────────────────────────

FROM nginx:1.27-alpine

# Static assets.
COPY --from=build /app/frontend/build /usr/share/nginx/html

# SPA fallback + /api/* → backend proxy.
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://localhost/ >/dev/null 2>&1 || exit 1

CMD ["nginx", "-g", "daemon off;"]
