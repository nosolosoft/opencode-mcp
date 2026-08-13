"""Typed contracts for persistent OpenCode jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobStatus(StrEnum):
    """Lifecycle states persisted for a job."""

    STARTING = "starting"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"

    @property
    def terminal(self) -> bool:
        """Whether no further monitor events should change the job."""
        return self in {
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.TIMED_OUT,
        }


class JobHealth(StrEnum):
    """Operational health observed while a job is active."""

    HEALTHY = "healthy"
    STALE = "stale"
    UNREACHABLE = "unreachable"


class OrchestrationMode(StrEnum):
    """Whether the MCP explicitly activates ultrawork."""

    DIRECT = "direct"
    ULW = "ulw"


class InteractionType(StrEnum):
    """OpenCode interaction kinds that can suspend a job."""

    PERMISSION = "permission"
    QUESTION = "question"


class JobInteraction(BaseModel):
    """A pending permission or question requiring an external response."""

    model_config = ConfigDict(frozen=True)

    interaction_id: str
    type: InteractionType
    session_id: str
    title: str | None = None
    questions: list[dict[str, Any]] = Field(default_factory=list)
    permission_type: str | None = None
    pattern: str | list[str] | None = None
    created_at: datetime


class JobRecord(BaseModel):
    """Durable state and latest output snapshot for one OpenCode session."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    session_id: str | None
    message: str
    directory: str
    agent: str | None
    model: str | None
    variant: str | None
    orchestration: OrchestrationMode
    max_runtime_seconds: int | None
    max_output_tokens: int
    status: JobStatus
    health: JobHealth
    created_at: datetime
    updated_at: datetime
    last_event_at: datetime | None
    last_progress_at: datetime | None
    completed_at: datetime | None
    error: str | None
    runtime_seconds: float = 0.0
    active_started_at: datetime | None = None
    output: str = ""
    reasoning: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    interaction: JobInteraction | None = None

    @field_validator(
        "created_at",
        "updated_at",
        "last_event_at",
        "last_progress_at",
        "completed_at",
    )
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        """Reject naive timestamps so persisted comparisons stay unambiguous."""
        if value is not None and value.tzinfo != UTC:
            raise ValueError("timestamps must use UTC")
        return value

    @classmethod
    def new(
        cls,
        *,
        message: str,
        directory: str,
        agent: str | None,
        model: str | None,
        variant: str | None = None,
        orchestration: OrchestrationMode = OrchestrationMode.DIRECT,
        max_runtime_seconds: int | None = None,
        max_output_tokens: int = 25_000,
    ) -> JobRecord:
        """Create a new job record with a UTC creation timestamp."""
        now = datetime.now(UTC)
        return cls(
            job_id=f"job_{uuid4().hex}",
            session_id=None,
            message=message,
            directory=directory,
            agent=agent,
            model=model,
            variant=variant,
            orchestration=orchestration,
            max_runtime_seconds=max_runtime_seconds,
            max_output_tokens=max_output_tokens,
            status=JobStatus.STARTING,
            health=JobHealth.HEALTHY,
            created_at=now,
            updated_at=now,
            last_event_at=None,
            last_progress_at=None,
            completed_at=None,
            error=None,
            active_started_at=now,
        )


class JobStartRequest(BaseModel):
    """Validated input for starting an OpenCode job."""

    model_config = ConfigDict(frozen=True)

    message: str = Field(min_length=1)
    directory: str = Field(min_length=1)
    agent: str | None = None
    model: str | None = None
    variant: str | None = None
    session_id: str | None = None
    orchestration: OrchestrationMode = OrchestrationMode.DIRECT
    max_runtime_seconds: int | None = Field(default=None, ge=1)
    max_output_tokens: int = Field(default=25_000, ge=1)


class JobResponse(BaseModel):
    """Compact job state returned by MCP tools."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    session_id: str | None
    status: JobStatus
    health: JobHealth
    directory: str
    agent: str | None
    model: str | None
    created_at: datetime
    updated_at: datetime
    last_event_at: datetime | None
    last_progress_at: datetime | None
    error: str | None
    output_preview: str
    interaction: JobInteraction | None

    @classmethod
    def from_record(cls, record: JobRecord) -> JobResponse:
        """Project a durable record into a compact status response."""
        return cls(
            job_id=record.job_id,
            session_id=record.session_id,
            status=record.status,
            health=record.health,
            directory=record.directory,
            agent=record.agent,
            model=record.model,
            created_at=record.created_at,
            updated_at=record.updated_at,
            last_event_at=record.last_event_at,
            last_progress_at=record.last_progress_at,
            error=record.error,
            output_preview=record.output[-4_000:],
            interaction=record.interaction,
        )


class JobResultResponse(BaseModel):
    """Paged output and final metadata for a job."""

    model_config = ConfigDict(frozen=True)

    job_id: str
    status: JobStatus
    output: str
    reasoning: str
    tool_calls: list[dict[str, Any]]
    error: str | None
    next_offset: int | None
