import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from src.services.fast_mcp.opencode_server.job_models import (
    JobStartRequest,
    JobStatus,
    OrchestrationMode,
)
from src.services.fast_mcp.opencode_server.job_manager import JobManager
from src.services.fast_mcp.opencode_server.job_store import JobStore
from src.services.fast_mcp.opencode_server.models import OpenCodeResult
from src.services.fast_mcp.opencode_server.opencode_executor import OpenCodeExecutor
from src.services.fast_mcp.opencode_server.serve_client.models import SessionStatus, SessionStatusType


class FakeProcess:
    def start(self, directory: str) -> None:
        return None

    def stop(self) -> None:
        return None


class FakeClient:
    def __init__(
        self,
        event_delay: float = 60.0,
        event: object | None = None,
        messages: list[dict] | None = None,
        keep_stream_open: bool = False,
        require_stream_before_prompt: bool = False,
        session_idle: bool = False,
    ) -> None:
        self.messages: list[str] = []
        self.event_delay = event_delay
        self.event = event
        self.history = messages or []
        self.keep_stream_open = keep_stream_open
        self.require_stream_before_prompt = require_stream_before_prompt
        self.session_idle = session_idle
        self.stream_started = False
        self.aborted_sessions: list[str] = []
        self.prompt_options: dict[str, object] = {}
        self.sessions_created = 0

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def list_agents(self, directory: str | None = None) -> list[dict]:
        return [{"name": "build", "mode": "primary"}, {"name": "explore", "mode": "subagent"}]

    async def create_session(self, title: str | None = None, directory: str | None = None):
        self.sessions_created += 1
        return type("Session", (), {"id": "ses_test"})()

    async def prompt_async(self, session_id: str, text: str, **kwargs: str | None) -> None:
        if self.require_stream_before_prompt:
            await asyncio.sleep(0)
        if self.require_stream_before_prompt and not self.stream_started:
            raise AssertionError("SSE monitor must start before prompt_async")
        self.messages.append(text)
        self.prompt_options = kwargs

    async def get_messages(self, session_id: str) -> list[dict]:
        return self.history

    async def get_session_status(self, session_id: str) -> SessionStatus:
        status = SessionStatusType.IDLE if self.session_idle else SessionStatusType.BUSY
        return SessionStatus(type=status)

    async def abort_session(self, session_id: str) -> None:
        self.aborted_sessions.append(session_id)

    async def stream_events(self, directory: str | None = None):
        self.stream_started = True
        await asyncio.sleep(self.event_delay)
        if self.event is not None:
            yield self.event
        if self.keep_stream_open:
            await asyncio.sleep(60)


@pytest.mark.asyncio
async def test_start_job_keeps_explicit_agent_and_direct_message(tmp_path) -> None:
    client = FakeClient()
    manager = JobManager(
        store=JobStore(tmp_path / "jobs.db"),
        process=FakeProcess(),
        client_factory=lambda directory: client,
    )

    record = await manager.start(
        JobStartRequest(
            message="Do the work",
            directory=str(tmp_path),
            agent="explore",
        )
    )

    assert record.agent == "explore"
    assert client.messages == ["Do the work"]
    await manager.shutdown()


@pytest.mark.asyncio
async def test_start_job_injects_ulw_only_when_requested(tmp_path) -> None:
    client = FakeClient()
    manager = JobManager(
        store=JobStore(tmp_path / "jobs.db"),
        process=FakeProcess(),
        client_factory=lambda directory: client,
    )

    await manager.start(
        JobStartRequest(
            message="Do the work",
            directory=str(tmp_path),
            orchestration=OrchestrationMode.ULW,
        )
    )

    assert client.messages == ["ulw Do the work"]
    await manager.shutdown()


@pytest.mark.asyncio
async def test_start_job_converts_public_model_id_to_prompt_model(monkeypatch, tmp_path) -> None:
    async def list_models(self, provider=None, timeout=None):
        return OpenCodeResult(
            success=True,
            data=["openai/gpt-5.4"],
        )

    monkeypatch.setattr(OpenCodeExecutor, "list_models", list_models)
    client = FakeClient()
    manager = JobManager(
        store=JobStore(tmp_path / "jobs.db"),
        process=FakeProcess(),
        client_factory=lambda directory: client,
    )

    await manager.start(
        JobStartRequest(
            message="Do the work",
            directory=str(tmp_path),
            model="openai/gpt-5.4",
        )
    )

    model = client.prompt_options["model"]
    assert model is not None
    assert model.providerID == "openai"
    assert model.modelID == "gpt-5.4"
    await manager.shutdown()


@pytest.mark.asyncio
async def test_start_job_passes_variant_inside_prompt_model(monkeypatch, tmp_path) -> None:
    async def list_models(self, provider=None, timeout=None):
        return OpenCodeResult(
            success=True,
            data=["google/gemini-3.1-pro-preview"],
        )

    monkeypatch.setattr(OpenCodeExecutor, "list_models", list_models)
    client = FakeClient()
    manager = JobManager(
        store=JobStore(tmp_path / "jobs.db"),
        process=FakeProcess(),
        client_factory=lambda directory: client,
    )

    await manager.start(
        JobStartRequest(
            message="Do the work",
            directory=str(tmp_path),
            model="google/gemini-3.1-pro-preview",
            variant="high",
        )
    )

    model = client.prompt_options["model"]
    assert model is not None
    assert model.variant == "high"
    await manager.shutdown()


@pytest.mark.asyncio
async def test_start_job_rejects_unknown_model_with_live_options(monkeypatch, tmp_path) -> None:
    async def list_models(self, provider=None, timeout=None):
        return OpenCodeResult(
            success=True,
            data=["openai/gpt-5.4", "openai/gpt-5.6-luna", "google/gemini-3.1-pro-preview"],
        )

    monkeypatch.setattr(OpenCodeExecutor, "list_models", list_models)
    client = FakeClient()
    manager = JobManager(
        store=JobStore(tmp_path / "jobs.db"),
        process=FakeProcess(),
        client_factory=lambda directory: client,
    )

    with pytest.raises(ValueError, match="openai/gpt-5.4.*openai/gpt-5.6-luna"):
        await manager.start(
            JobStartRequest(
                message="Do the work",
                directory=str(tmp_path),
                model="openai/not-a-real-model",
            )
        )

    assert client.sessions_created == 0
    assert client.messages == []
    await manager.shutdown()


@pytest.mark.asyncio
async def test_start_job_rejects_unknown_agent_with_available_names(tmp_path) -> None:
    client = FakeClient()
    manager = JobManager(
        store=JobStore(tmp_path / "jobs.db"),
        process=FakeProcess(),
        client_factory=lambda directory: client,
    )

    with pytest.raises(ValueError, match="build.*explore"):
        await manager.start(
            JobStartRequest(
                message="Do the work",
                directory=str(tmp_path),
                agent="missing",
            )
        )

    assert client.sessions_created == 0
    await manager.shutdown()


@pytest.mark.asyncio
async def test_start_subscribes_to_events_before_sending_prompt(tmp_path) -> None:
    client = FakeClient(require_stream_before_prompt=True)
    manager = JobManager(
        store=JobStore(tmp_path / "jobs.db"),
        process=FakeProcess(),
        client_factory=lambda directory: client,
    )

    await manager.start(JobStartRequest(message="Do the work", directory=str(tmp_path)))

    assert client.stream_started
    await manager.shutdown()


@pytest.mark.asyncio
async def test_monitor_completes_when_session_is_idle_without_terminal_sse_event(tmp_path) -> None:
    client = FakeClient(session_idle=True, keep_stream_open=True)
    manager = JobManager(
        store=JobStore(tmp_path / "jobs.db"),
        process=FakeProcess(),
        client_factory=lambda directory: client,
    )
    manager.MONITOR_TICK_SECONDS = 0.01

    record = await manager.start(JobStartRequest(message="Do the work", directory=str(tmp_path)))
    await asyncio.sleep(0.03)

    current = manager.store.get(record.job_id)
    assert current is not None
    assert current.status is JobStatus.COMPLETED
    await manager.shutdown()


@pytest.mark.asyncio
async def test_monitor_keeps_sse_read_alive_across_watchdog_ticks(tmp_path) -> None:
    client = FakeClient(
        event_delay=0.03,
        event=SimpleNamespace(
            type="message.part.updated",
            properties={
                "part": {"type": "text", "sessionID": "ses_test"},
                "delta": "hello",
            },
        ),
        keep_stream_open=True,
    )
    manager = JobManager(
        store=JobStore(tmp_path / "jobs.db"),
        process=FakeProcess(),
        client_factory=lambda directory: client,
    )
    manager.MONITOR_TICK_SECONDS = 0.01

    record = await manager.start(
        JobStartRequest(message="Do the work", directory=str(tmp_path))
    )
    await asyncio.sleep(0.06)

    current = manager.store.get(record.job_id)
    assert current is not None
    assert current.output == "hello"
    await manager.shutdown()


@pytest.mark.asyncio
async def test_terminal_event_reconciles_final_output_from_session_history(tmp_path) -> None:
    client = FakeClient(
        event_delay=0.01,
        event=SimpleNamespace(
            type="session.idle",
            properties={"sessionID": "ses_test"},
        ),
        messages=[
            {
                "info": {"role": "user"},
                "parts": [{"type": "text", "text": "Reply OK"}],
            },
            {
                "info": {"role": "assistant"},
                "parts": [{"type": "text", "text": "OK"}],
            }
        ],
    )
    manager = JobManager(
        store=JobStore(tmp_path / "jobs.db"),
        process=FakeProcess(),
        client_factory=lambda directory: client,
    )

    record = await manager.start(
        JobStartRequest(message="Reply OK", directory=str(tmp_path))
    )
    await asyncio.sleep(0.03)

    current = manager.store.get(record.job_id)
    assert current is not None
    assert current.status is JobStatus.COMPLETED
    assert current.output == "OK"
    await manager.shutdown()


@pytest.mark.asyncio
async def test_monitor_aborts_job_when_explicit_runtime_limit_is_reached(tmp_path) -> None:
    client = FakeClient()
    manager = JobManager(
        store=JobStore(tmp_path / "jobs.db"),
        process=FakeProcess(),
        client_factory=lambda directory: client,
    )
    manager.MONITOR_TICK_SECONDS = 0.01

    record = await manager.start(
        JobStartRequest(
            message="Do the work",
            directory=str(tmp_path),
            max_runtime_seconds=1,
        )
    )
    current = manager.store.get(record.job_id)
    assert current is not None
    manager.store.update(
        current.model_copy(
            update={"active_started_at": datetime.now(UTC) - timedelta(seconds=2)}
        )
    )
    await asyncio.sleep(0.03)

    timed_out = manager.store.get(record.job_id)
    assert timed_out is not None
    assert timed_out.status is JobStatus.TIMED_OUT
    assert client.aborted_sessions == ["ses_test"]
    await manager.shutdown()


@pytest.mark.asyncio
async def test_monitor_expires_waiting_interaction_after_24_hours(tmp_path) -> None:
    client = FakeClient(
        event_delay=0.01,
        event=SimpleNamespace(
            type="permission.updated",
            properties={
                "sessionID": "ses_test",
                "id": "perm_test",
                "type": "read",
                "title": "Permission required",
            },
        ),
        keep_stream_open=True,
    )
    manager = JobManager(
        store=JobStore(tmp_path / "jobs.db"),
        process=FakeProcess(),
        client_factory=lambda directory: client,
    )
    manager.MONITOR_TICK_SECONDS = 0.01

    record = await manager.start(
        JobStartRequest(message="Need permission", directory=str(tmp_path))
    )
    await asyncio.sleep(0.03)
    current = manager.store.get(record.job_id)
    assert current is not None
    assert current.status is JobStatus.WAITING_INPUT
    assert current.interaction is not None
    manager.store.update(
        current.model_copy(
            update={
                "interaction": current.interaction.model_copy(
                    update={
                        "created_at": datetime.now(UTC) - timedelta(days=2),
                    }
                )
            }
        )
    )
    await asyncio.sleep(0.03)

    expired = manager.store.get(record.job_id)
    assert expired is not None
    assert expired.status is JobStatus.TIMED_OUT
    assert client.aborted_sessions == ["ses_test"]
    await manager.shutdown()
