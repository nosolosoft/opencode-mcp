"""
OpenCode Serve API Models
Pydantic models based on OpenCode's TypeScript types.gen.d.ts

These models represent the data structures used by the opencode serve HTTP API.
"""

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class SessionStatusType(str, Enum):
    """Session status types."""
    IDLE = "idle"
    BUSY = "busy"
    RETRY = "retry"


class PermissionResponseType(str, Enum):
    """Permission response options."""
    ONCE = "once"
    ALWAYS = "always"
    REJECT = "reject"


class ToolStatus(str, Enum):
    """Tool execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"


# =============================================================================
# Time Models
# =============================================================================

class TimeCreated(BaseModel):
    """Time information with created timestamp."""
    created: int = Field(description="Unix timestamp in milliseconds")


class TimeCreatedUpdated(BaseModel):
    """Time information with created and updated timestamps."""
    created: int = Field(description="Unix timestamp in milliseconds")
    updated: int = Field(description="Unix timestamp in milliseconds")


class TimeCreatedCompleted(BaseModel):
    """Time information with created and optional completed timestamps."""
    created: int = Field(description="Unix timestamp in milliseconds")
    completed: Optional[int] = Field(default=None, description="Completion timestamp")


# =============================================================================
# Model Info
# =============================================================================

class ModelInfo(BaseModel):
    """Model selection information."""
    providerID: str = Field(description="Provider identifier (e.g., 'anthropic')")
    modelID: str = Field(description="Model identifier (e.g., 'claude-sonnet-4-20250514')")
    variant: Optional[str] = Field(default=None, description="Optional model variant")


class TokenInfo(BaseModel):
    """Token usage information."""
    input: int = Field(default=0, description="Input tokens")
    output: int = Field(default=0, description="Output tokens")
    reasoning: int = Field(default=0, description="Reasoning tokens")
    cache: Optional[Dict[str, int]] = Field(
        default=None,
        description="Cache read/write tokens"
    )


# =============================================================================
# Session Models
# =============================================================================

class Session(BaseModel):
    """OpenCode session representation."""
    id: str = Field(description="Unique session identifier")
    projectID: str = Field(description="Project identifier")
    directory: str = Field(description="Working directory")
    parentID: Optional[str] = Field(default=None, description="Parent session ID")
    title: str = Field(description="Session title")
    share: Optional[Dict[str, str]] = Field(default=None, description="Share information")
    time: TimeCreatedUpdated = Field(description="Timestamps")

    class Config:
        extra = "allow"


class SessionStatus(BaseModel):
    """Session status information."""
    type: SessionStatusType = Field(description="Current status")
    since: Optional[int] = Field(default=None, description="Since timestamp")


class SessionListResponse(BaseModel):
    """Response for session list endpoint."""
    sessions: List[Session] = Field(default_factory=list)


class SessionStatusResponse(BaseModel):
    """Response for session status endpoint."""
    status: Dict[str, SessionStatus] = Field(default_factory=dict)


# =============================================================================
# Message Part Models
# =============================================================================

class TextPart(BaseModel):
    """Text content part."""
    type: Literal["text"] = "text"
    text: str = Field(description="Text content")


class ReasoningPart(BaseModel):
    """Reasoning/thinking content part."""
    type: Literal["reasoning"] = "reasoning"
    text: str = Field(description="Reasoning text")
    redacted: bool = Field(default=False, description="Whether content is redacted")


class ToolStatePending(BaseModel):
    """Tool pending state."""
    status: Literal["pending"] = "pending"


class ToolStateRunning(BaseModel):
    """Tool running state."""
    status: Literal["running"] = "running"
    input: Optional[Any] = Field(default=None, description="Tool input")


class ToolStateCompleted(BaseModel):
    """Tool completed state."""
    status: Literal["completed"] = "completed"
    input: Any = Field(description="Tool input")
    output: Any = Field(description="Tool output")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Tool metadata")


class ToolStateError(BaseModel):
    """Tool error state."""
    status: Literal["error"] = "error"
    input: Optional[Any] = Field(default=None, description="Tool input")
    error: str = Field(description="Error message")


ToolState = Union[ToolStatePending, ToolStateRunning, ToolStateCompleted, ToolStateError]


class ToolPart(BaseModel):
    """Tool call part."""
    type: Literal["tool"] = "tool"
    callID: str = Field(description="Unique call identifier")
    tool: str = Field(description="Tool name")
    state: ToolState = Field(description="Tool execution state")


class FilePart(BaseModel):
    """File reference part."""
    type: Literal["file"] = "file"
    mediaType: str = Field(description="MIME type")
    filename: str = Field(description="File name")
    url: str = Field(description="File URL or path")


class StepStartPart(BaseModel):
    """Step start marker."""
    type: Literal["step-start"] = "step-start"


class StepFinishPart(BaseModel):
    """Step finish marker."""
    type: Literal["step-finish"] = "step-finish"
    finishReason: str = Field(description="Reason for step completion")


# Union of all part types
MessagePart = Union[
    TextPart,
    ReasoningPart,
    ToolPart,
    FilePart,
    StepStartPart,
    StepFinishPart,
]


# =============================================================================
# Message Models
# =============================================================================

class UserMessage(BaseModel):
    """User message representation."""
    id: str = Field(description="Message identifier")
    sessionID: str = Field(description="Session identifier")
    role: Literal["user"] = "user"
    time: TimeCreated = Field(description="Timestamps")
    agent: Optional[str] = Field(default=None, description="Agent identifier")
    model: Optional[ModelInfo] = Field(default=None, description="Model info")
    system: Optional[str] = Field(default=None, description="System prompt")
    parts: List[MessagePart] = Field(default_factory=list, description="Message parts")

    class Config:
        extra = "allow"


class MessageError(BaseModel):
    """Message error information."""
    type: str = Field(description="Error type")
    message: Optional[str] = Field(default=None, description="Error message")


class AssistantMessage(BaseModel):
    """Assistant message representation."""
    id: str = Field(description="Message identifier")
    sessionID: str = Field(description="Session identifier")
    role: Literal["assistant"] = "assistant"
    time: TimeCreatedCompleted = Field(description="Timestamps")
    error: Optional[MessageError] = Field(default=None, description="Error if any")
    parentID: str = Field(description="Parent message ID")
    modelID: str = Field(description="Model identifier")
    providerID: str = Field(description="Provider identifier")
    cost: float = Field(default=0.0, description="Cost in USD")
    tokens: TokenInfo = Field(default_factory=TokenInfo, description="Token usage")
    parts: List[MessagePart] = Field(default_factory=list, description="Message parts")

    class Config:
        extra = "allow"


Message = Union[UserMessage, AssistantMessage]


class MessageListResponse(BaseModel):
    """Response for message list endpoint."""
    messages: List[Message] = Field(default_factory=list)


# =============================================================================
# Request Models
# =============================================================================

class PromptPart(BaseModel):
    """Part of a prompt request."""
    type: Literal["text", "file"] = Field(description="Part type")
    text: Optional[str] = Field(default=None, description="Text content")
    mediaType: Optional[str] = Field(default=None, description="MIME type for files")
    filename: Optional[str] = Field(default=None, description="File name")
    url: Optional[str] = Field(default=None, description="File URL")


class CreateSessionRequest(BaseModel):
    """Request to create a new session."""
    title: Optional[str] = Field(default=None, description="Session title")


class PromptRequest(BaseModel):
    """Request to send a prompt to a session."""
    parts: List[PromptPart] = Field(description="Prompt parts")
    model: Optional[ModelInfo] = Field(default=None, description="Model override")
    agent: Optional[str] = Field(default=None, description="Agent override")
    system: Optional[str] = Field(default=None, description="System prompt override")


class PermissionReplyRequest(BaseModel):
    """Request to reply to a permission prompt."""
    response: PermissionResponseType = Field(description="Permission response")


class CommandRequest(BaseModel):
    """Request to execute a slash command."""
    input: str = Field(description="Command input")


class ShellRequest(BaseModel):
    """Request to execute a shell command."""
    command: str = Field(description="Shell command")


# =============================================================================
# Permission Models
# =============================================================================

class PermissionLocation(BaseModel):
    """Permission location information."""
    file: Optional[str] = Field(default=None)
    line: Optional[int] = Field(default=None)


class Permission(BaseModel):
    """Permission request from OpenCode."""
    id: str = Field(description="Permission identifier")
    sessionID: str = Field(description="Session identifier")
    messageID: str = Field(description="Message identifier")
    toolCallID: str = Field(description="Tool call identifier")
    tool: str = Field(description="Tool name")
    title: str = Field(description="Permission title")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Tool metadata")
    time: TimeCreated = Field(description="Timestamps")

    class Config:
        extra = "allow"


class PermissionResponse(BaseModel):
    """Response to a permission request."""
    response: PermissionResponseType = Field(description="User response")


# =============================================================================
# SSE Event Models
# =============================================================================

class EventBase(BaseModel):
    """Base class for SSE events."""
    type: str = Field(description="Event type")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Event properties")


class EventServerConnected(BaseModel):
    """Server connected event."""
    type: Literal["server.connected"] = "server.connected"
    properties: Dict[str, Any] = Field(default_factory=dict)


class EventSessionCreated(BaseModel):
    """Session created event."""
    type: Literal["session.created"] = "session.created"
    properties: Session


class EventSessionUpdated(BaseModel):
    """Session updated event."""
    type: Literal["session.updated"] = "session.updated"
    properties: Session


class EventSessionDeleted(BaseModel):
    """Session deleted event."""
    type: Literal["session.deleted"] = "session.deleted"
    properties: Dict[str, str]  # sessionID


class EventSessionStatus(BaseModel):
    """Session status change event."""
    type: Literal["session.status"] = "session.status"
    properties: Dict[str, Any]  # sessionID, status


class EventSessionError(BaseModel):
    """Session error event."""
    type: Literal["session.error"] = "session.error"
    properties: Dict[str, Any]  # error details


class EventMessageUpdated(BaseModel):
    """Message updated event."""
    type: Literal["message.updated"] = "message.updated"
    properties: Dict[str, Any]  # Contains message data


class EventMessageRemoved(BaseModel):
    """Message removed event."""
    type: Literal["message.removed"] = "message.removed"
    properties: Dict[str, Any]  # messageID, sessionID


class EventMessagePartUpdated(BaseModel):
    """Message part updated event (for streaming)."""
    type: Literal["message.part.updated"] = "message.part.updated"
    properties: Dict[str, Any]  # part, delta, messageID, sessionID


class EventPermissionUpdated(BaseModel):
    """Permission request event."""
    type: Literal["permission.updated"] = "permission.updated"
    properties: Permission


class EventPermissionReplied(BaseModel):
    """Permission replied event."""
    type: Literal["permission.replied"] = "permission.replied"
    properties: Dict[str, Any]  # permissionID, response


class EventTodoUpdated(BaseModel):
    """Todo list updated event."""
    type: Literal["todo.updated"] = "todo.updated"
    properties: Dict[str, Any]  # todos


class EventFileEdited(BaseModel):
    """File edited event."""
    type: Literal["file.edited"] = "file.edited"
    properties: Dict[str, Any]  # file details


# Union of all SSE event types
SSEEvent = Union[
    EventServerConnected,
    EventSessionCreated,
    EventSessionUpdated,
    EventSessionDeleted,
    EventSessionStatus,
    EventSessionError,
    EventMessageUpdated,
    EventMessageRemoved,
    EventMessagePartUpdated,
    EventPermissionUpdated,
    EventPermissionReplied,
    EventTodoUpdated,
    EventFileEdited,
    EventBase,  # Fallback for unknown events
]


# =============================================================================
# API Response Models
# =============================================================================

class ProviderInfo(BaseModel):
    """Provider information."""
    id: str
    name: str


class ConfigResponse(BaseModel):
    """Configuration response."""
    providers: List[ProviderInfo] = Field(default_factory=list)
    models: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    version: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response from API."""
    error: str = Field(description="Error message")
    code: Optional[str] = Field(default=None, description="Error code")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional details")


# =============================================================================
# Search & File API Models (Serve API endpoints)
# =============================================================================

class FindTextSubmatch(BaseModel):
    """Submatch within a ripgrep text match."""
    match: Dict[str, str] = Field(description="Match text object with 'text' key")
    start: int = Field(description="Start offset within the line")
    end: int = Field(description="End offset within the line")


class FindTextMatch(BaseModel):
    """Single match from ripgrep text search (/find endpoint)."""
    path: Dict[str, str] = Field(description="File path object with 'text' key")
    lines: Dict[str, str] = Field(description="Matched line(s) with 'text' key")
    line_number: int = Field(description="Line number of the match")
    absolute_offset: int = Field(description="Absolute byte offset in file")
    submatches: List[FindTextSubmatch] = Field(
        default_factory=list, description="Submatch details"
    )

    class Config:
        extra = "allow"


class FileContentResponse(BaseModel):
    """Response from /file/content endpoint."""
    type: str = Field(description="Content type: 'text' or 'binary'")
    content: str = Field(description="File content (text) or base64 (binary)")
    diff: Optional[str] = Field(default=None, description="Git diff if modified")
    patch: Optional[Dict[str, Any]] = Field(default=None, description="Parsed patch hunks")
    encoding: Optional[str] = Field(default=None, description="Encoding (e.g., 'base64' for binary)")
    mimeType: Optional[str] = Field(default=None, description="MIME type for binary files")

    class Config:
        extra = "allow"


class FileNode(BaseModel):
    """Directory entry from /file endpoint."""
    name: str = Field(description="File or directory name")
    path: str = Field(description="Relative path")
    absolute: str = Field(description="Absolute path")
    type: str = Field(description="'file' or 'directory'")
    ignored: bool = Field(description="Whether the entry is gitignored")


class FileStatusEntry(BaseModel):
    """Git file status from /file/status endpoint."""
    path: str = Field(description="Relative file path")
    added: int = Field(description="Lines added")
    removed: int = Field(description="Lines removed")
    status: str = Field(description="Git status: 'added', 'deleted', or 'modified'")
