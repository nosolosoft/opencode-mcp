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
            auto_start_server=os.environ.get("OPENCODE_SERVE_AUTO_START", "true").lower() == "true",
        )
    return _serve_handler


# =============================================================================
# Tool Definitions - Simplified for core functionality
# =============================================================================
TOOLS = [
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
                "model": {
                    "type": "string",
                    "description": "Model in provider/model format, e.g., 'anthropic/claude-sonnet-4-20250514' (optional)",
                },
                "timeout": {
                    "type": "number",
                    "default": 300,
                    "description": "Timeout in seconds (default: 300)",
                },
            },
            "required": ["message"],
        },
    ),
    Tool(
        name="opencode_status",
        description="Get status of the OpenCode serve instance. "
        "Returns server health, connection info, and session statistics.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="opencode_abort",
        description="Abort a running session. Use when a prompt is taking too long or needs to be cancelled.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID to abort",
                },
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="opencode_list_models",
        description="List available LLM models/providers from OpenCode.",
        inputSchema={
            "type": "object",
            "properties": {},
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
]


@server.list_tools()
async def list_tools() -> List[Tool]:
    """Return list of available tools."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """
    Handle tool calls.

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
        serve_handler = await get_or_create_serve_handler()

        if name == "opencode_prompt":
            result = await serve_handler.prompt(
                message=arguments["message"],
                directory=arguments.get("directory"),
                session_id=arguments.get("session_id"),
                model=arguments.get("model"),
                timeout=arguments.get("timeout", 300),
            )

        elif name == "opencode_status":
            result = await serve_handler.get_serve_status()

        elif name == "opencode_abort":
            result = await serve_handler.abort_session(
                session_id=arguments["session_id"],
            )

        elif name == "opencode_list_models":
            result = await serve_handler.get_providers()

        elif name == "opencode_list_sessions":
            result = await serve_handler.list_sessions()

        else:
            raise ValueError(f"Unknown tool: {name}")

        # Format result as JSON
        result_json = result.model_dump_json(indent=2)
        return [TextContent(type="text", text=result_json)]

    except ValueError as e:
        # Validation errors (empty response, invalid model, etc.)
        logger.error(f"Validation error in tool {name}: {str(e)}")
        error_result = OpenCodeResult(
            success=False,
            error=f"Validation error: {str(e)}",
            execution_time=time.time() - start_time,
            exit_code=1,
        )
        return [TextContent(type="text", text=error_result.model_dump_json(indent=2))]

    except Exception as e:
        # Other unexpected errors
        logger.error(f"Error executing tool {name}: {str(e)}", exc_info=True)
        error_result = OpenCodeResult(
            success=False,
            error=f"Error: {str(e)}",
            execution_time=time.time() - start_time,
            exit_code=1,
        )
        return [TextContent(type="text", text=error_result.model_dump_json(indent=2))]


async def main():
    """Main entry point for the MCP server."""
    logger.info(f"Starting OpenCode MCP Server v{settings.mcp_server_version}")
    logger.info(f"Default timeout: {settings.default_timeout}s")

    try:
        # Run the MCP server with stdio transport
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    finally:
        # Cleanup serve handler if it was initialized
        global _serve_handler
        if _serve_handler is not None:
            logger.info("Shutting down serve handler...")
            await _serve_handler.shutdown()
            _serve_handler = None


if __name__ == "__main__":
    asyncio.run(main())
