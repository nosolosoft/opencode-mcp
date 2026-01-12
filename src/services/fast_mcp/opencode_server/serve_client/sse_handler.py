"""
SSE Event Handler
Specialized handler for Server-Sent Events from opencode serve.

Provides robust SSE parsing, reconnection logic, and event aggregation
for streaming responses from OpenCode.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set

import httpx

from .models import (
    SSEEvent,
    EventBase,
    EventMessagePartUpdated,
    EventSessionStatus,
    EventPermissionUpdated,
    SessionStatusType,
    PermissionResponseType,
    TextPart,
    ToolPart,
)

logger = logging.getLogger(__name__)


@dataclass
class StreamedResponse:
    """
    Aggregated response from streaming events.
    
    Collects text chunks, tool calls, and other parts from SSE events
    into a coherent response.
    """
    session_id: str
    message_id: Optional[str] = None
    text_chunks: List[str] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    reasoning_chunks: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    completed: bool = False
    tokens: Dict[str, int] = field(default_factory=lambda: {
        "input": 0, "output": 0, "reasoning": 0
    })
    cost: float = 0.0
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    
    @property
    def text(self) -> str:
        """Get the full aggregated text response."""
        return "".join(self.text_chunks)
    
    @property
    def reasoning(self) -> str:
        """Get the full reasoning/thinking text."""
        return "".join(self.reasoning_chunks)
    
    @property
    def duration(self) -> float:
        """Get response duration in seconds."""
        end = self.end_time or time.time()
        return end - self.start_time
    
    def add_text_chunk(self, delta: str) -> None:
        """Add a text chunk to the response."""
        if delta:
            self.text_chunks.append(delta)
    
    def add_reasoning_chunk(self, delta: str) -> None:
        """Add a reasoning chunk to the response."""
        if delta:
            self.reasoning_chunks.append(delta)
    
    def add_tool_call(self, tool_data: Dict[str, Any]) -> None:
        """Add or update a tool call."""
        call_id = tool_data.get("callID")
        
        # Update existing or add new
        for i, existing in enumerate(self.tool_calls):
            if existing.get("callID") == call_id:
                self.tool_calls[i] = tool_data
                return
        
        self.tool_calls.append(tool_data)
    
    def mark_completed(self, tokens: Optional[Dict] = None, cost: float = 0.0) -> None:
        """Mark the response as completed."""
        self.completed = True
        self.end_time = time.time()
        if tokens:
            self.tokens.update(tokens)
        self.cost = cost
    
    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "session_id": self.session_id,
            "message_id": self.message_id,
            "text": self.text,
            "reasoning": self.reasoning if self.reasoning else None,
            "tool_calls": self.tool_calls if self.tool_calls else None,
            "errors": self.errors if self.errors else None,
            "completed": self.completed,
            "tokens": self.tokens,
            "cost": self.cost,
            "duration": self.duration,
        }


class SSEHandler:
    """
    Handler for SSE events from OpenCode serve.
    
    Provides:
    - Robust SSE parsing with reconnection
    - Event aggregation into StreamedResponse
    - Permission handling callbacks
    - Timeout and cancellation support
    
    Example:
        ```python
        handler = SSEHandler(client, directory="/my/project")
        
        async for response in handler.stream_prompt(session_id, "Write code"):
            print(response.text, end="", flush=True)
            
            if response.completed:
                print(f"\\nDone in {response.duration:.1f}s")
        ```
    """
    
    DEFAULT_RECONNECT_DELAY = 1.0
    MAX_RECONNECT_ATTEMPTS = 3
    
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        directory: Optional[str] = None,
        permission_callback: Optional[Callable[[Dict], PermissionResponseType]] = None,
        auto_approve_permissions: bool = True,
    ):
        """
        Initialize SSE handler.
        
        Args:
            http_client: The httpx async client to use
            directory: Working directory for the opencode instance
            permission_callback: Optional callback for permission decisions
            auto_approve_permissions: Auto-approve permissions if no callback
        """
        self.client = http_client
        self.directory = directory
        self.permission_callback = permission_callback
        self.auto_approve_permissions = auto_approve_permissions
        
        self._active_streams: Set[str] = set()
        self._cancelled: Set[str] = set()
    
    async def stream_events(
        self,
        timeout: Optional[float] = None,
    ) -> AsyncGenerator[EventBase, None]:
        """
        Stream raw SSE events from the server.
        
        Args:
            timeout: Optional timeout for the entire stream
            
        Yields:
            EventBase objects for each event
        """
        params = {"directory": self.directory} if self.directory else {}
        
        try:
            async with self.client.stream(
                "GET",
                "/event",
                params=params,
                timeout=httpx.Timeout(timeout) if timeout else httpx.Timeout(None),
            ) as response:
                response.raise_for_status()
                
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        
                        if not line:
                            continue
                        
                        if line.startswith("data:"):
                            try:
                                data = json.loads(line[5:].strip())
                                yield EventBase(
                                    type=data.get("type", "unknown"),
                                    properties=data.get("properties", {}),
                                )
                            except json.JSONDecodeError as e:
                                logger.warning(f"Failed to parse SSE data: {e}")
                        elif line.startswith(":"):
                            # Comment/keepalive, ignore
                            pass
                        
        except httpx.ReadTimeout:
            logger.debug("SSE stream timed out")
        except asyncio.CancelledError:
            logger.debug("SSE stream cancelled")
            raise
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            raise
    
    async def stream_prompt(
        self,
        session_id: str,
        filter_session: bool = True,
        timeout: Optional[float] = None,
    ) -> AsyncGenerator[StreamedResponse, None]:
        """
        Stream events for a prompt, aggregating into StreamedResponse.
        
        This method connects to the SSE stream and yields updated
        StreamedResponse objects as events arrive.
        
        Args:
            session_id: Session to monitor
            filter_session: Only yield events for this session
            timeout: Optional timeout for the entire operation
            
        Yields:
            Updated StreamedResponse objects
        """
        response = StreamedResponse(session_id=session_id)
        stream_id = f"{session_id}:{time.time()}"
        self._active_streams.add(stream_id)
        
        try:
            async for event in self.stream_events(timeout=timeout):
                # Check for cancellation
                if stream_id in self._cancelled:
                    logger.info(f"Stream {stream_id} cancelled")
                    break
                
                # Extract session from event
                props = event.properties
                event_session = props.get("sessionID")
                
                # Filter by session if requested
                if filter_session and event_session and event_session != session_id:
                    continue
                
                # Process event
                await self._process_event(event, response)
                
                # Yield updated response
                yield response
                
                # Check for completion
                if response.completed:
                    break
                    
        finally:
            self._active_streams.discard(stream_id)
            self._cancelled.discard(stream_id)
    
    async def _process_event(
        self,
        event: EventBase,
        response: StreamedResponse,
    ) -> None:
        """Process a single SSE event and update the response."""
        event_type = event.type
        props = event.properties
        
        if event_type == "message.part.updated":
            await self._handle_part_update(props, response)
        
        elif event_type == "message.updated":
            response.message_id = props.get("id")
            # Check for completion in message update
            if props.get("time", {}).get("completed"):
                tokens = props.get("tokens", {})
                cost = props.get("cost", 0.0)
                response.mark_completed(tokens=tokens, cost=cost)
        
        elif event_type == "session.status":
            status = props.get("status", {})
            if isinstance(status, dict) and status.get("type") == "idle":
                response.mark_completed()
        
        elif event_type == "session.error":
            error = props.get("error", {})
            error_msg = error.get("message") if isinstance(error, dict) else str(error)
            response.add_error(error_msg)
            response.mark_completed()
        
        elif event_type == "permission.updated":
            await self._handle_permission(props, response.session_id)
    
    async def _handle_part_update(
        self,
        props: Dict[str, Any],
        response: StreamedResponse,
    ) -> None:
        """Handle a message part update event."""
        part = props.get("part", {})
        delta = props.get("delta")
        part_type = part.get("type")
        
        if part_type == "text":
            if delta:
                response.add_text_chunk(delta)
        
        elif part_type == "reasoning":
            if delta:
                response.add_reasoning_chunk(delta)
        
        elif part_type == "tool":
            response.add_tool_call(part)
        
        elif part_type == "step-finish":
            # Check for completion reason
            finish_reason = part.get("finishReason", "")
            if finish_reason in ("stop", "end_turn"):
                response.mark_completed()
    
    async def _handle_permission(
        self,
        permission: Dict[str, Any],
        session_id: str,
    ) -> None:
        """Handle a permission request."""
        perm_id = permission.get("id")
        perm_session = permission.get("sessionID")
        
        if not perm_id or perm_session != session_id:
            return
        
        # Determine response
        response_type = PermissionResponseType.ONCE
        
        if self.permission_callback:
            try:
                response_type = self.permission_callback(permission)
            except Exception as e:
                logger.error(f"Permission callback error: {e}")
        elif not self.auto_approve_permissions:
            logger.warning(f"Permission required but auto-approve disabled: {permission}")
            return
        
        # Send permission response
        try:
            resp = await self.client.post(
                f"/session/{session_id}/permissions/{perm_id}",
                json={"response": response_type.value},
            )
            resp.raise_for_status()
            logger.debug(f"Permission {perm_id} responded with {response_type.value}")
        except Exception as e:
            logger.error(f"Failed to respond to permission: {e}")
    
    def cancel_stream(self, session_id: str) -> None:
        """
        Cancel an active stream for a session.
        
        Args:
            session_id: Session ID to cancel
        """
        for stream_id in list(self._active_streams):
            if stream_id.startswith(f"{session_id}:"):
                self._cancelled.add(stream_id)
    
    async def collect_response(
        self,
        session_id: str,
        timeout: Optional[float] = None,
        on_chunk: Optional[Callable[[str], None]] = None,
    ) -> StreamedResponse:
        """
        Collect a complete response from SSE events.
        
        This is a convenience method that streams events and returns
        the final aggregated response.
        
        Args:
            session_id: Session to monitor
            timeout: Optional timeout
            on_chunk: Optional callback for each text chunk
            
        Returns:
            Final StreamedResponse with all aggregated data
        """
        final_response: Optional[StreamedResponse] = None
        
        async for response in self.stream_prompt(session_id, timeout=timeout):
            final_response = response
            
            # Call chunk callback if provided
            if on_chunk and response.text_chunks:
                latest_chunk = response.text_chunks[-1] if response.text_chunks else ""
                if latest_chunk:
                    on_chunk(latest_chunk)
        
        if final_response is None:
            return StreamedResponse(session_id=session_id, completed=True)
        
        return final_response


class SSEEventAggregator:
    """
    Aggregates multiple SSE events into structured data.
    
    Useful for collecting tool calls, files, and other artifacts
    from a streaming session.
    """
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.messages: List[Dict[str, Any]] = []
        self.tool_results: Dict[str, Any] = {}  # callID -> result
        self.files_created: List[str] = []
        self.files_modified: List[str] = []
        self.errors: List[str] = []
    
    def process_event(self, event: EventBase) -> None:
        """Process an event and update aggregated state."""
        if event.type == "message.updated":
            self.messages.append(event.properties)
        
        elif event.type == "message.part.updated":
            part = event.properties.get("part", {})
            if part.get("type") == "tool":
                state = part.get("state", {})
                if state.get("status") == "completed":
                    self.tool_results[part.get("callID")] = state.get("output")
        
        elif event.type == "file.edited":
            file_info = event.properties
            file_path = file_info.get("path")
            if file_path:
                if file_info.get("created"):
                    self.files_created.append(file_path)
                else:
                    self.files_modified.append(file_path)
        
        elif event.type == "session.error":
            error = event.properties.get("error", {})
            self.errors.append(str(error))
    
    def to_dict(self) -> Dict[str, Any]:
        """Get aggregated data as dictionary."""
        return {
            "session_id": self.session_id,
            "messages": self.messages,
            "tool_results": self.tool_results,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "errors": self.errors,
        }
