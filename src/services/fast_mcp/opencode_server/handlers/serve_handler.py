"""
Serve Handler
Handler for OpenCode serve HTTP API operations.

Provides MCP tool handlers that use the persistent HTTP connection
to opencode serve instead of spawning subprocess per request.
"""

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from ..models import OpenCodeResult
from ..serve_client import (
    OpenCodeServeClient,
    SessionManager,
    SessionContext,
    SSEHandler,
    StreamedResponse,
    ServerNotRunningError,
    SessionBusyError,
    ModelInfo,
    PermissionResponseType,
)

logger = logging.getLogger(__name__)


class ServeHandler:
    """
    Handler for OpenCode serve API operations.

    This handler manages a persistent connection to an opencode serve
    instance and provides high-level methods for MCP tools.

    Features:
    - Automatic server startup (optional)
    - Session pooling and reuse
    - Streaming response support
    - Permission auto-approval
    - Provider cache with TTL for model validation
    """

    # Provider cache TTL (5 minutes)
    PROVIDER_CACHE_TTL = 300

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4096,
        default_directory: Optional[str] = None,
        auto_start_server: bool = False,
        auto_approve_permissions: bool = True,
        default_timeout: float = 300.0,
    ):
        """
        Initialize the serve handler.

        Args:
            host: Server host
            port: Server port
            default_directory: Default working directory
            auto_start_server: Start server if not running
            auto_approve_permissions: Auto-approve tool permissions
            default_timeout: Default timeout for operations
        """
        self.host = host
        self.port = port
        self.default_directory = default_directory or os.getcwd()
        self.auto_start_server = auto_start_server
        self.auto_approve_permissions = auto_approve_permissions
        self.default_timeout = default_timeout

        self._client: Optional[OpenCodeServeClient] = None
        self._session_manager: Optional[SessionManager] = None
        self._initialized = False

        # Provider cache with TTL
        self._provider_cache: Optional[Dict[str, Any]] = None
        self._provider_cache_time: float = 0
    
    async def initialize(self) -> None:
        """Initialize the handler and connect to server."""
        if self._initialized:
            return
        
        self._client = OpenCodeServeClient(
            host=self.host,
            port=self.port,
            directory=self.default_directory,
            auto_approve_permissions=self.auto_approve_permissions,
            timeout=self.default_timeout,
        )
        
        try:
            await self._client.connect()
        except ServerNotRunningError:
            if self.auto_start_server:
                logger.info("Server not running, starting...")
                await self._client.start_server()
            else:
                raise
        
        self._session_manager = SessionManager(
            self._client,
            auto_cleanup=True,
        )
        await self._session_manager.start()
        
        self._initialized = True
        logger.info(f"ServeHandler initialized, connected to {self.host}:{self.port}")
    
    async def shutdown(self) -> None:
        """Shutdown the handler and cleanup."""
        if self._session_manager:
            await self._session_manager.stop()
            self._session_manager = None
        
        if self._client:
            await self._client.disconnect()
            self._client = None
        
        self._initialized = False
        logger.info("ServeHandler shutdown")
    
    @property
    def client(self) -> OpenCodeServeClient:
        """Get the client, raising if not initialized."""
        if self._client is None:
            raise RuntimeError("ServeHandler not initialized. Call initialize() first.")
        return self._client
    
    @property
    def session_manager(self) -> SessionManager:
        """Get the session manager, raising if not initialized."""
        if self._session_manager is None:
            raise RuntimeError("ServeHandler not initialized. Call initialize() first.")
        return self._session_manager
    
    async def _ensure_initialized(self) -> None:
        """Ensure the handler is initialized."""
        if not self._initialized:
            await self.initialize()

    async def _get_cached_providers(self) -> Optional[Dict[str, Any]]:
        """
        Get providers with TTL cache.

        Returns:
            Cached or fresh provider data, or None if unavailable
        """
        now = time.time()

        # Check cache validity
        if (self._provider_cache is not None and
            now - self._provider_cache_time < self.PROVIDER_CACHE_TTL):
            logger.debug("Using cached providers")
            return self._provider_cache

        # Fetch fresh data
        try:
            providers_result = await self.get_providers()
            if providers_result.success and providers_result.data:
                self._provider_cache = providers_result.data
                self._provider_cache_time = now
                logger.debug("Refreshed provider cache")
                return self._provider_cache
        except Exception as e:
            logger.warning(f"Failed to fetch providers for cache: {e}")

        return None

    async def _validate_model(
        self,
        model_info: Optional[ModelInfo],
        soft: bool = True,
    ) -> None:
        """
        Validate that model is supported.

        Args:
            model_info: Model to validate
            soft: If True, log warning instead of raising error (default)

        Raises:
            ValueError: If model not found and soft=False
        """
        if not model_info:
            return  # No model specified, use default

        # Get available providers (cached with TTL)
        providers_data = await self._get_cached_providers()

        if not providers_data:
            logger.warning("Could not validate model, providers unavailable")
            return

        # Validate provider/model exists
        models_list = providers_data.get("models", [])
        target = f"{model_info.providerID}/{model_info.modelID}"
        found = target in models_list

        if not found:
            error_msg = (
                f"Model '{target}' not found in available models. "
                f"Use opencode_list_models to see available models."
            )

            if soft:
                # Soft validation: warn but allow request
                logger.warning(f"Soft validation failed: {error_msg}")
            else:
                # Hard validation: block request
                raise ValueError(error_msg)

    # =========================================================================
    # MCP Tool Methods
    # =========================================================================

    async def prompt(
        self,
        message: str,
        directory: Optional[str] = None,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        agent: Optional[str] = None,
        timeout: Optional[float] = None,
        stream: bool = False,
    ) -> OpenCodeResult:
        """
        Send a prompt to OpenCode via the serve API.
        
        This is the main entry point for interacting with OpenCode through
        the HTTP API instead of subprocess.
        
        Args:
            message: The prompt/message to send
            directory: Working directory (defaults to self.default_directory)
            session_id: Existing session ID to reuse
            model: Model in provider/model format (e.g., "anthropic/claude-sonnet-4-20250514")
            agent: Agent to use
            timeout: Timeout in seconds
            stream: Whether to stream the response
            
        Returns:
            OpenCodeResult with response data
        """
        import time
        start_time = time.time()
        
        await self._ensure_initialized()
        
        directory = directory or self.default_directory
        timeout = timeout or self.default_timeout
        
        try:
            # Get or create session
            if session_id:
                # Use provided session
                sid = session_id
            else:
                # Get from session manager
                sid = await self.session_manager.get_session(directory)
            
            # Parse model if provided
            model_info = None
            if model and "/" in model:
                provider, model_id = model.split("/", 1)
                model_info = ModelInfo(providerID=provider, modelID=model_id)

            # Validate model if specified (soft validation by default)
            if model_info:
                await self._validate_model(model_info, soft=True)

            try:
                if stream:
                    # Stream response
                    response = await self._stream_prompt(
                        session_id=sid,
                        message=message,
                        model=model_info,
                        agent=agent,
                        timeout=timeout,
                        directory=directory,
                    )
                else:
                    # Synchronous response
                    messages = await self.client.prompt(
                        session_id=sid,
                        text=message,
                        model=model_info,
                        agent=agent,
                    )
                    
                    response = self._extract_response_text(messages)
                
                execution_time = time.time() - start_time
                
                return OpenCodeResult(
                    success=True,
                    data=response,
                    session_id=sid,
                    execution_time=execution_time,
                    exit_code=0,
                    raw_output=response.get("text") if isinstance(response, dict) else str(response),
                )
                
            finally:
                # Release session if we got it from manager
                if not session_id:
                    self.session_manager.release_session(sid)
                    
        except SessionBusyError as e:
            return OpenCodeResult(
                success=False,
                error=f"Session is busy: {str(e)}",
                execution_time=time.time() - start_time,
                exit_code=1,
            )
        except Exception as e:
            logger.error(f"Prompt error: {e}")
            return OpenCodeResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
                exit_code=1,
            )
    
    async def _stream_prompt(
        self,
        session_id: str,
        message: str,
        model: Optional[ModelInfo] = None,
        agent: Optional[str] = None,
        timeout: Optional[float] = None,
        directory: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Stream a prompt and collect the response."""
        sse_handler = SSEHandler(
            self.client.client,
            directory=directory or self.default_directory,
            auto_approve_permissions=self.auto_approve_permissions,
        )
        
        # Send async prompt
        await self.client.prompt_async(
            session_id=session_id,
            text=message,
            model=model,
            agent=agent,
        )
        
        # Collect response
        response = await sse_handler.collect_response(
            session_id=session_id,
            timeout=timeout,
        )
        
        return response.to_dict()
    
    def _extract_response_text(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract response text from API response.
        
        The API returns: {"info": {...AssistantMessage...}, "parts": [...Part...]}
        NOT a list of messages.
        """
        text_parts = []
        tool_calls = []
        
        # Handle the correct API response format
        parts = response.get("parts", [])
        info = response.get("info", {})
        
        for part in parts:
            part_type = part.get("type") if isinstance(part, dict) else None
            if part_type == "text":
                text_parts.append(part.get("text", ""))
            elif part_type == "tool":
                tool_calls.append(part)
        
        return {
            "text": "\n".join(text_parts),
            "tool_calls": tool_calls if tool_calls else None,
            "message_id": info.get("id"),
            "model": info.get("modelID"),
            "provider": info.get("providerID"),
            "tokens": info.get("tokens"),
            "cost": info.get("cost"),
        }
    
    async def create_session(
        self,
        directory: Optional[str] = None,
        title: Optional[str] = None,
    ) -> OpenCodeResult:
        """
        Create a new session.
        
        Args:
            directory: Working directory
            title: Session title
            
        Returns:
            OpenCodeResult with session data
        """
        import time
        start_time = time.time()
        
        await self._ensure_initialized()
        
        try:
            session = await self.client.create_session(
                title=title,
                directory=directory or self.default_directory,
            )
            
            return OpenCodeResult(
                success=True,
                data=session.model_dump(),
                session_id=session.id,
                execution_time=time.time() - start_time,
                exit_code=0,
            )
        except Exception as e:
            return OpenCodeResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
                exit_code=1,
            )
    
    async def list_sessions(self) -> OpenCodeResult:
        """
        List all sessions.
        
        Returns:
            OpenCodeResult with list of sessions
        """
        import time
        start_time = time.time()
        
        await self._ensure_initialized()
        
        try:
            sessions = await self.client.list_sessions()
            
            return OpenCodeResult(
                success=True,
                data=[s.model_dump() for s in sessions],
                execution_time=time.time() - start_time,
                exit_code=0,
            )
        except Exception as e:
            return OpenCodeResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
                exit_code=1,
            )
    
    async def get_session_messages(
        self,
        session_id: str,
    ) -> OpenCodeResult:
        """
        Get messages for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            OpenCodeResult with messages
        """
        import time
        start_time = time.time()
        
        await self._ensure_initialized()
        
        try:
            messages = await self.client.get_messages(session_id)
            
            return OpenCodeResult(
                success=True,
                data=messages,
                session_id=session_id,
                execution_time=time.time() - start_time,
                exit_code=0,
            )
        except Exception as e:
            return OpenCodeResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
                exit_code=1,
            )
    
    async def abort_session(
        self,
        session_id: str,
    ) -> OpenCodeResult:
        """
        Abort a running session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            OpenCodeResult indicating success/failure
        """
        import time
        start_time = time.time()
        
        await self._ensure_initialized()
        
        try:
            await self.client.abort_session(session_id)
            
            return OpenCodeResult(
                success=True,
                data={"aborted": True},
                session_id=session_id,
                execution_time=time.time() - start_time,
                exit_code=0,
            )
        except Exception as e:
            return OpenCodeResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
                exit_code=1,
            )
    
    async def get_providers(self) -> OpenCodeResult:
        """
        Get available providers and models.

        Returns:
            OpenCodeResult with structured provider/model data
        """
        start_time = time.time()

        await self._ensure_initialized()

        try:
            providers = await self.client.get_providers()

            # Format as structured list
            models_list = []
            for provider in providers:
                provider_id = provider.get("id", "")
                for model in provider.get("models", []):
                    model_id = model.get("id", "")
                    if provider_id and model_id:
                        models_list.append(f"{provider_id}/{model_id}")

            return OpenCodeResult(
                success=True,
                data={
                    "providers": providers,
                    "models": models_list,
                },
                execution_time=time.time() - start_time,
                exit_code=0,
                raw_output="\n".join(models_list),
            )
        except Exception as e:
            return OpenCodeResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
                exit_code=1,
            )
    
    async def get_tools(self) -> OpenCodeResult:
        """
        Get available tools.
        
        Returns:
            OpenCodeResult with tool list
        """
        import time
        start_time = time.time()
        
        await self._ensure_initialized()
        
        try:
            tools = await self.client.get_tools()
            
            return OpenCodeResult(
                success=True,
                data=tools,
                execution_time=time.time() - start_time,
                exit_code=0,
            )
        except Exception as e:
            return OpenCodeResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
                exit_code=1,
            )
    
    async def get_session_diff(
        self,
        session_id: str,
    ) -> OpenCodeResult:
        """
        Get diff of changes made in a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            OpenCodeResult with diff data
        """
        import time
        start_time = time.time()
        
        await self._ensure_initialized()
        
        try:
            diff = await self.client.get_session_diff(session_id)
            
            return OpenCodeResult(
                success=True,
                data=diff,
                session_id=session_id,
                execution_time=time.time() - start_time,
                exit_code=0,
            )
        except Exception as e:
            return OpenCodeResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
                exit_code=1,
            )
    
    async def get_serve_status(self) -> OpenCodeResult:
        """
        Get status of the opencode serve instance.
        
        Returns:
            OpenCodeResult with server status
        """
        import time
        start_time = time.time()
        
        try:
            await self._ensure_initialized()
            
            is_healthy = await self.client.is_healthy()
            
            # Get session manager stats
            stats = self.session_manager.get_stats()
            
            return OpenCodeResult(
                success=True,
                data={
                    "server_healthy": is_healthy,
                    "host": self.host,
                    "port": self.port,
                    "session_stats": stats,
                },
                execution_time=time.time() - start_time,
                exit_code=0,
            )
        except ServerNotRunningError:
            return OpenCodeResult(
                success=False,
                data={
                    "server_healthy": False,
                    "host": self.host,
                    "port": self.port,
                },
                error=f"Server not running at {self.host}:{self.port}",
                execution_time=time.time() - start_time,
                exit_code=1,
            )
        except Exception as e:
            return OpenCodeResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
                exit_code=1,
            )


# Global handler instance (lazy initialized)
_serve_handler: Optional[ServeHandler] = None


def get_serve_handler(
    host: str = "127.0.0.1",
    port: int = 4096,
    **kwargs,
) -> ServeHandler:
    """
    Get or create the global serve handler.
    
    Args:
        host: Server host
        port: Server port
        **kwargs: Additional arguments for ServeHandler
        
    Returns:
        ServeHandler instance
    """
    global _serve_handler
    
    if _serve_handler is None:
        _serve_handler = ServeHandler(host=host, port=port, **kwargs)
    
    return _serve_handler


async def shutdown_serve_handler() -> None:
    """Shutdown the global serve handler."""
    global _serve_handler
    
    if _serve_handler is not None:
        await _serve_handler.shutdown()
        _serve_handler = None
