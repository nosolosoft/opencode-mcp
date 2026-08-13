from datetime import UTC, datetime

from src.services.fast_mcp.opencode_server.job_models import JobRecord
from src.services.fast_mcp.opencode_server.job_store import JobStore


def test_job_store_round_trips_records(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    record = JobRecord.new(
        message="Run the task",
        directory="/tmp/project",
        agent="build",
        model=None,
    )

    store.create(record)

    loaded = store.get(record.job_id)

    assert loaded == record


def test_job_store_claim_is_exclusive(tmp_path) -> None:
    store = JobStore(tmp_path / "jobs.db")
    record = JobRecord.new(
        message="Run the task",
        directory="/tmp/project",
        agent=None,
        model=None,
    )
    store.create(record)
    expires_at = datetime.now(UTC).timestamp() + 60

    assert store.claim(record.job_id, "monitor-a", expires_at)
    assert not store.claim(record.job_id, "monitor-b", expires_at)
