"""API routes for the VoltSurge demo app."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, File, HTTPException, Response, UploadFile

from .csv_utils import parse_and_clean_csv
from .models import (
    CsvUploadPreviewResponse,
    DatasetSelectColumnsRequest,
    DatasetSelectColumnsResponse,
    DatasetStatusResponse,
    ProcessedDatasetSummary,
    SessionInfo,
)
from .processing import process_dataset_from_preview
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

    # Keep preview small and safe; processed dataset can be large.
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


# PUBLIC_INTERFACE
@router.post(
    "/dataset/upload",
    summary="Upload an electricity CSV and return schema + preview",
    description=(
        "Accepts a CSV file upload, parses it, performs basic cleaning (trim whitespace, "
        "convert empty values to null, remove fully-empty rows, remove duplicate rows), "
        "and returns a schema + preview to support later column selection (date, usage, unit, region). "
        "Stores the cleaned preview in the in-memory session payload."
    ),
    response_model=CsvUploadPreviewResponse,
    operation_id="uploadDatasetCsv",
)
async def upload_dataset_csv(
    response: Response,
    file: UploadFile = File(..., description="CSV file containing electricity/energy usage data."),
    vs_session_id: Optional[str] = Cookie(default=None),
) -> CsvUploadPreviewResponse:
    """
    Upload CSV file and return schema/preview.

    - Basic validation: file extension/type, UTF-8 decode, header presence, at least one data row.
    - Cleaning: normalize headers, empty->null, drop fully-empty rows, remove duplicates.

    Returns:
        CsvUploadPreviewResponse containing preview rows and per-column schema profile.

    Notes:
        This endpoint intentionally does not do unit conversion; later steps handle mapping the
        selected energy usage column and unit normalization to kWh.
    """
    session_id = _ensure_session(response, vs_session_id)
    session = STORE.get(session_id)

    if file is None:
        raise HTTPException(status_code=400, detail="Missing file.")
    if not (file.filename or "").lower().endswith(".csv"):
        # Still allow unknown extensions if content-type is text/csv-ish, but keep UX strict for demo.
        content_type = (file.content_type or "").lower()
        if "csv" not in content_type and "text" not in content_type:
            raise HTTPException(status_code=400, detail="Only CSV uploads are supported.")

    try:
        raw = await file.read()
        parsed = parse_and_clean_csv(raw, filename=file.filename or "upload.csv")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to parse CSV.") from e

    # Store a small, session-scoped payload for later steps.
    STORE.patch_payload(
        session_id,
        {
            "upload": {
                "filename": parsed["filename"],
                "columns_original": parsed["columns_original"],
                "columns_normalized": parsed["columns_normalized"],
                "row_count": parsed["row_count"],
                "row_count_after_cleaning": parsed["row_count_after_cleaning"],
                "duplicate_rows_removed": parsed["duplicate_rows_removed"],
                "warnings": parsed["warnings"],
            },
            "preview": {
                "columns": parsed["columns"],
                "rows": parsed["preview_rows"],
                "schema": parsed["schema"],
            },
            # Clear any previous processed dataset for this session when a new upload happens.
            "processed": None,
        },
    )

    # Re-read session for updated timestamps
    session = STORE.get(session_id)

    return CsvUploadPreviewResponse(
        session=SessionInfo(
            session_id=session_id,
            created_at=session.created_at if session else None,
            updated_at=session.updated_at if session else None,
        ),
        filename=parsed["filename"],
        row_count=parsed["row_count"],
        row_count_after_cleaning=parsed["row_count_after_cleaning"],
        duplicate_rows_removed=parsed["duplicate_rows_removed"],
        columns_original=parsed["columns_original"],
        columns_normalized=parsed["columns_normalized"],
        columns=parsed["columns"],
        preview_rows=parsed["preview_rows"],
        schema=parsed["schema"],
        warnings=parsed["warnings"],
    )


# PUBLIC_INTERFACE
@router.post(
    "/dataset/select",
    summary="Select date/usage/region columns and normalize usage to kWh",
    description=(
        "Uses the previously uploaded & cleaned preview rows stored in-session, applies the user's "
        "column selection (date column, usage column, optional region column) and usage unit, then "
        "normalizes energy usage values to kWh. The processed dataset is stored in the in-memory "
        "session payload under `processed`."
    ),
    response_model=DatasetSelectColumnsResponse,
    operation_id="selectDatasetColumnsAndNormalize",
)
def select_dataset_columns_and_normalize(
    request: DatasetSelectColumnsRequest,
    response: Response,
    vs_session_id: Optional[str] = Cookie(default=None),
) -> DatasetSelectColumnsResponse:
    """
    Select the dataset columns and normalize energy usage to kWh.

    Requirements implemented (Step 03.00):
    - API allows selecting date/usage/region columns and unit (w/kw/kwh)
    - Normalize selected energy values to kWh
    - Store processed dataset in the in-memory session store

    Returns:
        DatasetSelectColumnsResponse with summary and a small preview.

    Errors:
        - 400 if no upload/preview exists, columns are invalid, or processing cannot proceed.
    """
    session_id = _ensure_session(response, vs_session_id)
    session = STORE.get(session_id)
    payload = (session.payload if session else {}) or {}

    preview = payload.get("preview") or {}
    preview_rows = preview.get("rows") or []
    if not isinstance(preview_rows, list) or len(preview_rows) == 0:
        raise HTTPException(status_code=400, detail="No uploaded dataset preview found. Upload a CSV first.")

    try:
        result = process_dataset_from_preview(
            preview_rows=preview_rows,
            date_column=request.date_column,
            usage_column=request.usage_column,
            usage_unit=request.usage_unit,
            region_column=request.region_column,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to process dataset.") from e

    # Store processed dataset (this is the main Step 03.00 requirement).
    STORE.patch_payload(
        session_id,
        {
            "selection": {
                "date_column": request.date_column,
                "usage_column": request.usage_column,
                "usage_unit": request.usage_unit,
                "region_column": request.region_column,
            },
            "processed": {
                "rows": result.processed_rows,
                "summary": result.summary,
            },
        },
    )

    session = STORE.get(session_id)

    return DatasetSelectColumnsResponse(
        session=SessionInfo(
            session_id=session_id,
            created_at=session.created_at if session else None,
            updated_at=session.updated_at if session else None,
        ),
        summary=ProcessedDatasetSummary(**result.summary),
        preview_rows=result.preview_rows,
    )
