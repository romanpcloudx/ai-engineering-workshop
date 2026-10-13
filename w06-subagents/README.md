# Workshop 06 — Subagentes y scope separation

## Material

- [Presentación — Subagentes & Scope Separation](./subagentes-scope-separation.pptx)
- [Transcripción del workshop (VTT)](./workshop-06.vtt)
- [Agente usado en la demo](https://github.com/GBurgardt/tools-workshop-agent)

## Qué vimos

Por qué separar trabajo en otro contexto, cómo implementan subagentes los
distintos harnesses y cómo hacerlo con un loop manual.

La demo delega una tarea a `researcher`: historial nuevo, instrucciones propias,
sólo `search_web` y un máximo de ocho llamadas al modelo. El padre espera y
recibe el informe, no las búsquedas intermedias.

## Código para seguir la clase

1. `src/agent.js`: agrega `run_subagent` al catálogo del padre.
2. `src/subagent.js`: perfil, contrato, historial del hijo y retorno del informe.
3. `src/agent-loop.js`: loop compartido, ejecución de tools y resultados.

Es el mismo agente de W02 y W04. No se duplica su código en este repositorio.

La transcripción conserva el archivo original de la sesión, sin correcciones.
