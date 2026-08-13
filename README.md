# OpenCode MCP Jobs

MCP local para lanzar trabajos persistentes de OpenCode desde un subagente del
CLI. Las ejecuciones no bloquean la llamada MCP: devuelven un `job_id`, guardan
su estado en SQLite y se pueden consultar o reanudar después de reiniciar el
MCP.

## Herramientas

- `opencode_job_start`: inicia un trabajo y acepta `message`, `directory`, `agent`, `model`, `variant`, `session_id`, `orchestration` y `max_runtime_seconds`.
- `opencode_job_status`: consulta estado, salud, actividad e interacción pendiente.
- `opencode_job_result`: recupera salida y razonamiento por bloques.
- `opencode_job_respond`: responde un permiso o una pregunta.
- `opencode_job_cancel`: aborta la sesión.
- `opencode_job_list`: enumera trabajos recientes.
- `opencode_list_agents`: descubre agentes disponibles en un proyecto.
- `opencode_list_models`: descubre modelos del CLI.
- `opencode_list_sessions`: lista sesiones del CLI.
- `opencode_health_check`: comprueba SQLite, el servidor delegado, el CLI y los modelos.

`opencode_prompt` y las herramientas públicas de archivos han sido retiradas.
OpenCode ya proporciona `read`, `grep`, `glob`, estado Git y edición como
herramientas nativas.

## Flujo

1. El subagente llama a `opencode_job_start` con un directorio absoluto.
2. El MCP devuelve el trabajo inmediatamente.
3. El subagente consulta `opencode_job_status` y `opencode_job_result`.
4. Si OpenCode pide permiso o una respuesta, el estado pasa a `waiting_input`.
5. El subagente responde con `opencode_job_respond`.

El agente se valida contra los agentes disponibles en OpenCode. Se aceptan
agentes integrados y personalizados; si el nombre no existe, el error incluye
los nombres válidos. Para elegir modelo, llama primero a `opencode_list_models`
y pasa a `opencode_job_start` el ID exacto `provider/model`. Un modelo inválido
también devuelve la lista viva del proveedor. Si omites `model`, OpenCode decide
según su propia configuración. `orchestration` es `direct` por defecto; solo
`ulw` añade la activación de oh-my-openagent.

No existe un timeout de ejecución predeterminado. `max_runtime_seconds` solo
se aplica si el trabajo lo solicita y no consume tiempo mientras espera una
interacción. La falta de eventos marca la salud como `stale`, pero no cancela
el trabajo. Las interacciones abandonadas vencen tras 24 horas.

## Configuración

Dependencias:

```bash
uv pip install -r requirements.txt
```

Entrada MCP:

```json
{
  "opencode": {
    "type": "local",
    "command": ["/ruta/al/proyecto/.venv/bin/python", "-m", "src.services.fast_mcp.opencode_server"],
    "environment": {
      "PYTHONPATH": "/ruta/al/proyecto",
      "OPENCODE_JOB_DB": "~/.local/state/opencode-mcp/jobs.db",
      "OPENCODE_SERVE_PORT": "4097"
    },
    "enabled": true,
    "timeout": 30000
  }
}
```

El MCP arranca un `opencode serve` dedicado en `127.0.0.1:4097` y le inyecta
una configuración donde el MCP `opencode` está desactivado. Esto impide que la
sesión delegada se invoque a sí misma.

## Persistencia

El estado se guarda por defecto en:

```text
~/.local/state/opencode-mcp/jobs.db
```

Se puede cambiar con `OPENCODE_JOB_DB`. Los resultados completos permanecen en
la sesión de OpenCode; SQLite conserva metadatos, interacciones y un snapshot
de salida para recuperar el trabajo sin duplicar todo el historial.

## Desarrollo

```bash
PYTHONPATH=. .venv/bin/pytest -q
PYTHONPATH=. .venv/bin/python -m src.services.fast_mcp.opencode_server
```
