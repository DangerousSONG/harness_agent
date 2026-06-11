"""Production entry point.

Imports the FastAPI ``app`` from :mod:`web.server` and:

1. Registers a lightweight ``GET /api/health`` liveness endpoint at
   the path the platform manifest, Dockerfile HEALTHCHECK, and Helm
   chart probes all reference. The endpoint returns ``{"status":
   "ok"}`` synchronously, so the kubelet probes can hit it without
   ever exercising business logic.
2. When a built ``web/ui/dist`` is present (the Dockerfile copies it
   in during the multi-stage build), mounts the bundle as the static
   frontend with an SPA-style ``index.html`` fallback so React Router
   URLs survive a hard refresh.

The base ``web.server`` module is intentionally left untouched, so
the test suite keeps driving it the same way it always has.

Usage::

    uvicorn web.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from web.server import app

_HERE = Path(__file__).resolve().parent
_UI_DIST = _HERE / "ui" / "dist"


# --------------------------------------------------------------- health


@app.get("/api/health", include_in_schema=False)
def _health() -> JSONResponse:
    """Cheap liveness probe used by Docker HEALTHCHECK, Helm probes,
    and the platform manifest contract. Must never touch business
    state — return as fast as possible so the kubelet's tight loop
    doesn't fight for I/O with real requests."""
    return JSONResponse({"status": "ok"})


# --------------------------------------------------- static frontend


def _mount_static_frontend() -> None:
    """Wire the built UI when it's available.

    If ``web/ui/dist`` is missing (e.g. running tests, or running the
    server locally with ``npm run dev`` for the frontend), this is a
    no-op and the API still works on its own.
    """
    if not _UI_DIST.is_dir() or not (_UI_DIST / "index.html").is_file():
        return

    # ``/assets`` is where Vite emits the hashed JS / CSS bundle, so
    # mount that as a real ``StaticFiles`` directory for proper
    # caching headers + content types.
    assets_dir = _UI_DIST / "assets"
    if assets_dir.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=assets_dir),
            name="ui-assets",
        )

    # Catch-all: any path that didn't match an API route returns a
    # file from the dist directory when one exists (so /favicon.ico /
    # /robots.txt etc. still resolve), otherwise the SPA index.html.
    # FastAPI matches routes in registration order; because all /api/*
    # routes were registered inside ``create_app()`` *before* we ran
    # this, they keep priority over this fallback.
    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa_fallback(full_path: str = "") -> FileResponse:
        if full_path.startswith("api/"):
            # API path that didn't match a concrete route is a real
            # 404 — do not silently swallow it with index.html.
            raise HTTPException(status_code=404)
        candidate = _UI_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_UI_DIST / "index.html")


_mount_static_frontend()
