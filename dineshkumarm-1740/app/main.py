"""
FastAPI entrypoint for the VoltSurge demo application.

Serves:
- Static frontend assets from / (app/static)
- REST APIs under /api

This is a single-container demo app with an in-memory session store.

Step 06.00 integration notes:
- Ensure SPA is served at `/` while APIs remain under `/api/*` with no CORS issues.
- Mount static files last so they never shadow `/api/*`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
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
        description="Demo web app for CSV upload, normalization to kWh, anomaly detection, and dashboard metrics.",
        version=APP_VERSION,
        openapi_tags=openapi_tags,
    )

    # CORS:
    # In the intended deployment, frontend and backend are same-origin (no CORS needed).
    # However, allowing common localhost origins makes dev setups resilient (e.g., opening index.html from a different port).
    # This remains safe for demo because there's no auth and the API is session-cookie based.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost",
            "http://localhost:8000",
            "http://127.0.0.1",
            "http://127.0.0.1:8000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include API routes BEFORE mounting the SPA/static files.
    # This prevents StaticFiles from shadowing /api/* paths.
    app.include_router(api_router)

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

    # Static hosting (frontend) mounted last.
    # Note: `html=True` allows serving index.html for directory requests.
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

    # SPA fallback: if a route isn't found and it isn't an API path, serve index.html.
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: Exception):  # type: ignore[override]
        """Serve index.html for unknown non-API routes; otherwise return JSON 404."""
        if request.url.path.startswith("/api"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})

        index_path = STATIC_DIR / "index.html"
        if index_path.exists():
            # Avoid caching HTML shell too aggressively; JS/CSS can be cached normally by the browser.
            return FileResponse(
                str(index_path),
                headers={
                    "Cache-Control": "no-store",
                },
            )
        return JSONResponse(status_code=404, content={"detail": "Frontend not built/available"})

    return app


app = _build_app()
