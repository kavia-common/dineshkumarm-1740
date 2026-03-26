"""API routes for the VoltSurge demo app."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Cookie, File, HTTPException, Query, Response, UploadFile

from .analytics import build_timeseries_for_chartjs, compute_summary_metrics, detect_anomalies
from .csv_utils import parse_and_clean_csv
from .models import (
    CsvUploadPreviewResponse,
    DatasetSelectColumnsRequest,
    DatasetSelectColumnsResponse,
    DatasetStatusResponse,
    ProcessedDatasetSummary,
    SessionInfo,
)
from .models_step04 import AnomalyDetectionResponse, SummaryMetricsResponse, TimeseriesResponse
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


def _get_processed_rows_or_400(session_id: str) -> list[dict]:
    """Fetch processed rows from the session payload or raise 400 if missing."""
    session = STORE.get(session_id)
    payload = (session.payload if session else {}) or {}
    processed = payload.get("processed") or {}
    rows = processed.get("rows") or []
    if not isinstance(rows, list) or len(rows) == 0:
        raise HTTPException(
            status_code=400,
            detail="No processed dataset found. Upload CSV and run /api/dataset/select first.",
        )
    return rows


# PUBLIC_INTERFACE
@router.get(
    "/metrics/summary",
    summary="Compute summary dashboard metrics (avg/max/total kWh)",
    description=(
        "Computes summary metrics over the processed in-session dataset. "
        "Optionally filters by exact-match region (if a region column was selected during processing)."
    ),
    response_model=SummaryMetricsResponse,
    operation_id="getSummaryMetrics",
)
def get_summary_metrics(
    response: Response,
    vs_session_id: Optional[str] = Cookie(default=None),
    region: Optional[str] = Query(default=None, description="Optional exact-match region filter."),
) -> SummaryMetricsResponse:
    """
    Compute summary metrics (average, max, total kWh) for the current session's processed dataset.

    Parameters:
        region: Optional region filter (exact match).

    Returns:
        SummaryMetricsResponse containing KPI values for the dashboard.
    """
    session_id = _ensure_session(response, vs_session_id)
    rows = _get_processed_rows_or_400(session_id)

    metrics = compute_summary_metrics(rows, region=region)

    session = STORE.get(session_id)
    return SummaryMetricsResponse(
        session=SessionInfo(
            session_id=session_id,
            created_at=session.created_at if session else None,
            updated_at=session.updated_at if session else None,
        ),
        region=region,
        row_count_total=metrics.row_count_total,
        row_count_with_kwh=metrics.row_count_with_kwh,
        average_kwh=metrics.average_kwh,
        max_kwh=metrics.max_kwh,
        total_kwh=metrics.total_kwh,
    )


# PUBLIC_INTERFACE
@router.get(
    "/anomalies",
    summary="Detect anomalies (kWh ≥ 20% above average)",
    description=(
        "Detects anomalies in the processed in-session dataset, defined as kWh values that are at least "
        "20% above the baseline average. Optionally filters by exact-match region."
    ),
    response_model=AnomalyDetectionResponse,
    operation_id="detectAnomalies",
)
def get_anomalies(
    response: Response,
    vs_session_id: Optional[str] = Cookie(default=None),
    region: Optional[str] = Query(default=None, description="Optional exact-match region filter."),
    threshold_ratio: float = Query(
        default=0.20,
        ge=0.0,
        le=10.0,
        description="Anomaly threshold ratio above baseline average (0.20 = 20%).",
    ),
) -> AnomalyDetectionResponse:
    """
    Detect anomalies for the current session's processed dataset.

    Parameters:
        region: Optional region filter (exact match).
        threshold_ratio: Ratio above average used to flag an anomaly (default 0.20).

    Returns:
        AnomalyDetectionResponse with baseline average and a sorted list of anomalies.
    """
    session_id = _ensure_session(response, vs_session_id)
    rows = _get_processed_rows_or_400(session_id)

    baseline, anomalies = detect_anomalies(rows, threshold_ratio=threshold_ratio, region=region)

    session = STORE.get(session_id)
    return AnomalyDetectionResponse(
        session=SessionInfo(
            session_id=session_id,
            created_at=session.created_at if session else None,
            updated_at=session.updated_at if session else None,
        ),
        region=region,
        threshold_ratio=threshold_ratio,
        baseline_avg_kwh=float(baseline),
        anomaly_count=len(anomalies),
        anomalies=[
            {
                "date_iso": a.date_iso,
                "kwh": a.kwh,
                "baseline_avg_kwh": a.baseline_avg_kwh,
                "percent_above_average": a.percent_above_average,
                "region": a.region,
            }
            for a in anomalies
        ],
    )


# PUBLIC_INTERFACE
@router.get(
    "/timeseries",
    summary="Get Chart.js-friendly energy usage timeseries (with optional anomaly series)",
    description=(
        "Returns a Chart.js-friendly object containing labels (date_iso) and datasets. "
        "Supports optional exact-match region filtering and optional inclusion of an anomaly-only dataset."
    ),
    response_model=TimeseriesResponse,
    operation_id="getTimeseries",
)
def get_timeseries(
    response: Response,
    vs_session_id: Optional[str] = Cookie(default=None),
    region: Optional[str] = Query(default=None, description="Optional exact-match region filter."),
    include_anomalies: bool = Query(default=True, description="Whether to include a second dataset containing only anomalies."),
    anomaly_threshold_ratio: float = Query(
        default=0.20,
        ge=0.0,
        le=10.0,
        description="Threshold ratio used to compute anomaly series (0.20 = 20%).",
    ),
) -> TimeseriesResponse:
    """
    Provide a Chart.js-friendly timeseries payload for the dashboard chart.

    Parameters:
        region: Optional region filter (exact match).
        include_anomalies: If true, includes a dataset where only anomalies have non-null points.
        anomaly_threshold_ratio: Threshold ratio used when computing anomaly series.

    Returns:
        TimeseriesResponse with labels + datasets.
    """
    session_id = _ensure_session(response, vs_session_id)
    rows = _get_processed_rows_or_400(session_id)

    chart_payload = build_timeseries_for_chartjs(
        rows,
        region=region,
        include_anomaly_series=include_anomalies,
        anomaly_threshold_ratio=anomaly_threshold_ratio,
    )

    # Provide some useful meta for the UI without requiring extra requests.
    baseline, anomalies = detect_anomalies(rows, threshold_ratio=anomaly_threshold_ratio, region=region)
    meta = {
        "baseline_avg_kwh": float(baseline) if baseline else 0.0,
        "anomaly_count": len(anomalies),
        "threshold_ratio": anomaly_threshold_ratio,
        "unit": "kwh",
    }

    session = STORE.get(session_id)
    return TimeseriesResponse(
        session=SessionInfo(
            session_id=session_id,
            created_at=session.created_at if session else None,
            updated_at=session.updated_at if session else None,
        ),
        region=region,
        labels=chart_payload.get("labels") or [],
        datasets=chart_payload.get("datasets") or [],
        meta=meta,
    )
