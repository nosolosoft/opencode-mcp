#!/bin/bash
set -e

echo "🔍 Checking MCP Health..."

# Check venv exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found"
    exit 1
fi

# Check MCP module
.venv/bin/python -c "import mcp" 2>/dev/null && echo "✅ MCP module: OK" || echo "❌ MCP module: FAIL"

# Check server import
.venv/bin/python -c "from src.services.fast_mcp.opencode_server import main" 2>/dev/null && echo "✅ Server import: OK" || echo "❌ Server import: FAIL"

# Check server startup
timeout 2 .venv/bin/python -m src.services.fast_mcp.opencode_server 2>&1 | grep -q "Starting OpenCode MCP Server" && echo "✅ Server startup: OK" || echo "❌ Server startup: FAIL"

echo "✅ MCP Health Check Complete"
