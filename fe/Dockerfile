# syntax=docker/dockerfile:1.7
# Globetrekker frontend (React + Vite + antd). Targets: `dev` (Vite HMR) and `prod` (nginx static).

ARG NODE_VERSION=22

# ---------- deps ----------
FROM node:${NODE_VERSION}-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci

# ---------- dev ----------
# The source is bind-mounted by docker-compose.override.yml; node_modules stays in the image (anonymous volume).
FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# ---------- build ----------
FROM deps AS build
ARG VITE_API_BASE_URL=/api/v1
ARG VITE_PUBLIC_APP_URL=https://globetrekker.me
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_PUBLIC_APP_URL=${VITE_PUBLIC_APP_URL}
COPY . .
RUN npm run build

# ---------- prod ----------
FROM nginx:1.27-alpine AS prod
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1/healthz || exit 1
