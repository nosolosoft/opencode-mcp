# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🤖 MCP Server Integrations

### Active MCP Servers

**Droid MCP Server** - Terminal Operations & AI Integration
- **Location**: `~/IA/droid_mcp/`
- **Tool**: `mcp__droid-cli__execute_droid_command`
- **Models**: GLM-4.7 (default via Pro subscription)
- **Configuration**: Configured in `~/.claude.json`
- **Capabilities**: Terminal operations, bash automation, migrations, enterprise tooling, reasoning
- **Benchmark**: 58.8% Terminal-Bench score
- **Performance**: 31x faster for enterprise migrations

**Memory MCP** - Knowledge Graph & Persistence
- **Tools**: `mcp__memory__*` (create_entities, create_relations, add_observations, search_nodes, etc.)
- **Purpose**: Persistent knowledge management across sessions

**Codex MCP (DEPRECATED)** - Code Execution & Generation
- **Tools**: `mcp__codex__codex`, `mcp__codex__codex-reply`
- **Purpose**: Autonomous code generation and execution workflows

**Gemini MCP (DEPRECATED)** - Analysis & Documentation
- **Tools**: `mcp__gemini-mcp__gemini_pro`, `mcp__gemini-mcp__gemini_flash`, `mcp__gemini-mcp__gemini_analyze`
- **Purpose**: Large context analysis, comprehensive documentation

**CCR MCP Server** - Command Execution (Experimental/Legacy)
- **Location**: `~/claude/ccr-mcp/`
- **Tools**: `mcp__ccr__execute`, `mcp__ccr__create_file`, `mcp__ccr__run_task`
- **Status**: May have connectivity issues; prefer standard tools

### CLI Alternatives (Skill Delegacion)

Además de los MCP servers, se puede usar CLI directo via skill `delegacion` para ejecución en **background**:

| CLI | Comando | Default Model | Cuándo Usar |
|-----|---------|---------------|-------------|
| OpenCode | `opencode run -m MODEL "PROMPT"` | glm-4.7 | Background tasks, paralelo |
| Gemini | `gemini --model MODEL --yolo "PROMPT"` | google/gemini-3.1-pro-preview | Análisis largo, fire-and-forget |
| Codex | `codex exec -m MODEL --dangerously-bypass-approvals-and-sandbox "PROMPT"` | gpt-5.4 | Implementación larga |
| Claude | `claude -p --model MODEL --dangerously-skip-permissions "PROMPT"` | opus | Decisiones delegadas |

**Triggers para CLI**: "delega a", "pásale a", "encárgale a", "background:", "CLI:", "nueva terminal:"

### MCP vs CLI: Decision Guide

```
MCP (inline):  Usuario necesita el resultado para continuar trabajando
CLI (background): Usuario puede seguir con otra cosa mientras se ejecuta
```

| Escenario | MCP | CLI |
|-----------|-----|-----|
| Resultado necesario para siguiente paso | SI | - |
| Usuario puede continuar con otra tarea | - | SI |
| Ejecución paralela requerida | - | SI |
| Fire-and-forget explícito | - | SI |
| Trigger "delega a", "pásale a" | - | SI |
| Contexto compartido crítico | SI | - |

**Nota**: Los CLIs se ejecutan via `Bash(command="...", run_in_background=true)`. Monitorear con `/tasks`.

## 🔄 Background Task Management

For long-running operations, use `run_in_background: true` parameter:

```javascript
{
  "tool": "Bash",
  "command": "python long-running-task.py",
  "run_in_background": true
}
```

### Managing Background Tasks
```bash
/bashes                                         # View all background tasks
# Check bash_N output via prompt
# Kill bash_N via prompt
```

## Project Overview

This is a development project for creating an MCP server for OpenCode, focused on two AI/automation technologies:

1. **OpenCode** - Open-source AI coding agent for the terminal (sst/opencode). Multi-model support (Claude, OpenAI, Google, local models), LSP integration, and parallel sessions
2. **MCP (Model Context Protocol) Build** - Protocol for building servers that provide resources, tools, and prompts to LLMs

## Project Structure

```
opencode-mcp/
├── docs/
│   └── opencode_documentation.md   # OpenCode CLI documentation (to create)
├── prompts/
│   └── prompts.md                  # Workflow prompts and templates
├── src/                            # MCP server source (to create)
└── CLAUDE.md                       # This file
```

## Key Technologies and Concepts

### OpenCode (sst/opencode)
- Open-source AI coding agent for the terminal (30k+ GitHub stars)
- Multi-model support: Claude, OpenAI, Google, and local models
- Built-in LSP (Language Server Protocol) for code intelligence
- Dual agent system: "build" (full access) and "plan" (read-only analysis)
- CLI commands: `run`, `serve`, `acp`, `models`
- JSON output format (`--format json`) for programmatic integration
- Session continuation and parallel workflows

### MCP (Model Context Protocol)
- **Resources**: File-like data for clients to read
- **Tools**: Functions callable by LLMs (with approval)
- **Prompts**: Pre-written templates for specific tasks

## Development Requirements

### MCP Server Development
- **Python**: 3.10+ with MCP SDK 1.2.0+
- **Node.js**: 16+ with TypeScript
- **Java**: 17+ with Spring Boot 3.3.x+
- **Kotlin**: Java 17+
- **C#**: .NET 8+

### Critical MCP Rules
- Never write to stdout in STDIO-based servers (use stderr/file logging)
- Use absolute paths in configuration
- Tool names must follow specified format
- Avoid stdout corruption in STDIO transport

## Integration Testing (MCP)
To verify Claude Desktop connection:
1. Check for "Search and tools" icon
2. Confirm tools appear in MCP slider
3. Test with sample queries
4. Review logs in `~/Library/Logs/Claude/mcp*.log`

## Documentation Sources
- OpenCode: https://opencode.ai/docs/
- OpenCode GitHub: https://github.com/sst/opencode
- MCP Build: https://modelcontextprotocol.io/docs/develop/build-server

## Project Status
This project is in initial development phase for creating an MCP server that wraps OpenCode CLI.

**Completed:**
- CLAUDE.md configuration

**Pending:**
- MCP server implementation (`execute_opencode_command` tool)
- OpenCode documentation in `docs/`
- Integration testing with Claude Desktop