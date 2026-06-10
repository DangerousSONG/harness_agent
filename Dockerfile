# syntax=docker/dockerfile:1.6
#
# Harness Agent — multi-stage production image.
#
# Stage 1: build the React/Vite frontend into ``web/ui/dist``.
# Stage 2: install the Python backend and copy the built UI in.
#
# The image starts the FastAPI app via ``web.main:app``, which mounts
# the static UI alongside the existing /api/* routes.

# ---------------------------------------------------------- Stage 1
FROM node:20-alpine AS ui-builder
WORKDIR /ui

# Install dependencies first so a source-only change reuses the cache.
COPY web/ui/package.json web/ui/package-lock.json* ./
RUN if [ -f package-lock.json ]; then \
        npm ci --no-audit --no-fund ; \
    else \
        npm install --no-audit --no-fund ; \
    fi

COPY web/ui/ ./
RUN npm run build

# ---------------------------------------------------------- Stage 2
FROM python:3.12-slim AS runtime

# Keep apt + pip quiet and deterministic. ``ca-certificates`` is needed
# for HTTPS calls to OpenAI; ``curl`` is handy for healthchecks.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production \
    HOST=0.0.0.0 \
    PORT=8000

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps before copying source so changes to runtime/
# code don't bust the dependency cache.
COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Copy the backend. ``.dockerignore`` keeps .git / .env / runtime
# directories out of the image.
COPY . ./

# Copy the built frontend from stage 1 into the location ``web/main``
# expects.
COPY --from=ui-builder /ui/dist ./web/ui/dist

# Drop privileges. The runtime needs to be able to read its own code
# and write to the bind-mounted runtime directories; the platform
# is expected to mount those with matching ownership.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin app \
    && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || curl -fsS http://127.0.0.1:8000/ || exit 1

CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "8000"]
