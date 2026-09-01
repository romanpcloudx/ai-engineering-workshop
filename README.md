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

## Requisitos

- Node.js 18 o superior y npm (W01; W02 y W04 si se clona el agente compartido)
- Python 3.12 o superior (W03)
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
