# ── Stage 1: Build frontend ───────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder
WORKDIR /app/web
COPY web/package*.json ./
RUN npm ci --silent
COPY web/ ./
RUN npm run build

# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first (layer cache)
COPY pyproject.toml ./
COPY comobot/ ./comobot/
COPY bridge/ ./bridge/
RUN pip install --no-cache-dir . && \
    pip cache purge

# Frontend static files
COPY --from=frontend-builder /app/web/dist ./web/dist

# Data directory
RUN mkdir -p /root/.comobot/workspace

EXPOSE 18790

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:18790/api/health || exit 1

CMD ["comobot", "gateway"]
