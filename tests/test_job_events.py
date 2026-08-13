from datetime import UTC, datetime

from src.services.fast_mcp.opencode_server.job_events import apply_event
from src.services.fast_mcp.opencode_server.job_models import JobRecord, JobStatus
from src.services.fast_mcp.opencode_server.job_store import JobStore


def test_part_event_uses_nested_session_id_and_ignores_other_sessions(tmp_path) -> None:
    record = JobRecord.new(message="Task", directory="/tmp", agent=None, model=None).model_copy(
        update={"session_id": "ses_target"}
    )
    now = datetime.now(UTC)
    event = type(
        "Event",
        (),
        {
            "type": "message.part.updated",
            "properties": {
                "part": {"type": "text", "sessionID": "ses_other"},
                "delta": "wrong",
            },
        },
    )()

    result = apply_event(record, event, now, JobStore(tmp_path / "jobs.db"))

    assert result.status is JobStatus.STARTING
    assert result.output == ""
