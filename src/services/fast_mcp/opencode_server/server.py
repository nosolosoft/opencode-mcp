"""
OpenCode MCP Server
Main server implementation with tool definitions.
"""

import asyncio
import logging
import sys
from typing import Any, Dict, List

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .settings import settings
from .models import OpenCodeResult
from .opencode_executor import opencode_executor
from .handlers import ExecutionHandler, SessionHandler, DiscoveryHandler

# Configure logging to stderr (never stdout for MCP)
logging.basicConfig(
    level=getattr(logging, settings.server_log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# Initialize server and handlers
server = Server(settings.mcp_server_name)
execution_handler = ExecutionHandler(opencode_executor)
session_handler = SessionHandler(opencode_executor)
discovery_handler = DiscoveryHandler(opencode_executor)


# Tool Definitions
TOOLS = [
    Tool(
        name="execute_opencode_command",
        description="Execute any OpenCode CLI command with full flexibility. "
        "This is the main tool for interacting with OpenCode.",
        inputSchema={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The prompt or task description for OpenCode to execute",
                },
                "model": {
                    "type": "string",
                    "description": "Model to use in provider/model format (e.g., 'openai/gpt-4')",
                },
                "agent": {
                    "type": "string",
                    "description": "Agent to use for execution",
                },
                "session": {
                    "type": "string",
                    "description": "Session ID to continue from",
                },
                "continue_session": {
                    "type": "boolean",
                    "default": False,
                    "description": "Whether to continue the last session",
                },
                "timeout": {
                    "type": "integer",
                    "minimum": 10,
                    "maximum": 600,
                    "default": 300,
                    "description": "Timeout in seconds (default: 300)",
                },
            },
            "required": ["prompt"],
        },
    ),
    Tool(
        name="opencode_run",
        description="Run OpenCode with a simple prompt message. "
        "Best for quick, one-off tasks.",
        inputSchema={
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Message/prompt to send to OpenCode",
                },
                "model": {
                    "type": "string",
                    "description": "Model to use in provider/model format",
                },
                "agent": {
                    "type": "string",
                    "description": "Agent to use for execution",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files to attach to the message",
                },
                "timeout": {
                    "type": "integer",
                    "default": 300,
                    "description": "Timeout in seconds",
                },
            },
            "required": ["message"],
        },
    ),
    Tool(
        name="opencode_continue_session",
        description="Continue an existing OpenCode session. "
        "Use this to resume work from a previous session.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID to continue",
                },
                "message": {
                    "type": "string",
                    "description": "Optional follow-up message",
                },
                "timeout": {
                    "type": "integer",
                    "default": 300,
                    "description": "Timeout in seconds",
                },
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="opencode_list_models",
        description="List available models in OpenCode. "
        "Optionally filter by provider.",
        inputSchema={
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "description": "Filter by provider (optional)",
                },
            },
        },
    ),
    Tool(
        name="opencode_export_session",
        description="Export an OpenCode session as JSON. "
        "Use this to retrieve artifacts and history from a session.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID to export",
                },
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="opencode_get_status",
        description="Check OpenCode CLI availability and status. "
        "Returns version, available models, and CLI path.",
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

    try:
        result: OpenCodeResult

        if name == "execute_opencode_command":
            result = await execution_handler.execute_generic(
                prompt=arguments["prompt"],
                model=arguments.get("model"),
                agent=arguments.get("agent"),
                session=arguments.get("session"),
                continue_session=arguments.get("continue_session", False),
                timeout=arguments.get("timeout"),
            )

        elif name == "opencode_run":
            result = await execution_handler.run(
                message=arguments["message"],
                model=arguments.get("model"),
                agent=arguments.get("agent"),
                files=arguments.get("files"),
                timeout=arguments.get("timeout"),
            )

        elif name == "opencode_continue_session":
            result = await execution_handler.continue_session(
                session_id=arguments["session_id"],
                message=arguments.get("message"),
                timeout=arguments.get("timeout"),
            )

        elif name == "opencode_list_models":
            result = await discovery_handler.list_models(
                provider=arguments.get("provider")
            )

        elif name == "opencode_export_session":
            result = await session_handler.export_session(
                session_id=arguments["session_id"]
            )

        elif name == "opencode_get_status":
            status = await discovery_handler.get_status()
            # Convert status to JSON string
            result_json = status.model_dump_json(indent=2)
            return [TextContent(type="text", text=result_json)]

        else:
            raise ValueError(f"Unknown tool: {name}")

        # Format result as JSON
        result_json = result.model_dump_json(indent=2)
        return [TextContent(type="text", text=result_json)]

    except Exception as e:
        logger.error(f"Error executing tool {name}: {str(e)}")
        error_result = OpenCodeResult(
            success=False,
            error=f"Error executing tool {name}: {str(e)}",
            execution_time=0.0,
        )
        return [TextContent(type="text", text=error_result.model_dump_json(indent=2))]


async def main():
    """Main entry point for the MCP server."""
    logger.info(f"Starting OpenCode MCP Server v{settings.mcp_server_version}")
    logger.info(f"OpenCode command: {settings.opencode_command}")
    logger.info(f"Default timeout: {settings.default_timeout}s")

    # Check if OpenCode CLI is available
    status = await discovery_handler.get_status()
    if status.status != "available":
        logger.error(f"OpenCode CLI not available: {status.error}")
        logger.error("Please ensure OpenCode is installed: npm i -g opencode-ai")
        sys.exit(1)

    logger.info(f"OpenCode CLI is available. Version: {status.version}")
    if status.available_models:
        logger.info(f"Available models: {len(status.available_models)}")

    # Run the MCP server with stdio transport
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
