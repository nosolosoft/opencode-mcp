# Plan de Mejoras: OpenCode MCP Server

## Resumen Ejecutivo

Este documento presenta el plan de investigación, análisis y mejoras para el MCP Server de OpenCode, incluyendo la creación del repositorio Git y la implementación de nuevas funcionalidades.

---

## PARTE 1: Creación del Repositorio Git

### 1.1 Estado Actual
- **Directorio**: `/home/manu/IA/opencode-mcp/`
- **Git Status**: No es un repositorio git (verificado)
- **GitHub CLI**: Autenticado como `nosolosoft`

### 1.2 Acciones Planificadas

```bash
# 1. Inicializar repositorio git
cd /home/manu/IA/opencode-mcp
git init

# 2. Crear .gitignore
cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
.env
.venv
venv/

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Project specific
opencode/  # Submodule de referencia
tests/*.txt  # Test outputs
EOF

# 3. Crear estructura README
# (Se creará README.md con documentación del proyecto)

# 4. Commit inicial
git add .
git commit -m "Initial commit: OpenCode MCP Server v1.0.0

Features:
- 6 herramientas MCP implementadas
- Handlers: execution, session, discovery
- Async subprocess execution con timeout
- JSON Lines parsing robusto
- Pydantic models para validación"

# 5. Crear repositorio en GitHub
gh repo create opencode-mcp --public --description "MCP Server for OpenCode CLI integration" --source=. --push
```

### 1.3 Estructura de Archivos a Commitear

```
opencode-mcp/
├── src/
│   └── services/
│       └── fast_mcp/
│           └── opencode_server/
│               ├── __init__.py
│               ├── __main__.py
│               ├── server.py          # Main MCP server
│               ├── opencode_executor.py
│               ├── models.py          # Pydantic models
│               ├── settings.py        # Configuration
│               └── handlers/
│                   ├── __init__.py
│                   ├── execution.py
│                   ├── session.py
│                   └── discovery.py
├── prompts/
│   └── prompts.md
├── requirements.txt
├── AGENTS.md
├── CLAUDE.md
├── README.md                    # A CREAR
├── LICENSE                      # A CREAR (MIT)
└── .gitignore                   # A CREAR
```

---

## PARTE 2: Análisis del MCP Actual

### 2.1 Herramientas Implementadas (6)

| Herramienta | Comando CLI | Estado |
|-------------|-------------|--------|
| `execute_opencode_command` | `opencode run` | ✅ Completo |
| `opencode_run` | `opencode run [message]` | ✅ Completo |
| `opencode_continue_session` | `opencode run --continue` | ✅ Completo |
| `opencode_list_models` | `opencode models` | ✅ Completo |
| `opencode_export_session` | `opencode export` | ✅ Completo |
| `opencode_get_status` | Internal check | ✅ Completo |

### 2.2 Arquitectura Actual

```
server.py
    ├── TOOLS[] (6 definiciones)
    ├── @server.list_tools()
    └── @server.call_tool() → handlers

handlers/
    ├── ExecutionHandler (run, continue, generic)
    ├── SessionHandler (export, stats)
    └── DiscoveryHandler (models, status)

opencode_executor.py
    └── OpenCodeExecutor
        ├── execute_command() → subprocess
        ├── _parse_output() → JSON Lines
        └── métodos específicos
```

### 2.3 Fortalezas
- ✅ Arquitectura modular con handlers
- ✅ Parsing robusto de JSON Lines
- ✅ Timeout handling con asyncio
- ✅ Modelos Pydantic para validación
- ✅ Configuración via env vars

### 2.4 Debilidades Identificadas
- ❌ `allowed_operations` no se usa (validación faltante)
- ❌ `allowed_file_extensions` no se valida
- ❌ `max_file_size` no se verifica
- ❌ Logging incluye prompts completos (riesgo seguridad)
- ❌ Sin patrón async para operaciones largas
- ❌ Sin streaming support

---

## PARTE 3: Propuesta de Mejoras

### 3.1 Nuevas Herramientas (Prioridad ALTA)

| # | Herramienta | Comando CLI | Complejidad | Valor |
|---|-------------|-------------|-------------|-------|
| 1 | `opencode_import_session` | `import <file/URL>` | Baja | Alto |
| 2 | `opencode_list_sessions` | `session list` | Baja | Alto |
| 3 | `opencode_get_stats` | `stats` | Media | Alto |
| 4 | `opencode_list_agents` | `agent list` | Baja | Alto |
| 5 | `opencode_share_session` | `run --share` | Baja | Medio |

### 3.2 Nuevas Herramientas (Prioridad MEDIA)

| # | Herramienta | Comando CLI | Complejidad | Valor |
|---|-------------|-------------|-------------|-------|
| 6 | `opencode_github_run` | `github run` | Alta | Alto |
| 7 | `opencode_pr_checkout` | `pr <number>` | Media | Alto |
| 8 | `opencode_list_credentials` | `auth list` | Baja | Medio |
| 9 | `opencode_start_server` | `serve` | Baja | Medio |

### 3.3 Nuevas Herramientas (Prioridad BAJA)

| # | Herramienta | Comando CLI | Complejidad | Valor |
|---|-------------|-------------|-------------|-------|
| 10 | `opencode_create_agent` | `agent create` | Alta | Bajo |
| 11 | `opencode_upgrade` | `upgrade` | Media | Bajo |

### 3.4 Mejoras de Arquitectura

#### 3.4.1 Nuevos Handlers Necesarios

```python
# handlers/github_handler.py
class GitHubHandler:
    async def run_github_action(...)
    async def checkout_pr(...)

# handlers/agent_handler.py  
class AgentHandler:
    async def list_agents(...)
    async def create_agent(...)  # Requiere LLM

# handlers/auth_handler.py
class AuthHandler:
    async def list_credentials(...)  # Solo metadata, NO tokens
```

#### 3.4.2 Patrón Async + Polling (Operaciones Largas)

```python
# long_job_manager.py
class LongJobManager:
    """Gestión de trabajos asíncronos para operaciones largas."""
    
    jobs: Dict[str, JobStatus]  # {job_id: {status, started_at, result, error}}
    
    async def start_job(self, tool_name: str, coroutine) -> str:
        """Inicia job y retorna job_id inmediatamente."""
        
    async def get_job_status(self, job_id: str) -> JobStatus:
        """Consulta estado del job."""
        
    async def cancel_job(self, job_id: str) -> bool:
        """Cancela job en progreso."""

# Nueva herramienta
Tool(
    name="opencode_get_job_status",
    description="Check status of a long-running operation",
    inputSchema={
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "Job ID returned from async operation"}
        },
        "required": ["job_id"]
    }
)
```

#### 3.4.3 Mejoras de Seguridad

```python
# security.py
class SecurityValidator:
    """Validaciones de seguridad centralizadas."""
    
    def validate_file_path(self, path: str) -> bool:
        """Valida rutas de archivo contra allowed_file_extensions."""
        
    def validate_file_size(self, path: str) -> bool:
        """Valida tamaño contra max_file_size."""
        
    def sanitize_log_message(self, message: str) -> str:
        """Trunca/anonimiza prompts para logging seguro."""
        
    def validate_operation(self, operation: str) -> bool:
        """Valida contra allowed_operations."""

# En handlers, ANTES de ejecutar:
if not security.validate_operation("github_run"):
    raise OperationNotAllowedError("github_run")
```

---

## PARTE 4: Plan de Implementación

### Fase 1: Repositorio y Fundamentos (Semana 1)

**Día 1-2: Setup Git**
- [ ] Inicializar repositorio git
- [ ] Crear .gitignore
- [ ] Crear README.md con documentación
- [ ] Crear LICENSE (MIT)
- [ ] Push a GitHub

**Día 3-4: Mejoras de Seguridad**
- [ ] Implementar SecurityValidator
- [ ] Activar validaciones existentes (allowed_operations, file_extensions, max_size)
- [ ] Sanitizar logging

**Día 5: Testing Base**
- [ ] Configurar pytest-asyncio
- [ ] Tests para herramientas existentes
- [ ] CI/CD con GitHub Actions

### Fase 2: Herramientas Core (Semana 2)

**Día 1-2:**
- [ ] `opencode_import_session`
- [ ] `opencode_list_sessions`
- [ ] Tests

**Día 3-4:**
- [ ] `opencode_get_stats`
- [ ] `opencode_list_agents`
- [ ] Tests

**Día 5:**
- [ ] `opencode_share_session`
- [ ] Integración y documentación

### Fase 3: Operaciones GitHub (Semana 3)

**Día 1-2:**
- [ ] Implementar LongJobManager
- [ ] `opencode_get_job_status`
- [ ] Tests async

**Día 3-4:**
- [ ] GitHubHandler
- [ ] `opencode_github_run` (async)
- [ ] `opencode_pr_checkout`
- [ ] Tests

**Día 5:**
- [ ] `opencode_list_credentials`
- [ ] `opencode_start_server`
- [ ] Integración final

### Fase 4: Finalización (Semana 4)

- [ ] Documentación completa
- [ ] Release v2.0.0
- [ ] Publicar en MCP registry (opcional)

---

## PARTE 5: Validaciones Realizadas

### 5.1 Agentes Utilizados

| Agente | Tarea | Resultado |
|--------|-------|-----------|
| Task (explore) | Análisis gaps CLI vs MCP | 10 comandos NO implementados identificados |
| Gemini 3 Pro | Validación arquitectura | Ajustes de priorización + riesgos seguridad |
| Codex (read-only) | Auditoría código | Gaps de seguridad + patrón async recomendado |

### 5.2 Consenso de Validaciones

**Priorización Ajustada (Post-Validación):**

1. ✅ `opencode_list_sessions` - ALTA (prerequisito para navegación)
2. ✅ `opencode_get_stats` - ALTA (monitoreo costos)
3. ✅ `opencode_list_agents` - ALTA (elevado por Gemini - prerequisito de ejecución)
4. ✅ `opencode_import_session` - ALTA (colaboración)
5. ⬇️ `opencode_start_server` - BAJA (degradado por Gemini - conflictos potenciales)
6. ✅ `opencode_github_run` - ALTA pero ASYNC (patrón polling)
7. ✅ `opencode_list_credentials` - Solo METADATA, nunca tokens

### 5.3 Riesgos de Seguridad Identificados

| Riesgo | Severidad | Mitigación |
|--------|-----------|------------|
| Fuga de tokens en `list_credentials` | CRÍTICA | Solo devolver metadata (provider, status, scope) |
| Ejecución arbitraria GitHub | ALTA | Modo dry-run + confirmación parámetros |
| Prompt injection via import | ALTA | Validar JSON schema + sanitizar contenido |
| Logging de prompts | MEDIA | Truncar/anonimizar en logs |
| Rutas arbitrarias en files | MEDIA | Validar extensiones + cwd sandboxing |

---

## PARTE 6: Estimaciones

### 6.1 Esfuerzo Total
- **Herramientas nuevas**: 8-10 (según prioridad)
- **Tiempo estimado**: 3-4 semanas
- **Complejidad promedio**: Media
- **Líneas de código estimadas**: ~1500-2000

### 6.2 Dependencias Externas
- OpenCode CLI instalado y accesible
- GitHub CLI (gh) para operaciones GitHub
- Credenciales configuradas para proveedores

---

## Conclusión

El plan propone una expansión significativa del MCP Server:
- De 6 herramientas → 14-16 herramientas
- Cobertura de CLI: ~40% → ~85%
- Mejoras de seguridad críticas
- Soporte para operaciones asíncronas

**Próximo paso**: Aprobación del usuario para iniciar Fase 1 (creación repositorio).
