# Voltsurge (FastAPI backend)

In-memory CSV processing API:
- Upload CSV
- Clean/validate (missing values, duplicates)
- User-driven column selection (date/usage/unit)
- Normalize all usage values to kWh
- Summary stats (average/max/total)
- Anomaly detection (>= 20% above average)

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 3001
```

## API flow (quickstart)

1) Upload CSV:
- `POST /sessions/upload` (multipart form: `file=@data.csv`)
- Response includes `session_id` and detected `columns`

2) Configure & process (choose columns):
- `POST /sessions/{session_id}/configure`
- JSON example:
```json
{
  "date_column": "Date",
  "usage_column": "Energy",
  "unit_column": "Unit",
  "default_unit": "kwh"
}
```

3) Fetch outputs:
- `GET /sessions/{session_id}/data`
- `GET /sessions/{session_id}/stats`
- `GET /sessions/{session_id}/anomalies`
