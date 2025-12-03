# OpenCode MCP Server

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![MCP 1.2.0+](https://img.shields.io/badge/MCP-1.2.0+-green.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An MCP (Model Context Protocol) server that provides seamless integration with [OpenCode](https://github.com/sst/opencode), the open-source AI coding agent for the terminal.

## Features

- **Execute OpenCode Commands**: Run any OpenCode CLI command programmatically
- **Session Management**: Create, continue, and export coding sessions
- **Model Discovery**: List available AI models from all configured providers
- **Async Execution**: Non-blocking command execution with timeout handling
- **JSON Lines Parsing**: Robust parsing of OpenCode's streaming output format

## Tools Available

| Tool | Description |
|------|-------------|
| `execute_opencode_command` | Execute any OpenCode CLI command with full flexibility |
| `opencode_run` | Run OpenCode with a simple prompt message |
| `opencode_continue_session` | Continue an existing OpenCode session |
| `opencode_list_models` | List available models, optionally filtered by provider |
| `opencode_export_session` | Export session data as JSON |
| `opencode_get_status` | Check OpenCode CLI availability and status |

## Installation

### Prerequisites

- Python 3.10+
- [OpenCode CLI](https://opencode.ai/docs/cli/) installed and configured
- MCP-compatible client (Claude Desktop, etc.)

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure MCP Client

Add to your MCP client configuration (e.g., `~/.claude.json` or Claude Desktop settings):

```json
{
  "mcpServers": {
    "opencode": {
      "command": "python",
      "args": ["-m", "src.services.fast_mcp.opencode_server"],
      "cwd": "/path/to/opencode-mcp"
    }
  }
}
```

## Usage

### Basic Usage

Once configured, the MCP tools are available through your MCP client:

```
# Run a coding task
opencode_run(message="Create a Python function that calculates fibonacci numbers")

# List available models
opencode_list_models(provider="anthropic")

# Continue a previous session
opencode_continue_session(session_id="abc123", message="Now add unit tests")

# Check status
opencode_get_status()
```

### Tool Parameters

#### `execute_opencode_command`

```python
{
    "prompt": str,           # Required: The prompt/task for OpenCode
    "model": str,            # Optional: Model in provider/model format (e.g., "anthropic/claude-sonnet-4-20250514")
    "agent": str,            # Optional: Agent to use (e.g., "build", "plan")
    "session": str,          # Optional: Session ID to continue
    "continue_session": bool, # Optional: Whether to continue last session
    "timeout": int           # Optional: Timeout in seconds (default: 300, max: 600)
}
```

#### `opencode_run`

```python
{
    "message": str,     # Required: Message/prompt to send
    "model": str,       # Optional: Model to use
    "agent": str,       # Optional: Agent to use
    "files": [str],     # Optional: Files to attach
    "timeout": int      # Optional: Timeout in seconds
}
```

#### `opencode_continue_session`

```python
{
    "session_id": str,  # Required: Session ID to continue
    "message": str,     # Optional: Follow-up message
    "timeout": int      # Optional: Timeout in seconds
}
```

## Configuration

Environment variables (prefix: `OPENCODE_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENCODE_COMMAND` | `opencode` | Path to OpenCode CLI |
| `OPENCODE_DEFAULT_MODEL` | None | Default model to use |
| `OPENCODE_DEFAULT_AGENT` | None | Default agent to use |
| `OPENCODE_DEFAULT_TIMEOUT` | `300` | Default timeout (seconds) |
| `OPENCODE_MAX_TIMEOUT` | `600` | Maximum timeout (seconds) |
| `OPENCODE_SERVER_LOG_LEVEL` | `INFO` | Logging level |

## Architecture

```
src/services/fast_mcp/opencode_server/
├── __init__.py
├── __main__.py          # Entry point
├── server.py            # MCP server & tool definitions
├── opencode_executor.py # CLI execution wrapper
├── models.py            # Pydantic models
├── settings.py          # Configuration
└── handlers/
    ├── __init__.py
    ├── execution.py     # Run/continue operations
    ├── session.py       # Session management
    └── discovery.py     # Model/status discovery
```

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Code Formatting

```bash
black src/
ruff check src/
```

## Roadmap

Planned features for v2.0:

- [ ] `opencode_import_session` - Import sessions from JSON/URL
- [ ] `opencode_list_sessions` - List all sessions with filtering
- [ ] `opencode_get_stats` - Usage statistics and cost tracking
- [ ] `opencode_list_agents` - List available agents
- [ ] `opencode_github_run` - GitHub Actions integration (async)
- [ ] `opencode_pr_checkout` - PR workflow support

## Contributing

Contributions are welcome! Please read the contributing guidelines before submitting PRs.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Related Projects

- [OpenCode](https://github.com/sst/opencode) - The AI coding agent this server integrates with
- [Model Context Protocol](https://modelcontextprotocol.io/) - The protocol specification
- [MCP SDK](https://github.com/modelcontextprotocol/python-sdk) - Python SDK for MCP

## Acknowledgments

- [SST Team](https://sst.dev/) for creating OpenCode
- [Anthropic](https://anthropic.com/) for the MCP specification
