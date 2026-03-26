"""Pydantic models for VoltSurge APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

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


class ColumnSchema(BaseModel):
    """Per-column schema derived from preview profiling."""

    name: str = Field(..., description="Normalized column name.")
    non_null_count: int = Field(..., description="Count of non-missing values in the preview sample.")
    null_count: int = Field(..., description="Count of missing values in the preview sample.")
    unique_count: int = Field(..., description="Approx unique value count in the preview sample.")
    example_values: List[str] = Field(default_factory=list, description="Example (non-missing) values from the preview sample.")


class CsvUploadPreviewResponse(BaseModel):
    """Response returned after uploading a CSV: schema + preview for column selection."""

    session: SessionInfo
    filename: str = Field(..., description="Original filename provided by the browser upload.")
    row_count: int = Field(..., description="Number of non-empty rows parsed (before de-duplication).")
    row_count_after_cleaning: int = Field(..., description="Row count after basic cleaning (e.g., duplicate removal).")
    duplicate_rows_removed: int = Field(..., description="Number of rows removed due to exact duplicates.")
    columns_original: List[str] = Field(..., description="Original header names as found in the file.")
    columns_normalized: List[str] = Field(..., description="Normalized header names (lowercase, underscores, de-conflicted).")
    columns: List[str] = Field(..., description="Alias of columns_normalized; list of selectable columns.")
    preview_rows: List[Dict[str, Any]] = Field(..., description="Small preview of cleaned rows (values are strings or null).")
    schema: List[ColumnSchema] = Field(..., description="Per-column schema/profile derived from preview.")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal warnings encountered while parsing/cleaning.")
