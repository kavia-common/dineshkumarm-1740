# VoltSurge Demo (FastAPI + Static Frontend)

This container hosts a single FastAPI application that:
- Serves the static frontend from `app/static/`
- Exposes REST endpoints under `/api/*`
- Maintains an in-memory, session-scoped dataset store (no database)

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Then open:
- http://localhost:8000

## Notes
- This is a demo-only in-memory store. All uploaded/processed data will be lost when the server restarts.
- Session is tracked via a cookie (`vs_session_id`).
"""
