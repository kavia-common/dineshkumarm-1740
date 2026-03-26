"""Pydantic models for VoltSurge APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

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


EnergyUnit = Literal["w", "kw", "kwh"]


class DatasetSelectColumnsRequest(BaseModel):
    """Request payload for selecting columns and normalizing usage to kWh."""

    date_column: str = Field(..., description="Normalized name of the column containing date/time values.")
    usage_column: str = Field(..., description="Normalized name of the column containing numeric energy usage values.")
    usage_unit: EnergyUnit = Field(..., description="Unit of the usage values: 'w' (Wh assumed per interval), 'kw', or 'kwh'.")
    region_column: Optional[str] = Field(
        None,
        description="Optional normalized column name to treat as region (used later for filtering/slicers).",
    )


class ProcessedDatasetSummary(BaseModel):
    """Summary metadata about the processed dataset stored in-session."""

    row_count: int = Field(..., description="Number of processed rows stored.")
    included_null_rows: int = Field(..., description="Rows kept but with missing/invalid kWh values (kwh=null).")
    dropped_rows: int = Field(..., description="Rows dropped due to missing date or irrecoverable parsing errors.")
    usage_unit_input: EnergyUnit = Field(..., description="The unit provided by the client for usage values.")
    usage_unit_normalized: Literal["kwh"] = Field("kwh", description="Normalized unit for stored usage values (always kWh).")
    date_column: str = Field(..., description="Selected date column name.")
    usage_column: str = Field(..., description="Selected usage column name.")
    region_column: Optional[str] = Field(None, description="Selected region column name, if any.")
    warnings: List[str] = Field(default_factory=list, description="Non-fatal processing warnings (sampled).")


class DatasetSelectColumnsResponse(BaseModel):
    """Response returned after processing selection + normalization."""

    session: SessionInfo
    summary: ProcessedDatasetSummary
    preview_rows: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Small preview of processed rows (date_raw, date_iso, kwh, region, usage_raw).",
    )
