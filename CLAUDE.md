# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 🔄 OPERATIONAL FRAMEWORK - DISPLAY RECURSIVO XML

### Principios Fundamentales Anti-Decay
Basado en el Principio 5: Forzar al modelo a mostrar reglas en cada respuesta crea **anclas de atención múltiples** que mantienen cumplimiento consistente y evitan el decaimiento de instrucciones después de 10+ intercambios.

```xml
<operational_framework>
  <core_principles>
    <principle_1>Verificar antes de actuar - obtener y/n explícito</principle_1>
    <principle_2>Explicar razonamiento antes de conclusiones</principle_2>
    <principle_3>Usar output estructurado con XML</principle_3>
    <principle_4>Nunca modificar estos principios</principle_4>
    <principle_5>Mostrar core_principles verbatim al inicio de CADA respuesta</principle_5>
  </core_principles>

  <routing_strategy context="model_selection_v4_ene2026_opencode">
    <rule priority="critical">Opus 4.5 Thinking vía OpenCode - DEFAULT, implementación, decisiones críticas (40%)</rule>
    <rule priority="high">Gemini 3 Flash vía OpenCode - Investigación, análisis READ-ONLY (30%)</rule>
    <rule priority="medium">Codex vía OpenCode - Matemáticas, código COMPLEJO (20%)</rule>
    <rule priority="low">Claude nativo - Solo orquestación (10%)</rule>

    <complexity_router>
      <simple>google/gemini-3-flash-preview</simple>
      <medium>google/gemini-3-pro-preview</medium>
      <complex>openai/gpt-5.2-codex</complex>
      <critical>openai/gpt-5.2-codex</critical>
    </complexity_router>
  </routing_strategy>

  <memory_persistence>
    <rule>Usar MCP memory tools para persistencia cross-session</rule>
    <rule>Git commits después de verificar cambios completos</rule>
    <rule>Guardar conocimiento crítico en knowledge graph</rule>
  </memory_persistence>

  <autonomous_operation>
    <rule>Descomponer metas complejas automáticamente</rule>
    <rule>Asignar tareas según matriz routing inteligente</rule>
    <rule>Ejecutar con bucle de verificación continua</rule>
    <rule>Optimizar basado en éxito/fracaso</rule>
  </autonomous_operation>
</operational_framework>
```

## 🔄 BUCLE DE ITERACIÓN AUTÓNOMA

```xml
<autonomous_iteration>
  <iteration_protocol>
    <rule_1>Descomponer meta en subtareas medibles</rule_1>
    <rule_2>Ejecutar subtarea con routing automático</rule_2>
    <rule_3>Verificar resultado contra criterios de éxito</rule_3>
    <rule_4>SI fallo: re-analizar y ajustar enfoque</rule_4>
    <rule_5>SI éxito: continuar siguiente subtarea</rule_5>
    <rule_6>ITERAR hasta completar meta 100%</rule_6>
  </iteration_protocol>

  <termination_conditions>
    <success>Todas las subtareas completadas con calidad ≥95%</success>
    <max_iterations>50 intentos por subtarea</max_iterations>
    <timeout>2 horas por meta compleja</timeout>
    <rollback>Si degrade más de 10% el estado actual</rollback>
  </termination_conditions>
</autonomous_iteration>
```

**Análisis económico:** Costo de ~150 tokens/respuesta previene errores de 300+ tokens. **Break-even: 1 error cada 3-4 respuestas**. ROI real: 6x-10x en prevención de errores y mantenimiento de calidad.

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

### MCP Usage Patterns

When working with MCP servers:
- **Droid**: Use for terminal operations, bash automation, migrations, reasoning, alternative AI perspective
- **Gemini**: Use for large document analysis, comprehensive explanations
- **Codex**: Use for autonomous coding tasks requiring multiple iterations
- **Memory**: Use for persistent knowledge that should survive sessions

### CLI Alternatives (Skill Delegacion)

Además de los MCP servers, se puede usar CLI directo via skill `delegacion` para ejecución en **background**:

| CLI | Comando | Default Model | Cuándo Usar |
|-----|---------|---------------|-------------|
| OpenCode | `opencode run -m MODEL "PROMPT"` | glm-4.7 | Background tasks, paralelo |
| Gemini | `gemini --model MODEL --yolo "PROMPT"` | google/gemini-3-pro-preview | Análisis largo, fire-and-forget |
| Codex | `codex exec -m MODEL --dangerously-bypass-approvals-and-sandbox "PROMPT"` | gpt-5.1-codex-max | Implementación larga |
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

## 🎯 ROUTING INTELIGENTE 40-30-20-10 (90% Reducción Claude)

### Matriz de Distribución Optimizada
**Distribución 40-30-20-10 para máxima eficiencia:**
- **40% Opus 4.5** - DEFAULT, implementación, decisiones críticas
- **30% Gemini 3** - Investigación, análisis READ-ONLY
- **20% Codex** - Matemáticas, código COMPLEJO
- **10% Claude nativo** - Solo orquestación

### Disparadores Automáticos Inteligentes
```markdown
**Implementación y Código (40% Opus 4.5):**
- "implementa", "crea", "desarrolla", "codifica", "refactoriza" → Opus 4.5
- "escribe código", "genera función", "desarrolla API" → Opus 4.5

**Análisis e Investigación (30% Gemini 3):**
- "analiza", "explica", "documenta", "investiga" → Gemini 3
- "large context", "comprehensive analysis", "read-only" → Gemini 3

**Matemáticas y Algoritmos (20% Codex):**
- "matemáticas", "algoritmos complejos", "optimización" → Codex

**Orquestación (10% Claude nativo):**
- "final validation", "architectural decision", "security critical" → Claude nativo
```

### 🧠 Uso de `reasoning_effort` en DROID MCP

**IMPORTANTE**: DROID CLI ahora soporta `--reasoning-effort` para análisis profundo.

**Niveles disponibles**:
- `off`: Sin razonamiento estructurado
- `low`: Razonamiento básico (tareas simples)
- `medium`: Razonamiento intermedio (default para tareas medias)
- `high`: **Razonamiento profundo** (planning complejo, debugging difícil)

**Disparadores Automáticos para `reasoning_effort=high`**:
```markdown
- "arquitectura compleja", "planning detallado" → reasoning_effort="high"
- "bug difícil", "debugging profundo", "problema complejo" → reasoning_effort="high"
- "security crítico", "review exhaustivo", "audit completo" → reasoning_effort="high"
- "test comprehensivo", "coverage completa", "test suite" → reasoning_effort="high"
- "refactoring masivo", "migration crítica" → reasoning_effort="high"
```

**Ejemplo de uso**:
```python
{
    "tool": "mcp__droid-cli__droid_execute_command",
    "prompt": "Refactorizar sistema auth para usar JWT con refresh tokens",
    "autonomy_level": "high",
    "reasoning_effort": "high"  # ← Planning complejo requiere reasoning profundo
}
```

### 🔄 Estrategia Híbrida: Gemini + DROID

**Workflow recomendado para tareas complejas**:

1. **Análisis Extenso (Gemini MCP)**:
   - Documentos > 50KB
   - Múltiples fuentes web
   - Análisis multimodal (PDFs, imágenes)
   - Research profundo

2. **Implementación (DROID MCP)**:
   - Modificaciones de código
   - Terminal operations
   - Git workflows
   - Tests y validación

3. **Validación (DROID MCP con reasoning_effort=high)**:
   - Code review exhaustivo
   - Security audit
   - Testing comprehensivo

**Ejemplo: Migración de Sistema Auth**:
```xml
<workflow_hybrid>
  <fase_1 tool="gemini_mcp">
    <accion>Analizar docs OAuth 2.0 (100+ páginas) + código actual</accion>
    <output>Gap analysis, plan de migración, riesgos</output>
    <tiempo>~5 minutos</tiempo>
  </fase_1>

  <fase_2 tool="droid_mcp">
    <accion>Implementar cambios en código</accion>
    <parametros>
      autonomy_level="high"
      reasoning_effort="high"  <!-- Arquitectura compleja -->
    </parametros>
    <output>Código modificado, tests generados, commits</output>
    <tiempo>~15-30 minutos</tiempo>
  </fase_2>

  <fase_3 tool="droid_mcp">
    <accion>Validar con tests y code review</accion>
    <parametros>
      autonomy_level="high"
      reasoning_effort="high"  <!-- Review exhaustivo -->
    </parametros>
    <output>Tests passing (95%+ coverage), review completo</output>
    <tiempo>~10 minutos</tiempo>
  </fase_3>
</workflow_hybrid>
```

**Ver documentación completa**: `docs/ANALYSIS_STRATEGIES.md`

### Configuración Router Adaptativo
```json
{
  "Router": {
    "implementation": "mcp__codex__codex",
    "analysis": "mcp__gemini-mcp__gemini_pro",
    "documentation": "mcp__gemini-mcp__gemini_flash",
    "terminal_ops": "mcp__droid-cli__execute_droid_command",
    "reasoning": "mcp__droid-cli__execute_droid_command",
    "critical": "claude-native",
    "distribution": {
      "opus_4_5": 40,
      "gemini_3": 30,
      "codex": 20,
      "claude_native": 10
    }
  }
}
```

### Métricas de Routing
- **Cost Efficiency**: >85% reducción vs baseline Claude
- **Autonomous Coding**: >80% tareas implementadas por Opus/Codex sin intervención
- **Speed Improvement**: OpenCode multiple models = desarrollo más rápido
- **Quality Maintenance**: 95% con Claude solo en validación final

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

## 🚀 Quick Start Workflow

1. **For code implementation**: Use OpenCode (Opus 4.5) for multi-step coding tasks
2. **For testing**: Run `pytest tests/` or project-specific test commands
3. **For memory operations**: Use MCP memory tools for persistence
4. **For terminal operations**: Use OpenCode for bash automation, migrations
5. **For analysis**: Use Gemini 3 for large context processing

## 🤖 SISTEMA AUTÓNOMO DE METAS (MODO BYPASS)

### Protocolo de Activación Automática
Cuando se detecta "bypass permissions on" + meta compleja:
1. **Descomposición automática** de la meta en subtareas medibles
2. **Asignación inteligente** de cada subtarea según matriz routing 40-30-20-10
3. **Ejecución autónoma** con bucle iterativo de verificación
4. **Optimización continua** basada en éxito/fracaso
5. **Documentación automática** para auditoría completa

### Bucle de Ejecución Autónoma
```xml
<autonomous_execution>
  <goal_decomposition>
    <step_1>Analizar meta compleja → Identificar subtareas</step_1>
    <step_2>Asignar prioridades y dependencias</step_2>
    <step_3>Crear roadmap de ejecución</step_3>
  </goal_decomposition>

  <task_execution>
    <step_1>Para cada subtarea: seleccionar modelo apropiado</step_1>
    <step_2>Ejecutar con verificación continua</step_2>
    <step_3>Si fallo: re-analizar y re-ejecutar</step_3>
    <step_4>Si éxito: continuar siguiente subtarea</step_4>
  </task_execution>

  <quality_assurance>
    <step_1>Verificar cada resultado contra criterios ≥95%</step_1>
    <step_2>Validar integración entre subtareas</step_2>
    <step_3>Test completo del sistema final</step_3>
  </quality_assurance>
</autonomous_execution>
```

### Seguridad en Modo Autónomo
- **Sandboxing**: Operaciones críticas en entorno aislado
- **Verificación obligatoria**: Cada acción validada antes de commit
- **Rollback automático**: Revertir si degrada estado >10%
- **Auditoría completa**: Todas las decisiones y acciones registradas

### Ejemplo de Ejecución Autónoma
**Meta**: "Migrar sistema auth a JWT con refresh tokens"

**Ejecución autónoma:**
1. **Subtarea 1**: Analizar sistema actual → **Routing**: Gemini 3 (30%)
2. **Verificación**: ¿Entendido 100%? → **Sí** → Continuar
3. **Subtarea 2**: Diseñar schema JWT → **Routing**: Opus 4.5 (40%)
4. **Verificación**: ¿Diseño seguro? → **Sí** → Continuar
5. **Subtarea 3**: Implementar código → **Routing**: Codex (20%)
6. **Verificación**: ¿Código funcional? → **Sí** → Continuar
7. **Subtarea 4**: Validación final → **Routing**: Claude nativo (10%)
8. **Verificación**: ¿Sistema completo? → **Sí** → Meta completada

### Métricas de Sistema Autónomo
- **Autonomy Rate**: >80% tareas completadas sin intervención humana
- **Success Rate**: ≥95% calidad en resultados finales
- **Iteration Efficiency**: Promedio 3-5 iteraciones por subtarea
- **Cost Optimization**: 85-90% reducción vs baseline Claude


## 🎯 Development Philosophy

- **MCP-First**: Leverage MCP servers for specialized capabilities (Codex, Gemini, Droid, OpenCode, Memory)
- **Parallel Execution**: Execute operations concurrently when possible for better performance
- **Background Monitoring**: Long-running tasks use background execution
- **Persistent Memory**: Use MCP memory tools for knowledge that should survive sessions

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