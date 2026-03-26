"""
Step 03.00 dataset processing utilities.

Responsibilities:
- Accept column selections (date, usage, optional region, unit)
- Normalize selected energy values to kWh from W/kW/kWh
- Build a processed dataset suitable for later steps (metrics, anomaly detection, charts)
- Keep dependencies minimal (stdlib-only)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple


EnergyUnit = Literal["w", "kw", "kwh"]


@dataclass(frozen=True)
class ProcessResult:
    """Result of processing/normalizing a dataset for a session."""

    processed_rows: List[Dict[str, Any]]
    summary: Dict[str, Any]
    preview_rows: List[Dict[str, Any]]


def _parse_float(value: Any) -> Optional[float]:
    """
    Parse a float from typical CSV string formats.

    Accepts:
    - numbers
    - strings like "1,234.56" or "  1234 " (commas stripped)

    Returns:
        float or None if not parseable / missing.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if not isinstance(value, str):
        return None
    s = value.strip()
    if s == "":
        return None
    # Strip thousands separators
    s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    """
    Best-effort parse of date/time strings.

    Supported (common export formats):
    - ISO-ish: 2024-01-31, 2024-01-31 13:45, 2024-01-31T13:45:00Z
    - US: 01/31/2024 or 01/31/2024 13:45
    - With seconds optionally

    Returns:
        A timezone-aware UTC datetime (assumes naive datetimes are in local/unknown time, so we treat them as UTC for demo),
        or None if parsing fails.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    if not isinstance(value, str):
        return None

    s = value.strip()
    if s == "":
        return None

    # Normalize Z suffix for fromisoformat compatibility
    s_iso = s.replace("Z", "+00:00")

    # Try ISO first (datetime or date)
    try:
        dt = datetime.fromisoformat(s_iso)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Try a few common strptime formats
    patterns = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%m/%d/%Y",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
    ]
    for p in patterns:
        try:
            dt = datetime.strptime(s, p)
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue

    return None


def _to_kwh(value: Optional[float], unit: EnergyUnit) -> Optional[float]:
    """
    Convert a usage value from the provided unit to kWh.

    Notes:
    - For demo simplicity, we treat:
        - 'w' as Wh-like values per interval; conversion: Wh -> kWh (divide by 1000)
        - 'kw' as kW; without an interval length we cannot compute kWh exactly.
          For demo purposes (and per simplified user instruction), we treat values as kWh-equivalent
          when unit='kw' by assuming a 1-hour interval, so kWh = kW * 1h (no change).
        - 'kwh' is already kWh.

    Returns:
        kWh float or None.
    """
    if value is None:
        return None
    if unit == "kwh":
        return value
    if unit == "w":
        return value / 1000.0
    if unit == "kw":
        return value
    return None


# PUBLIC_INTERFACE
def process_dataset_from_preview(
    *,
    preview_rows: List[Dict[str, Any]],
    date_column: str,
    usage_column: str,
    usage_unit: EnergyUnit,
    region_column: Optional[str] = None,
    max_rows_store: int = 50_000,
) -> ProcessResult:
    """
    Process the currently stored preview rows using the selected columns and normalize usage to kWh.

    Args:
        preview_rows: The cleaned rows stored from upload step (values are strings or None).
        date_column: Normalized name of date column to parse.
        usage_column: Normalized name of usage column to parse as float and convert.
        usage_unit: Unit of the usage column: w, kw, or kwh.
        region_column: Optional normalized name of region/slicer column.
        max_rows_store: Safety cap for in-memory storage size.

    Returns:
        ProcessResult containing processed rows, a summary dict, and a small preview.

    Raises:
        ValueError: If required columns are missing or dataset is empty.
    """
    if not preview_rows:
        raise ValueError("No preview rows available. Upload a dataset first.")

    sample_row = preview_rows[0] if preview_rows else {}
    if date_column not in sample_row:
        raise ValueError(f"Selected date column '{date_column}' not found in dataset.")
    if usage_column not in sample_row:
        raise ValueError(f"Selected usage column '{usage_column}' not found in dataset.")
    if region_column and region_column not in sample_row:
        raise ValueError(f"Selected region column '{region_column}' not found in dataset.")

    processed: List[Dict[str, Any]] = []
    warnings: List[str] = []
    included_null_rows = 0
    dropped_rows = 0

    for idx, row in enumerate(preview_rows):
        if idx >= max_rows_store:
            warnings.append(f"Row limit reached ({max_rows_store}); additional rows were not processed/stored.")
            break

        date_raw = row.get(date_column)
        dt = _parse_datetime(date_raw)
        if dt is None:
            # Without a date we cannot chart; drop this row.
            dropped_rows += 1
            continue

        usage_raw = row.get(usage_column)
        usage_num = _parse_float(usage_raw)
        kwh = _to_kwh(usage_num, usage_unit)

        if kwh is None:
            included_null_rows += 1

        region_val = row.get(region_column) if region_column else None

        processed.append(
            {
                "date_raw": date_raw,
                "date_iso": dt.isoformat(),
                "kwh": kwh,
                "usage_raw": usage_raw,
                "usage_unit_input": usage_unit,
                "region": region_val,
            }
        )

    summary = {
        "row_count": len(processed),
        "included_null_rows": included_null_rows,
        "dropped_rows": dropped_rows,
        "usage_unit_input": usage_unit,
        "usage_unit_normalized": "kwh",
        "date_column": date_column,
        "usage_column": usage_column,
        "region_column": region_column,
        "warnings": warnings[:50],
    }

    # Small preview for UX
    preview = processed[:25]

    return ProcessResult(processed_rows=processed, summary=summary, preview_rows=preview)
