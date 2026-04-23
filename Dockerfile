# syntax=docker/dockerfile:1.7

# ==============================================================================
# Stage 1 — Viewer build (Vite / pnpm).
# ==============================================================================
FROM node:20-alpine AS viewer-build

RUN corepack enable
WORKDIR /app

# Workspace manifests first so the layer cache works for repeated rebuilds.
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY viewer/package.json viewer/
COPY web/core/package.json web/core/

RUN pnpm install --frozen-lockfile

# Source for viewer + the vendored Kaggle core that viewer imports.
COPY viewer/ viewer/
COPY web/ web/

# Build viewer → viewer/dist (served as static by the Python backend).
RUN pnpm --filter @orbit-wars-lab/viewer build

# ==============================================================================
# Stage 2 — Python runtime (FastAPI + tournament runner).
# ==============================================================================
FROM python:3.12-slim

# git for installing kaggle-environments from GitHub master; build-essential
# for any wheels that need compilation. Cleared after pip install.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code + zoo + leaderboard seed.
COPY orbit_wars_app/ orbit_wars_app/
COPY agents/ agents/
COPY runs/ runs/

# Prebuilt viewer bundle from stage 1 — backend mounts this on '/'.
COPY --from=viewer-build /app/viewer/dist viewer/dist

EXPOSE 8000
CMD ["uvicorn", "orbit_wars_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
