"""
FastAPI entrypoint for the VoltSurge demo application.

Serves:
- Static frontend assets from / (app/static)
- REST APIs under /api

This is a single-container demo app with an in-memory session store.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import router as api_router
from .models import HealthResponse

APP_NAME = "voltsurge"
APP_VERSION = "0.1.0"

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


def _build_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    openapi_tags = [
        {"name": "meta", "description": "Health and metadata endpoints."},
        {"name": "api", "description": "VoltSurge demo APIs (session + dataset processing endpoints)."},
    ]

    app = FastAPI(
        title="VoltSurge Demo API",
        description="Demo web app for CSV upload, normalization to kWh, anomaly detection, and dashboard metrics. "
        "This step provides the app skeleton: static UI hosting + in-memory session store.",
        version=APP_VERSION,
        openapi_tags=openapi_tags,
    )

    app.include_router(api_router)

    # Static hosting (frontend)
    # Note: `html=True` allows serving index.html for directory requests.
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    # PUBLIC_INTERFACE
    @app.get(
        "/api/health",
        summary="Health check",
        description="Simple health endpoint to verify the server is running.",
        response_model=HealthResponse,
        tags=["meta"],
        operation_id="health",
    )
    def health() -> HealthResponse:
        """Return a health response."""
        return HealthResponse(status="ok", app=APP_NAME, version=APP_VERSION)

    # SPA fallback: if a route isn't found and it isn't an API path, serve index.html.
    # This allows frontend routing later if needed.
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception):  # type: ignore[override]
        """Serve index.html for unknown non-API routes; otherwise return JSON 404."""
        if request.url.path.startswith("/api"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return JSONResponse(status_code=404, content={"detail": "Frontend not built/available"})

    return app


app = _build_app()
