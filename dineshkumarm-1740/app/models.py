"""Pydantic models for VoltSurge APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class SessionInfo(BaseModel):
    """Session identification and timestamps."""

    session_id: str = Field(..., description="Session identifier used to scope in-memory demo data.")
    created_at: Optional[datetime] = Field(None, description="UTC timestamp for session creation.")
    updated_at: Optional[datetime] = Field(None, description="UTC timestamp for last session update.")


class HealthResponse(BaseModel):
    """Health response."""

    status: str = Field(..., description="Health status string.")
    app: str = Field(..., description="Application name.")
    version: str = Field(..., description="Application version.")


class DatasetStatusResponse(BaseModel):
    """High-level status of the in-memory dataset payload for the current session."""

    session: SessionInfo
    has_payload: bool = Field(..., description="Whether the session has any stored payload yet.")
    payload_keys: list[str] = Field(default_factory=list, description="Top-level keys present in the session payload.")
    payload_preview: Dict[str, Any] = Field(default_factory=dict, description="Small preview of stored payload.")
