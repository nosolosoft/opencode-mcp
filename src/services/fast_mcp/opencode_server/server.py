"""
OpenCode MCP Server
Simplified server focused on sending prompts to OpenCode.

Uses HTTP serve API for persistent connection to opencode serve instance.
"""

import asyncio
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .settings import settings
from .models import OpenCodeResult
from .handlers import (
    ServeHandler,
    get_serve_handler,
)
from .handlers.execution import ExecutionHandler
from .handlers.model_registry import ModelRegistry, get_model_registry
from .opencode_executor import OpenCodeExecutor

# Configure logging to stderr (never stdout for MCP)
logging.basicConfig(
    level=getattr(logging, settings.server_log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Initialize server
server = Server(settings.mcp_server_name)

# Serve handler (lazy initialized when tools are used)
_serve_handler: Optional[ServeHandler] = None


async def get_or_create_serve_handler() -> ServeHandler:
    """Get or create the serve handler (lazy initialization)."""
    global _serve_handler
    if _serve_handler is None:
        _serve_handler = get_serve_handler(
            host=os.environ.get("OPENCODE_SERVE_HOST", "127.0.0.1"),
            port=int(os.environ.get("OPENCODE_SERVE_PORT", "4096")),
            # Auto-start enabled by default - server is shared across MCP sessions
            auto_start_server=os.environ.get(
                "OPENCODE_SERVE_AUTO_START", "true"
            ).lower()
            == "true",
        )
    return _serve_handler


# =============================================================================
# Tool Definitions - Built dynamically for model enum support
# =============================================================================

def _build_model_description(model_list: Optional[List[str]] = None) -> str:
    """Build the description for the model parameter with examples."""
    base = (
        "Model in provider/model format. Examples: 'anthropic/claude-sonnet-4-20250514', "
        "'google/gemini-3-flash-preview', 'openai/gpt-5.4'. "
        "Short aliases also accepted: 'opus', 'sonnet', 'haiku', 'gemini-flash', 'codex'. "
        "If omitted, uses server default. DO NOT guess model names - use list_models tool first "
        "or omit this parameter entirely."
    )
    return base


def _build_model_property(model_list: Optional[List[str]] = None) -> Dict[str, Any]:
    """Build the model property schema, optionally with enum including aliases."""
    from .handlers.model_registry import DEFAULT_ALIASES

    prop: Dict[str, Any] = {
        "type": "string",
        "description": _build_model_description(model_list),
    }
    if model_list:
        # Include aliases in enum so MCP client doesn't reject them
        aliases = sorted(DEFAULT_ALIASES.keys())
        prop["enum"] = model_list + aliases
    return prop


def build_tools(model_list: Optional[List[str]] = None) -> List[Tool]:
    """
    Build tool definitions, optionally populating model enum dynamically.

    Args:
        model_list: List of valid model IDs to populate the enum
    """
    return [
        Tool(
            name="opencode_prompt",
            description="Send a prompt to OpenCode. This is the main tool for interacting with OpenCode. "
            "Uses persistent HTTP connection for fast response.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The prompt/message to send to OpenCode",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Working directory for the operation (optional)",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Existing session ID to continue conversation (optional)",
                    },
                    "model": _build_model_property(model_list),
                    "agent": {
                        "type": "string",
                        "description": "Agent mode to use. 'build' has full read/write access for implementation tasks. "
                        "'plan' is read-only for analysis, planning, and code review. "
                        "If omitted, uses the server default.",
                        "enum": ["build", "plan"],
                    },
                    "timeout": {
                        "type": "number",
                        "default": 600,
                        "description": "Timeout in seconds (default: 600)",
                    },
                    "max_output_tokens": {
                        "type": "number",
                        "default": 25000,
                        "description": "Maximum number of tokens for the model's response (default: 25000). "
                        "This is a soft limit enforced through enhanced prompt instructions with emphasis, "
                        "consequences, and strategic guidance. The instruction adapts based on token range "
                        "for optimal compliance. Note: This is not a hard API limit.",
                    },
                    "variant": {
                        "type": "string",
                        "description": "Optional model variant for Gemini models to control reasoning level. "
                        "Options: 'minimal', 'low', 'medium' (default), 'high'. "
                        "Use 'high' for complex analysis and deep reasoning, 'low' for simple queries, "
                        "'medium' for standard tasks. If not specified, defaults to 'medium'. "
                        "Only applies to google/gemini-* models.",
                        "enum": ["minimal", "low", "medium", "high"],
                    },
                    "use_ultrawork": {
                        "type": "boolean",
                        "default": True,
                        "description": "Enable oh-my-opencode multi-agent orchestration via 'ulw' keyword injection. "
                        "When enabled (default), prompts are prefixed with 'ulw' to activate Sisyphus orchestration "
                        "for automatic task decomposition and multi-agent execution. Set to false for direct execution "
                        "without orchestration.",
                    },
                },
                "required": ["message"],
            },
        ),
        Tool(
            name="opencode_list_models",
            description="List available LLM models/providers from OpenCode CLI. "
            "Returns all available models in provider/model format.",
            inputSchema={
                "type": "object",
                "properties": {
                    "provider": {
                        "type": "string",
                        "description": "Optional provider to filter by (e.g., 'google', 'openai')",
                    },
                },
            },
        ),
        Tool(
            name="opencode_list_sessions",
            description="List all active sessions. Useful to find session IDs for continuing conversations.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="opencode_health_check",
            description="Check OpenCode server health: CLI availability, serve API status, cached models, and version.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        # =====================================================================
        # Search & File Tools (via opencode serve API)
        # =====================================================================
        Tool(
            name="opencode_search_text",
            description="Search for text patterns across files in the project using ripgrep. "
            "Returns matching lines with file paths and line numbers. "
            "Supports regex patterns. Results are limited to 200 matches.",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to search for (ripgrep syntax)",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Working directory (project root). Optional, uses server default if omitted.",
                    },
                },
                "required": ["pattern"],
            },
        ),
        Tool(
            name="opencode_find_files",
            description="Search for files by name or pattern in the project. "
            "Returns matching file paths. Useful for locating files before reading them.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "File name or pattern to search for (e.g., 'server.py', '*.tsx')",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Working directory (project root). Optional.",
                    },
                    "type": {
                        "type": "string",
                        "description": "Filter by entry type",
                        "enum": ["file", "directory"],
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="opencode_read_file",
            description="Read the content of a file. Returns text content for text files, "
            "or a placeholder message for binary files. Large files are truncated to 100KB.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to the project root (e.g., 'src/main.py')",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Working directory (project root). Optional.",
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="opencode_list_directory",
            description="List files and directories at a given path. "
            "Shows file names, types (file/directory), and whether they are gitignored.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list, relative to project root (default: '.')",
                        "default": ".",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Working directory (project root). Optional.",
                    },
                },
            },
        ),
        Tool(
            name="opencode_file_status",
            description="Get git status of all modified files in the project. "
            "Shows which files are added, modified, or deleted with line counts.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Working directory (project root). Optional.",
                    },
                },
            },
        ),
    ]


# Start with static tools, will be updated dynamically after model cache loads
TOOLS = build_tools()


@server.list_tools()
async def list_tools() -> List[Tool]:
    """Return list of available tools with dynamic model enum."""
    global TOOLS
    try:
        registry = await get_model_registry()
        models = registry.get_cached_models()
        if models:
            TOOLS = build_tools(models)
    except Exception as e:
        logger.debug(f"Could not refresh model enum for tools: {e}")
    return TOOLS


async def _validate_and_resolve_model(model: Optional[str]) -> str:
    """
    Validate and resolve a model parameter.

    Resolution chain: exact match → alias → fuzzy match → default.

    Args:
        model: The model string from tool arguments (may be None)

    Returns:
        A valid model ID string
    """
    if not model:
        return settings.opencode_default_model or ""

    try:
        registry = await get_model_registry()
        is_valid, resolved, method = registry.validate_and_resolve(model)

        if is_valid:
            return resolved  # Exact match
        elif resolved:
            logger.info(f"Model resolved via {method}: '{model}' -> '{resolved}'")
            return resolved
        else:
            logger.warning(
                f"Model '{model}' could not be resolved, falling back to default: "
                f"'{settings.opencode_default_model}'"
            )
            return settings.opencode_default_model or ""
    except Exception as e:
        logger.error(f"Model validation error: {e}, using provided model as-is")
        return model


def _get_timeout_for_operation(name: str, user_timeout: Optional[int] = None) -> int:
    """
    Get the appropriate timeout for an operation.

    Uses per-operation defaults, respects user overrides, and applies
    the buffer for subprocess coordination.
    """
    if name == "opencode_list_models":
        base_timeout = settings.timeout_list_models
    elif name == "opencode_list_sessions":
        base_timeout = settings.timeout_list_sessions
    elif name == "opencode_health_check":
        base_timeout = settings.timeout_health
    elif name in ("opencode_search_text", "opencode_find_files"):
        base_timeout = settings.timeout_search
    elif name in ("opencode_read_file", "opencode_list_directory", "opencode_file_status"):
        base_timeout = settings.timeout_file_ops
    else:
        base_timeout = settings.default_timeout

    # User override takes priority but is capped
    effective = min(user_timeout or base_timeout, settings.max_timeout)

    return effective


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """
    Handle tool calls with model validation and adaptive timeouts.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of TextContent with results
    """
    logger.info(f"Tool called: {name} with arguments: {arguments}")
    start_time = time.time()

    try:
        result: OpenCodeResult

        if name == "opencode_prompt":
            execution_handler = ExecutionHandler(OpenCodeExecutor())

            # Validate and resolve model
            raw_model = arguments.get("model")
            model = await _validate_and_resolve_model(raw_model)

            session_id = arguments.get("session_id")
            directory = arguments.get("directory")
            agent = arguments.get("agent") or settings.opencode_default_agent
            max_output_tokens = arguments.get(
                "max_output_tokens", settings.default_max_output_tokens
            )
            timeout = _get_timeout_for_operation(name, arguments.get("timeout"))

            if session_id:
                result = await execution_handler.continue_session(
                    session_id=session_id,
                    message=arguments.get("message"),
                    timeout=timeout,
                    max_output_tokens=max_output_tokens,
                )
                result.model = "(session continues with original model)"
            else:
                use_ultrawork = arguments.get("use_ultrawork", True)
                result = await execution_handler.run(
                    message=arguments["message"],
                    model=model,
                    agent=agent,
                    timeout=timeout,
                    max_output_tokens=max_output_tokens,
                    variant=arguments.get("variant"),
                    use_ultrawork=use_ultrawork,
                    cwd=directory,
                )
                # Show resolution info if model was corrected
                if raw_model and raw_model != model:
                    result.model = f"{model} (resolved from '{raw_model}')"
                else:
                    result.model = model

        elif name == "opencode_list_models":
            executor = OpenCodeExecutor()
            timeout = _get_timeout_for_operation(name)
            result = await executor.list_models(
                provider=arguments.get("provider"),
                timeout=timeout,
            )

        elif name == "opencode_list_sessions":
            executor = OpenCodeExecutor()
            timeout = _get_timeout_for_operation(name)
            result = await executor.list_sessions(timeout=timeout)

        elif name == "opencode_health_check":
            result = await _execute_health_check()

        # =================================================================
        # Search & File Tools (via serve API)
        # =================================================================

        elif name == "opencode_search_text":
            pattern = arguments.get("pattern", "").strip()
            if not pattern:
                raise ValueError("'pattern' is required and cannot be empty")
            handler = await get_or_create_serve_handler()
            result = await handler.search_text(
                pattern=pattern,
                directory=arguments.get("directory"),
            )

        elif name == "opencode_find_files":
            query = arguments.get("query", "").strip()
            if not query:
                raise ValueError("'query' is required and cannot be empty")
            handler = await get_or_create_serve_handler()
            result = await handler.find_files(
                query=query,
                directory=arguments.get("directory"),
                file_type=arguments.get("type"),
            )

        elif name == "opencode_read_file":
            path = arguments.get("path", "").strip()
            if not path:
                raise ValueError("'path' is required and cannot be empty")
            handler = await get_or_create_serve_handler()
            result = await handler.read_file(
                path=path,
                directory=arguments.get("directory"),
            )

        elif name == "opencode_list_directory":
            handler = await get_or_create_serve_handler()
            result = await handler.list_directory(
                path=arguments.get("path", "."),
                directory=arguments.get("directory"),
            )

        elif name == "opencode_file_status":
            handler = await get_or_create_serve_handler()
            result = await handler.file_status(
                directory=arguments.get("directory"),
            )

        else:
            raise ValueError(f"Unknown tool: {name}")

        # Format result as JSON
        result_json = result.model_dump_json(indent=2)
        return [TextContent(type="text", text=result_json)]

    except ValueError as e:
        logger.error(f"Validation error in tool {name}: {str(e)}")
        error_result = OpenCodeResult(
            success=False,
            error=f"Validation error: {str(e)}",
            execution_time=time.time() - start_time,
            exit_code=1,
            is_error=True,
        )
        return [TextContent(type="text", text=error_result.model_dump_json(indent=2))]

    except Exception as e:
        logger.error(f"Error executing tool {name}: {str(e)}", exc_info=True)
        error_result = OpenCodeResult(
            success=False,
            error=f"Error: {str(e)}",
            execution_time=time.time() - start_time,
            exit_code=1,
            is_error=True,
        )
        return [TextContent(type="text", text=error_result.model_dump_json(indent=2))]


async def _execute_health_check() -> OpenCodeResult:
    """Execute a comprehensive health check."""
    start_time = time.time()
    health_data = {
        "cli_available": False,
        "cli_version": None,
        "serve_api_running": False,
        "models_cached": 0,
        "cached_models": [],
        "default_model": settings.opencode_default_model,
        "server_version": settings.mcp_server_version,
    }

    executor = OpenCodeExecutor()

    # Check CLI availability
    try:
        version = await executor.get_version()
        if version:
            health_data["cli_available"] = True
            health_data["cli_version"] = version
    except Exception as e:
        health_data["cli_error"] = str(e)

    # Check serve API
    try:
        serve_running = await executor._is_serve_running()
        health_data["serve_api_running"] = serve_running
    except Exception:
        pass

    # Check model registry
    try:
        registry = await get_model_registry()
        models = registry.get_cached_models()
        health_data["models_cached"] = len(models)
        health_data["cached_models"] = models
    except Exception as e:
        health_data["model_cache_error"] = str(e)

    all_ok = health_data["cli_available"] and health_data["models_cached"] > 0

    return OpenCodeResult(
        success=all_ok,
        data=health_data,
        execution_time=time.time() - start_time,
        exit_code=0 if all_ok else 1,
    )


async def main():
    """Main entry point for the MCP server."""
    logger.info(f"Starting OpenCode MCP Server v{settings.mcp_server_version}")
    logger.info(f"Default timeout: {settings.default_timeout}s")
    logger.info(f"Default model: {settings.opencode_default_model}")

    # Pre-populate model registry in background (non-blocking)
    async def _warmup_registry():
        try:
            registry = await get_model_registry()
            models = registry.get_cached_models()
            logger.info(f"Model registry warmed up: {len(models)} models")
        except Exception as e:
            logger.warning(f"Model registry warmup failed (will retry on first use): {e}")

    # Start warmup as background task
    warmup_task = asyncio.create_task(_warmup_registry())

    try:
        # Run the MCP server with stdio transport
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        # Cancel warmup if still running
        if not warmup_task.done():
            warmup_task.cancel()

        # Cleanup serve handler if it was initialized
        global _serve_handler
        if _serve_handler is not None:
            logger.info("Shutting down serve handler...")
            await _serve_handler.shutdown()
            _serve_handler = None


if __name__ == "__main__":
    asyncio.run(main())
