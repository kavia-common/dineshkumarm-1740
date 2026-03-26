"""
CSV parsing and lightweight cleaning utilities for VoltSurge.

Step 02.00 responsibilities:
- Parse uploaded CSV content
- Perform basic validation (has header, at least one row)
- Clean data (normalize column names, trim whitespace, convert empty strings to None, drop fully-empty rows)
- De-duplicate rows (exact match across all columns)
- Return schema + preview for later user column selection

Notes:
- This module is intentionally dependency-free (stdlib only).
- More advanced parsing (dates, numeric casting, unit conversion) is done in later steps.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ColumnProfile:
    """Profiled properties for a CSV column in the preview sample."""

    name: str
    non_null_count: int
    null_count: int
    unique_count: int
    example_values: List[str]


def _normalize_column_name(name: str) -> str:
    """
    Normalize a column name for consistent UX and simpler matching.

    - Trim whitespace
    - Collapse whitespace to underscores
    - Remove non-alphanumeric/underscore characters
    - Lowercase
    """
    base = (name or "").strip()
    base = re.sub(r"\s+", "_", base)
    base = re.sub(r"[^A-Za-z0-9_]", "", base)
    base = base.strip("_")
    return base.lower() or "column"


def _dedupe_preserve_order(rows: Sequence[Dict[str, Any]], columns: Sequence[str]) -> Tuple[List[Dict[str, Any]], int]:
    """De-duplicate exact-match rows while preserving original order."""
    seen: set[Tuple[Any, ...]] = set()
    out: List[Dict[str, Any]] = []
    removed = 0
    for r in rows:
        key = tuple(r.get(c) for c in columns)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        out.append(r)
    return out, removed


def _is_missing(value: Any) -> bool:
    """Treat empty strings/whitespace as missing."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _sniff_dialect(sample_text: str) -> csv.Dialect:
    """
    Attempt to sniff the CSV dialect from a small text sample.

    Falls back to excel dialect if sniffing fails.
    """
    try:
        sniffer = csv.Sniffer()
        return sniffer.sniff(sample_text, delimiters=[",", ";", "\t", "|"])
    except Exception:
        return csv.get_dialect("excel")


# PUBLIC_INTERFACE
def parse_and_clean_csv(
    raw_bytes: bytes,
    *,
    filename: str,
    max_rows: int = 50_000,
    preview_rows: int = 25,
) -> Dict[str, Any]:
    """
    Parse and clean an uploaded CSV file and return a schema/preview payload.

    Args:
        raw_bytes: Raw bytes of the uploaded file.
        filename: Original upload filename (used for metadata only).
        max_rows: Maximum number of data rows allowed (excluding header).
        preview_rows: Number of rows to include in the preview.

    Returns:
        Dict payload containing:
        - filename, row_count, row_count_after_cleaning, duplicate_rows_removed
        - columns_original, columns_normalized, columns
        - preview_rows
        - schema: per-column profiling info
        - warnings: list of warning strings

    Raises:
        ValueError: On invalid CSV (no header, no columns, too many rows, etc.).
    """
    if not raw_bytes:
        raise ValueError("Empty file upload.")

    # Decode with UTF-8 (accept BOM). If it fails, give a clear message.
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise ValueError("CSV must be UTF-8 encoded.") from e

    # Use a small sample to sniff delimiter/quote.
    sample = text[:4096]
    dialect = _sniff_dialect(sample)

    reader = csv.reader(io.StringIO(text), dialect=dialect)
    try:
        header = next(reader)
    except StopIteration as e:
        raise ValueError("CSV has no rows.") from e

    if not header or all((h or "").strip() == "" for h in header):
        raise ValueError("CSV header row is missing or empty.")

    columns_original = [h.strip() for h in header]
    if len(columns_original) == 0:
        raise ValueError("CSV contains zero columns.")

    # Normalize columns and de-conflict duplicates
    normalized_base = [_normalize_column_name(c) for c in columns_original]
    normalized: List[str] = []
    counts: Dict[str, int] = {}
    for base_name in normalized_base:
        if base_name not in counts:
            counts[base_name] = 0
            normalized.append(base_name)
        else:
            counts[base_name] += 1
            normalized.append(f"{base_name}_{counts[base_name]}")

    # Read data rows
    rows: List[Dict[str, Any]] = []
    warnings: List[str] = []
    total_rows = 0

    for raw in reader:
        # Normalize row length to header length
        if raw is None:
            continue
        if len(raw) < len(columns_original):
            raw = list(raw) + [""] * (len(columns_original) - len(raw))
        elif len(raw) > len(columns_original):
            raw = list(raw[: len(columns_original)])
            warnings.append("Some rows had extra trailing columns; they were truncated to header length.")

        record: Dict[str, Any] = {}
        all_missing = True
        for idx, col in enumerate(normalized):
            v = raw[idx] if idx < len(raw) else ""
            if isinstance(v, str):
                v = v.strip()
            if _is_missing(v):
                record[col] = None
            else:
                record[col] = v
                all_missing = False

        # Drop fully-empty rows (common in exports)
        if all_missing:
            continue

        rows.append(record)
        total_rows += 1
        if total_rows > max_rows:
            raise ValueError(f"CSV exceeds maximum supported row count ({max_rows}).")

    if total_rows == 0:
        raise ValueError("CSV contains no data rows.")

    # Dedupe
    deduped_rows, dup_removed = _dedupe_preserve_order(rows, normalized)

    # Build preview
    preview = deduped_rows[:preview_rows]

    # Column profiling from preview sample
    schema: List[Dict[str, Any]] = []
    for col in normalized:
        values = [r.get(col) for r in preview]
        non_null = [v for v in values if not _is_missing(v)]
        # Unique count based on stringified value for stability
        uniq = {str(v) for v in non_null}
        examples: List[str] = []
        for v in non_null[:5]:
            examples.append(str(v))
        schema.append(
            {
                "name": col,
                "non_null_count": len(non_null),
                "null_count": len(values) - len(non_null),
                "unique_count": len(uniq),
                "example_values": examples,
            }
        )

    return {
        "filename": filename,
        "row_count": len(rows),
        "row_count_after_cleaning": len(deduped_rows),
        "duplicate_rows_removed": dup_removed,
        "columns_original": columns_original,
        "columns_normalized": normalized,
        "columns": normalized,
        "preview_rows": preview,
        "schema": schema,
        "warnings": warnings[:20],
    }
