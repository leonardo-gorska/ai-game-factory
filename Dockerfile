# ─────────────────────────────────────────────────
# GORVAX GAME FACTORY — Dockerfile
# Multi-stage build: Python backend + Node.js apps
# ─────────────────────────────────────────────────

# ── Stage 1: Node.js dependencies ────────────────
FROM node:20-slim AS node-deps

# Dashboard
WORKDIR /app/dashboard
COPY dashboard/package*.json ./
RUN npm ci --silent

# Game
WORKDIR /app/game
COPY game/package*.json ./
RUN npm ci --silent


# ── Stage 2: Runtime ─────────────────────────────
FROM python:3.12-slim

# System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        nodejs \
        npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy node_modules from builder stage
COPY --from=node-deps /app/dashboard/node_modules ./dashboard/node_modules
COPY --from=node-deps /app/game/node_modules ./game/node_modules

# Copy application code
COPY backend/ ./backend/
COPY game/ ./game/
COPY dashboard/ ./dashboard/
COPY start.py ./start.py
COPY pyproject.toml ./pyproject.toml

# Create required directories
RUN mkdir -p backend/storage/iterations data/memory data/screenshots

# Copy .env.example if it exists (user must provide .env)
COPY .env.example* ./

# Default environment
ENV BACKEND_PORT=8000
ENV DASHBOARD_PORT=3000
ENV GAME_PORT=5173
ENV LOG_LEVEL=INFO
ENV PYTHONUNBUFFERED=1

# Expose ports
EXPOSE 8000 3000 5173

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:${BACKEND_PORT}/api/v1/health || exit 1

# Start all services
CMD ["python", "start.py"]
