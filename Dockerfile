# Stage 1: Build Vue frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
RUN npm run build

# Stage 2: Build WhatsApp bridge
FROM node:20-slim AS bridge-builder
WORKDIR /app/bridge
COPY bridge/package.json bridge/package-lock.json* ./
RUN npm install
COPY bridge/ ./
RUN npm run build

# Stage 3: Final image
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install Node.js 20 runtime only (no build tools)
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg git && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get purge -y gnupg && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p comobot bridge && touch comobot/__init__.py && \
    uv pip install --system --no-cache . && \
    rm -rf comobot bridge

# Copy Python source and install
COPY comobot/ comobot/
RUN uv pip install --system --no-cache .

# Copy pre-built bridge (runtime only, no node_modules rebuild)
COPY --from=bridge-builder /app/bridge/dist/ bridge/dist/
COPY --from=bridge-builder /app/bridge/node_modules/ bridge/node_modules/
COPY --from=bridge-builder /app/bridge/package.json bridge/

# Copy pre-built frontend into the location the app expects
COPY --from=frontend-builder /app/web/dist/ web/dist/

# Create data directory
RUN mkdir -p /root/.comobot

# Volumes for persistent data
VOLUME ["/root/.comobot"]

# Gateway default port
EXPOSE 18790

ENTRYPOINT ["comobot"]
CMD ["gateway"]
