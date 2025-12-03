"""
OpenCode MCP Server Entry Point
Run with: python -m src.services.fast_mcp.opencode_server
"""

import asyncio
from .server import main

if __name__ == "__main__":
    asyncio.run(main())
