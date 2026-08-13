from datetime import UTC, datetime

import pytest

from src.services.fast_mcp.opencode_server.job_models import (
    JobHealth,
    JobRecord,
    JobStatus,
    OrchestrationMode,
)


def test_job_record_defaults_to_running_and_healthy() -> None:
    record = JobRecord.new(
        message="Run the task",
        directory="/tmp/project",
        agent="build",
        model="openai/gpt-5.6",
    )

    assert record.status is JobStatus.STARTING
    assert record.health is JobHealth.HEALTHY
    assert record.orchestration is OrchestrationMode.DIRECT
    assert record.max_runtime_seconds is None


def test_job_record_rejects_non_utc_timestamps() -> None:
    with pytest.raises(ValueError, match="UTC"):
        JobRecord(
            job_id="job_test",
            session_id=None,
            message="Run the task",
            directory="/tmp/project",
            agent="build",
            model=None,
            variant=None,
            orchestration=OrchestrationMode.DIRECT,
            max_runtime_seconds=None,
            max_output_tokens=25_000,
            status=JobStatus.STARTING,
            health=JobHealth.HEALTHY,
            created_at=datetime.now(),
            updated_at=datetime.now(UTC),
            last_event_at=None,
            last_progress_at=None,
            completed_at=None,
            error=None,
        )
