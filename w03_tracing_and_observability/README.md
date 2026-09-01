# Workshop 03 — Tracing y observabilidad

Las respuestas muestran qué produjo el agente. Los traces aportan la evidencia
para entender cómo llegó, dónde falló y cómo mejorarlo.

Este directorio es el material de demo de W03: un asistente bancario con datos
mockeados, pensado para encadenar tools, y una capa de instrumentación que envía
esas ejecuciones a Langfuse cuando hay credenciales.

El marco conceptual (session, trace, span, qué medir, dónde observar) está en
[`speech.md`](../w03_tracing_observability_presentation/speech.md) y
[`outline.md`](../w03_tracing_observability_presentation/outline.md). Acá está
la implementación.

## 1. Qué hay que poder explicar

Un agente no es una sola llamada al modelo. En un turno puede haber varias
llamadas LLM, selección de tools, argumentos, resultados, reintentos y una
respuesta final. Monitoring avisa que subió la latencia o que hubo un error.
Observability permite reconstruir el camino.

Tres niveles:

| Nivel | Qué agrupa | Pregunta típica |
| --- | --- | --- |
| Session | Varios traces relacionados (una conversación) | ¿El usuario resolvió el trámite en esta charla? |
| Trace | Una ejecución autocontenida (un turno) | ¿Qué tools usó y en qué orden? |
| Span | Una unidad de trabajo (LLM, tool, HTTP) | ¿Dónde se fue el tiempo o el error? |

ADK Web sirve para inspeccionar en el momento. Langfuse persiste las mismas
preguntas entre ejecuciones: comparar turnos, agrupar por session y buscar
patrones.

## 2. El agente de demo

[`agent.py`](./agent.py) es un asistente de atención al cliente de un banco.
El usuario ya está logueado: el harness siembra `customer_id` en el estado de
la sesión. El modelo nunca recibe ni pasa ese id; cada tool lo lee de
`tool_context`.

Tres decisiones de diseño que importan al mirar el trace:

1. **Las reglas de negocio viven en las tools**, no en el prompt. Umbrales de
   bonificación, plazos y qué gestiones están permitidas se deciden en código.
   El LLM orquesta; las tools deciden. Si los umbrales estuvieran también en la
   instruction habría dos fuentes de verdad.
2. **Solicitar y confirmar son dos tools.** Un upgrade, una cuenta comitente o
   una promesa de pago primero generan un `operation_id` (`request_*`). Recién
   después de un sí explícito se llama a `confirm_*`. En el trace se ve el
   patrón: preparar, mostrar resumen, esperar, ejecutar.
3. **Minimización de datos.** Ninguna tool devuelve cuánto gana el cliente ni
   cuánto tiene invertido. Devuelven la decisión (a qué paquetes accede) y el
   requisito publicado. Todo lo que una tool retorna entra al próximo
   `call_llm` y queda escrito en el trace: el trace es también una superficie
   de PII.

El cliente mock (`cust_1042`, Roman) **no acredita haberes**, tiene paquete
silver, Visa vencida e impaga, Mastercard sin consumos, y todavía no pidió
cuenta comitente. Eso fuerza cadenas de tools: para explicar por qué le cobran
el paquete hay que llamar a `get_package_options`; para invertir, hay que abrir
comitente y recordar que la encuesta la completa el usuario.

## 3. Dónde vive la observabilidad

La instrumentación corre en [`__init__.py`](./__init__.py), no en `agent.py`.
Tiene que ejecutarse **antes** de que ADK importe y corra el agente.

Al importar el paquete:

1. Carga `.env` de esta carpeta y, si hace falta, el de la raíz del repo.
2. Si hay `LANGFUSE_PUBLIC_KEY` y `LANGFUSE_SECRET_KEY`, autentica contra
   Langfuse e instrumenta Google ADK con OpenInference.
3. Recién entonces importa `agent`.

Sin keys, ADK Web sigue andando. Solo no se envían traces al dashboard.

```text
Agente (ADK)
   │
   ▼
GoogleADKInstrumentor (OpenInference)
   │
   ▼
OpenTelemetry
   │
   ├── ADK Web   (inspección local)
   └── Langfuse  (si hay credenciales)
```

## 4. Cómo correrlo

### Requisitos

- Python 3.12 o superior
- una API key de Google Gemini (`GOOGLE_API_KEY`)
- opcional: keys de Langfuse para persistir traces

### Setup

Desde la raíz del repositorio:

```bash
pip install -r w03_tracing_and_observability/requirements.txt
cp w03_tracing_and_observability/.env.example w03_tracing_and_observability/.env
```

Completar en `.env`:

```dotenv
GOOGLE_API_KEY=

# Opcional. Settings → API Keys en Langfuse.
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

También se pueden poner esas variables en el `.env` de la raíz. El paquete no
pisa variables ya definidas en el shell.

### Correr

Desde la raíz del repo:

```bash
adk web
```

Elegir el agente `w03_tracing_and_observability` (`asistente_banco`).

Si Langfuse está bien configurado, en la consola debería aparecer
`Langfuse OK — traces visibles en el dashboard`. Si no, el mensaje indica qué
falta y la UI local funciona igual.

## 5. Qué probar y qué mirar

Cada prompt debería generar un camino distinto en el trace. No hay un orden
fijo en el prompt: el modelo encadena tools según lo que pide el usuario y lo
que van devolviendo las tools.

```text
¿Por qué me cobran el paquete de tarjetas?
```

Debería llamar a `get_package_options`. El resultado dice que silver no está
bonificado y cuál es el requisito publicado. No deberían aparecer haberes ni
inversiones del cliente.

```text
Quiero pasar a gold.
```

Debería preparar el cambio con `request_package_upgrade`, mostrar costo y
efectos, y **no** confirmar hasta un sí explícito. Después de confirmar,
`confirm_package_upgrade` consume el `operation_id`: un segundo intento falla
en lugar de emitir plásticos dos veces.

```text
Abrime una cuenta para invertir.
```

`request_investment_account` / `confirm_investment_account`. En el resultado
queda pendiente la encuesta de perfil de inversor, que el asistente no puede
completar.

```text
El resumen de la Visa está vencido. Puedo pagar el 20 de este mes?
```

`get_card_statement` y, si aplica, `request_payment_promise`. La tool valida
plazo (máximo 30 días) y estado `vencido_impago`. Los intereses siguen
devengándose: tiene que decirlo antes de confirmar.

```text
No reconozco un consumo de la Mastercard.
```

Debería ir a `escalate_to_human` en vez de intentar resolver fraude.

En **ADK Web**: llamadas al modelo, tools, argumentos, resultados y tiempos de
ese turno.

En **Langfuse**: la misma jerarquía session → traces → spans, persistida. Varios
turnos de la misma conversación deberían agruparse. Sirve para comparar “por qué
me cobran” (una tool de lectura) contra “pasame a gold” (request + confirm).

## 6. Ideas principales del encuentro

1. La respuesta final no alcanza para operar un agente; hace falta el camino.
2. Session, trace y span permiten preguntar en el nivel correcto.
3. Instrumentar el framework cubre LLM y tools; las reglas de negocio siguen
   viviendo en código.
4. Todo lo que una tool devuelve puede quedar en el próximo prompt y en el
   trace: minimizar PII es parte de observar.
5. ADK Web inspecciona; Langfuse (u otro backend OTel) persiste y agrega.
6. Las herramientas cambian; las preguntas no: qué hizo, por qué, cuánto costó,
   qué tan bien funcionó y cómo mejorarlo.

## Referencias

- [Google ADK](https://google.github.io/adk-docs/)
- [OpenTelemetry: traces](https://opentelemetry.io/docs/concepts/signals/traces/)
- [OpenInference](https://arize.com/docs/phoenix/learn/tracing/what-are-traces)
- [Langfuse: observability](https://langfuse.com/docs/observability/overview)
- [Langfuse + Google ADK](https://langfuse.com/integrations/frameworks/google-adk)
