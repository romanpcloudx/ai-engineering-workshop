# Resumen del workshop 04 — Skills y progressive disclosure

Fuente: transcripción del workshop interno sobre skills de agentes. La sesión
combinó teoría sobre el origen del patrón con una demo en vivo en un agente
propio: loop simple con DeepSeek vía OpenRouter y una skill de "patos".

## 1. La skill es un índice, no un archivador

El system prompt siempre lleva sólo el índice de skills: nombre y descripción,
tomados del frontmatter de cada `SKILL.md`. El cuerpo completo se carga on demand
con una tool cuando la tarea lo pide.

La analogía de la sesión fue una biblioteca con un índice: no leés toda la
biblioteca antes de encarar una tarea; vas directo al libro que necesitás. El
índice es barato y está siempre. El cuerpo se paga sólo cuando hace falta. Con 5
o 50 skills, lo que entra inicialmente al prompt sigue siendo una lista breve.

## 2. Un system prompt gordo cobra dos veces

El costo visible son los tokens. Un agente puede iterar 10 o 15 veces por
objetivo y en cada llamada reenvía todo el system prompt, incluso explicaciones
que la tarea actual no usa.

El costo invisible, y peor, es el sesgo. Cada palabra del prompt condiciona al
modelo: basta un renglón como "me gustan las bases de datos no relacionales" para
que una tarea que pedía Postgres termine en Mongo. Regla derivada: al prompt sólo
va lo mínimo y lo que es verdadero siempre; el resto entra por otros mecanismos.

## 3. El test de decisión: verdad siempre vs. verdad a veces

Si el conocimiento es transversal a cualquier interacción —quién es el agente o
cómo contesta— va en el system prompt, que debe ser corto. Si es específico de
una tarea —buenas prácticas de Next, cómo reportar un incidente o procesos
internos del equipo— va en una skill.

La skill no compite con el prompt: existe en el índice, pero no ocupa contexto
real hasta que es relevante. Una sesión larga puede terminar sin cargar ninguna
skill y eso es un éxito del patrón, no un desperdicio.

## 4. La implementación es casi trivial

Hay tres piezas:

1. Recorrer la carpeta de skills y parsear el frontmatter.
2. Inyectar ese índice como string al final del system prompt.
3. Exponer una tool `load_skill(name)` que devuelve el cuerpo como output.

Opcionalmente, una segunda tool carga archivos de referencia. No hay magia: el
modelo decide cuándo cargar mirando el índice y el harness ejecuta.

En la demo, una pregunta por patos azules produjo tres iteraciones: primero se
cargó el cuerpo de la skill; después, `references/patos-azules.md`; finalmente,
el modelo respondió. La referencia de otro tipo de pato nunca entró al contexto
porque no hacía falta.

## 5. References: el mismo patrón dentro de la skill

El cuerpo puede contener un segundo índice: por ejemplo, "si preguntan por patos
azules, leé `references/patos-azules.md`; si preguntan por negros, leé su archivo
correspondiente".

`SKILL.md` es lo único obligatorio. `references/`, `scripts/` y `assets/` son
opcionales. Para skills grandes conviene un cuerpo chico y muchas referencias
chicas: se carga un archivo por tema y el resto nunca entra. Una única skill de
500 líneas es el camino malo.

## 6. El mapa: prompt, skill, tools/MCP y subagente

- **Prompt:** quién es el agente y cómo contesta; está siempre en contexto.
- **Skill:** cómo se hace una tarea puntual; entra a veces en contexto.
- **Tools/MCP:** capacidades externas que el modelo no obtiene por leer
  documentación, como consultar clima o actuar sobre APIs. Conviene una tool
  propia si se puede; MCP sirve para exponer capacidades a otros agentes. Una
  skill con script puede ser un parche cuando no se pueden crear tools.
- **Subagente:** otro loop con contexto propio que devuelve sólo el resultado
  valioso, como un consultor que entrega el informe sin narrar todo el proceso.

Todo el ecosistema gira alrededor de un recurso escaso: el contexto.

## 7. Anti-patrones y el caso Google ADK

Anti-patrones:

- Volcar todo al system prompt.
- Describir qué es la skill en vez de cuándo usarla. La descripción dispara su
  uso; con 30 skills, una descripción mala puede hacer que nunca se cargue.
- Escribir un `SKILL.md` gigante.
- Cargar todas las skills al arrancar la sesión.
- Acumular tantas skills que el índice se vuelve ruido, igual que con demasiadas
  tools.

Los scripts son código determinista que corre sin entrar al contexto y debería
tener un output predecible.

En el caso comentado de Google ADK, el índice se expone mediante una tool que
lista frontmatters. El agente no sabe qué skills existen hasta llamarla y puede
terminar haciéndolo incluso ante un "hola". La carga dinámica puede tener sentido
para agentes de larga vida que atraviesan fases —arquitectura, implementación,
test y deploy—, pero para esta demo agrega una vuelta innecesaria.

## Bonus: checklist para escribir una skill

- Usar conocimiento genuinamente propio. Si está en internet, el modelo ya puede
  conocerlo o buscarlo.
- Escribir la descripción como contexto de uso, no como definición.
- Preferir cuerpo corto y referencias por tema antes que un monolito.
- Usar scripts sólo para pasos deterministas y con output estable.
- Mantener pocas skills: el índice también cuesta.

## Nota abierta

Todavía falta una forma estándar de distribuir skills de sólo lectura, como un
marketplace. Hoy se comparten carpetas o enlaces y cada persona puede editarlas.
El ecosistema sigue emergiendo; el frontmatter de `SKILL.md` es la parte más
portable entre agentes como Claude Code, Codex y agentes propios.
