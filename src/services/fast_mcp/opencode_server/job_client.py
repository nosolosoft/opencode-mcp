"""Protocols for OpenCode operations used by persistent jobs."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from .serve_client.models import ModelInfo, PermissionResponseType


class SessionLike(Protocol):
    """Minimum session shape required by the manager."""

    id: str


class JobClient(Protocol):
    """OpenCode operations used by a running job."""

    async def connect(self) -> None: ...

    async def list_agents(self, directory: str | None = None) -> list[dict[str, Any]]: ...

    async def create_session(
        self,
        title: str | None = None,
        directory: str | None = None,
    ) -> SessionLike: ...

    async def prompt_async(
        self,
        session_id: str,
        text: str,
        model: ModelInfo | None = None,
        agent: str | None = None,
    ) -> None: ...

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]: ...

    async def stream_events(self, directory: str | None = None) -> AsyncIterator[Any]: ...

    async def abort_session(self, session_id: str) -> None: ...

    async def reply_permission(
        self,
        session_id: str,
        permission_id: str,
        response: PermissionResponseType,
    ) -> None: ...

    async def reply_question(
        self,
        request_id: str,
        answers: list[list[str]],
        directory: str | None = None,
    ) -> None: ...

    async def reject_question(self, request_id: str, directory: str | None = None) -> None: ...

    async def disconnect(self) -> None: ...
