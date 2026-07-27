# Informe — Milestone 2: Memoria, prompting y robustez

**Proyecto:** tp_mia_agentes_2026
**Autores:** Hugo Cabaña, Oscar
**Repositorio:** [HugoCabana/tp_mia_agentes_2026](https://github.com/HugoCabana/tp_mia_agentes_2026)

---

## 1. Estrategia de memoria

* Implementado en `student_framework/agent.py`

### Statefulness

El agente pasó de ser *stateless* (M1) a mantener conversación entre llamadas: `MyAgent` guarda un historial persistente (`self._history`) que se acumula en cada llamada a `run(...)` sobre la misma instancia. La fachada externa (`build_agent`, `register_tool`, `run`) no cambió.

### Sliding window por unidades atómicas

El constructor acepta `max_history_messages`. Antes de cada llamada a `chat(...)`, el historial completo se recorta con una ventana deslizante que nunca envía más mensajes que ese tope.

La estrategia elegida agrupa el historial en **unidades atómicas** antes de recortar:

- Un mensaje `assistant` que incluye `tool_calls` **no puede separarse** de los mensajes `tool` que le siguen inmediatamente: juntos forman una sola "jugada" (pedido de herramienta + resultado). Cortar ese par rompería el historial para providers reales (por ejemplo, Bedrock exige que todo `toolUse` tenga su `toolResult` inmediatamente después) y confundiría al modelo con un pedido de tool sin respuesta.
- El resto de los mensajes (`user`, y `assistant` de cierre sin tool calls) son unidades de a uno.

Con esas unidades armadas, se recorren desde la más reciente hacia atrás, acumulando mientras entren en el presupuesto, y se descartan las más antiguas que no entran. Como el mensaje de usuario recién agregado es siempre la última unidad del historial, queda garantizado que entra en la ventana mientras el presupuesto alcance para al menos una unidad.

**Por qué esta estrategia y no otra:** se evaluó "recortar por cantidad de mensajes" a secas (más simple), pero se descartó porque puede partir un par `tool_call`/`tool_result` a la mitad, dejando un `assistant` con una llamada a herramienta "colgada" sin su resultado. Se evaluó también *summarization* (resumir los turnos viejos en un mensaje de sistema), pero se descartó para esta entrega por la complejidad adicional de mantener un resumen actualizado y consistente con llamadas a tools, y porque requeriría una llamada extra al LLM (costo de tokens y latencia) solo para mantener la memoria. *Offload/retrieve* (guardar turnos viejos afuera y recuperarlos por relevancia) tampoco se justificaba para el alcance de este trabajo, al no haber un caso de uso que necesite recuperar contexto antiguo específico. La sliding window atómica es la opción más simple que cumple la invariante de recencia sin romper la estructura de tool calls.

### Invariante de recencia

El mensaje de usuario más reciente siempre aparece en la próxima llamada al LLM, porque es la última unidad agregada al historial antes de armar la ventana, y el algoritmo prioriza las unidades más nuevas.

### Problemas encontrados

- **Caso límite documentado:** si una única unidad atómica (por ejemplo, un tramo largo dentro de una misma jugada de tool calls) excede ella sola el presupuesto configurado, se trunca esa unidad conservando su cola más reciente. En ese caso puede perderse la correlación `toolUse`/`toolResult` más antigua dentro de esa unidad puntual. Se dejó documentado como limitación conocida (ver sección 4) en lugar de resolverlo con lógica adicional, dado que no ocurre con los tamaños de `max_history_messages` usados en los tests ni en el uso normal del agente.
- El historial completo (`self._history`) no se recorta a sí mismo, solo se recorta la vista que se envía al LLM en cada llamada. Esto simplifica la implementación pero implica que el historial en memoria del proceso crece sin límite a lo largo de una conversación muy larga (ver sección 4).

---

## 2. Salida estructurada

* Implementado en `student_framework/agent.py`

### Cómo se ofrece `final_result` al LLM

`structured_call(prompt, schema, max_repair_attempts=2)` arma una sub-conversación acotada (independiente de `self._history`, para no contaminar la memoria de la conversación principal con intentos de reparación fallidos) y ofrece al LLM una única tool disponible: la tool sintética `final_result`, generada a partir del `schema` de Pydantic provisto vía `final_result_tool_schema(schema)` (definida en `mia_agents.tool_schema`, nombre fijo `FINAL_RESULT_TOOL_NAME`). Esto obliga al modelo a responder invocando esa tool en lugar de texto libre.

### Cómo se validan los argumentos

Cuando la respuesta del LLM incluye una `tool_call` a `final_result`:

1. Se parsean sus argumentos como JSON (`json.loads`).
2. Se validan contra el `schema` de Pydantic con `schema.model_validate(...)`.

Si ambos pasos son exitosos, `structured_call` devuelve la instancia validada del schema.

### Cómo se reparan los fallos

Ante cualquiera de estos tres casos:

- el modelo respondió con texto libre en vez de invocar `final_result`,
- los argumentos no son JSON válido,
- los argumentos no cumplen el schema (`ValidationError`),

se arma un turno de reparación: se agrega a la sub-conversación el mensaje `assistant` con la tool call fallida (cuando existió) y un mensaje `tool` con un error descriptivo y accionable (qué se esperaba, qué se recibió, qué corregir), y se vuelve a llamar al LLM. Esto le da al modelo el contexto exacto de por qué falló para poder corregirse.

### Qué pasa cuando se agotan los reintentos

`max_repair_attempts` define cuántas reparaciones se permiten además del intento inicial (`max_repair_attempts=2` → hasta 3 llamadas totales al LLM). Si tras agotar todos los intentos ninguno produjo una salida válida, `structured_call` levanta `StructuredOutputError` (subclase de `RuntimeError`) con el detalle del último error de validación — falla limpiamente en lugar de devolver un resultado inconsistente o silenciar el problema.

### Verificación

- Reparación exitosa: primer intento con argumentos con tipos inválidos → falla la validación → segundo intento corrige → se recupera. Verificado que solo se hacen 2 llamadas al LLM (no se gastan reintentos de más una vez lograda la validación).
- Agotamiento: 3 respuestas seguidas en texto libre con `max_repair_attempts=2` → se agota en el 3° intento y se levanta `StructuredOutputError` (1 inicial + 2 reparaciones = 3 llamadas).

---

## 3. Errores en herramientas

* Implementado en `student_framework/tools/calculadora.py` y `student_framework/tools/lector_archivo.py`

El criterio general aplicado: cada error recuperable devuelve un mensaje que indica **qué falló, qué valor se recibió y cómo corregirlo**, para que el LLM pueda reintentar con argumentos válidos sin intervención humana. Los errores no recuperables (bugs inesperados de la tool, argumentos con nombres incompatibles con la firma) se manejan aparte, en el agente (`_invoke_tool`, sección de resiliencia), que los captura y también los devuelve como mensaje accionable en vez de romper el `run`.

### Calculadora (`calculadora.py`)

| Error recuperable | Información devuelta |
|---|---|
| Operando no numérico | Qué parámetro falló (`a` o `b`), qué valor y tipo se recibió, y ejemplo de valor válido |
| Operador no soportado | Lista dinámica de los operadores permitidos (`+`, `-`, `*`, `/`, `%`), generada desde la tabla de operadores real (nunca queda desactualizada) |
| División o módulo por cero | Mensaje específico por operador explicando la restricción matemática (no un genérico "error de cálculo") |

**Ejemplo concreto de recuperación:** el LLM llama a la calculadora con `{"a": "diez", "b": 2, "operador": "+"}`. La tool detecta que `a` no es convertible a número y devuelve:
> `Error en el parámetro 'a': el valor recibido ('diez', tipo str) no es un número válido. Enviá 'a' como número (int o float), p. ej. 3 o 3.5.`

El LLM recibe ese mensaje como resultado de la tool, entiende que debía enviar `10` en vez de `"diez"`, y reintenta con `{"a": 10, "b": 2, "operador": "+"}`, que se resuelve correctamente.

### Lector de archivos (`lector_archivo.py`)

| Error recuperable | Información devuelta |
|---|---|
| Ruta vacía | Indica que no puede estar vacía y da un ejemplo de ruta relativa válida |
| Ruta absoluta | Señala que las rutas absolutas no están permitidas y cómo expresarla en forma relativa |
| Ruta con `..` / que escapa del sandbox | Explica que ese patrón permitiría salir del directorio de trabajo permitido, y pide una ruta relativa que se quede adentro |
| Archivo inexistente | Si el directorio contenedor existe, **lista los archivos disponibles ahí** para que el LLM elija la ruta correcta |
| La ruta apunta a un directorio | Lo indica explícitamente y **lista el contenido de ese directorio** |

**Ejemplo concreto de recuperación:** el LLM pide leer `"datos/reporte.txt"`, que no existe, pero el directorio `datos/` sí. La tool devuelve:
> `Error: el archivo 'datos/reporte.txt' no existe en 'datos'. Archivos disponibles ahí: notas.txt, resumen.txt.`

El LLM ve los nombres reales disponibles en `datos/` y reintenta con `"datos/resumen.txt"`, que existe y se lee correctamente — sin necesitar que un humano intervenga para corregir la ruta.

---

## 4. Modos de fallo: dentro vs. fuera de alcance

### Dentro de alcance (cubierto en esta entrega)

- Fallos transitorios del cliente LLM (timeouts, 5xx, rate limits, excepciones de red): reintentados automáticamente con backoff exponencial corto (3 intentos) antes de propagar el fallo.
- Fallo persistente del LLM tras agotar reintentos: `run(...)` no crashea; devuelve un `AgentResult` con `answer` explicativo no vacío y `error` seteado.
- Tool inexistente, argumentos malformados (JSON inválido, tipos incompatibles con la firma) o excepción inesperada dentro de una tool: capturados y devueltos como mensaje accionable al LLM, sin interrumpir el `run`.
- Argumentos inválidos "de negocio" en calculadora y lector de archivos (operandos no numéricos, operador no soportado, división por cero, rutas fuera del sandbox, archivo inexistente, ruta-es-directorio): mensajes accionables específicos por caso.
- Historial que supera el presupuesto de contexto en conversaciones largas: manejado con sliding window atómica sin romper la estructura de tool calls ni perder el mensaje de usuario más reciente.
- Salida estructurada rota (texto libre en vez de tool call, JSON inválido, schema inválido): reparación acotada por `max_repair_attempts`, con fallo limpio (`StructuredOutputError`) si se agotan los intentos.

### Deliberadamente fuera de alcance

- **Crecimiento ilimitado de `self._history` en memoria de proceso:** solo se recorta la *vista* enviada al LLM, no el historial persistido en el objeto `MyAgent`. Para conversaciones extremadamente largas (miles de turnos) esto puede crecer de forma no acotada en RAM. No se abordó porque excede el alcance de M2 (no hay persistencia a disco/DB pedida) y no afecta la corrección de las respuestas, solo el uso de memoria del proceso.
- **Truncamiento interno de una unidad atómica que por sí sola excede el presupuesto:** caso límite de la sliding window (ver sección 1) que puede dejar un `toolUse` sin su `toolResult` correspondiente dentro de esa unidad puntual. No se resolvió con lógica adicional (por ejemplo, resumir esa unidad) por la complejidad que agregaría, dado que no se presenta con los tamaños de ventana usados en la práctica.
- **Reintentos diferenciados por tipo de error del LLM:** se reintenta cualquier excepción de `chat(...)` de la misma manera, sin distinguir (por ejemplo) un error de autenticación (no transitorio, no debería reintentarse) de un timeout (sí transitorio). El protocolo `LLMClient` no estandariza tipos de excepción por proveedor, así que diferenciarlos requeriría acoplarse a la implementación concreta del cliente — se prefirió una política uniforme y simple para esta entrega.
- **Recuperación automática de argumentos por parte del agente** (por ejemplo, convertir `"diez"` a `10` automáticamente antes de llamar a la tool): se decidió que la corrección la haga el LLM a partir del mensaje de error, no el framework, para mantener la separación de responsabilidades pedida por la consigna ("el LLM puede corregir los argumentos y reintentar").
- **Persistencia de memoria entre procesos** (reiniciar el programa y continuar la misma conversación): fuera de alcance de M2; el estado vive solo en memoria del proceso mientras la instancia de `MyAgent` esté viva.

---

## Verificación

- `pytest tests/conformance/test_m1.py tests/conformance/test_m2.py -q` → **12/12 tests pasan**.
- Criterios de aprobación del enunciado verificados manualmente además de los tests automatizados:
  - Conversación que supera el presupuesto de contexto: el agente sigue respondiendo con sensatez, sin romper pares tool_call/tool_result.
  - Prompt de salida estructurada deliberadamente roto: dispara reparación y se recupera, o falla limpiamente con `StructuredOutputError`.
  - Timeout simulado del cliente LLM: se reintenta y la ejecución termina con éxito.
  - Calculadora y lector de archivos: mensajes claros y accionables ante errores recuperables (ver ejemplos en sección 3).
  - `AgentResult.input_tokens` / `output_tokens` reflejan la suma de lo reportado por el cliente LLM durante `run(...)`.
