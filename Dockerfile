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
# Stage 2 — Python dep builder.
#
# Compiles every Python dependency into a wheel, then the runtime stage copies
# just the wheels + installs them without ever seeing a C compiler. Saves
# ~300 MB off the final image vs. installing build-essential into runtime.
# ==============================================================================
FROM python:3.12-slim AS py-build

RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt ./
RUN pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt

# ==============================================================================
# Stage 3 — Python runtime (FastAPI + tournament runner).
# ==============================================================================
FROM python:3.12-slim

# `git` is still needed at runtime ONLY so `pip install -e .` below can parse
# the kaggle-environments VCS ref embedded in pyproject.toml's `dependencies`.
# No build-essential — wheels are already built.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=py-build /wheels /wheels
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

# Application code + zoo + leaderboard seed.
COPY orbit_wars_app/ orbit_wars_app/
COPY agents/ agents/
COPY runs/ runs/

# Register the package + console_scripts entry points from pyproject.toml
# (`orbit-wars-tournament` CLI). --no-deps because deps are already installed.
RUN pip install --no-cache-dir --no-deps -e .

# Prebuilt viewer bundle from stage 1 — backend mounts this on '/'.
COPY --from=viewer-build /app/viewer/dist viewer/dist

# Non-root user so files written to the mounted ./agents and ./runs on the
# host match the host's user instead of coming out root-owned. compose.yml
# overrides UID/GID to the host user's (defaulting to 1000 which matches
# most Linux installs; macOS users set UID=501 in a .env file).
RUN useradd --create-home --uid 1000 --shell /bin/bash app \
    && chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health').read()" || exit 1
CMD ["uvicorn", "orbit_wars_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
