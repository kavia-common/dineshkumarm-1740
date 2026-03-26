"""API routes for the VoltSurge demo app."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, Response
from fastapi.responses import JSONResponse

from .models import DatasetStatusResponse, SessionInfo
from .session_store import STORE

router = APIRouter(prefix="/api", tags=["api"])

SESSION_COOKIE_NAME = "vs_session_id"


def _ensure_session(response: Response, vs_session_id: Optional[str]) -> str:
    """Ensure a session exists and set the cookie if a new session is created."""
    session_id = STORE.get_or_create_session_id(vs_session_id)
    # Always set cookie to ensure browser keeps it; safe/idempotent.
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=False,  # demo; in production set True behind HTTPS
        max_age=60 * 60 * 24 * 7,  # 7 days
    )
    return session_id


# PUBLIC_INTERFACE
@router.get(
    "/session",
    summary="Get or create the current demo session",
    description="Ensures an in-memory session exists and returns its identifiers/timestamps. "
    "Session is tracked using the `vs_session_id` cookie.",
    response_model=SessionInfo,
    operation_id="getSession",
)
def get_session(response: Response, vs_session_id: Optional[str] = Cookie(default=None)) -> SessionInfo:
    """Return session info for the current browser session."""
    session_id = _ensure_session(response, vs_session_id)
    session = STORE.get(session_id)
    return SessionInfo(session_id=session_id, created_at=session.created_at if session else None, updated_at=session.updated_at if session else None)


# PUBLIC_INTERFACE
@router.get(
    "/dataset/status",
    summary="Get dataset payload status for current session",
    description="Returns whether this session has any dataset payload stored yet (demo in-memory store).",
    response_model=DatasetStatusResponse,
    operation_id="getDatasetStatus",
)
def get_dataset_status(response: Response, vs_session_id: Optional[str] = Cookie(default=None)) -> DatasetStatusResponse:
    """Return dataset payload presence and a small preview for the current session."""
    session_id = _ensure_session(response, vs_session_id)
    session = STORE.get(session_id)

    payload = (session.payload if session else {}) or {}
    keys = list(payload.keys())

    # Keep preview small and safe; later steps will store larger arrays.
    preview = {}
    for k in keys[:5]:
        v = payload.get(k)
        if isinstance(v, (str, int, float, bool)) or v is None:
            preview[k] = v
        elif isinstance(v, dict):
            preview[k] = {kk: v[kk] for kk in list(v.keys())[:5]}
        elif isinstance(v, list):
            preview[k] = v[:5]
        else:
            preview[k] = str(v)

    return DatasetStatusResponse(
        session=SessionInfo(
            session_id=session_id,
            created_at=session.created_at if session else None,
            updated_at=session.updated_at if session else None,
        ),
        has_payload=bool(payload),
        payload_keys=keys,
        payload_preview=preview,
    )
