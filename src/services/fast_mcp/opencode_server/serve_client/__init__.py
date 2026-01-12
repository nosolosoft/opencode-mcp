"""
OpenCode Serve Client
HTTP client for interacting with opencode serve API.

This module provides a persistent HTTP client that connects to
an opencode serve instance instead of spawning subprocess for each request.
"""

from .client import (
    OpenCodeServeClient,
    OpenCodeServeError,
    ServerNotRunningError,
    SessionBusyError,
    PermissionRequiredError,
    create_opencode_client,
)
from .models import (
    # Session models
    Session,
    SessionStatus,
    SessionStatusType,
    # Message models
    Message,
    UserMessage,
    AssistantMessage,
    MessagePart,
    TextPart,
    ToolPart,
    # Event models
    SSEEvent,
    EventMessageUpdated,
    EventMessagePartUpdated,
    EventSessionStatus,
    EventPermissionUpdated,
    # Permission models
    Permission,
    PermissionResponse,
    PermissionResponseType,
    # Request/Response models
    CreateSessionRequest,
    PromptRequest,
    PromptPart,
    ModelInfo,
)
from .session_manager import SessionManager, SessionContext, SessionInfo
from .sse_handler import SSEHandler, StreamedResponse, SSEEventAggregator

__all__ = [
    # Main client
    "OpenCodeServeClient",
    "create_opencode_client",
    # Exceptions
    "OpenCodeServeError",
    "ServerNotRunningError",
    "SessionBusyError",
    "PermissionRequiredError",
    # Session management
    "SessionManager",
    "SessionContext",
    "SessionInfo",
    # SSE handling
    "SSEHandler",
    "StreamedResponse",
    "SSEEventAggregator",
    # Session models
    "Session",
    "SessionStatus",
    "SessionStatusType",
    # Message models
    "Message",
    "UserMessage",
    "AssistantMessage",
    "MessagePart",
    "TextPart",
    "ToolPart",
    # Event models
    "SSEEvent",
    "EventMessageUpdated",
    "EventMessagePartUpdated",
    "EventSessionStatus",
    "EventPermissionUpdated",
    # Permission models
    "Permission",
    "PermissionResponse",
    "PermissionResponseType",
    # Request/Response models
    "CreateSessionRequest",
    "PromptRequest",
    "PromptPart",
    "ModelInfo",
]
