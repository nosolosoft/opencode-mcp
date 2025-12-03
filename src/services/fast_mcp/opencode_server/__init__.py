"""
OpenCode MCP Server
MCP server that wraps OpenCode CLI for use with Claude Desktop and other LLM clients.
"""

from .server import server, main
from .settings import settings
from .models import OpenCodeResult, OpenCodeStatusResponse
from .opencode_executor import opencode_executor, OpenCodeExecutor

__version__ = "1.0.0"
__all__ = [
    "server",
    "main",
    "settings",
    "OpenCodeResult",
    "OpenCodeStatusResponse",
    "opencode_executor",
    "OpenCodeExecutor",
]
