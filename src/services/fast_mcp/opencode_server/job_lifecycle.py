"""Lifecycle operations for persistent OpenCode jobs."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import Any

from .job_client import JobClient
from .job_events import refresh_health
from .job_models import (
    InteractionType,
    JobHealth,
    JobRecord,
    JobResponse,
    JobResultResponse,
    JobStartRequest,
    JobStatus,
)
from .opencode_executor import OpenCodeExecutor
from .serve_client.client import OpenCodeServeClient, ServerNotRunningError
from .serve_client.models import ModelInfo, PermissionResponseType


class JobLifecycleMixin:
    """Implement public job lifecycle operations for JobManager."""

    async def start(self, request: JobStartRequest) -> JobRecord:
        """Start a job and return after OpenCode accepts its prompt."""
        model = await self._validate_model(request.model, request.variant)
        self.process.start(request.directory)
        client = self.client_factory(request.directory)
        await self._connect_with_retry(client)
        if request.agent is not None:
            agents = await client.list_agents(request.directory)
            names = sorted(
                {
                    name
                    for agent in agents
                    if (name := str(agent.get("name", "")).strip())
                }
            )
            if request.agent not in names:
                await client.disconnect()
                available = ", ".join(names) or "none"
                raise ValueError(
                    f"Unknown OpenCode agent: {request.agent}. Available agents: {available}"
                )

        session_id = request.session_id
        if session_id is None:
            session = await client.create_session(
                title=f"MCP job: {request.message[:60]}",
                directory=request.directory,
            )
            session_id = session.id

        record = JobRecord.new(
            message=request.message,
            directory=request.directory,
            agent=request.agent,
            model=request.model,
            variant=request.variant,
            orchestration=request.orchestration,
            max_runtime_seconds=request.max_runtime_seconds,
            max_output_tokens=request.max_output_tokens,
        ).model_copy(update={"session_id": session_id, "status": JobStatus.RUNNING})
        self.store.create(record)
        self._clients[record.job_id] = client
        record = await self._reconcile_output(record, client)
        message = request.message if request.orchestration.value == "direct" else f"ulw {request.message}"
        monitor = asyncio.create_task(self._monitor(record.job_id))
        self._tasks[record.job_id] = monitor
        await asyncio.sleep(0)
        prompt_succeeded = False
        try:
            await client.prompt_async(
                session_id,
                message,
                model=model,
                agent=request.agent,
            )
            prompt_succeeded = True
        finally:
            if not prompt_succeeded:
                monitor.cancel()
                await asyncio.gather(monitor, return_exceptions=True)
                self._tasks.pop(record.job_id, None)
                self._clients.pop(record.job_id, None)
        return record

    async def _validate_model(
        self,
        model: str | None,
        variant: str | None,
    ) -> ModelInfo | None:
        if model is None:
            return None
        if "/" not in model:
            raise ValueError("Model must use the exact provider/model format")

        provider, model_id = model.split("/", 1)
        if not provider or not model_id:
            raise ValueError("Model must use the exact provider/model format")

        result = await OpenCodeExecutor().list_models(provider=provider)
        if not result.success:
            raise ValueError(
                f"Unable to validate model '{model}': "
                f"{result.error or 'OpenCode model listing failed'}"
            )

        available = [
            candidate
            for candidate in result.data or []
            if isinstance(candidate, str)
        ]
        if model not in available:
            options = ", ".join(available) or "none"
            raise ValueError(
                f"Unknown OpenCode model: {model}. "
                f"Available models for provider '{provider}': {options}"
            )

        return ModelInfo(providerID=provider, modelID=model_id, variant=variant)

    async def recover(self) -> None:
        """Reconnect monitors for persisted jobs that were active before restart."""
        for record in self.store.list():
            if record.status.terminal or record.session_id is None:
                continue
            self.process.start(record.directory)
            client = self.client_factory(record.directory)
            try:
                await client.connect()
            except (ConnectionError, OSError):
                updated = record.model_copy(update={"health": JobHealth.UNREACHABLE})
                self.store.update(updated)
                continue
            self._clients[record.job_id] = client
            record = await self._reconcile_output(record, client)
            self.store.update(record)
            self._tasks[record.job_id] = asyncio.create_task(self._monitor(record.job_id))

    async def status(self, job_id: str) -> JobResponse:
        """Return the current persisted state for a job."""
        record = self._require(job_id)
        record = refresh_health(record, self.STALE_AFTER_SECONDS)
        self.store.update(record)
        return JobResponse.from_record(record)

    async def result(self, job_id: str, offset: int = 0, limit: int = 20_000) -> JobResultResponse:
        """Return a bounded slice of the latest job output."""
        record = self._require(job_id)
        output = record.output[offset : offset + limit]
        next_offset = offset + len(output) if offset + len(output) < len(record.output) else None
        return JobResultResponse(
            job_id=job_id,
            status=record.status,
            output=output,
            reasoning=record.reasoning,
            tool_calls=record.tool_calls,
            error=record.error,
            next_offset=next_offset,
        )

    async def respond(
        self,
        job_id: str,
        interaction_id: str,
        decision: str | None = None,
        answers: list[list[str]] | None = None,
    ) -> JobRecord:
        """Resolve one pending permission or question and resume its job."""
        record = self._require(job_id)
        interaction = record.interaction
        if interaction is None or interaction.interaction_id != interaction_id:
            raise ValueError(f"Unknown interaction for job: {interaction_id}")
        client = self._clients.get(job_id) or self.client_factory(record.directory)
        await client.connect()
        if interaction.type is InteractionType.PERMISSION:
            if decision not in {item.value for item in PermissionResponseType}:
                raise ValueError("Permission decision must be once, always, or reject")
            await client.reply_permission(
                record.session_id or "",
                interaction_id,
                PermissionResponseType(decision),
            )
        elif answers is None:
            await client.reject_question(interaction_id, record.directory)
        else:
            await client.reply_question(interaction_id, answers, record.directory)
        updated = record.model_copy(
            update={
                "status": JobStatus.RUNNING,
                "health": JobHealth.HEALTHY,
                "interaction": None,
                "updated_at": datetime.now(UTC),
                "active_started_at": datetime.now(UTC),
            }
        )
        self.store.update(updated)
        self._clients[job_id] = client
        return updated

    async def cancel(self, job_id: str) -> JobRecord:
        """Abort the OpenCode session and mark the job cancelled."""
        record = self._require(job_id)
        client = self._clients.get(job_id) or self.client_factory(record.directory)
        await client.connect()
        if record.session_id:
            await client.abort_session(record.session_id)
        updated = record.model_copy(
            update={
                "status": JobStatus.CANCELLED,
                "updated_at": datetime.now(UTC),
                "completed_at": datetime.now(UTC),
            }
        )
        self.store.update(updated)
        task = self._tasks.pop(job_id, None)
        if task is not None:
            task.cancel()
        await client.disconnect()
        self._clients.pop(job_id, None)
        return updated

    async def list(self, limit: int = 50) -> list[JobResponse]:
        """List recent persisted jobs."""
        return [JobResponse.from_record(record) for record in self.store.list(limit)]

    async def list_agents(self, directory: str) -> list[dict[str, Any]]:
        """List agents available to OpenCode in a project directory."""
        self.process.start(directory)
        client = self.client_factory(directory)
        await self._connect_with_retry(client)
        try:
            return await client.list_agents(directory)
        finally:
            await client.disconnect()

    def health(self) -> dict[str, Any]:
        """Return local manager health without contacting a job session."""
        active = sum(not record.status.terminal for record in self.store.list(limit=500))
        return {
            "database": str(self.store.path),
            "active_jobs": active,
            "monitors": len(self._tasks),
            "serve_process_running": self.process.process is not None
            and self.process.process.poll() is None,
        }

    async def shutdown(self) -> None:
        """Cancel monitors and close clients without aborting active sessions."""
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for client in self._clients.values():
            await client.disconnect()
        self._tasks.clear()
        self._clients.clear()

    async def _connect_with_retry(self, client: JobClient) -> None:
        for attempt in range(20):
            try:
                await client.connect()
                return
            except ServerNotRunningError:
                if attempt == 19:
                    raise
                await asyncio.sleep(0.25)

    @staticmethod
    def _default_client(directory: str) -> JobClient:
        return OpenCodeServeClient(
            host=os.environ.get("OPENCODE_SERVE_HOST", "127.0.0.1"),
            port=int(os.environ.get("OPENCODE_SERVE_PORT", "4097")),
            directory=directory,
            auto_approve_permissions=False,
            timeout=30.0,
        )
