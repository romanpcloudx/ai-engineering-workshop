# ADK + A2A + MCP + Composio

Dos agentes ADK independientes:

```text
humano
  │
  ▼
Agent A: generalist_agent
  │  RemoteA2aAgent
  │  A2A / HTTP
  ▼
Agent B: outlook_email_agent (/a2a/outlook_agent)
  │  McpToolset
  │  MCP / Streamable HTTP
  ▼
Composio hosted MCP session
  │
  └── OUTLOOK_SEND_EMAIL (única tool)
          │
          ▼
      Cuenta Outlook conectada
```

El pedido original mencionaba Twitter, pero la tool indicada es
`OUTLOOK_SEND_EMAIL` y la cuenta configurada es de Outlook. Por eso el agente
especializado implementado es de **Outlook/email**, no de Twitter.

## Responsabilidad de cada agente

### Agent A — consumidor generalista

Está en `consuming_agent/agent.py`. Es el agente con el que habla el usuario.

- Responde saludos y preguntas generales por sí mismo.
- Tiene un `RemoteA2aAgent` llamado `outlook_email_agent`.
- Delega por A2A solamente cuando el usuario quiere enviar un email.
- No conoce Composio, MCP ni las credenciales de Outlook.
- No puede afirmar que envió algo hasta recibir confirmación de Agent B.

`RemoteA2aAgent` recibe la URL de la Agent Card:

```text
http://127.0.0.1:8000/a2a/outlook_agent/.well-known/agent-card.json
```

ADK descarga esa card y usa el proxy remoto como un sub-agent. Agent A no
importa el código de Agent B: lo único que comparten es esa URL, y la
comunicación cruza HTTP usando A2A aunque los sirva el mismo proceso.

### Agent B — Outlook expuesto

Está en `outlook_agent/agent.py`.

- Es un `LlmAgent` especializado en enviar correo.
- Se conecta al MCP hospedado por Composio mediante `McpToolset`.
- Solo recibe `OUTLOOK_SEND_EMAIL`.
- Se expone por A2A gracias a su `agent.json` y al flag `--a2a`.
- Exige destinatario, asunto, cuerpo e intención explícita de enviar antes de
  ejecutar el efecto externo.

El archivo no levanta ningún servidor. ADK arma el executor, el task store y
las rutas JSON-RPC cuando encuentra el `agent.json` de la carpeta.

## Cómo llega una sola tool desde Composio

Composio no publica una URL de MCP fija que puedas pegar en una variable de
entorno. El endpoint nace de una **sesión**, y es esa sesión la que define qué
tools quedan visibles. Por eso `outlook_agent/agent.py` la crea al arrancar:

```python
session = composio.sessions.create(
    user_id=...,
    toolkits=['outlook'],
    tools={'outlook': {'enable': ['OUTLOOK_SEND_EMAIL']}},
    auth_configs={'outlook': ...},
    connected_accounts={'outlook': [...]},
    session_preset=SESSION_PRESET_DIRECT_TOOLS,
    mcp=True,
)
```

Las partes importantes son:

1. `toolkits=['outlook']` excluye otros productos.
2. `tools=...enable...` permite solamente `OUTLOOK_SEND_EMAIL`.
3. `SESSION_PRESET_DIRECT_TOOLS` hace que el MCP publique la tool directamente
   y deshabilita las meta-tools de búsqueda.
4. `connected_accounts` fija exactamente la cuenta de Outlook que ejecutará el
   envío.
5. `mcp=True` hace que Composio devuelva `session.mcp.url` y
   `session.mcp.headers`.

Después Agent B crea:

```python
McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=session.mcp.url,
        headers=session.mcp.headers,
    ),
    tool_filter=['OUTLOOK_SEND_EMAIL'],
)
```

Hay dos filtros deliberadamente:

- Composio publica una sola tool.
- ADK vuelve a filtrar antes de entregársela al modelo.

Aunque el toolkit completo tenga más de 200 tools, el modelo de Agent B recibe
solo `OUTLOOK_SEND_EMAIL`.

## Variables de entorno

Copiar `.env.example` a `.env` dentro de esta carpeta, o agregar las variables
al `.env` de la raíz:

```dotenv
GOOGLE_API_KEY=...
ADK_MODEL=gemini-3.7-flash

COMPOSIO_API_KEY=...
COMPOSIO_USER_ID=...
COMPOSIO_AUTH_CONFIG_ID=ac_-VUnfyXRcOFR
COMPOSIO_CONNECTED_ACCOUNT_ID=ca_XNWTVw6SIgaJ

OUTLOOK_AGENT_URL=http://127.0.0.1:8000/a2a/outlook_agent
```

`COMPOSIO_USER_ID` debe ser el mismo usuario dueño de
`ca_XNWTVw6SIgaJ`. Composio rechazará la sesión si la cuenta conectada pertenece
a otro usuario.

Los IDs `ac_...` y `ca_...` seleccionan configuración y cuenta; no sustituyen
`COMPOSIO_API_KEY`.

## Instalar dependencias

Desde la raíz del repositorio:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

Este ejemplo agrega `google-adk[a2a]` y `composio` al `requirements.txt` de la
raíz.

Ojo con `mcp`: `google-adk` importa `mcp.shared.session`, que existe en `mcp`
1.x pero no en 2.x. Por eso el `requirements.txt` fija `mcp>=1.24,<2`. Con
`mcp` 2.x instalado, `McpToolset` no se puede importar y ADK **se traga el
error en silencio** (el `__init__.py` de `mcp_tool` captura el `ImportError`),
así que el síntoma es un `ImportError: cannot import name 'McpToolset'` que no
explica la causa.

## Ejecutar

Un solo comando, desde la raíz del repositorio:

```powershell
.\.venv\Scripts\adk.exe web --a2a w05-mcp-and-a2a/adk-a2a-mcp
```

Abrir http://127.0.0.1:8000 y elegir `consuming_agent` en el desplegable.

El flag `--a2a` es lo que expone a Agent B: ADK recorre las carpetas del
`AGENTS_DIR`, encuentra `outlook_agent/agent.json` y monta ese agente en
`/a2a/outlook_agent`. Las carpetas sin `agent.json` (como `consuming_agent`)
solo se sirven por la UI.

Para comprobar que Agent B quedó publicado:

```text
http://127.0.0.1:8000/a2a/outlook_agent/.well-known/agent-card.json
```

### Por qué el AGENTS_DIR va como argumento

`adk web` toma un directorio donde **cada subcarpeta es un agente**. Si lo
corrieras sin argumento desde la raíz, ADK trataría `w05-mcp-and-a2a`,
`w03-tracing-and-observability`, etc. como agentes y fallaría al importarlos
(los guiones no son válidos en nombres de módulo). Pasando el directorio como
argumento, los únicos nombres que ADK importa son `consuming_agent` y
`outlook_agent`, que sí son identificadores válidos. Los guiones en las
carpetas padre no molestan porque esas rutas solo entran al `sys.path`.

### Correr Agent B en un proceso aparte (opcional)

Si preferís que los dos agentes no compartan proceso:

```powershell
# Terminal 1
.\.venv\Scripts\adk.exe api_server --a2a --port 8001 w05-mcp-and-a2a/adk-a2a-mcp

# Terminal 2
.\.venv\Scripts\adk.exe web w05-mcp-and-a2a/adk-a2a-mcp
```

En ese caso hay que apuntar Agent A al otro puerto, en el `.env`:

```dotenv
OUTLOOK_AGENT_URL=http://127.0.0.1:8001/a2a/outlook_agent
```

### El agent.json

Es la Agent Card de Agent B y es lo que habilita `--a2a`. Está generada con el
`AgentCardBuilder` de ADK, así que refleja las skills reales del agente
(incluida `OUTLOOK_SEND_EMAIL`, que llega desde Composio vía MCP). Si cambiás
el nombre, la descripción o las tools de Agent B, conviene regenerarla:

```powershell
.\.venv\Scripts\python.exe -c @"
import sys, asyncio, warnings; warnings.filterwarnings('ignore')
sys.path.insert(0, r'w05-mcp-and-a2a\adk-a2a-mcp')
from google.protobuf.json_format import MessageToJson
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from outlook_agent.agent import root_agent
async def main():
    card = await AgentCardBuilder(agent=root_agent, rpc_url='http://127.0.0.1:8000/a2a/outlook_agent').build()
    open(r'w05-mcp-and-a2a\adk-a2a-mcp\outlook_agent\agent.json','w',encoding='utf-8').write(MessageToJson(card, indent=2))
asyncio.run(main())
"@
```

> El puerto 8000 es también el que usa `mcp-minimo/server.py`. No corras los
> dos ejemplos a la vez sin cambiar uno de los puertos.

## Por qué Agent B le contesta directo al usuario

En la UI vas a ver un `transfer_to_agent("outlook_email_agent")` y, a partir de
ahí, las respuestas aparecen firmadas por Agent B en lugar de volver a Agent A.
Eso es el comportamiento **por defecto** de `sub_agents` en ADK, no algo del
protocolo A2A.

Cuando un `LlmAgent` declara `sub_agents=[...]`, ADK le agrega automáticamente
la tool `transfer_to_agent`. Esa tool **transfiere el control**: el sub-agente
pasa a ser el agente activo de la sesión y le habla al usuario directamente,
y sigue activo en los turnos siguientes hasta que transfiera de vuelta. No es
una llamada que devuelve un valor a quien la hizo.

El salto A2A sí ocurre igual: Agent A no ejecuta código de Agent B, le manda el
mensaje por HTTP al endpoint `/a2a/outlook_agent`. Lo que cambia es quién
redacta la respuesta final.

Si alguna vez querés el otro flujo (B le responde a A, y A le habla al usuario),
hay que tratar al remoto como **tool** en vez de sub-agente:

```python
from google.adk.tools.agent_tool import AgentTool

root_agent = LlmAgent(
    ...,
    tools=[AgentTool(agent=outlook_agent)],   # en lugar de sub_agents=[...]
)
```

Así la respuesta de Agent B entra al contexto de Agent A como resultado de
función, y el autor del mensaje final sigue siendo `generalist_agent`.

> ADK también ofrece `mode='single_turn'` para lograr esto sin `AgentTool`,
> pero ese campo existe en `LlmAgent` y **no** en `RemoteA2aAgent`, así que
> para un agente remoto la opción es `AgentTool`.

## Ver la cola y los estados de las tasks A2A

La UI muestra eventos de ADK, no el ciclo de vida A2A. El task store de
`adk web --a2a` es en memoria y no tiene pantalla propia, pero el cliente
loguea cada request y response A2A en nivel DEBUG:

```powershell
.\.venv\Scripts\adk.exe web --a2a --log_level debug w05-mcp-and-a2a/adk-a2a-mcp
```

En cada delegación vas a ver algo así:

```text
A2A Response:
Task ID: a8563286-9537-4800-92da-6fa7c9d2a955
Context ID: 39ce6b3e-176b-4869-a544-771d4e4d2aa4
Status State: 3
History Length: 2
Artifacts Count: 1
```

`Status State` sale como número porque en `a2a-sdk` 1.x es un enum protobuf:

| Valor | Estado |
|---|---|
| 1 | `SUBMITTED` |
| 2 | `WORKING` |
| 3 | `COMPLETED` |
| 4 | `FAILED` |
| 5 | `CANCELED` |
| 6 | `INPUT_REQUIRED` |
| 7 | `REJECTED` |
| 8 | `AUTH_REQUIRED` |

El `Task ID` es lo que identifica la task del lado de Agent B, y el
`Context ID` es lo que hila los turnos de una misma conversación A2A.

## Probar sin enviar primero

Estas interacciones no deberían ejecutar Outlook:

```text
hola
¿Qué es MCP?
Quiero enviar un email
```

La última está incompleta; Agent A debe pedir destinatario, asunto y cuerpo.

Una solicitud completa y explícita sí será delegada:

```text
Envía ahora un email a persona@example.com,
asunto "Prueba A2A",
cuerpo "Este mensaje fue enviado por el agente."
```

Flujo de esa solicitud:

1. Agent A decide delegar al `RemoteA2aAgent`.
2. ADK envía el mensaje a Agent B por A2A.
3. Agent B decide usar `OUTLOOK_SEND_EMAIL`.
4. `McpToolset` manda `tools/call` al endpoint MCP de Composio.
5. Composio ejecuta la tool con la cuenta conectada.
6. El resultado vuelve MCP → Agent B → A2A → Agent A → usuario.

El envío es real: usar un destinatario de prueba.
