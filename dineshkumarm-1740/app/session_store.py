"""
In-memory, session-scoped store for demo purposes.

This module intentionally uses process memory only:
- No persistence across restarts
- Not safe for multi-worker deployments unless replaced with a shared store (Redis/DB)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Dict, Optional
from uuid import uuid4


@dataclass
class SessionData:
    """Per-session storage for uploaded/processed data and derived results."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # For step 01.00 we keep this generic; later steps can store parsed rows, schema, metrics, etc.
    payload: Dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        """Update last-modified timestamp."""
        self.updated_at = datetime.now(timezone.utc)


class InMemorySessionStore:
    """Thread-safe in-memory session store."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._sessions: Dict[str, SessionData] = {}

    # PUBLIC_INTERFACE
    def get_or_create_session_id(self, requested_id: Optional[str]) -> str:
        """
        Get an existing session id if present; otherwise create one.

        Args:
            requested_id: Session id provided by a cookie/header.

        Returns:
            A session id string.
        """
        if requested_id:
            with self._lock:
                if requested_id not in self._sessions:
                    self._sessions[requested_id] = SessionData()
                return requested_id

        new_id = uuid4().hex
        with self._lock:
            self._sessions[new_id] = SessionData()
        return new_id

    # PUBLIC_INTERFACE
    def get(self, session_id: str) -> Optional[SessionData]:
        """
        Retrieve session data.

        Args:
            session_id: The session id.

        Returns:
            SessionData if found else None.
        """
        with self._lock:
            return self._sessions.get(session_id)

    # PUBLIC_INTERFACE
    def upsert_payload(self, session_id: str, payload: Dict[str, Any]) -> SessionData:
        """
        Replace the session payload and update timestamps.

        Args:
            session_id: The session id.
            payload: Arbitrary JSON-serializable data to store.

        Returns:
            Updated SessionData.
        """
        with self._lock:
            session = self._sessions.get(session_id) or SessionData()
            session.payload = payload
            session.touch()
            self._sessions[session_id] = session
            return session

    # PUBLIC_INTERFACE
    def patch_payload(self, session_id: str, patch: Dict[str, Any]) -> SessionData:
        """
        Merge keys into the session payload (shallow merge).

        Args:
            session_id: The session id.
            patch: Keys/values to set into the payload.

        Returns:
            Updated SessionData.
        """
        with self._lock:
            session = self._sessions.get(session_id) or SessionData()
            session.payload.update(patch)
            session.touch()
            self._sessions[session_id] = session
            return session


# A single process-wide store instance for the demo app.
STORE = InMemorySessionStore()
