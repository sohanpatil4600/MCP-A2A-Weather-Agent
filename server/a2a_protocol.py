from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
import hashlib
import json
import os
import sqlite3
import uuid


@dataclass
class A2AHandoffEnvelope:
    task_id: str
    trace_id: str
    parent_task_id: str | None
    query: str
    target_agent: str
    priority: str = "normal"
    retry_count: int = 0
    deadline_ms: int = 12000
    idempotency_key: str = field(default_factory=lambda: uuid.uuid4().hex)
    cancel_token: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def deadline_at(self) -> datetime:
        created = datetime.fromisoformat(self.created_at)
        return created + timedelta(milliseconds=self.deadline_ms)

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.deadline_at()

    def remaining_seconds(self) -> float:
        remaining = (self.deadline_at() - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, remaining)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "parent_task_id": self.parent_task_id,
            "query": self.query,
            "target_agent": self.target_agent,
            "priority": self.priority,
            "retry_count": self.retry_count,
            "deadline_ms": self.deadline_ms,
            "idempotency_key": self.idempotency_key,
            "cancel_token": self.cancel_token,
            "created_at": self.created_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class A2AIdempotencyStore:
    """Simple in-memory idempotency store for A2A handoffs."""

    def __init__(self) -> None:
        self._results: dict[str, str] = {}

    def has(self, idempotency_key: str) -> bool:
        return idempotency_key in self._results

    def get(self, idempotency_key: str) -> str | None:
        return self._results.get(idempotency_key)

    def set(self, idempotency_key: str, result: str) -> None:
        self._results[idempotency_key] = result


class SQLiteA2AIdempotencyStore:
    """Durable idempotency store backed by SQLite."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _ensure_schema(self) -> None:
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency_results (
                    idempotency_key TEXT PRIMARY KEY,
                    result TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def has(self, idempotency_key: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM idempotency_results WHERE idempotency_key = ? LIMIT 1",
                (idempotency_key,),
            ).fetchone()
            return row is not None

    def get(self, idempotency_key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT result FROM idempotency_results WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if row is None:
                return None
            return row[0]

    def set(self, idempotency_key: str, result: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO idempotency_results (idempotency_key, result, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(idempotency_key)
                DO UPDATE SET result=excluded.result
                """,
                (idempotency_key, result, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()


def _make_idempotency_key(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def build_handoff(
    query: str,
    target_agent: str,
    parent_task_id: str | None = None,
    deadline_ms: int = 12000,
    idempotency_seed: str | None = None,
) -> A2AHandoffEnvelope:
    seed = idempotency_seed or f"{target_agent}:{query.strip().lower()}"
    return A2AHandoffEnvelope(
        task_id=f"task_{uuid.uuid4().hex[:12]}",
        trace_id=f"trace_{uuid.uuid4().hex[:12]}",
        parent_task_id=parent_task_id,
        query=query,
        target_agent=target_agent,
        deadline_ms=deadline_ms,
        idempotency_key=_make_idempotency_key(seed),
    )
