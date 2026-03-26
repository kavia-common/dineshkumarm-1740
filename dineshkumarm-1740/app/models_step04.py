"""Pydantic models for Step 04.00 analytics endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .models import SessionInfo


class SummaryMetricsResponse(BaseModel):
    """Summary metrics response for dashboard KPIs."""

    session: SessionInfo
    region: Optional[str] = Field(None, description="Region filter applied (exact match). If null, metrics use all rows.")
    row_count_total: int = Field(..., description="Number of processed rows considered (post-filter).")
    row_count_with_kwh: int = Field(..., description="Number of rows with numeric kWh values (post-filter).")
    average_kwh: Optional[float] = Field(None, description="Average kWh over rows with numeric kWh.")
    max_kwh: Optional[float] = Field(None, description="Maximum kWh over rows with numeric kWh.")
    total_kwh: float = Field(..., description="Total kWh summed over rows with numeric kWh.")


class AnomalyItem(BaseModel):
    """Anomaly item for alert display."""

    date_iso: str = Field(..., description="UTC ISO timestamp for the anomalous point.")
    kwh: float = Field(..., description="kWh value at this timestamp.")
    baseline_avg_kwh: float = Field(..., description="Baseline average kWh for the selected scope (global/region).")
    percent_above_average: float = Field(..., description="Percent above baseline average (e.g. 25.0 means 25% above).")
    region: Optional[str] = Field(None, description="Region value for the row, if any.")


class AnomalyDetectionResponse(BaseModel):
    """Anomaly detection response."""

    session: SessionInfo
    region: Optional[str] = Field(None, description="Region filter applied (exact match). If null, uses all rows.")
    threshold_ratio: float = Field(..., description="Threshold ratio used for anomaly definition (0.20 = 20% above avg).")
    baseline_avg_kwh: float = Field(..., description="Computed baseline average kWh for the selected scope.")
    anomaly_count: int = Field(..., description="Number of anomalies detected.")
    anomalies: List[AnomalyItem] = Field(default_factory=list, description="List of detected anomaly points.")


class TimeseriesDataset(BaseModel):
    """A Chart.js dataset object (minimal)."""

    label: str = Field(..., description="Dataset label.")
    data: List[Optional[float]] = Field(..., description="Array of numeric values aligned to labels; nulls allowed.")


class TimeseriesResponse(BaseModel):
    """Chart.js-friendly timeseries response."""

    session: SessionInfo
    region: Optional[str] = Field(None, description="Region filter applied (exact match). If null, uses all rows.")
    labels: List[str] = Field(..., description="X-axis labels (UTC ISO timestamps).")
    datasets: List[TimeseriesDataset] = Field(..., description="Chart.js datasets aligned to labels.")
    meta: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (e.g., baseline average, anomaly count).",
    )
