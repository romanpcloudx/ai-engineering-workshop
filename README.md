# AI Engineering Workshop

Repositorio de ejemplos y notas para la serie de workshops internos sobre AI
Engineering.

El objetivo es estudiar cómo se construyen agentes y aplicaciones con LLMs desde
sus componentes básicos: requests a APIs, historial, reasoning, tool calls,
memoria, costos, evaluación y observabilidad. Los ejemplos priorizan código
pequeño y explícito antes que frameworks de alto nivel.

## Workshops

### W01 — El loop de un agente

Introducción a agentes, workflows, estado conversacional, herramientas, reasoning
y context caching.

Incluye dos implementaciones del mismo agente para comparar formatos de API:

- OpenAI Responses API
- DeepSeek mediante Chat Completions

[Ver material y documentación de W01](./w01-agent-loop/README.md)

### W02 — Tools y funciones

Diseño de tools, schemas, dispatch, errores accionables y continuidad del agent
loop después de cada `tool_result`.

[Ver presentación y recursos de W02](./w02-tools/README.md)

### W03 — Tracing y observabilidad

Session, trace y span. Un asistente bancario en Google ADK para inspeccionar el
camino de cada turno en ADK Web y persistir traces en Langfuse.

[Ver material y documentación de W03](./w03-tracing-and-observability/README.md)

### W04 — Skills y progressive disclosure

Descubrimiento de skills, índice mínimo en el system prompt y carga bajo demanda
de instrucciones y archivos adicionales.

[Ver resumen y recursos de W04](./w04-skills/README.md)

W02 y W04 usan el mismo agente, publicado como recurso independiente:
[tools-workshop-agent](https://github.com/GBurgardt/tools-workshop-agent).

### W05 — MCP y A2A

MCP conecta agentes con capacidades externas; A2A conecta agentes independientes.
La sesión avanza desde un servidor MCP con una tool de suma hasta un caso
integrador donde un agente generalista delega por A2A a un especialista de
Outlook, que ejecuta `OUTLOOK_SEND_EMAIL` mediante MCP.

- [Guía conceptual, ejemplos y comandos de W05](./w05-mcp-and-a2a/README.md)
- [Presentación: Sesión 05 — MCP y A2A](./w05-mcp-and-a2a/sesion-05-mcp-a2a.pptx)

#### Resumen conceptual de W05

| MCP | A2A |
|---|---|
| Conecta una aplicación agente con tools, resources y prompts | Conecta agentes independientes mediante un contrato interoperable |
| El client descubre el catálogo del MCP server y ejecuta la capacidad elegida | El cliente descubre una Agent Card y delega trabajo mediante messages o tasks |
| La unidad operativa típica es una tool call | La unidad rastreable es una Task con estado, historial y artifacts |

En A2A, la **Agent Card** publica identidad, endpoints, capacidades, formatos,
seguridad y **Agent Skills**. Una skill explica qué sabe hacer el agente y qué
entradas y salidas acepta. El discovery puede hacerse mediante la URI
`/.well-known/agent-card.json`, un registro curado o configuración directa.

Cuando el pedido requiere seguimiento, el servidor crea una **Task**. Sus
estados no terminales incluyen `SUBMITTED` y `WORKING`; puede interrumpirse con
`INPUT_REQUIRED` o `AUTH_REQUIRED`; y termina en `COMPLETED`, `FAILED`,
`CANCELED` o `REJECTED`. `taskId` identifica el trabajo y `contextId` agrupa
turnos y tasks relacionados.

El `AgentExecutor` adapta la lógica interna del agente al protocolo y publica
Tasks, actualizaciones y Artifacts en una `EventQueue`. El cliente puede recibir
los cambios por polling, streaming SSE o push notifications.

Los ejemplos avanzan en cuatro pasos:

1. `mcp-minimo`: un client descubre y llama la tool `add` de un FastMCP server.
2. `a2a`: Hello World hardcodeado, pero con Card, skill, Task, executor y stream.
3. `a2a-langgraph`: el mismo contrato rodea un agente real con memoria y tool.
4. `adk-a2a-mcp`: Agent A delega por A2A a Agent B; Agent B envía email mediante
   la tool MCP `OUTLOOK_SEND_EMAIL`.

## Requisitos

- Node.js 18 o superior y npm (W01; W02 y W04 si se clona el agente compartido)
- Python 3.12 o superior (W03 y W05)
- API keys para los proveedores utilizados en cada ejemplo

## Preparación

Para los ejemplos en Node, instalar dependencias desde la raíz:

```bash
npm install
```

Crear un archivo `.env` a partir de `.env.example` y completar únicamente las
credenciales necesarias:

```dotenv
OPENWEATHER_KEY=
OPENAI_API_KEY=
OPENAI_MODEL=
DEEPSEEK_API_KEY=
VERBOSE_OPENAI_RESPONSE=0
GOOGLE_API_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

W03 también puede usar un `.env` propio en `w03-tracing-and-observability/`.
Las keys de Langfuse son opcionales: sin ellas ADK Web sigue andando.

El archivo `.env` está ignorado por Git. Nunca deben subirse API keys al
repositorio.

## Ejecutar un ejemplo

W01 se ejecuta con Node:

```bash
node w01-agent-loop/openai-responses-api.js
```

```bash
node w01-agent-loop/deepseek-completions-api.js
```

W03 se ejecuta con Google ADK, desde la raíz del repo:

```bash
pip install -r w03-tracing-and-observability/requirements.txt
adk web
```

Elegir el agente `w03-tracing-and-observability`.

Cada carpeta contiene su propio README con requisitos, conceptos y pruebas
sugeridas.

## Estructura

```text
.
├── helpers/                          # Utilidades compartidas
├── w01-agent-loop/                   # Workshop 01: loop del agente
├── w02-tools/                        # Workshop 02: presentación y recursos
├── w03-tracing-and-observability/    # Workshop 03: traces, ADK y Langfuse
├── w04-skills/                       # Workshop 04: resumen y recursos
├── w05-mcp-and-a2a/                  # Workshop 05: MCP, A2A y presentación
├── .env.example                      # Variables de entorno requeridas
├── package.json                      # Dependencias de los ejemplos en Node
└── README.md                         # Índice general
```

Los encuentros siguen el formato `wNN-tema/`, manteniendo juntos el código y la
documentación de cada workshop.

El agente compartido por W02 y W04 vive en un repositorio separado para evitar
duplicar código dentro de cada capítulo.

## Notas

- Las APIs de los proveedores pueden tener contratos parecidos, pero sus
  estructuras no son necesariamente intercambiables.
- Ejecutar los ejemplos puede generar costos de API.
- Los nombres de modelos, parámetros, precios y límites cambian con el tiempo;
  consultar siempre la documentación vigente del proveedor.
- Este código tiene fines educativos. Antes de usarlo en producción deben
  agregarse validación, límites de ejecución, manejo de errores, seguridad,
  persistencia y observabilidad.
