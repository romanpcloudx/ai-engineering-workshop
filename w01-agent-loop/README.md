# Workshop 01 — El loop de un agente

Este directorio contiene el material del primer encuentro interno sobre AI
Engineering. El objetivo del workshop fue entender qué hay debajo de un agente:
cómo decide su próximo paso, cómo conserva el contexto, cómo solicita la ejecución
de herramientas y por qué necesita un loop.

Los ejemplos implementan el mismo agente con dos protocolos diferentes:

- [`openai-responses-api.js`](./openai-responses-api.js): OpenAI Responses API.
- [`deepseek-completions-api.js`](./deepseek-completions-api.js): DeepSeek usando
  el formato compatible con OpenAI Chat Completions.

Los dos programas exponen una herramienta `get_weather`, mantienen el historial
en memoria y repiten llamadas al modelo hasta obtener una respuesta final. La
diferencia importante no está en la idea del agente, sino en la estructura del
request, del response y de los mensajes que se agregan al historial.

> **Precisión de nombres:** OpenAI ofrece actualmente, entre otras interfaces,
> **Chat Completions API** y **Responses API**. Existe además un endpoint legacy
> llamado Completions, pero no es el que se compara en este workshop. Cuando este
> documento dice “Completions” se refiere a **Chat Completions**.

## 1. Agentes y workflows no son lo mismo

Un LLM, por sí solo, recibe una entrada y genera tokens. Para convertirlo en un
agente hace falta un runtime que le permita observar el estado, elegir una acción,
ejecutarla y volver a evaluar el resultado.

La característica central es la **agencia** (*agency*): la capacidad de decidir
dinámicamente cuál es el próximo paso.

Un workflow determinístico tiene una secuencia definida por el programador:

```text
leer email → extraer producto → consultar stock → responder
```

Aunque uno de esos pasos use un LLM, el flujo continúa siendo un workflow si el
modelo no decide libremente qué acción ejecutar después.

En un agente, en cambio, el modelo puede decidir:

- responder directamente;
- consultar una o varias herramientas;
- inspeccionar nueva información;
- reintentar luego de un error;
- cambiar de estrategia;
- delegar una tarea a un subagente;
- finalizar cuando considera que ya tiene una respuesta suficiente.

Esto aporta flexibilidad, pero también menos predictibilidad. Para muchos casos de
uso empresariales, un workflow es más simple, económico, seguro y fácil de
testear. No todo sistema que usa un LLM necesita ser un agente.

Un chat con RAG tampoco es necesariamente un agente. RAG puede ser una herramienta
que un agente decide utilizar, pero recuperar información de una base vectorial no
implica por sí solo que exista autonomía.

## 2. El modelo es stateless

Las APIs utilizadas en estos ejemplos no recuerdan automáticamente los requests
anteriores. Cada llamada debe incluir el contexto que el modelo necesita para
responder.

La aplicación es dueña del estado:

```js
const history = [{ role: "system", content: SYSTEM }];

history.push({ role: "user", content: query });
```

Después de recibir la salida del modelo, también la agrega al historial. En el
siguiente turno vuelve a enviar el historial completo.

Una forma de imaginarlo es el protagonista de *Memento*: en cada interacción
necesita recibir nuevamente sus “notas” para saber qué ocurrió antes.

En este workshop el historial vive en un array de JavaScript. En producción podría
guardarse en Redis, una base de datos o un servicio de conversaciones. El lugar de
persistencia cambia, pero la responsabilidad sigue siendo de la aplicación.

### Roles e instrucciones

Los mensajes conversacionales suelen distinguir estos roles:

- `system`: instrucciones, comportamiento, restricciones y contexto de mayor
  prioridad;
- `user`: entrada del usuario;
- `assistant`: salida del modelo;
- `tool`: resultado de una herramienta en Chat Completions.

El mensaje de sistema debe contener reglas estables y relevantes. No constituye
una barrera de seguridad absoluta: ayuda a orientar el modelo, pero los permisos,
la validación y los controles sobre acciones sensibles deben implementarse
también en código.

## 3. El loop mínimo de un agente

El núcleo del ejemplo es un `while (true)`:

```text
Usuario
   │
   ▼
Enviar historial + herramientas al modelo
   │
   ▼
¿El modelo pidió herramientas?
   ├── No ──► devolver respuesta final
   │
   └── Sí
         │
         ▼
      ejecutar herramientas en el runtime
         │
         ▼
      agregar resultados al historial
         │
         └──────────────► volver a llamar al modelo
```

Ante un saludo como “hola”, probablemente haya una sola iteración. Ante una
pregunta como “¿qué clima hace en Buenos Aires?”, el flujo puede ser:

1. El usuario agrega su pregunta al historial.
2. El modelo devuelve una solicitud para ejecutar `get_weather`.
3. La aplicación guarda esa solicitud en el historial.
4. La aplicación ejecuta la función local.
5. El resultado se agrega al historial asociado al identificador de la llamada.
6. El modelo recibe nuevamente todo el contexto.
7. El modelo produce una respuesta final y termina el loop.

El modelo **no ejecuta la función**. Solo devuelve una estructura indicando qué
herramienta quiere usar y con qué argumentos. La aplicación valida la solicitud,
ejecuta código real y devuelve el resultado.

## 4. Cómo se describe una herramienta

Al proveedor no se le envía la implementación de `getWeather`. Se le envía una
descripción:

- nombre de la herramienta;
- propósito;
- esquema JSON de los argumentos;
- campos requeridos;
- restricciones adicionales.

La descripción funciona como parte de las instrucciones del modelo. Si es ambigua,
el modelo puede usar la herramienta en un momento incorrecto, enviar argumentos
inválidos o no usarla cuando corresponde.

El resultado de una herramienta también debe ser informativo. Un error como
`OpenWeatherMap returned 401` es más útil que un simple `false`: permite que el
modelo decida si debe reintentar, cambiar de estrategia o explicar el problema.

Una respuesta del modelo puede incluir varias llamadas en el mismo turno. Por
ejemplo, una consulta por el clima de Buenos Aires y Nueva York puede generar dos
tool calls. El runtime puede ejecutarlas secuencialmente, como en estos ejemplos,
o en paralelo si son independientes.

## 5. Responses API y Chat Completions API

Ambas APIs permiten construir el mismo loop, pero sus contratos no son
intercambiables.

### OpenAI Responses API

El request usa `input`:

```js
const response = await client.responses.create({
  model: MODEL,
  input: history,
  tools: TOOLS,
  reasoning: { effort: "high" },
  max_output_tokens: 8000,
});
```

`response.output` es un array de items tipados. Puede contener, entre otros:

- un item de reasoning;
- un mensaje del assistant;
- una o varias llamadas `function_call`.

Por eso el ejemplo agrega todos los items con spread:

```js
history.push(...response.output);
```

Las llamadas se encuentran filtrando el array:

```js
const toolCalls = response.output.filter(
  (item) => item.type === "function_call",
);
```

El resultado de cada herramienta vuelve como otro item:

```js
history.push({
  type: "function_call_output",
  call_id: toolCall.call_id,
  output: toolOutput,
});
```

La propiedad `response.output_text` es una conveniencia del SDK para obtener el
texto final sin recorrer manualmente todos los items.

### DeepSeek con Chat Completions

El request usa `messages`:

```js
const response = await client.chat.completions.create({
  model: MODEL,
  messages: history,
  tools: TOOLS,
  thinking: { type: "enabled" },
  reasoning_effort: "high",
  max_tokens: 8000,
});
```

Chat Completions devuelve alternativas en `choices`. En el ejemplo se utiliza la
primera:

```js
const message = response.choices[0].message;
history.push(message);
```

`message` es un objeto, no un array. Puede contener simultáneamente:

```js
{
  role: "assistant",
  content: "...",
  reasoning_content: "...",
  tool_calls: [
    {
      id: "call_123",
      type: "function",
      function: {
        name: "get_weather",
        arguments: "{\"city\":\"Buenos Aires,AR\"}"
      }
    }
  ]
}
```

Que sea un solo objeto no limita la respuesta a una sola operación:
`message.tool_calls` es un array y puede contener múltiples llamadas.

El resultado se representa como un mensaje con rol `tool`:

```js
history.push({
  role: "tool",
  tool_call_id: toolCall.id,
  content: toolOutput,
});
```

### Equivalencias principales

- Request: `input` en Responses; `messages` en Chat Completions.
- Salida: `response.output` en Responses; `response.choices[0].message` en Chat
  Completions.
- Tool call: item `function_call` en Responses; elemento de
  `message.tool_calls` en Chat Completions.
- Tool output: item `function_call_output` en Responses; mensaje con rol `tool`
  en Chat Completions.
- ID de llamada: `call_id` en Responses; `tool_call_id` en el resultado de Chat
  Completions.
- Límite de salida: `max_output_tokens` en Responses; `max_tokens` en este
  ejemplo de Chat Completions.
- Historial: `history.push(...response.output)` en Responses;
  `history.push(response.choices[0].message)` en Chat Completions.

La estructura de definición de herramientas también cambia:

```js
// Responses API
{
  type: "function",
  name: "get_weather",
  description: "...",
  parameters: { /* ... */ }
}
```

```js
// Chat Completions
{
  type: "function",
  function: {
    name: "get_weather",
    description: "...",
    parameters: { /* ... */ }
  }
}
```

No conviene mezclar ambas representaciones. Campos como `input`,
`response.output` y `function_call_output` pertenecen al protocolo de Responses;
`messages`, `choices`, `tool_calls` y el rol `tool` pertenecen al protocolo de
Chat Completions.

## 6. Reasoning: resumen, estado y visibilidad

Los modelos de razonamiento usan tokens internos para analizar el problema antes
de producir la respuesta final. Aumentar `reasoning_effort` puede mejorar la
calidad en tareas complejas, pero suele aumentar latencia y costo. No garantiza
por sí solo una respuesta correcta.

### OpenAI

En Responses API, el reasoning aparece como un item separado dentro de
`response.output`. OpenAI puede exponer un **summary** del razonamiento, pero no el
chain of thought interno completo en texto legible.

Dependiendo del modelo y de la configuración, un item de reasoning puede contener
estado opaco o `encrypted_content` para poder conservarlo y reenviarlo sin revelar
el razonamiento interno. No debe asumirse que todo reasoning de OpenAI siempre
llega encriptado ni que el summary equivale al razonamiento completo.

La regla segura para este loop es preservar los items devueltos por la API:

```js
history.push(...response.output);
```

De esta forma, cualquier estado de reasoning necesario para continuar una cadena
de tool calls se devuelve intacto al proveedor.

### DeepSeek

En Thinking Mode, DeepSeek devuelve `reasoning_content` junto a `content` dentro
del mensaje del assistant. Esto permite inspeccionar el texto de razonamiento que
el proveedor decide exponer:

```js
const message = response.choices[0].message;

console.log(message.reasoning_content);
console.log(message.content);
```

Según la documentación de DeepSeek:

- si no hubo tool calls, el reasoning anterior no necesita participar en el
  próximo turno y será ignorado si se envía;
- si hubo tool calls, `reasoning_content` debe conservarse y reenviarse en las
  solicitudes siguientes.

Agregar el mensaje completo resuelve ambos casos:

```js
history.push(message);
```

La diferencia de visibilidad entre proveedores no cambia el principio general:
el runtime debe preservar el estado que el protocolo exige, aunque no deba
mostrarlo al usuario final.

## 7. Contexto, memoria y compactación

Cada modelo tiene una ventana de contexto limitada. Por eso una conversación no
puede crecer para siempre.

Las estrategias posibles incluyen:

- conservar todo mientras entre en la ventana;
- mantener una ventana de mensajes recientes;
- resumir mensajes antiguos;
- extraer hechos importantes a una memoria persistente;
- recuperar información relevante bajo demanda;
- combinar resumen, mensajes recientes y memoria externa.

Una compactación típica puede reconstruir el contexto con:

1. las instrucciones de sistema;
2. un resumen detallado de la conversación antigua;
3. los últimos mensajes completos.

La compactación la realiza el runtime de la aplicación, no el modelo de forma
automática. Además es una transformación con pérdida: un resumen puede omitir un
detalle que después resulte importante.

El resumen histórico debe presentarse claramente como contexto, no como una nueva
orden del usuario. Usar `system` puede darle mayor prioridad, pero también mezcla
instrucciones con datos históricos. En una implementación real conviene elegir el
rol y la estructura según el proveedor, separar instrucciones de datos y tratar
como no confiable cualquier contenido proveniente del usuario.

## 8. Context caching y costos

Los proveedores pueden reutilizar cómputo cuando requests consecutivos comparten
un prefijo idéntico. Para favorecer el cache:

- mantener las instrucciones estables al comienzo;
- no insertar timestamps, IDs aleatorios u otros valores variables en el prefijo;
- conservar el orden del historial;
- agregar nueva información al final;
- evitar compactaciones innecesariamente frecuentes.

El cache no evita enviar el historial: reduce el costo o el cómputo asociado a los
tokens del prefijo que el proveedor reconoce.

Hay una precisión matemática importante:

- el tamaño del input de **cada request** crece aproximadamente de forma lineal a
  medida que se acumula el historial;
- el costo **acumulado de muchos turnos**, sin cache, puede crecer
  aproximadamente de forma cuadrática porque cada request vuelve a incluir lo
  anterior;
- no es correcto describir el tamaño de cada request individual como
  exponencial.

Modificar un mensaje antiguo puede invalidar el cache desde ese punto del
prefijo, pero agregar mensajes al final es justamente el patrón que permite
reutilizar el prefijo previo. Los descuentos, mínimos de tokens y reglas exactas
dependen del proveedor y del modelo, por lo que deben consultarse en la
documentación y pricing vigentes.

Compactar cada pocos mensajes suele sacrificar cache y contexto demasiado pronto.
Una estrategia razonable es establecer umbrales de tokens y compactar cuando el
costo, la calidad o la ventana de contexto lo justifiquen, midiendo el resultado
en lugar de aplicar una frecuencia fija.

## 9. Controles necesarios en agentes reales

Un `while (true)` es didáctico, pero una implementación de producción necesita
límites y observabilidad:

- máximo de iteraciones o tool calls;
- timeout total y por herramienta;
- cancelación y propagación de señales;
- presupuesto máximo de tokens o dinero;
- allowlist de herramientas;
- validación estricta de argumentos;
- permisos por usuario y por acción;
- confirmación humana para operaciones destructivas;
- idempotencia y políticas de reintento;
- registro de trazas y métricas;
- estrategia explícita para conservar o descartar un turno cancelado.

Los errores de las tools deben regresar al loop como resultados estructurados.
Eso permite que el modelo observe el problema, pero no implica que deba tener
reintentos ilimitados.

## 10. Agentes de largo horizonte, subagentes y evaluación

Un agente puede trabajar durante muchos minutos y encadenar lectura de archivos,
comandos, edición, búsquedas y pruebas. Cuanto más largo es el horizonte, mayor es
la necesidad de:

- planes y checkpoints;
- trazas legibles;
- límites de presupuesto;
- recuperación ante fallos;
- detección de loops;
- intervención humana.

Una tool también puede iniciar otro loop con un modelo especializado. Así se
construyen subagentes: el agente principal delega y recibe el resultado como si
fuera el output de otra herramienta. La delegación no elimina la necesidad de
definir responsabilidades, límites y contratos claros.

Debido a que un agente puede elegir rutas distintas entre ejecuciones, los tests
tradicionales no alcanzan. Los EVALs permiten medir sistemáticamente:

- si eligió la herramienta correcta;
- si respetó el orden o las restricciones esperadas;
- si usó argumentos válidos;
- si resolvió el objetivo;
- cuánto costó;
- cuántas iteraciones necesitó;
- cómo reaccionó ante errores.

Es importante evaluar múltiples ejecuciones y conservar las trazas. Cambios
pequeños en el system prompt o en una tool description pueden cambiar
considerablemente el comportamiento.

## 11. Ejecutar los ejemplos

### Requisitos

- Node.js con soporte para ES modules y `fetch`;
- una API key de OpenAI;
- una API key de DeepSeek;
- una API key de OpenWeatherMap.

Instalar dependencias desde la raíz del repositorio:

```bash
npm install
```

Crear `.env` a partir de `.env.example` y completar:

```dotenv
OPENAI_API_KEY=
OPENAI_MODEL=
DEEPSEEK_API_KEY=
OPENWEATHER_KEY=
```

Ejecutar OpenAI Responses API:

```bash
node w01-agent-loop/openai-responses-api.js
```

Ejecutar DeepSeek Chat Completions:

```bash
node w01-agent-loop/deepseek-completions-api.js
```

Pruebas sugeridas:

```text
hola
```

```text
¿Qué clima hace en Buenos Aires?
```

```text
Compará el clima de Buenos Aires y Nueva York.
```

La primera consulta permite observar una respuesta sin tools. La segunda muestra
una tool call. La tercera permite verificar si el modelo solicita múltiples
herramientas en un mismo turno.

## 12. Ideas principales del encuentro

1. Un agente es un sistema: modelo + loop + tools + estado + controles.
2. La agencia consiste en decidir dinámicamente el próximo paso.
3. El modelo solicita herramientas; el runtime las ejecuta.
4. El historial pertenece a la aplicación y debe reenviarse porque la API es
   stateless.
5. Responses y Chat Completions expresan conceptos parecidos con estructuras
   diferentes.
6. El estado de reasoning debe conservarse según el contrato del proveedor.
7. Las tool descriptions y sus errores forman parte de la interfaz con el modelo.
8. El context cache favorece prefijos estables, pero no reemplaza una estrategia
   de memoria.
9. La compactación debe dispararse por métricas y umbrales, no por una frecuencia
   arbitraria.
10. Los agentes necesitan límites, trazas y EVALs para operar de forma confiable.

## Referencias

- [OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses)
- [OpenAI: migrar a Responses API](https://platform.openai.com/docs/guides/migrate-to-responses)
- [OpenAI: Reasoning models](https://platform.openai.com/docs/guides/reasoning)
- [OpenAI: Prompt caching](https://platform.openai.com/docs/guides/prompt-caching)
- [DeepSeek: Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode)
- [DeepSeek: Multi-round Conversation](https://api-docs.deepseek.com/guides/multi_round_chat)
- [DeepSeek: Tool Calls](https://api-docs.deepseek.com/guides/tool_calls)
- [DeepSeek: Context Caching](https://api-docs.deepseek.com/guides/kv_cache)
- [Anthropic: Building effective agents](https://www.anthropic.com/research/building-effective-agents)
- [Anthropic: Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)
