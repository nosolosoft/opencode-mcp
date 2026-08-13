"""SQLite persistence for OpenCode job state and monitor leases."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from .job_models import JobInteraction, JobRecord

SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    record_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    lease_owner TEXT,
    lease_expires_at REAL
);
CREATE TABLE IF NOT EXISTS interactions (
    interaction_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    interaction_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS jobs_updated_idx ON jobs(updated_at DESC);
CREATE INDEX IF NOT EXISTS interactions_job_idx ON interactions(job_id);
"""


class JobStore:
    """Small synchronous repository for metadata-sized SQLite operations."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def create(self, record: JobRecord) -> None:
        """Persist a new job record."""
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO jobs(job_id, record_json, updated_at) VALUES (?, ?, ?)",
                (record.job_id, record.model_dump_json(), record.updated_at.isoformat()),
            )

    def get(self, job_id: str) -> JobRecord | None:
        """Return one job, or None when it is unknown."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT record_json FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return JobRecord.model_validate_json(row[0])

    def list(self, limit: int = 50) -> list[JobRecord]:
        """Return recent jobs in reverse update order."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT record_json FROM jobs ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [JobRecord.model_validate_json(row[0]) for row in rows]

    def update(self, record: JobRecord) -> None:
        """Replace the durable snapshot for an existing job."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET record_json = ?, updated_at = ? WHERE job_id = ?",
                (record.model_dump_json(), record.updated_at.isoformat(), record.job_id),
            )

    def claim(self, job_id: str, owner: str, expires_at: float) -> bool:
        """Acquire a monitor lease unless another live owner holds it."""
        now = datetime.now(UTC).timestamp()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET lease_owner = ?, lease_expires_at = ?
                WHERE job_id = ?
                  AND (lease_owner IS NULL OR lease_expires_at < ? OR lease_owner = ?)
                """,
                (owner, expires_at, job_id, now, owner),
            )
        return cursor.rowcount == 1

    def release(self, job_id: str, owner: str) -> None:
        """Release a monitor lease owned by the caller."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET lease_owner = NULL, lease_expires_at = NULL "
                "WHERE job_id = ? AND lease_owner = ?",
                (job_id, owner),
            )

    def put_interaction(self, job_id: str, interaction: JobInteraction) -> None:
        """Persist or replace a pending interaction."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO interactions(interaction_id, job_id, interaction_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(interaction_id) DO UPDATE SET interaction_json = excluded.interaction_json
                """,
                (
                    interaction.interaction_id,
                    job_id,
                    interaction.model_dump_json(),
                    interaction.created_at.isoformat(),
                ),
            )

    def remove_interaction(self, interaction_id: str) -> None:
        """Remove a resolved interaction."""
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM interactions WHERE interaction_id = ?",
                (interaction_id,),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level="IMMEDIATE")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
