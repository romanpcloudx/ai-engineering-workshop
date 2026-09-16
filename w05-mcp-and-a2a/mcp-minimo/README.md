# MCP mínimo

Una tool, un servidor, un agente. Sin A2A. Dos procesos, como en producción:
alguien administra el server; el agent solo conoce una URL.

```text
humano
  │  Python, mismo proceso que el agent
  ▼
agent.py  (DeepSeek + function calling)     terminal 2
  │  MCP Streamable HTTP  (JSON-RPC)
  │  http://127.0.0.1:8000/mcp
  ▼
server.py  (FastMCP, tool `add`)            terminal 1
```

El modelo **no** habla MCP. Ve una función OpenAI (`add`) que el cliente armó
después de `list_tools`. Cuando pide la función, el cliente traduce eso a
`tools/call` y le devuelve el texto al modelo.

Eso es MCP: un contrato para que un programa publique tools y otro las
descubra y ejecute, sin importar el código ni quién levanta el server.

## Archivos

- `server.py`: publica `add(a, b)` y escucha en `:8000/mcp`. Proceso propio.
- `agent.py`: se conecta a esa URL, hace handshake, descubre la tool y corre
  el loop LLM. No lanza el server.

## De dónde sale el contrato de la tool

Nada se declara a mano. El SDK lo deriva de la firma:

| Parte del schema | De dónde sale |
|---|---|
| `name` | El nombre de la función |
| `description` | El docstring |
| `properties` / `type` | Los type hints (`a: int` → `integer`) |
| `required` | Los parámetros sin default |
| `description` de cada param | `Annotated[int, Field(description=...)]` |

Lo que ve el cliente tras `list_tools`:

```json
{
  "name": "add",
  "description": "Add two integers and return the sum.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "a": {"type": "integer", "description": "First number to add."},
      "b": {"type": "integer", "description": "Second number to add."}
    },
    "required": ["a", "b"]
  }
}
```

El `instructions` del `FastMCP` es otra cosa: describe **el servidor**, no la
tool. Viaja en el handshake, no en `list_tools`.

> Este ejemplo corre sobre `mcp` 1.x, porque `google-adk` todavía no soporta
> `mcp` 2.x y comparten el mismo venv. En 1.x el modelo `Tool` usa
> `inputSchema` y `CallToolResult` usa `isError` (camelCase), y el transport
> entrega `(read, write, get_session_id)`.

## Agregar más tools

Otro decorador. Nada más:

```python
@mcp.tool()
def multiply(
    a: Annotated[int, Field(description='First factor.')],
    b: Annotated[int, Field(description='Second factor.')],
) -> int:
    """Multiply two integers."""
    return a * b
```

El cliente no cambia: `list_tools` ya la devuelve y el loop LLM la ofrece.
Hay que **reiniciar el server** para que registre la tool nueva; después
reiniciar el agent para que vuelva a descubrirla.

## Cómo funciona el agent (client), paso a paso

No hay una clase `ToolRegistry`. En este código hay **dos registros** y un
traductor en el medio.

```text
server  ToolManager          (Python: @mcp.tool)
            │  list_tools / tools/call   (MCP JSON-RPC por HTTP)
            ▼
client  listed.tools         (objetos MCP)
            │  _openai_tools()
            ▼
LLM     tools=[...]          (schema OpenAI / DeepSeek)
```

El modelo nunca ve MCP. Ve funciones. El cliente es el que habla los dos
idiomas.

### 1. El agent se conecta a un server que ya está arriba

`main()` no spawnea `server.py`. Tiene una URL, igual que si el calculator
lo administrara otro equipo:

```python
MCP_URL = 'http://127.0.0.1:8000/mcp'
```

`streamable_http_client(MCP_URL)` abre HTTP contra ese endpoint. Si nadie
escucha, el agent falla con un mensaje para levantar el server en otra
terminal. Eso es el caso real: el cliente consume; no opera el server.

stdio (un subprocess que el client lanza) sigue existiendo en MCP y es
válido para un plugin local. Esta demo usa HTTP a propósito, para que los
ciclos de vida no se mezclen.

### 2. Handshake (`initialize`)

`ClientSession` envuelve los streams HTTP. `session.initialize()` es el
saludo MCP: el cliente dice quién es y qué protocolo habla; el server
responde `serverInfo` (`name=calculator`, `description=Arithmetic helpers…`).
Hasta acá **no hay tools**. Solo hay una sesión viva.

### 3. Descubrimiento (`list_tools`)

Eso pasa una sola vez, al entrar a `chat()`:

```python
listed = await session.list_tools()
```

El cliente manda el método MCP `tools/list`. El server recorre lo que
registró `@mcp.tool()` y devuelve, para cada función, `name`, `description`
e `inputSchema`. El cliente no importó `add`. No conoce su firma. La
**importación** es esta llamada.

Si mañana agregás `multiply` en el server, reiniciás el server y después el
agent, aparece sola.

### 4. El “tool registry” del LLM

`listed.tools` todavía es el formato MCP. DeepSeek no lo entiende. Entonces:

```python
tools = _openai_tools(listed.tools)
```

Esa lista es el registro que usa el modelo. Cada item queda así:

```python
{
  'type': 'function',
  'function': {
    'name': tool.name,                 # "add"
    'description': tool.description,   # docstring
    'parameters': tool.inputSchema,    # JSON Schema de a y b
  },
}
```

A partir de acá, `tools` se pasa en **cada** `chat.completions.create`. El
modelo elige por nombre (`add`). Ese nombre es el mismo `tool.name` que
después va a `session.call_tool`. Si los nombres no coincidieran, el LLM
pediría una función que MCP no sabe ejecutar.

El registro **no se actualiza** en cada turno. Se arma al conectar y vive
hasta que cerrás el chat. Por eso un server con tools nuevas requiere
reiniciar el agent.

### 5. El loop de conversación

`messages` arranca con el system prompt y se va acumulando. Cada `user >`
hace `append` del turno humano y llama `step(...)`.

`step` es el loop clásico:

1. Manda historial + `tools` a DeepSeek.
2. Si el modelo responde texto (`hola` → “Hola, ¿en qué te ayudo?”),
   **no hay `tool_calls`**. Se imprime y listo. MCP no se toca.
3. Si el modelo pide una función, parsea `call.function.arguments` y llama
   `session.call_tool(nombre, arguments)`. Eso es MCP `tools/call`. El
   server ejecuta `add(a, b)` de verdad y devuelve el número.
4. El cliente aplana el resultado a texto (`_tool_text`) y lo mete en
   `messages` con `role: tool` y el `tool_call_id` que mandó el modelo.
   Sin ese id, DeepSeek no puede atar el resultado al pedido.
5. Vuelve al paso 1, ahora con el resultado en el historial, hasta que el
   modelo hable o se cansen los 4 pasos.

```text
user > hola
        DeepSeek  (ve add, no la usa)
agent > Hola...

user > cuanto es 12 mas 30
        DeepSeek  tool_call add(12, 30)
            │
            ▼
        session.call_tool('add', {a: 12, b: 30})     MCP HTTP
            │
            ▼
        server.add(12, 30) → 42
            │
            ▼
        messages += {role: tool, content: "42"}
        DeepSeek  (ya tiene 42)
agent > 12 más 30 es 42.
```

### 6. Qué no hace este cliente

No cachea las tools en disco. No las importa como módulo Python. No
despacha por un `if name == 'add'`. El único dispatch es **el nombre que
eligió el LLM**, reenviado a MCP. El server es el que sabe qué función
correr. El agent no es dueño del proceso del server.

## Ejecutar

Dos terminales, desde la raíz del repo. `DEEPSEEK_API_KEY` en `.env` solo
hace falta en la del agent.

```powershell
# Terminal 1 — server MCP (se queda escuchando)
python .\w05-mcp-and-a2a\mcp-minimo\server.py

# Terminal 2 — agent
python .\w05-mcp-and-a2a\mcp-minimo\agent.py
```

`hola` responde sin tool. `cuanto es 12 mas 30` dispara `tools/call`.
`exit` cierra el chat, no el server.
