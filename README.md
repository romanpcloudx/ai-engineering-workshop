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

## Requisitos

- Node.js 18 o superior
- npm
- API keys para los proveedores utilizados en cada ejemplo

## Preparación

Instalar las dependencias:

```bash
npm install
```

Crear un archivo `.env` a partir de `.env.example` y completar únicamente las
credenciales necesarias:

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=
DEEPSEEK_API_KEY=
OPENWEATHER_KEY=
VERBOSE_OPENAI_RESPONSE=0
```

El archivo `.env` está ignorado por Git. Nunca deben subirse API keys al
repositorio.

## Ejecutar un ejemplo

Los ejemplos se ejecutan directamente con Node.

```bash
node w01-agent-loop/openai-responses-api.js
```

```bash
node w01-agent-loop/deepseek-completions-api.js
```

Cada carpeta contiene su propio README con requisitos, conceptos y pruebas
sugeridas.

## Estructura

```text
.
├── helpers/                 # Utilidades compartidas
├── w01-agent-loop/          # Workshop 01 y sus ejemplos
├── .env.example             # Variables de entorno requeridas
├── package.json             # Dependencias comunes
└── README.md                # Índice general
```

Los próximos encuentros seguirán el formato `wNN-tema/`, manteniendo juntos el
código y la documentación de cada workshop.

## Notas

- Las APIs de los proveedores pueden tener contratos parecidos, pero sus
  estructuras no son necesariamente intercambiables.
- Ejecutar los ejemplos puede generar costos de API.
- Los nombres de modelos, parámetros, precios y límites cambian con el tiempo;
  consultar siempre la documentación vigente del proveedor.
- Este código tiene fines educativos. Antes de usarlo en producción deben
  agregarse validación, límites de ejecución, manejo de errores, seguridad,
  persistencia y observabilidad.

