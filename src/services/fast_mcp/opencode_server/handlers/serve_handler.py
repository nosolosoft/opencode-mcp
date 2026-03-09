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
from ..settings import settings
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
        default_timeout: float = 600.0,
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
        Send a prompt to OpenCode via the serve API with auto-recovery for corrupted sessions.

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

        # Track if we should retry on failure
        is_managed_session = session_id is None
        retry_attempted = False

        try:
            # Get or create session
            if session_id:
                # Use provided session
                sid = session_id
            else:
                # Get from session manager
                sid = await self.session_manager.get_session(directory)

            # Parse model if provided, or use default
            model_info = None
            model_to_use = model or settings.opencode_default_model

            if model_to_use and "/" in model_to_use:
                provider, model_id = model_to_use.split("/", 1)
                model_info = ModelInfo(providerID=provider, modelID=model_id)

            # Validate model if specified (soft validation by default)
            if model_info:
                await self._validate_model(model_info, soft=True)

            async def _execute_prompt(current_sid: str):
                """Execute prompt with given session."""
                try:
                    if stream:
                        return await self._stream_prompt(
                            session_id=current_sid,
                            message=message,
                            model=model_info,
                            agent=agent,
                            timeout=timeout,
                            directory=directory,
                        )
                    else:
                        messages = await self.client.prompt(
                            session_id=current_sid,
                            text=message,
                            model=model_info,
                            agent=agent,
                        )
                        return self._extract_response_text(messages)
                except Exception as e:
                    # Convert streaming errors to ValueError for unified handling
                    error_msg = str(e).lower()
                    if "empty" in error_msg or "timeout" in error_msg or "sse" in error_msg:
                        raise ValueError(f"Stream error (possible corrupted session): {e}") from e
                    raise

            try:
                response = await _execute_prompt(sid)

                execution_time = time.time() - start_time

                return OpenCodeResult(
                    success=True,
                    data=response,
                    session_id=sid,
                    execution_time=execution_time,
                    exit_code=0,
                    raw_output=response.get("text") if isinstance(response, dict) else str(response),
                )

            except ValueError as e:
                # Check for "empty response" (corrupted session indicator)
                is_empty_response = "empty response" in str(e).lower()

                if is_empty_response and is_managed_session and not retry_attempted:
                    logger.warning(f"Session {sid} returned empty response, retrying with new session")
                    retry_attempted = True

                    # 1. Invalidate corrupted session (async, public method)
                    await self.session_manager.invalidate_session(sid)

                    # 2. Get NEW session (force new)
                    sid = await self.session_manager.get_session(
                        directory,
                        prefer_existing=False  # Force new
                    )

                    # 3. Retry once
                    response = await _execute_prompt(sid)

                    execution_time = time.time() - start_time

                    return OpenCodeResult(
                        success=True,
                        data=response,
                        session_id=sid,
                        execution_time=execution_time,
                        exit_code=0,
                        raw_output=response.get("text") if isinstance(response, dict) else str(response),
                    )
                else:
                    # Not recoverable or already retried
                    raise

            finally:
                # Release session if we got it from manager
                if is_managed_session:
                    self.session_manager.release_session(sid)

        except SessionBusyError as e:
            return OpenCodeResult(
                success=False,
                error=f"Session is busy: {str(e)}",
                execution_time=time.time() - start_time,
                exit_code=1,
            )
        except Exception as e:
            logger.error(f"Prompt error: {e}", exc_info=True)
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
            providers_data = await self.client.get_providers()

            # Handle API response format: can be list or {"all": [list]}
            if isinstance(providers_data, dict) and "all" in providers_data:
                providers = providers_data["all"]
            elif isinstance(providers_data, list):
                providers = providers_data
            else:
                providers = []

            # Format as structured list
            models_list = []
            for provider in providers:
                if not isinstance(provider, dict):
                    continue

                provider_id = provider.get("id", "")
                models = provider.get("models", {})

                # Models can be dict or list
                if isinstance(models, dict):
                    # Models is a dict: {model_id: model_obj}
                    for model_id, model_obj in models.items():
                        if provider_id and model_id:
                            models_list.append(f"{provider_id}/{model_id}")
                elif isinstance(models, list):
                    # Models is a list: [model_obj, ...]
                    for model in models:
                        if isinstance(model, dict):
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

    # =========================================================================
    # Search & File Tool Methods (Serve API endpoints)
    # =========================================================================

    async def search_text(
        self,
        pattern: str,
        directory: Optional[str] = None,
    ) -> OpenCodeResult:
        """
        Search for text patterns across files using ripgrep.

        Truncates results to settings.max_search_results.

        Args:
            pattern: Regex pattern to search for
            directory: Working directory override

        Returns:
            OpenCodeResult with list of matches
        """
        start_time = time.time()

        await self._ensure_initialized()

        directory = directory or self.default_directory

        try:
            matches = await self.client.find_text(
                pattern=pattern,
                directory=directory,
                timeout=float(settings.timeout_search),
            )

            total_count = len(matches)
            truncated = False

            if total_count > settings.max_search_results:
                matches = matches[:settings.max_search_results]
                truncated = True

            # Format matches for readability
            formatted = []
            for m in matches:
                path_text = m.get("path", {}).get("text", "") if isinstance(m.get("path"), dict) else str(m.get("path", ""))
                line_text = m.get("lines", {}).get("text", "").rstrip() if isinstance(m.get("lines"), dict) else str(m.get("lines", ""))
                formatted.append({
                    "path": path_text,
                    "line_number": m.get("line_number", 0),
                    "text": line_text,
                })

            result_data = {
                "matches": formatted,
                "count": len(formatted),
                "total": total_count,
                "pattern": pattern,
            }

            if truncated:
                result_data["truncated"] = True
                result_data["message"] = (
                    f"Showing {settings.max_search_results} of {total_count} matches. "
                    f"Refine your pattern for more specific results."
                )

            return OpenCodeResult(
                success=True,
                data=result_data,
                execution_time=time.time() - start_time,
                exit_code=0,
            )
        except Exception as e:
            logger.error(f"search_text error: {e}", exc_info=True)
            return OpenCodeResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
                exit_code=1,
                is_error=True,
            )

    async def find_files(
        self,
        query: str,
        directory: Optional[str] = None,
        file_type: Optional[str] = None,
    ) -> OpenCodeResult:
        """
        Search for files by name or pattern.

        Args:
            query: File name pattern
            directory: Working directory override
            file_type: Filter by 'file' or 'directory'

        Returns:
            OpenCodeResult with list of matching file paths
        """
        start_time = time.time()

        await self._ensure_initialized()

        directory = directory or self.default_directory

        try:
            files = await self.client.find_files(
                query=query,
                directory=directory,
                file_type=file_type,
                timeout=float(settings.timeout_search),
            )

            return OpenCodeResult(
                success=True,
                data={
                    "files": files,
                    "count": len(files),
                    "query": query,
                },
                execution_time=time.time() - start_time,
                exit_code=0,
            )
        except Exception as e:
            logger.error(f"find_files error: {e}", exc_info=True)
            return OpenCodeResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
                exit_code=1,
                is_error=True,
            )

    async def read_file(
        self,
        path: str,
        directory: Optional[str] = None,
    ) -> OpenCodeResult:
        """
        Read file content with binary detection and size limits.

        Binary files return a placeholder message.
        Files exceeding max_file_read_size are truncated.

        Args:
            path: File path (relative to project root)
            directory: Working directory override

        Returns:
            OpenCodeResult with file content
        """
        start_time = time.time()

        await self._ensure_initialized()

        directory = directory or self.default_directory

        try:
            data = await self.client.read_file(
                path=path,
                directory=directory,
                timeout=float(settings.timeout_file_ops),
            )

            file_type = data.get("type", "text")
            content = data.get("content", "")

            # Handle empty response (API returns 200 with empty content for nonexistent files)
            if file_type == "text" and not content and not data.get("diff"):
                return OpenCodeResult(
                    success=False,
                    error=f"File not found or empty: {path}",
                    execution_time=time.time() - start_time,
                    exit_code=1,
                    is_error=True,
                )

            # Handle binary files
            if file_type == "binary":
                return OpenCodeResult(
                    success=True,
                    data={
                        "path": path,
                        "type": "binary",
                        "content": f"[Binary file] (MIME: {data.get('mimeType', 'unknown')}). Cannot display as text.",
                        "size": len(content) if content else 0,
                    },
                    execution_time=time.time() - start_time,
                    exit_code=0,
                )

            # Detect binary content via null bytes (fallback)
            if content and "\x00" in content:
                return OpenCodeResult(
                    success=True,
                    data={
                        "path": path,
                        "type": "binary",
                        "content": f"[Binary file] (Size: {len(content)} bytes). Cannot display as text.",
                        "size": len(content),
                    },
                    execution_time=time.time() - start_time,
                    exit_code=0,
                )

            # Truncate large files
            truncated = False
            original_size = len(content.encode("utf-8", errors="replace"))
            if original_size > settings.max_file_read_size:
                # Truncate to byte limit (approximate for UTF-8)
                content = content[:settings.max_file_read_size]
                truncated = True

            result_data = {
                "path": path,
                "type": file_type,
                "content": content,
                "size": original_size,
            }

            if data.get("diff"):
                result_data["diff"] = data["diff"]

            if truncated:
                result_data["truncated"] = True
                result_data["message"] = (
                    f"File truncated to {settings.max_file_read_size // 1024}KB "
                    f"(original: {original_size // 1024}KB)."
                )

            return OpenCodeResult(
                success=True,
                data=result_data,
                execution_time=time.time() - start_time,
                exit_code=0,
            )
        except Exception as e:
            error_msg = str(e)
            # Detect file not found from HTTP 404 or specific error messages
            is_not_found = "404" in error_msg or "not found" in error_msg.lower()
            return OpenCodeResult(
                success=False,
                error=f"File not found: {path}" if is_not_found else error_msg,
                execution_time=time.time() - start_time,
                exit_code=1,
                is_error=True,
            )

    async def list_directory(
        self,
        path: str = ".",
        directory: Optional[str] = None,
    ) -> OpenCodeResult:
        """
        List files and directories at a path.

        Args:
            path: Directory path to list (relative to project root)
            directory: Working directory override

        Returns:
            OpenCodeResult with directory entries
        """
        start_time = time.time()

        await self._ensure_initialized()

        directory = directory or self.default_directory

        try:
            entries = await self.client.list_directory(
                path=path,
                directory=directory,
                timeout=float(settings.timeout_file_ops),
            )

            # Format entries
            formatted = []
            for entry in entries:
                formatted.append({
                    "name": entry.get("name", ""),
                    "path": entry.get("path", ""),
                    "type": entry.get("type", "file"),
                    "ignored": entry.get("ignored", False),
                })

            return OpenCodeResult(
                success=True,
                data={
                    "entries": formatted,
                    "count": len(formatted),
                    "path": path,
                },
                execution_time=time.time() - start_time,
                exit_code=0,
            )
        except Exception as e:
            error_msg = str(e)
            is_not_found = "404" in error_msg or "not found" in error_msg.lower()
            return OpenCodeResult(
                success=False,
                error=f"Directory not found: {path}" if is_not_found else error_msg,
                execution_time=time.time() - start_time,
                exit_code=1,
                is_error=True,
            )

    async def file_status(
        self,
        directory: Optional[str] = None,
    ) -> OpenCodeResult:
        """
        Get git status of modified files.

        Args:
            directory: Working directory override

        Returns:
            OpenCodeResult with git file status entries
        """
        start_time = time.time()

        await self._ensure_initialized()

        directory = directory or self.default_directory

        try:
            entries = await self.client.file_status(
                directory=directory,
                timeout=float(settings.timeout_file_ops),
            )

            return OpenCodeResult(
                success=True,
                data={
                    "files": entries,
                    "count": len(entries),
                },
                execution_time=time.time() - start_time,
                exit_code=0,
            )
        except Exception as e:
            logger.error(f"file_status error: {e}", exc_info=True)
            return OpenCodeResult(
                success=False,
                error=str(e),
                execution_time=time.time() - start_time,
                exit_code=1,
                is_error=True,
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
