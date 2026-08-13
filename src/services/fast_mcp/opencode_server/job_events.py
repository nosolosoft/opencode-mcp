"""Project OpenCode events into durable job state."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from .job_models import InteractionType, JobHealth, JobInteraction, JobRecord, JobStatus
from .job_store import JobStore


def apply_event(record: JobRecord, event: Any, now: datetime, store: JobStore) -> JobRecord:  # noqa: ANN401
    """Apply one OpenCode event to a job snapshot."""
    event_type = getattr(event, "type", "unknown")
    properties = getattr(event, "properties", {})
    if not isinstance(properties, dict):
        return record
    part = properties.get("part", {})
    session_id = properties.get("sessionID")
    if session_id is None and isinstance(part, dict):
        session_id = part.get("sessionID")
    if session_id is not None and session_id != record.session_id:
        return record
    if event_type == "permission.updated":
        interaction = JobInteraction(
            interaction_id=str(properties.get("id", "")),
            type=InteractionType.PERMISSION,
            session_id=record.session_id or "",
            title=str(properties.get("title", "Permission required")),
            permission_type=str(properties.get("type", "")),
            pattern=properties.get("pattern"),
            created_at=now,
        )
        store.put_interaction(record.job_id, interaction)
        return record.model_copy(update={"status": JobStatus.WAITING_INPUT, "interaction": interaction})
    if event_type in {"question.asked", "question.updated"}:
        interaction = JobInteraction(
            interaction_id=str(properties.get("id", properties.get("requestID", ""))),
            type=InteractionType.QUESTION,
            session_id=record.session_id or "",
            title=str(properties.get("title", "Question")),
            questions=properties.get("questions", []),
            created_at=now,
        )
        store.put_interaction(record.job_id, interaction)
        return record.model_copy(update={"status": JobStatus.WAITING_INPUT, "interaction": interaction})
    if event_type in {"session.idle", "session.status"}:
        status = properties.get("status", {})
        idle = event_type == "session.idle" or (isinstance(status, dict) and status.get("type") == "idle")
        if idle:
            return record.model_copy(
                update={"status": JobStatus.COMPLETED, "health": JobHealth.HEALTHY, "completed_at": now}
            )
    if event_type == "session.error":
        return record.model_copy(
            update={"status": JobStatus.FAILED, "error": str(properties.get("error", "OpenCode session error"))}
        )
    if event_type == "message.part.updated":
        delta = properties.get("delta", "")
        if isinstance(part, dict) and part.get("type") == "reasoning":
            return record.model_copy(update={"reasoning": record.reasoning + str(delta), "last_progress_at": now})
        if isinstance(part, dict) and part.get("type") == "text":
            return record.model_copy(update={"output": record.output + str(delta), "last_progress_at": now})
        return record.model_copy(update={"last_progress_at": now})
    return record


def check_runtime(record: JobRecord, now: datetime) -> JobRecord:
    """Enforce only an explicitly configured active runtime limit."""
    if record.max_runtime_seconds is None or record.active_started_at is None:
        return record
    if record.status is JobStatus.WAITING_INPUT:
        return record
    runtime = record.runtime_seconds + (now - record.active_started_at).total_seconds()
    if runtime >= record.max_runtime_seconds:
        return record.model_copy(
            update={
                "status": JobStatus.TIMED_OUT,
                "runtime_seconds": runtime,
                "completed_at": now,
                "error": "Job exceeded max_runtime_seconds",
            }
        )
    return record.model_copy(update={"runtime_seconds": runtime, "active_started_at": now})


def refresh_health(record: JobRecord, stale_after_seconds: float) -> JobRecord:
    """Mark active jobs stale when their last event is too old."""
    if record.status.terminal or record.last_event_at is None:
        return record
    stale = time.time() - record.last_event_at.timestamp() > stale_after_seconds
    return record.model_copy(update={"health": JobHealth.STALE if stale else JobHealth.HEALTHY})
