"""MCP adapter exposing persistent OpenCode jobs."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .job_manager import JobManager
from .job_models import JobStartRequest
from .job_store import JobStore
from .opencode_executor import OpenCodeExecutor
from .serve_process import ServeProcess
from .serve_client.client import OpenCodeServeClient
from .settings import settings

logging.basicConfig(
    level=getattr(logging, settings.server_log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)
server = Server(settings.mcp_server_name)


def _manager() -> JobManager:
    if not hasattr(_manager, "instance"):
        process = ServeProcess(
            settings.opencode_command,
            settings.opencode_serve_host,
            settings.opencode_serve_port,
        )

        def client_factory(directory: str) -> OpenCodeServeClient:
            return OpenCodeServeClient(
                host=settings.opencode_serve_host,
                port=settings.opencode_serve_port,
                directory=directory,
                auto_approve_permissions=False,
                timeout=30.0,
            )

        _manager.instance = JobManager(JobStore(settings.job_db), process, client_factory)
    return _manager.instance


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        result["required"] = required
    return result


def build_tools() -> list[Tool]:
    """Return the stable public MCP tool catalog."""
    return [
        Tool(
            name="opencode_job_start",
            description="Start a persistent OpenCode job and return its job_id immediately.",
            inputSchema=_schema(
                {
                    "message": {"type": "string", "minLength": 1},
                    "directory": {"type": "string", "description": "Absolute project directory"},
                    "agent": {"type": "string", "description": "Exact agent name returned by opencode_list_agents"},
                    "model": {"type": "string", "description": "Exact provider/model ID returned by opencode_list_models; omit to use OpenCode's default"},
                    "variant": {"type": "string", "description": "Optional variant sent inside the selected model"},
                    "session_id": {"type": "string"},
                    "orchestration": {"type": "string", "enum": ["direct", "ulw"], "default": "direct"},
                    "max_runtime_seconds": {"type": "integer", "minimum": 1},
                    "max_output_tokens": {"type": "integer", "minimum": 1, "default": 25000},
                },
                ["message", "directory"],
            ),
        ),
        Tool(
            name="opencode_job_status",
            description="Inspect job lifecycle, health, activity timestamps, and pending interaction.",
            inputSchema=_schema({"job_id": {"type": "string"}}, ["job_id"]),
        ),
        Tool(
            name="opencode_job_result",
            description="Read bounded output, reasoning, tool calls, and final error for a job.",
            inputSchema=_schema(
                {"job_id": {"type": "string"}, "offset": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1}},
                ["job_id"],
            ),
        ),
        Tool(
            name="opencode_job_respond",
            description="Resolve a pending permission or question for a job.",
            inputSchema=_schema(
                {
                    "job_id": {"type": "string"},
                    "interaction_id": {"type": "string"},
                    "decision": {"type": "string", "enum": ["once", "always", "reject"]},
                    "answers": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
                },
                ["job_id", "interaction_id"],
            ),
        ),
        Tool(
            name="opencode_job_cancel",
            description="Abort the OpenCode session and cancel a running job.",
            inputSchema=_schema({"job_id": {"type": "string"}}, ["job_id"]),
        ),
        Tool(
            name="opencode_job_list",
            description="List recent persistent OpenCode jobs.",
            inputSchema=_schema({"limit": {"type": "integer", "minimum": 1, "maximum": 500}}),
        ),
        Tool(
            name="opencode_list_agents",
            description="List agents available to OpenCode in a project directory.",
            inputSchema=_schema({"directory": {"type": "string"}}, ["directory"]),
        ),
        Tool(
            name="opencode_list_models",
            description="List exact provider/model IDs available to the OpenCode CLI. Use this before selecting a model.",
            inputSchema=_schema({"provider": {"type": "string"}}),
        ),
        Tool(
            name="opencode_list_sessions",
            description="List OpenCode sessions using the CLI.",
            inputSchema=_schema({}),
        ),
        Tool(
            name="opencode_health_check",
            description="Check the MCP job database, delegated server process, CLI, and active jobs.",
            inputSchema=_schema({}),
        ),
    ]


@server.list_tools()
async def list_tools() -> list[Tool]:
    """Return the public catalog."""
    return build_tools()


def _json_content(value: Any) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(value, indent=2, default=str))]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:  # noqa: ANN401
    """Dispatch a validated MCP call to the job manager or CLI discovery."""
    manager = _manager()
    try:
        if name == "opencode_job_start":
            record = await manager.start(JobStartRequest.model_validate(arguments))
            return _json_content(record.model_dump(mode="json"))
        if name == "opencode_job_status":
            return _json_content((await manager.status(arguments["job_id"])).model_dump(mode="json"))
        if name == "opencode_job_result":
            result = await manager.result(arguments["job_id"], arguments.get("offset", 0), arguments.get("limit", 20_000))
            return _json_content(result.model_dump(mode="json"))
        if name == "opencode_job_respond":
            record = await manager.respond(
                arguments["job_id"],
                arguments["interaction_id"],
                arguments.get("decision"),
                arguments.get("answers"),
            )
            return _json_content(record.model_dump(mode="json"))
        if name == "opencode_job_cancel":
            record = await manager.cancel(arguments["job_id"])
            return _json_content(record.model_dump(mode="json"))
        if name == "opencode_job_list":
            jobs = await manager.list(arguments.get("limit", 50))
            return _json_content([job.model_dump(mode="json") for job in jobs])
        if name == "opencode_list_agents":
            return _json_content(await manager.list_agents(arguments["directory"]))
        if name == "opencode_list_models":
            result = await OpenCodeExecutor().list_models(provider=arguments.get("provider"))
            return _json_content(result.model_dump(mode="json"))
        if name == "opencode_list_sessions":
            result = await OpenCodeExecutor().list_sessions()
            return _json_content(result.model_dump(mode="json"))
        if name == "opencode_health_check":
            cli = await OpenCodeExecutor().check_status()
            return _json_content(
                {
                    "manager": manager.health(),
                    "cli": cli.model_dump(mode="json"),
                    "models_available": len(cli.available_models or []),
                }
            )
        raise ValueError(f"Unknown tool: {name}")
    except (KeyError, ValueError, OSError) as error:
        logger.error("MCP tool failed", extra={"tool": name, "error": str(error)})
        return _json_content({"success": False, "error": str(error), "tool": name})


async def main() -> None:
    """Run the MCP server over stdio and recover persisted monitors."""
    await _manager().recover()
    try:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await _manager().shutdown()


if __name__ == "__main__":
    asyncio.run(main())
