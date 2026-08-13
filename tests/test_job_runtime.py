from datetime import UTC, datetime, timedelta

from src.services.fast_mcp.opencode_server.job_models import JobHealth, JobRecord, JobStatus


def test_runtime_is_paused_without_a_runtime_limit() -> None:
    started = datetime.now(UTC) - timedelta(hours=2)
    record = JobRecord.new(message="Task", directory="/tmp", agent=None, model=None).model_copy(
        update={"active_started_at": started, "status": JobStatus.WAITING_INPUT, "health": JobHealth.HEALTHY}
    )

    assert record.max_runtime_seconds is None
    assert record.status is JobStatus.WAITING_INPUT
    assert record.runtime_seconds == 0.0
