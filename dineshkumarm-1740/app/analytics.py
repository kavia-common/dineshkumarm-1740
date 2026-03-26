"""
Step 04.00 analytics utilities.

Responsibilities:
- Compute summary metrics (avg, max, total) over the processed in-memory dataset
- Detect anomalies where kWh is >= (1 + threshold) * baseline average
- Provide a Chart.js-friendly time series structure (labels + datasets), optionally filtered by region

Notes:
- This module is stdlib-only and operates on the processed rows created in Step 03.00.
- Processed rows shape (from processing.py):
    {
        "date_iso": str (UTC ISO timestamp),
        "kwh": Optional[float],
        "region": Optional[str],
        ...
    }
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class SummaryMetrics:
    """Computed summary metrics over a set of processed rows."""

    row_count_total: int
    row_count_with_kwh: int
    average_kwh: Optional[float]
    max_kwh: Optional[float]
    total_kwh: float


@dataclass(frozen=True)
class AnomalyPoint:
    """A single anomaly detection record."""

    date_iso: str
    kwh: float
    baseline_avg_kwh: float
    percent_above_average: float
    region: Optional[str] = None


def _safe_float(v: Any) -> Optional[float]:
    """Convert to float if possible and not NaN; otherwise None."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            fv = float(v)
        except Exception:
            return None
        # NaN check without importing math (NaN != NaN)
        if fv != fv:
            return None
        return fv
    return None


def _parse_iso_datetime(s: str) -> Optional[datetime]:
    """Parse ISO date string (accepts Z or offset). Returns naive/aware datetime for sorting."""
    if not s or not isinstance(s, str):
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _filter_rows_by_region(rows: Iterable[Dict[str, Any]], region: Optional[str]) -> List[Dict[str, Any]]:
    """Return rows filtered by region if provided (exact match)."""
    if region is None or region == "":
        return list(rows)
    out: List[Dict[str, Any]] = []
    for r in rows:
        if (r.get("region") or "") == region:
            out.append(r)
    return out


# PUBLIC_INTERFACE
def compute_summary_metrics(processed_rows: List[Dict[str, Any]], *, region: Optional[str] = None) -> SummaryMetrics:
    """
    Compute summary metrics for the processed dataset (optionally filtered by region).

    Args:
        processed_rows: List of processed rows (Step 03.00 output).
        region: Optional exact-match region filter. If None, uses all rows.

    Returns:
        SummaryMetrics including average/max/total kWh computed over non-null kWh rows.
    """
    scoped = _filter_rows_by_region(processed_rows, region)

    kwh_values: List[float] = []
    for r in scoped:
        v = _safe_float(r.get("kwh"))
        if v is None:
            continue
        kwh_values.append(v)

    total = float(sum(kwh_values)) if kwh_values else 0.0
    avg = (total / len(kwh_values)) if kwh_values else None
    mx = (max(kwh_values)) if kwh_values else None

    return SummaryMetrics(
        row_count_total=len(scoped),
        row_count_with_kwh=len(kwh_values),
        average_kwh=avg,
        max_kwh=mx,
        total_kwh=total,
    )


# PUBLIC_INTERFACE
def detect_anomalies(
    processed_rows: List[Dict[str, Any]],
    *,
    threshold_ratio: float = 0.20,
    region: Optional[str] = None,
) -> Tuple[float, List[AnomalyPoint]]:
    """
    Detect anomalies defined as kWh >= (1 + threshold_ratio) * baseline average.

    Baseline average is computed over non-null kWh rows in the (optionally filtered) dataset.

    Args:
        processed_rows: List of processed rows (Step 03.00 output).
        threshold_ratio: Ratio above average to flag (default 0.20 = 20%).
        region: Optional exact-match region filter.

    Returns:
        (baseline_average_kwh, anomalies_list)

    Notes:
        - If baseline average is not computable (no numeric kWh rows), anomalies list will be empty.
    """
    metrics = compute_summary_metrics(processed_rows, region=region)
    baseline = metrics.average_kwh
    if baseline is None or baseline <= 0:
        return 0.0, []

    cutoff = baseline * (1.0 + float(threshold_ratio))
    anomalies: List[AnomalyPoint] = []

    scoped = _filter_rows_by_region(processed_rows, region)
    # Sort for stable UX output
    scoped_sorted = sorted(
        scoped,
        key=lambda r: (_parse_iso_datetime(str(r.get("date_iso") or "")) or datetime.min),
    )

    for r in scoped_sorted:
        kwh = _safe_float(r.get("kwh"))
        if kwh is None:
            continue
        if kwh >= cutoff:
            pct = ((kwh - baseline) / baseline) * 100.0
            anomalies.append(
                AnomalyPoint(
                    date_iso=str(r.get("date_iso")),
                    kwh=kwh,
                    baseline_avg_kwh=baseline,
                    percent_above_average=pct,
                    region=r.get("region"),
                )
            )

    return baseline, anomalies


# PUBLIC_INTERFACE
def build_timeseries_for_chartjs(
    processed_rows: List[Dict[str, Any]],
    *,
    region: Optional[str] = None,
    include_anomaly_series: bool = True,
    anomaly_threshold_ratio: float = 0.20,
) -> Dict[str, Any]:
    """
    Build a Chart.js-friendly timeseries object for energy usage.

    Args:
        processed_rows: List of processed rows (Step 03.00 output).
        region: Optional exact-match region filter.
        include_anomaly_series: If True, also includes an "Anomalies" dataset where non-anomaly points are null.
        anomaly_threshold_ratio: Threshold for anomaly detection, used only if include_anomaly_series=True.

    Returns:
        Dict shaped for easy client usage:
        {
            "labels": [date_iso...],
            "datasets": [
                {"label": "kWh", "data": [number|null...], ...},
                {"label": "Anomalies", "data": [number|null...], ...}  # optional
            ]
        }
    """
    scoped = _filter_rows_by_region(processed_rows, region)

    # Sort ascending by date for chart continuity
    scoped_sorted = sorted(
        scoped,
        key=lambda r: (_parse_iso_datetime(str(r.get("date_iso") or "")) or datetime.min),
    )

    labels: List[str] = []
    series: List[Optional[float]] = []
    for r in scoped_sorted:
        labels.append(str(r.get("date_iso") or ""))
        series.append(_safe_float(r.get("kwh")))

    payload: Dict[str, Any] = {
        "labels": labels,
        "datasets": [
            {
                "label": "kWh",
                "data": series,
            }
        ],
    }

    if include_anomaly_series:
        baseline, anomalies = detect_anomalies(
            processed_rows,
            threshold_ratio=anomaly_threshold_ratio,
            region=region,
        )
        anomaly_dates = {a.date_iso for a in anomalies} if baseline > 0 else set()
        anomaly_series: List[Optional[float]] = []
        for i, dt in enumerate(labels):
            val = series[i]
            if val is None:
                anomaly_series.append(None)
            else:
                anomaly_series.append(val if dt in anomaly_dates else None)

        payload["datasets"].append(
            {
                "label": f"Anomalies (≥{int(anomaly_threshold_ratio*100)}% above avg)",
                "data": anomaly_series,
            }
        )

    return payload
