# INVESTIGACIÓN Y PLANIFICACION DELEGADA

Despliega agentes y haz uso de LLMs externos para investigar, planificar y analizar en profundidad y de manera proactiva los siguientes puntos.

Trasladale la investigación al MCP codex con approval-policy:never y sandbox:read-only para que exponga su análisis y sus propuestas.

En el caso de tener que procesar mucha información, ha uso de MCP gemini para el análisis de documentos, búsquedas en internet o procesado datos extensos.

Tras obtener respuesta por parte de codex y/o de gemini, habrá que validar, consensuar y verificar la investigación y/o planificación hecha por los LLMs externos del siguiente modo:
- Utiliza agentes especializados en las temáticas enumeradas
- Utiliza MCP droid-cli con reasoning_effort="high", que internamente podrá utilizar agentes especializados en las temáticas enumeradas

**SKILLS**
- episodic-memory:remembering-conversations
- operational-framework
- context-manager

* **Tareas a investigar y planificar:**
- Tarea 1: [DESCRIPCIÓN]


# INVESTIGACIÓN Y/O PLANIFICACIÓN

Investiga, planifica y analiza en profundidad y de manera proactiva los siguientes puntos.

Utiliza agentes especializados en las temáticas enumeradas para la investigación y planificación.

En el caso de tener que procesar mucha información, ha uso de MCP gemini 2.5 pro para el análisis de documentos, búsquedas en internet o procesado datos extensos.

Antes de ofrecer los datos de la investigación y/o planificación, despliega agentes para confirmar, consensuar, verificar y auditar la investigación y/o planificación hecha en cada punto haciendo uso de:
- MCP codex approval-policy:never y sandbox:read-only
- MCP Gemini 3

**SKILLS**
- episodic-memory:remembering-conversations
- operational-framework
- context-manager

* **Tareas a investigar y/o planificar:**
- Tarea 1: [DESCRIPCIÓN]


# CODIFICACION

Implementa de manera cuidadosa, proactiva, eficiente y sin olvidar nada las tareas enumeradas en la investigación y/o planificación anterior.

Utiliza agentes especializados en las temáticas enumeradas en la investigación y/o planificación

Tras implementar cada punto de la investigación y/o plan, despliega en paralelo agentes para verificar y auditar el código implementado haciendo uso de:
- MCP codex gpt-5-codex con approval-policy:never y sandbox:read-only
- MCP Gemini 3

**SKILLS**
- episodic-memory:remembering-conversations
- autonomous-goals.
- context-manager

**Tareas a codificar por los agentes:**
- Tarea 1: [Codifica el código necesario para implementar la solución propuesta anteriormente]

IMPORTANTE: Si la verificación o auditoría detecta que la implementación no es correcta o no cubre la planificación:
- Haz los cambios necesarios para corregir la implementación por ti mismo sin esperar nuevas instrucciones.
- NO HAGAS CAMBIOS SIN MI AUTORIZACIÓN. Reporta el problema y espera nuevas instrucciones.


# EVALUAR PULL REQUEST

Evalúa esta Pull Requests. Es importante que no cambies las ramas en local. Utiliza herramientas git para hacer fetch del codigo a evaluar en origin con las diferencias entre la rama de desarrollo XXXXXXXXXXXXX y la de destino que es develop (o XXXXXXXXXXX). Examina los diff desde origin sin hacer checkout en local.

REPOSITORIO: colgest-api  /  colgest-front

Solo quiero que evalues el código que hizo el compañero para la pull request para validarla o no. No hagas cambios ni arreglos ni nada. Está bien? Rompe algo? Cubre las especificaciones de la tarea?

**Tarea:**
- TITULO: [XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX]
- DESCRIPCIÓN: [XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX]
- COMENTARIOS ADICIONALES: [XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX]
- INFORMACIÓN EXTRA EN LA PULL REQUEST: [XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX]

A continuación te proporciono el RAW de los commits de la Pull Request a evaluar:

```[PEGA AQUÍ EL RAW DE LOS COMMITS DE LA PULL REQUEST]
```




# CODIFICACION CON CODEX - CONTEXTO AUTOMÁTICO

  **SKILLS**
  - autonomous-goals.
  - context-manager

  Despliega MCP codex con approval-policy:never y sandbox:workspace-write para codificar la solución propuesta anteriormente, incluyendo:

  **CONTEXTO AUTOMÁTICO**:
  1. Recuperar memoria reciente de la última hora
  2. Incluir como contexto los cambios recientes en el código con git diff HEAD~1
  3. Leer solo archivos esenciales del proyecto para la tarea automáticamente
  4. Pasar las 4 últimas interacciones de la conversación previa como contexto

  **PREPARACIÓN DEL CONTEXTO PARA CODEX**:
  - Usar mcp claude memory search para buscar patrones relevantes
  - Incluir git status y archivos modificados recientemente
  - Pasar el histórico de decisiones y trabajo previo de manera limitada
  - Proporcionar el plan recien planteado

  **TAREA**:
  [Implementar la solución planteada en el paso anterior con el contexto seleccionado]

  **VERIFICACIÓN**:
  Tras completar, verificar revisando con claude code y auditar con gemini y corregir si la implementación no es correcta o no cubre la planificación.

  **IMPORTANTE**:
  Claude orquestra y organiza, codex codifica

# CODIFICACIÓN CON GPRO-CODER - CONTEXTO AUTOMÁTICO

  Despliega gpro-coder con MCP Gemini Pro para codificar la solución propuesta anteriormente, incluyendo:

  **SKILLS**
  - autonomous-goals.
  - context-manager

  **CONTEXTO AUTOMÁTICO**:
  1. Recuperar memoria reciente de la última hora
  2. Incluir como contexto los cambios recientes en el código con git diff HEAD~1
  3. Leer solo archivos esenciales del proyecto para la tarea automáticamente
  4. Pasar las 4 últimas interacciones de la conversación previa como contexto

  **PREPARACIÓN DEL CONTEXTO PARA GEMINI**:
  - Usar mcp claude memory search para buscar patrones relevantes
  - Incluir git status y archivos modificados recientemente
  - Pasar el histórico de decisiones y trabajo previo de manera limitada
  - Proporcionar el plan recien planteado

  **TAREA**:
  [Implementar la solución planteada en el paso anterior con el contexto seleccionado]

  **VERIFICACIÓN**:
  Tras completar, verificar revisando con claude code y auditar con codex gpt-5 y corregir si la implementación no es correcta o no cubre la planificación.

  **IMPORTANTE**:
  Claude orquestra y organiza, Gemini codifica



# ESCRITURA DE DOCUMENTACIÓN

Despliega agentes que de manera cuidadosa, proactiva, eficiente y sin olvidar nada escriba la documentación necesaria para las siguientes tareas.

Tras escribir la documentación, despliega en paralelo agentes para verificar y auditar la documentación escrita haciendo uso de:
- MCP codex gpt-5-codex con approval-policy:never y sandbox:read-only
- MCP Gemini
- MCP claude code
- MCP droid-cli con reasoning_effort="high"

**SKILLS**
- autonomous-goals.
- context-manager

**Tareas a documentar por los agentes :**
- Tarea 1: [DESCRIPCIÓN]



