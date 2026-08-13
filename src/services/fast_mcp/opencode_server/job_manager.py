"""Asynchronous monitor for persistent OpenCode jobs."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from .job_client import JobClient
from .job_events import apply_event, check_runtime, refresh_health
from .job_lifecycle import JobLifecycleMixin
from .job_models import JobHealth, JobRecord, JobStatus
from .job_store import JobStore
from .serve_process import ServeProcess


class JobManager(JobLifecycleMixin):
    """Create, monitor, persist, and control long-running jobs."""

    STALE_AFTER_SECONDS = 180.0
    WAITING_INPUT_MAX_SECONDS = 24 * 60 * 60
    MONITOR_TICK_SECONDS = 30.0

    def __init__(
        self,
        store: JobStore,
        process: ServeProcess,
        client_factory: Callable[[str], JobClient] | None = None,
    ) -> None:
        self.store = store
        self.process = process
        self.client_factory = client_factory or self._default_client
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._clients: dict[str, JobClient] = {}

    async def _monitor(self, job_id: str) -> None:
        record = self._require(job_id)
        client = self._clients[job_id]
        events = client.stream_events(record.directory)
        event_task: asyncio.Task[Any] | None = asyncio.create_task(events.__anext__())
        try:
            while True:
                done, _ = await asyncio.wait(
                    (event_task,),
                    timeout=self.MONITOR_TICK_SECONDS,
                )
                if not done:
                    current = self._require(job_id)
                    now = datetime.now(UTC)
                    current = refresh_health(current, self.STALE_AFTER_SECONDS)
                    current = check_runtime(current, now)
                    if current.status is JobStatus.RUNNING and current.session_id:
                        session_status = await client.get_session_status(current.session_id)
                        if session_status.type.value == "idle":
                            current = current.model_copy(
                                update={
                                    "status": JobStatus.COMPLETED,
                                    "health": JobHealth.HEALTHY,
                                    "completed_at": now,
                                }
                            )
                    if current.status is JobStatus.WAITING_INPUT and current.interaction is not None:
                        waiting_seconds = (now - current.interaction.created_at).total_seconds()
                        if waiting_seconds >= self.WAITING_INPUT_MAX_SECONDS:
                            current = current.model_copy(
                                update={
                                    "status": JobStatus.TIMED_OUT,
                                    "completed_at": now,
                                    "error": "Job interaction expired after 24 hours",
                                }
                            )
                    self.store.update(current)
                    if current.status.terminal:
                        if current.session_id:
                            await client.abort_session(current.session_id)
                        return
                    continue
                try:
                    event = event_task.result()
                except StopAsyncIteration:
                    return
                event_task = asyncio.create_task(events.__anext__())
                current = self._require(job_id)
                now = datetime.now(UTC)
                current = current.model_copy(update={"last_event_at": now, "updated_at": now})
                current = apply_event(current, event, now, self.store)
                current = check_runtime(current, now)
                if current.status.terminal:
                    current = await self._reconcile_output(current, client)
                self.store.update(current)
                if current.status.terminal:
                    return
        except asyncio.CancelledError:
            raise
        except (ConnectionError, OSError) as error:
            current = self._require(job_id).model_copy(
                update={"health": JobHealth.UNREACHABLE, "error": str(error), "updated_at": datetime.now(UTC)}
            )
            self.store.update(current)
        finally:
            if event_task is not None and not event_task.done():
                event_task.cancel()
            if event_task is not None:
                await asyncio.gather(event_task, return_exceptions=True)
            if job_id in self._clients and self._require(job_id).status.terminal:
                await client.disconnect()
                self._clients.pop(job_id, None)

    def _require(self, job_id: str) -> JobRecord:
        record = self.store.get(job_id)
        if record is None:
            raise ValueError(f"Unknown job: {job_id}")
        return record

    async def _reconcile_output(self, record: JobRecord, client: JobClient) -> JobRecord:
        if record.session_id is None:
            return record
        messages = await client.get_messages(record.session_id)
        parts = [
            str(part.get("text", ""))
            for message in messages
            if isinstance(message.get("info"), dict) and message["info"].get("role") == "assistant"
            for part in message.get("parts", [])
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        output = "".join(parts)
        if output == record.output:
            return record
        now = datetime.now(UTC)
        return record.model_copy(update={"output": output, "last_progress_at": now, "updated_at": now})
