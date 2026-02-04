"""
OpenCode CLI Executor
Async subprocess wrapper with timeout handling, heartbeat polling,
partial output capture, retry logic, and robust JSON parsing.
"""

import asyncio
import json
import logging
import os
import shutil
import time
from typing import Any, Callable, Dict, List, Optional

import httpx

from .models import OpenCodeResult, OpenCodeStatusResponse
from .settings import settings
from .handlers.retry import RetryConfig, execute_with_retry

logger = logging.getLogger(__name__)

# Serve server configuration from environment
SERVE_HOST = os.environ.get("OPENCODE_SERVE_HOST", "127.0.0.1")
SERVE_PORT = int(os.environ.get("OPENCODE_SERVE_PORT", "4096"))

# Heartbeat interval for long-running processes (seconds)
HEARTBEAT_INTERVAL = 30


class OpenCodeExecutor:
    """Executor for OpenCode CLI commands with retry and heartbeat support."""

    def __init__(self):
        self.default_timeout = settings.default_timeout
        self.max_timeout = settings.max_timeout
        self._cli_path: Optional[str] = None

    async def execute_command(
        self,
        args: List[str],
        timeout: Optional[int] = None,
        use_json_format: bool = True,
        cwd: Optional[str] = None,
        enable_retry: bool = False,
        retry_config: Optional[RetryConfig] = None,
        progress_callback: Optional[Callable] = None,
    ) -> OpenCodeResult:
        """
        Execute an OpenCode CLI command with heartbeat monitoring
        and optional retry logic.

        Args:
            args: Command arguments (without 'opencode' prefix)
            timeout: Timeout in seconds (defaults to settings.default_timeout)
            use_json_format: Whether to add --format json flag
            cwd: Working directory for command execution
            enable_retry: Whether to enable retry on failure
            retry_config: Custom retry configuration
            progress_callback: Async callback(elapsed, timeout) for progress reporting

        Returns:
            OpenCodeResult with execution results
        """
        if enable_retry:
            config = retry_config or RetryConfig()

            async def _attempt(attempt: int) -> OpenCodeResult:
                adjusted_timeout = config.get_adjusted_timeout(
                    timeout or self.default_timeout, attempt
                )
                return await self._execute_single(
                    args, adjusted_timeout, use_json_format, cwd, progress_callback
                )

            return await execute_with_retry(_attempt, config)

        return await self._execute_single(
            args, timeout, use_json_format, cwd, progress_callback
        )

    async def _execute_single(
        self,
        args: List[str],
        timeout: Optional[int] = None,
        use_json_format: bool = True,
        cwd: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> OpenCodeResult:
        """
        Execute a single command attempt with heartbeat polling
        and partial output capture on timeout.
        """
        # Build command
        cmd = [settings.opencode_command] + args

        # Add JSON format if requested and not already present
        if use_json_format and "--format" not in args:
            cmd.extend(["--format", "json"])

        logger.info(f"Executing command: {' '.join(cmd)}")
        start_time = time.time()

        # Apply timeout buffer for subprocess coordination
        effective_timeout = min(timeout or self.default_timeout, self.max_timeout)
        # Subprocess gets slightly less time than MCP to allow response formatting
        # Only apply buffer for long timeouts; short timeouts use direct value
        if effective_timeout > settings.timeout_buffer + 10:
            subprocess_timeout = effective_timeout - settings.timeout_buffer
        else:
            subprocess_timeout = effective_timeout

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            # Use heartbeat polling loop instead of monolithic wait_for
            stdout_data, stderr_data, timed_out = await self._wait_with_heartbeat(
                process, subprocess_timeout, progress_callback
            )

            execution_time = time.time() - start_time
            stdout_str = stdout_data.decode("utf-8", errors="replace").strip()
            stderr_str = stderr_data.decode("utf-8", errors="replace").strip()

            if timed_out:
                logger.warning(
                    f"Command timed out after {subprocess_timeout}s, "
                    f"captured {len(stdout_str)} bytes of partial output"
                )
                # Return partial result with whatever output was captured
                result = self._parse_output(
                    stdout_str, stderr_str, -1, execution_time
                )
                result.partial = True
                result.error = (
                    f"Command timed out after {subprocess_timeout} seconds. "
                    f"Partial output ({len(stdout_str)} chars) captured below."
                )
                if not result.success:
                    result.is_error = True
                return result

            logger.debug(f"Exit code: {process.returncode}")
            logger.debug(f"Stdout length: {len(stdout_str)}")
            logger.debug(f"Stderr length: {len(stderr_str)}")

            return self._parse_output(
                stdout_str,
                stderr_str,
                process.returncode or 0,
                execution_time,
            )

        except FileNotFoundError:
            logger.error(f"OpenCode CLI not found: {settings.opencode_command}")
            return OpenCodeResult(
                success=False,
                error=f"OpenCode CLI not found at '{settings.opencode_command}'. "
                f"Please ensure OpenCode is installed and in PATH.",
                execution_time=time.time() - start_time,
                exit_code=-1,
                is_error=True,
            )
        except Exception as e:
            logger.error(f"Error executing command: {e}")
            return OpenCodeResult(
                success=False,
                error=f"Error executing command: {str(e)}",
                execution_time=time.time() - start_time,
                exit_code=-1,
                is_error=True,
            )

    async def _wait_with_heartbeat(
        self,
        process: asyncio.subprocess.Process,
        timeout: int,
        progress_callback: Optional[Callable] = None,
    ) -> tuple[bytes, bytes, bool]:
        """
        Wait for process completion with periodic heartbeat checks.

        Uses process.wait() polling (not communicate()) to allow
        repeated heartbeat checks without stream conflicts.
        Reads stdout/stderr concurrently via background tasks.

        Args:
            process: The subprocess to monitor
            timeout: Total timeout in seconds
            progress_callback: Optional async callback(elapsed, timeout)

        Returns:
            Tuple of (stdout_bytes, stderr_bytes, timed_out)
        """
        start_time = time.time()

        # Start reading stdout and stderr concurrently
        stdout_chunks: list[bytes] = []
        stderr_chunks: list[bytes] = []

        async def _read_stream(stream, chunks: list[bytes]):
            """Read a stream until EOF, collecting chunks."""
            if stream is None:
                return
            try:
                while True:
                    chunk = await stream.read(8192)
                    if not chunk:
                        break
                    chunks.append(chunk)
            except Exception:
                pass

        # Launch readers as background tasks
        stdout_task = asyncio.create_task(_read_stream(process.stdout, stdout_chunks))
        stderr_task = asyncio.create_task(_read_stream(process.stderr, stderr_chunks))

        # Poll process.wait() with heartbeat intervals
        while True:
            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                break

            check_interval = min(HEARTBEAT_INTERVAL, remaining)
            try:
                await asyncio.wait_for(
                    asyncio.shield(process.wait()), timeout=check_interval
                )
                # Process completed normally
                # Give readers a moment to finish
                await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                stdout = b"".join(stdout_chunks)
                stderr = b"".join(stderr_chunks)
                return stdout, stderr, False
            except asyncio.TimeoutError:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    break

                # Heartbeat - process still running
                logger.debug(
                    f"Heartbeat: process still running ({elapsed:.0f}s/{timeout}s)"
                )
                if progress_callback:
                    try:
                        await progress_callback(elapsed, timeout)
                    except Exception as e:
                        logger.debug(f"Progress callback error: {e}")

        # Timeout reached - kill process and collect partial output
        try:
            process.kill()
        except ProcessLookupError:
            pass

        # Give readers a brief moment to flush
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except (asyncio.TimeoutError, ProcessLookupError):
            pass

        stdout = b"".join(stdout_chunks)
        stderr = b"".join(stderr_chunks)
        return stdout, stderr, True

    def _parse_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        execution_time: float,
    ) -> OpenCodeResult:
        """
        Parse OpenCode CLI output with robust JSON extraction.

        Handles JSON Lines format from OpenCode CLI where output contains
        multiple events: step_start, text (with response), step_finish.
        """
        success = exit_code == 0

        # Try to parse JSON from stdout
        json_data = self._extract_json(stdout)

        if json_data is not None:
            # Extract sessionID (camelCase) and response text from JSON Lines
            session_id = None
            response_text = None

            if isinstance(json_data, list):
                # JSON Lines format: list of event objects
                for item in json_data:
                    if not isinstance(item, dict):
                        continue

                    # Extract sessionID from any event (usually in step_start/step_finish)
                    if session_id is None and "sessionID" in item:
                        session_id = item["sessionID"]

                    # Extract response text from "text" event
                    if item.get("type") == "text":
                        part = item.get("part", {})
                        if isinstance(part, dict) and "text" in part:
                            response_text = part["text"]

            elif isinstance(json_data, dict):
                # Single JSON object
                session_id = (
                    json_data.get("sessionID")
                    or json_data.get("session")
                    or json_data.get("session_id")
                )
                # Check if it's a text event
                if json_data.get("type") == "text":
                    part = json_data.get("part", {})
                    if isinstance(part, dict) and "text" in part:
                        response_text = part["text"]

            return OpenCodeResult(
                success=success,
                data=json_data,
                session_id=session_id,
                execution_time=execution_time,
                exit_code=exit_code,
                raw_output=response_text or stdout,
                stderr=stderr if stderr else None,
            )

        # No valid JSON found, return raw output
        return OpenCodeResult(
            success=success,
            data={"raw_output": stdout} if stdout else None,
            error=stderr if not success and stderr else None,
            execution_time=execution_time,
            exit_code=exit_code,
            raw_output=stdout,
            stderr=stderr if stderr else None,
        )

    def _extract_json(
        self, text: str
    ) -> Optional[List[Dict[str, Any]] | Dict[str, Any]]:
        """
        Extract JSON from text, handling JSON Lines format (newline-delimited JSON).

        OpenCode CLI with --format json outputs JSON Lines where each line
        is a separate JSON object (step_start, text, step_finish events).

        Returns:
            - List of dicts if multiple JSON objects found (JSON Lines)
            - Single dict if only one JSON object
            - None if no valid JSON found
        """
        if not text:
            return None

        # Strategy 1: Parse JSON Lines (each line is a JSON object)
        items = []
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        if items:
            # Return list if multiple items, single dict if one
            return items if len(items) > 1 else items[0]

        # Strategy 2: Try parsing entire text as single JSON (fallback)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Strategy 3: Extract JSON object from mixed content
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = text[start:end]
                return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        return None

    async def run_prompt(
        self,
        message: str,
        model: Optional[str] = None,
        agent: Optional[str] = None,
        files: Optional[List[str]] = None,
        timeout: Optional[int] = None,
        variant: Optional[str] = None,
    ) -> OpenCodeResult:
        """
        Run OpenCode with a prompt message.

        Uses retry logic for timeout resilience.

        Args:
            message: The prompt/message to send
            model: Optional model in provider/model format
            agent: Optional agent to use
            files: Optional list of files to attach
            timeout: Optional timeout in seconds
            variant: Optional model variant (minimal/low/medium/high) for Gemini models

        Note: Message is placed LAST in args to follow CLI best practices
        and avoid issues with prompts starting with '-'.
        """
        args = ["run", "--format", "json"]  # Force JSON Lines output for parsing

        # Add optional flags FIRST
        if model:
            args.extend(["--model", model])
        if agent:
            args.extend(["--agent", agent])
        if variant:
            args.extend(["--variant", variant])
        if files:
            for f in files:
                args.extend(["-f", f])

        # Add message as LAST positional argument
        args.append(message)

        return await self.execute_command(
            args,
            timeout=timeout,
            enable_retry=settings.retry_on_timeout,
        )

    async def _is_serve_running(self) -> bool:
        """Check if opencode serve is running on the configured port."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"http://{SERVE_HOST}:{SERVE_PORT}/doc")
                return response.status_code == 200
        except Exception:
            return False

    async def continue_session(
        self,
        session_id: str,
        message: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> OpenCodeResult:
        """
        Continue an existing OpenCode session.

        Args:
            session_id: The session ID to continue
            message: Optional follow-up message
            timeout: Optional timeout in seconds

        Note: Message is placed LAST in args to follow CLI best practices.
        If opencode serve is running, uses --attach to connect to it
        and avoid port conflicts.
        """
        args = ["run", "--format", "json"]  # Force JSON Lines output for parsing

        # Check if serve is running and attach to it to avoid port conflicts
        if await self._is_serve_running():
            serve_url = f"http://{SERVE_HOST}:{SERVE_PORT}"
            args.extend(["--attach", serve_url])
            logger.debug(f"Attaching to running serve at {serve_url}")

        # Add session flags
        args.extend(["--session", session_id, "--continue"])

        # Add message as LAST positional argument (if provided)
        if message:
            args.append(message)

        return await self.execute_command(
            args,
            timeout=timeout,
            enable_retry=settings.retry_on_timeout,
        )

    async def list_models(
        self,
        provider: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> OpenCodeResult:
        """
        List available models.

        Args:
            provider: Optional provider to filter by
            timeout: Optional timeout in seconds
        """
        args = ["models"]

        if provider:
            args.append(provider)

        return await self.execute_command(
            args,
            use_json_format=False,
            timeout=timeout or settings.timeout_list_models,
        )

    async def list_sessions(self, timeout: Optional[int] = None) -> OpenCodeResult:
        """
        List all active sessions using CLI.

        Args:
            timeout: Optional timeout in seconds

        Returns list of sessions managed by OpenCode CLI.
        """
        args = ["session", "list"]
        return await self.execute_command(
            args,
            use_json_format=False,
            timeout=timeout or settings.timeout_list_sessions,
        )

    async def export_session(self, session_id: str) -> OpenCodeResult:
        """
        Export a session as JSON.

        Args:
            session_id: The session ID to export
        """
        args = ["export", session_id]
        return await self.execute_command(args, use_json_format=False)

    async def get_stats(self) -> OpenCodeResult:
        """Get OpenCode usage statistics."""
        args = ["stats"]
        return await self.execute_command(args, use_json_format=False)

    async def get_version(self) -> Optional[str]:
        """Get OpenCode CLI version."""
        try:
            process = await asyncio.create_subprocess_exec(
                settings.opencode_command,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10)
            version = stdout.decode("utf-8", errors="replace").strip()
            return version if version else None
        except Exception as e:
            logger.error(f"Error getting version: {e}")
            return None

    async def check_status(self) -> OpenCodeStatusResponse:
        """
        Check OpenCode CLI availability and status.

        Returns:
            OpenCodeStatusResponse with status information
        """
        # Check if CLI exists
        cli_path = shutil.which(settings.opencode_command)

        if not cli_path:
            return OpenCodeStatusResponse(
                status="unavailable",
                error=f"OpenCode CLI not found in PATH. Command: {settings.opencode_command}",
            )

        # Get version
        version = await self.get_version()

        # Get available models
        models_result = await self.list_models()
        available_models = None

        if models_result.success:
            # Try to extract models from raw_output first
            if models_result.raw_output:
                models = []
                for line in models_result.raw_output.split("\n"):
                    line = line.strip()
                    if "/" in line and not line.startswith("#"):
                        models.append(line)
                available_models = models if models else None
            # Fallback to data if raw_output is None (JSON was parsed)
            elif models_result.data:
                if isinstance(models_result.data, list):
                    available_models = models_result.data
                elif isinstance(models_result.data, dict):
                    # Try common keys for model lists
                    available_models = (
                        models_result.data.get("models")
                        or models_result.data.get("items")
                        or models_result.data.get("raw_output", "").split("\n")
                    )
                    if isinstance(available_models, str):
                        available_models = [
                            m.strip() for m in available_models.split("\n") if "/" in m
                        ]

        return OpenCodeStatusResponse(
            status="available",
            version=version,
            cli_path=cli_path,
            available_models=available_models,
        )


# Global executor instance
opencode_executor = OpenCodeExecutor()
