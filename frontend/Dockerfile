# =============================================================================
# SleepReach Frontend — Multi-stage Docker Build
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Base with dependencies
# ---------------------------------------------------------------------------
FROM node:20-alpine AS base
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install

# ---------------------------------------------------------------------------
# Stage 2: Development (hot-reload dev server)
# ---------------------------------------------------------------------------
FROM base AS development
WORKDIR /app
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# ---------------------------------------------------------------------------
# Stage 3: Production build
# ---------------------------------------------------------------------------
FROM base AS builder
WORKDIR /app
COPY . .
RUN npm run build

FROM nginx:alpine AS production
# Remove default Nginx config and use custom SPA-optimised config
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
