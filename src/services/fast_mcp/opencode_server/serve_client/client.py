"""
OpenCode Serve HTTP Client
Async HTTP client for interacting with opencode serve API.

This client provides a Pythonic interface to the OpenCode serve HTTP API,
replacing subprocess execution with persistent HTTP connections.
"""

import asyncio
import json
import logging
import subprocess
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx

from .models import (
    Session,
    SessionStatus,
    SessionStatusType,
    Message,
    Permission,
    PermissionResponseType,
    CreateSessionRequest,
    PromptRequest,
    PromptPart,
    ModelInfo,
    ErrorResponse,
    SSEEvent,
    EventBase,
)

logger = logging.getLogger(__name__)


class OpenCodeServeError(Exception):
    """Base exception for OpenCode serve client errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, details: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class ServerNotRunningError(OpenCodeServeError):
    """Raised when the opencode serve server is not running."""
    pass


class SessionBusyError(OpenCodeServeError):
    """Raised when trying to use a busy session."""
    pass


class PermissionRequiredError(OpenCodeServeError):
    """Raised when a tool requires permission approval."""
    
    def __init__(self, permission: Permission):
        super().__init__(f"Permission required for tool: {permission.tool}")
        self.permission = permission


class OpenCodeServeClient:
    """
    Async HTTP client for OpenCode serve API.
    
    This client connects to a running `opencode serve` instance and provides
    methods for session management, prompts, and streaming responses.
    
    Example:
        ```python
        async with OpenCodeServeClient() as client:
            # Create a session
            session = await client.create_session(title="My Session")
            
            # Send a prompt and wait for response
            messages = await client.prompt(
                session_id=session.id,
                text="Hello, help me with Python"
            )
            
            # Or stream the response
            async for event in client.prompt_stream(session.id, "Write a function"):
                if event.type == "message.part.updated":
                    print(event.properties.get("delta", ""), end="")
        ```
    """
    
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 4096
    DEFAULT_TIMEOUT = 300.0  # 5 minutes for long operations
    CONNECT_TIMEOUT = 10.0
    
    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        directory: Optional[str] = None,
        auto_approve_permissions: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the OpenCode serve client.
        
        Args:
            host: Server host (default: 127.0.0.1)
            port: Server port (default: 4096)
            directory: Working directory for operations (sent via header)
            auto_approve_permissions: Whether to auto-approve tool permissions
            timeout: Default timeout for operations in seconds
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.directory = directory
        self.auto_approve_permissions = auto_approve_permissions
        self.timeout = timeout
        
        self._client: Optional[httpx.AsyncClient] = None
        self._server_process: Optional[subprocess.Popen] = None
        self._connected = False
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client, raising if not connected."""
        if self._client is None:
            raise RuntimeError("Client not connected. Use 'async with client:' or call connect()")
        return self._client
    
    def _get_headers(self, directory: Optional[str] = None) -> Dict[str, str]:
        """Get headers for API requests."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        dir_to_use = directory or self.directory
        if dir_to_use:
            headers["x-opencode-directory"] = dir_to_use
        return headers
    
    async def connect(self) -> None:
        """Connect to the OpenCode serve server."""
        if self._client is not None:
            return
        
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout, connect=self.CONNECT_TIMEOUT),
            headers=self._get_headers(),
        )
        
        # Verify server is running
        try:
            response = await self._client.get("/doc")
            if response.status_code != 200:
                raise ServerNotRunningError(
                    f"Server responded with status {response.status_code}"
                )
            self._connected = True
            logger.info(f"Connected to OpenCode serve at {self.base_url}")
        except httpx.ConnectError as e:
            await self.disconnect()
            raise ServerNotRunningError(
                f"Cannot connect to OpenCode serve at {self.base_url}. "
                f"Start it with: opencode serve --port {self.port}"
            ) from e
    
    async def disconnect(self) -> None:
        """Disconnect from the server."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        self._connected = False
        logger.info("Disconnected from OpenCode serve")
    
    async def __aenter__(self) -> "OpenCodeServeClient":
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect()
    
    # =========================================================================
    # Server Management
    # =========================================================================
    
    async def start_server(
        self,
        port: Optional[int] = None,
        wait_timeout: float = 30.0,
    ) -> None:
        """
        Start an opencode serve process.
        
        Args:
            port: Port to use (defaults to self.port)
            wait_timeout: Timeout waiting for server to start
        """
        port = port or self.port
        
        # Check if already running
        try:
            await self.connect()
            logger.info(f"Server already running at {self.base_url}")
            return
        except ServerNotRunningError:
            pass
        
        # Start the server process
        cmd = ["opencode", "serve", "--port", str(port), "--hostname", self.host]
        logger.info(f"Starting OpenCode serve: {' '.join(cmd)}")
        
        # Use DEVNULL for stdout/stderr to prevent buffer blocking
        # Use start_new_session=True to detach from parent process
        # This allows the serve process to survive when MCP closes
        self._server_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,  # Detach from parent - survives MCP shutdown
        )
        
        # Wait for server to be ready
        start_time = time.time()
        while time.time() - start_time < wait_timeout:
            try:
                await self.connect()
                logger.info(f"OpenCode serve started successfully on port {port}")
                return
            except ServerNotRunningError:
                await asyncio.sleep(0.5)
        
        # Timeout - kill the process
        if self._server_process:
            self._server_process.kill()
            self._server_process = None
        
        raise ServerNotRunningError(
            f"Timeout waiting for opencode serve to start after {wait_timeout}s"
        )
    
    async def stop_server(self, force: bool = False) -> None:
        """
        Stop the managed server process.
        
        Args:
            force: If True, actually terminate the server process.
                   If False (default), just disconnect - server keeps running
                   for other MCP sessions to use.
        """
        await self.disconnect()
        if force and self._server_process:
            self._server_process.terminate()
            try:
                self._server_process.wait(timeout=10)
            except Exception:
                self._server_process.kill()
            self._server_process = None
            logger.info("OpenCode serve stopped")
        elif self._server_process:
            # Don't kill - just forget the reference
            # Server continues running for other sessions
            logger.info("Disconnected from OpenCode serve (server still running)")
            self._server_process = None
    
    async def is_healthy(self) -> bool:
        """Check if the server is healthy."""
        try:
            response = await self.client.get("/doc")
            return response.status_code == 200
        except Exception:
            return False
    
    # =========================================================================
    # Session Management
    # =========================================================================
    
    async def list_sessions(self) -> List[Session]:
        """
        List all sessions.
        
        Returns:
            List of Session objects
        """
        response = await self.client.get("/session")
        response.raise_for_status()
        data = response.json()
        return [Session.model_validate(s) for s in data]
    
    async def create_session(
        self,
        title: Optional[str] = None,
        directory: Optional[str] = None,
    ) -> Session:
        """
        Create a new session.
        
        Args:
            title: Optional session title
            directory: Working directory for this session
            
        Returns:
            Created Session object
        """
        request = CreateSessionRequest(title=title)
        headers = self._get_headers(directory)
        
        response = await self.client.post(
            "/session",
            json=request.model_dump(exclude_none=True),
            headers=headers,
        )
        response.raise_for_status()
        return Session.model_validate(response.json())
    
    async def get_session(self, session_id: str) -> Session:
        """
        Get a session by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session object
        """
        response = await self.client.get(f"/session/{session_id}")
        response.raise_for_status()
        return Session.model_validate(response.json())
    
    async def delete_session(self, session_id: str) -> None:
        """
        Delete a session.
        
        Args:
            session_id: Session identifier
        """
        response = await self.client.delete(f"/session/{session_id}")
        response.raise_for_status()
    
    async def get_session_status(self, session_id: str) -> SessionStatus:
        """
        Get the status of a specific session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            SessionStatus object
        """
        response = await self.client.get("/session/status")
        response.raise_for_status()
        data = response.json()
        
        if session_id in data:
            return SessionStatus.model_validate(data[session_id])
        
        # Session not found or idle
        return SessionStatus(type=SessionStatusType.IDLE)
    
    async def abort_session(self, session_id: str) -> None:
        """
        Abort a running session.
        
        Args:
            session_id: Session identifier
        """
        response = await self.client.post(f"/session/{session_id}/abort")
        response.raise_for_status()
    
    # =========================================================================
    # Messages
    # =========================================================================
    
    async def get_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Get all messages for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of message dictionaries
        """
        response = await self.client.get(f"/session/{session_id}/message")
        response.raise_for_status()
        return response.json()
    
    async def prompt(
        self,
        session_id: str,
        text: str,
        model: Optional[ModelInfo] = None,
        agent: Optional[str] = None,
        system: Optional[str] = None,
        auto_approve: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """
        Send a prompt to a session and wait for completion.
        
        This is the synchronous version that waits for the full response.
        For streaming, use prompt_stream().
        
        Args:
            session_id: Session identifier
            text: Prompt text
            model: Optional model override
            agent: Optional agent override
            system: Optional system prompt
            auto_approve: Override auto_approve_permissions setting
            
        Returns:
            List of messages from the response
        """
        parts = [PromptPart(type="text", text=text)]
        request = PromptRequest(
            parts=parts,
            model=model,
            agent=agent,
            system=system,
        )
        
        # Use synchronous endpoint that waits for response
        endpoint = f"/session/{session_id}/message"
        
        response = await self.client.post(
            endpoint,
            json=request.model_dump(exclude_none=True),
            timeout=httpx.Timeout(self.timeout),
        )
        
        if response.status_code == 409:
            raise SessionBusyError(f"Session {session_id} is busy")
        
        response.raise_for_status()
        
        # If auto-approve is enabled and we need to handle permissions
        should_auto_approve = auto_approve if auto_approve is not None else self.auto_approve_permissions
        
        if should_auto_approve:
            # Check for pending permissions and approve them
            await self._handle_pending_permissions(session_id)
        
        return response.json()
    
    async def prompt_async(
        self,
        session_id: str,
        text: str,
        model: Optional[ModelInfo] = None,
        agent: Optional[str] = None,
        system: Optional[str] = None,
    ) -> None:
        """
        Send a prompt to a session without waiting for completion.
        
        Use this with SSE events to stream the response.
        
        Args:
            session_id: Session identifier
            text: Prompt text
            model: Optional model override
            agent: Optional agent override  
            system: Optional system prompt
        """
        parts = [PromptPart(type="text", text=text)]
        request = PromptRequest(
            parts=parts,
            model=model,
            agent=agent,
            system=system,
        )
        
        response = await self.client.post(
            f"/session/{session_id}/prompt_async",
            json=request.model_dump(exclude_none=True),
        )
        
        if response.status_code == 409:
            raise SessionBusyError(f"Session {session_id} is busy")
        
        response.raise_for_status()
    
    # =========================================================================
    # Permissions
    # =========================================================================
    
    async def reply_permission(
        self,
        session_id: str,
        permission_id: str,
        response: PermissionResponseType = PermissionResponseType.ONCE,
    ) -> None:
        """
        Reply to a permission request.
        
        Args:
            session_id: Session identifier
            permission_id: Permission identifier
            response: Permission response (once, always, reject)
        """
        resp = await self.client.post(
            f"/session/{session_id}/permissions/{permission_id}",
            json={"response": response.value},
        )
        resp.raise_for_status()
    
    async def _handle_pending_permissions(self, session_id: str) -> None:
        """
        Auto-approve any pending permissions for a session.
        
        This is called automatically when auto_approve_permissions is True.
        """
        # Note: The API might not expose pending permissions directly
        # This is handled via SSE events in streaming mode
        pass
    
    # =========================================================================
    # SSE Streaming
    # =========================================================================
    
    async def stream_events(
        self,
        directory: Optional[str] = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Stream SSE events from the server.
        
        This connects to the /event endpoint and yields events as they arrive.
        
        Args:
            directory: Working directory (required for session-specific events)
            
        Yields:
            SSEEvent objects
        """
        dir_to_use = directory or self.directory
        params = {"directory": dir_to_use} if dir_to_use else {}
        
        async with self.client.stream(
            "GET",
            "/event",
            params=params,
            timeout=httpx.Timeout(None),  # No timeout for streaming
        ) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                
                try:
                    data = json.loads(line[5:].strip())
                    yield self._parse_sse_event(data)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse SSE event: {line}")
                    continue
    
    async def prompt_stream(
        self,
        session_id: str,
        text: str,
        model: Optional[ModelInfo] = None,
        agent: Optional[str] = None,
        system: Optional[str] = None,
        auto_approve: Optional[bool] = None,
    ) -> AsyncGenerator[SSEEvent, None]:
        """
        Send a prompt and stream the response via SSE.
        
        This sends an async prompt and then streams events until the
        session becomes idle.
        
        Args:
            session_id: Session identifier
            text: Prompt text
            model: Optional model override
            agent: Optional agent override
            system: Optional system prompt
            auto_approve: Override auto_approve_permissions setting
            
        Yields:
            SSEEvent objects for the response
        """
        should_auto_approve = auto_approve if auto_approve is not None else self.auto_approve_permissions
        
        # Send the async prompt
        await self.prompt_async(
            session_id=session_id,
            text=text,
            model=model,
            agent=agent,
            system=system,
        )
        
        # Stream events until session is idle
        async for event in self.stream_events():
            # Handle permission requests if auto-approve is enabled
            if should_auto_approve and event.type == "permission.updated":
                permission = event.properties
                if isinstance(permission, dict):
                    perm_id = permission.get("id")
                    perm_session = permission.get("sessionID")
                    if perm_id and perm_session == session_id:
                        await self.reply_permission(
                            session_id=session_id,
                            permission_id=perm_id,
                            response=PermissionResponseType.ONCE,
                        )
            
            # Filter events for this session
            props = event.properties if hasattr(event, 'properties') else {}
            if isinstance(props, dict):
                event_session_id = props.get("sessionID")
                if event_session_id and event_session_id != session_id:
                    continue
            
            yield event
            
            # Check if session is done
            if event.type == "session.status":
                status = props.get("status", {}) if isinstance(props, dict) else {}
                if isinstance(status, dict) and status.get("type") == "idle":
                    break
    
    def _parse_sse_event(self, data: Dict[str, Any]) -> SSEEvent:
        """Parse raw SSE data into an event object."""
        event_type = data.get("type", "unknown")
        properties = data.get("properties", {})
        
        return EventBase(type=event_type, properties=properties)
    
    # =========================================================================
    # Commands
    # =========================================================================
    
    async def execute_command(
        self,
        session_id: str,
        command: str,
    ) -> Dict[str, Any]:
        """
        Execute a slash command in a session.
        
        Args:
            session_id: Session identifier
            command: Command to execute (e.g., "/help")
            
        Returns:
            Command result
        """
        response = await self.client.post(
            f"/session/{session_id}/command",
            json={"input": command},
        )
        response.raise_for_status()
        return response.json()
    
    async def execute_shell(
        self,
        session_id: str,
        command: str,
    ) -> Dict[str, Any]:
        """
        Execute a shell command in a session.
        
        Args:
            session_id: Session identifier
            command: Shell command to execute
            
        Returns:
            Command result
        """
        response = await self.client.post(
            f"/session/{session_id}/shell",
            json={"command": command},
        )
        response.raise_for_status()
        return response.json()
    
    # =========================================================================
    # Configuration
    # =========================================================================
    
    async def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        response = await self.client.get("/config")
        response.raise_for_status()
        return response.json()
    
    async def get_providers(self) -> List[Dict[str, Any]]:
        """Get available providers."""
        response = await self.client.get("/provider")
        response.raise_for_status()
        return response.json()
    
    async def get_tools(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get available tools.
        
        Args:
            provider: Provider ID (required by API, defaults to "anthropic")
            model: Model ID (required by API, defaults to "claude-sonnet-4-20250514")
            
        Returns:
            List of available tools
        """
        # API requires provider and model parameters
        params = {
            "provider": provider or "anthropic",
            "model": model or "claude-sonnet-4-20250514",
        }
        response = await self.client.get("/experimental/tool", params=params)
        response.raise_for_status()
        return response.json()
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    async def get_session_diff(self, session_id: str) -> Dict[str, Any]:
        """Get diff of changes made in a session."""
        response = await self.client.get(f"/session/{session_id}/diff")
        response.raise_for_status()
        return response.json()
    
    async def get_session_todos(self, session_id: str) -> List[Dict[str, Any]]:
        """Get todo items for a session."""
        response = await self.client.get(f"/session/{session_id}/todo")
        response.raise_for_status()
        return response.json()
    
    async def fork_session(
        self,
        session_id: str,
        message_id: str,
    ) -> Session:
        """
        Fork a session from a specific message.
        
        Args:
            session_id: Session to fork
            message_id: Message to fork from
            
        Returns:
            New forked Session
        """
        response = await self.client.post(
            f"/session/{session_id}/fork",
            json={"messageID": message_id},
        )
        response.raise_for_status()
        return Session.model_validate(response.json())


# Convenience function for creating a client
def create_opencode_client(
    host: str = OpenCodeServeClient.DEFAULT_HOST,
    port: int = OpenCodeServeClient.DEFAULT_PORT,
    **kwargs,
) -> OpenCodeServeClient:
    """
    Create an OpenCode serve client.
    
    Args:
        host: Server host
        port: Server port
        **kwargs: Additional arguments for OpenCodeServeClient
        
    Returns:
        OpenCodeServeClient instance
    """
    return OpenCodeServeClient(host=host, port=port, **kwargs)
