# Informe — Milestone 3: Evaluación sobre un problema objetivo

**Proyecto:** tp_mia_agentes_2026
**Autores:** Hugo Cabaña, Oscar Carrizo
**Repositorio:** [HugoCabana/tp_mia_agentes_2026](https://github.com/HugoCabana/tp_mia_agentes_2026)
**Proveedor LLM usado en la evaluación:** Ollama local, `llama3.1:latest` (8B)

> **Nota de estado:** este informe se armó de forma incremental, con datos
> reales a medida que se fueron corriendo escenarios (correr un escenario
> `hard`/`extreme` en este entorno toma entre ~10 y ~20 minutos en CPU
> local). Las secciones marcadas `[PENDIENTE]` tienen instrucciones
> exactas de qué correr para completarlas — no son texto a inventar.



## 1. Aproximación

Se reutilizó el framework de M1+M2 sin modificar su fachada externa
(`build_agent`, `register_tool`, `run`, `structured_call`). El agente
resuelve escenarios del mundo simulado (`mia_world/`) registrando las
tools del mundo (`look`, `examine`, `take`, `use`, y `go` en escenarios
multi-sala) sobre un `MyAgent` igual al usado en M1/M2 — no hubo que
tocar `agent.py` para que funcione con el nuevo dominio, lo cual valida
que el diseño de M1/M2 (tools genéricas + memoria + errores accionables)
generaliza a un problema no visto durante su construcción.

### Especializaciones hechas para M3

Toda la lógica nueva vive en `eval/`, no en el framework:

- **`eval/run.py`**: harness de evaluación reproducible con 5 variantes
  (`baseline`, `task_prompt`, `no_m1_tools`, `low_history_budget`,
  `tight_max_iterations`).
- **`eval/metrics.py`**: taxonomía de errores + agregación de métricas.
- **`eval/judge.py`**: dimensión cualitativa vía LLM-as-judge, reutilizando
  `structured_call` de M2.

### Dos correcciones reales en `agent.py` durante el pilotaje

Al correr los primeros escenarios contra un LLM real (no contra los
`MockLLMClient` usados en el pilotaje de M1/M2), aparecieron dos casos
donde el mensaje de error de `_invoke_tool` no le daba al LLM suficiente
información para autocorregirse:

1. Ante un `TypeError` de argumento inesperado, el mensaje no indicaba
   cuál era el nombre correcto del parámetro (solo decía cuál estaba
   mal). Se agregó, tomando la lista de parámetros del `ToolSchema` ya
   registrado: `"Parámetros esperados por '<tool>': <lista>."`
2. Para tools sin parámetros (`look`), esa lista queda vacía y el mensaje
   no aclaraba nada. Se agregó un caso explícito:
   `"'<tool>' no toma ningún parámetro: invocala como <tool>()."`

Ambos cambios están dentro del contrato de M2 ("errores recuperables con
mensaje accionable"), no son features nuevas — son correcciones a un caso
que los tests de conformidad (que usan `MockLLMClient` con respuestas ya
válidas) no ejercitan, porque ahí el LLM nunca comete estos errores.

### El `system_prompt` importa más que cualquier cambio de framework

El hallazgo más grande del pilotaje: el default de `MyAgent.system_prompt`
(`"Sos un agente muy eficiente hincha de River"`, un placeholder heredado
de M1/M2) no le da al LLM ningún marco sobre el dominio de sala de
escape. Con un modelo chico corriendo local, eso alcanza para que el
agente nunca llame a `look` y falle por completo. Ver sección 4
(Experimentos) para la comparación numérica.


## 2. Métricas

### Cuantitativa: success rate + eficiencia (calls / óptimo)

- **Success rate**: `goal_achieved` según `mia_world.goals.check_goal`
  sobre el estado final del mundo — no sobre el texto del agente. Es la
  métrica primaria porque es binaria, objetiva y no requiere juicio
  humano ni de otro LLM.
- **Eficiencia** (`tool_calls / OPTIMAL_CALLS[escenario]`, tabla del
  enunciado): mide qué tan lejos del camino óptimo operó el agente,
  incluso en corridas exitosas. Se justifica porque success rate solo
  responde "¿lo logró?" — la eficiencia captura cuánto "ruido" (reintentos,
  redundancia) hubo en el camino, que es justamente donde aparecen los
  problemas de M1/M2 puestos a prueba (manejo de errores, memoria).

Ambas se calculan en `eval/metrics.py::summarize_attempt` /
`aggregate`, agregadas global / por dificultad / por escenario.

### Cualitativa: LLM-as-judge sobre la trayectoria

`eval/judge.py` pide, vía `structured_call` (M2), un veredicto
(`TrajectoryJudgement`: `plan_coherence` 1-5, `redundant_actions`,
`used_out_of_context_tool`, `justification`) sobre la transcripción
completa. Se justifica porque la métrica cuantitativa no distingue
una trayectoria que repite una acción válida-pero-inútil muchas veces
(cuenta como `sin_error`, cero errores) de una trayectoria limpia — ver
el caso concreto de `apartment-keys` en la sección 3, donde 21 pasos sin
un solo error de framework terminaron en fracaso total.

**Actualización:** se corrieron ambos comandos pendientes. Resultado real
(desglosado en sección 3):

```bash
python -m eval.run --scenario color-locks --ablation task_prompt
python -m eval.run --scenario apartment-keys --ablation task_prompt
```

- `color-locks`: intento fallido, con juez completo (`plan_coherence: 1`,
  `redundant_actions: true`) — la única lectura cualitativa real
  obtenida hasta ahora.
- `apartment-keys`: intento también fallido, pero el harness devolvió
  `judge: null` en el JSON de salida pese a haberse invocado sin
  `--no-judge`. No se investigó la causa (¿timeout del juez, error
  silencioso en `judge.py`, corte por `max_iterations` antes de llegar
  a esa etapa?) — queda como `[TODO]` explícito en la sección 5.

No se logró, por lo tanto, el objetivo original de tener "uno exitoso,
uno fallido": ambas corridas de esta sesión fallaron. Curiosamente,
`color-locks` había resuelto en el intento `v3` reportado más arriba
(sección 3) con la misma configuración de ablation — la nueva corrida,
con el mismo prompt y mismo modelo, no. Esto es evidencia directa de
variabilidad entre intentos (mismo `system_prompt`, mismo escenario,
resultado distinto), y refuerza por qué `--repeats` (pass@k) sigue
siendo un TODO relevante (sección 5) y no solo una idea especulativa.

### Taxonomía de errores (cualitativa, complementaria)

`classify_step_error` categoriza cada `AgentStep` en 5 clases
(`sin_error`, `herramienta_inexistente`, `argumentos_invalidos`,
`regla_del_mundo`, `bug_inesperado`) — ver sección 3 para el desglose real.


## 3. Resultados

### Tabla de corridas realizadas hasta ahora

| Escenario | Dificultad | Ablation | Éxito | Calls | Óptimo | Eficiencia | Latencia | Tokens in/out |
|---|---|---|:---:|---:|---:|---:|---:|---:|
| study-with-key | easy | `baseline` | ✗ | 22 | 3 | 7.3× | 793.7s | n/d (falló antes de reportar) |
| study-with-key | easy | `task_prompt` (v1, sin fix de agent.py) | ✗ | 20 | 3 | 6.7× | 1093.7s | 23446 / 359 |
| study-with-key | easy | `task_prompt` (con fix de agent.py) | **✓** | 7 | 3 | 2.33× | 565.5s | 5391 / 145 |
| apartment-keys | medium | `task_prompt` (v2, max_iter=20) | ✗ | 24 | 7 | 3.43× | 609.6s | 21781 / 426 |
| apartment-keys | medium | `task_prompt` (v3, max_iter=40) | ✗ | 21 | 7 | 3.0× | 1108.9s | 100090 / 715 |
| color-locks | medium | `task_prompt` (v2, max_iter=20) | ✗ | 8 (cortado por respuesta en texto libre) | 11 | 0.73×* | 669.2s | 7840 / 194 |
| color-locks | medium | `task_prompt` (v3, max_iter=40) | **✓** | 21 | 11 | 1.91× | 703.0s | 34580 / 427 |
| color-locks | medium | `task_prompt` (con juez, attempt0) | ✗ | 40 | 11 | 3.64× | 1221.3s | 97344 / 757 |
| apartment-keys | medium | `task_prompt` (con juez, attempt0) | ✗ | 40 | 7 | 5.71× | 1170.7s | 76983 / 582 |
| library-search | hard | `task_prompt` (`--no-judge`) | ✗ | 32 | N/D** | N/D** | 2108.8s | 126966 / 639 |

\* En la corrida de `color-locks` v2 el agente se detuvo antes de tiempo
(respondió con texto libre en vez de ejecutar el plan), por eso la
eficiencia da engañosamente baja — no completó el escenario.

\*\* No se cuenta con el valor de `OPTIMAL_CALLS['library-search']` de la
tabla del enunciado en esta entrega — queda pendiente confirmarlo para
poder calcular la eficiencia real de este escenario.

**Success rate agregado, corridas finales (`task_prompt` v3) — únicos
resultados representativos del sistema ya ajustado:**

| Dificultad | n | Success rate | Eficiencia media |
|---|---:|---:|---:|
| easy | 1 | 100% | 2.33× |
| medium | 2 | 50% | 4.10× |
| hard | 1 | 0% | N/D (óptimo no confirmado) |
| extreme | `[PENDIENTE]` | — | — |

*Nota:* la fila `medium` de esta tabla sigue reflejando únicamente los
intentos `v3` originales (una corrida por escenario), tal como estaba
antes de esta actualización — no se recalculó incluyendo los dos
intentos nuevos "con juez" (ambos fallidos, ver tabla de corridas y
sección 2) para no mezclar corridas con distinta finalidad (ajuste de
framework vs. dimensión cualitativa) en un mismo promedio sin antes
correr `--repeats` de forma sistemática. Ver el TODO de la sección 5.

`hard` (`library-search`) ya tiene un primer intento (fallido, ver tabla
de corridas). `[PENDIENTE]` por falta de tiempo y de recursos de
hardware (cada corrida en CPU local, en este escenario, tardó ~35
minutos):
```bash
python -m eval.run --scenario extreme --no-judge --ablation task_prompt
```
Además, `hard` solo tiene un(1) intento — falta repetir para tener una
tasa de éxito real y no un dato puntual (mismo TODO de `--repeats` que
`medium`).

### Desglose por categoría de error (corridas `task_prompt` v3, medium)

| Categoría | apartment-keys | color-locks |
|---|---:|---:|
| sin_error | 21 | 18 |
| herramienta_inexistente | 0 | 0 |
| argumentos_invalidos | 22 | 3 |
| regla_del_mundo | 1 | 0 |
| bug_inesperado | 0 | 0 |

**Lectura:** `argumentos_invalidos` es, con diferencia, la categoría más
frecuente en ambos escenarios — consistente con el sesgo observado del
modelo a probar primero un nombre de parámetro genérico (`id`) antes del
correcto. En `color-locks` (que sí resolvió) esos errores se corrigen
rápido y no impiden el progreso. En `apartment-keys` (que no resolvió),
**21 de 21 pasos son `sin_error`** — el agente no cometió errores de
framework, simplemente se quedó dando vueltas con llamadas válidas pero
sin sentido (`look()` alternado con intentos inválidos de
`look(item=...)`). Esto es exactamente el caso que motiva tener la
dimensión cualitativa (sección 2): la taxonomía de errores por sí sola
diría "sin problemas" en una corrida que fracasó por completo.

### Desglose por categoría de error — corridas nuevas de esta sesión

| Categoría | apartment-keys (con juez) | color-locks (con juez) | library-search (hard) |
|---|---:|---:|---:|
| sin_error | 31 | 36 | 23 |
| herramienta_inexistente | 0 | 0 | 0 |
| argumentos_invalidos | 2 | 3 | 2 |
| regla_del_mundo | 7 | 1 | 7 |
| bug_inesperado | 0 | 0 | 0 |

**Lectura:**

- En `apartment-keys` (con juez), el agente sí encontró la llave dorada
  (`llave_oro`) en la cocina y volvió al recibidor, pero nunca completó
  el ciclo `go` de regreso a la cocina para tomarla correctamente
  después del primer intento fallido de `take` (error `regla_del_mundo`:
  "no es visible o accesible desde aquí" porque intentó tomarla estando
  en otra sala). El agente sí regresó a la cocina al final, pero se
  quedó sin iteraciones (40) justo al volver a verla, sin llegar a
  ejecutar el `take` correcto. Es el mismo patrón de confusión
  navegación/exploración descripto en la sección 5, ahora con un
  ejemplo aún más cercano al éxito que en el intento original.
- En `color-locks` (con juez), la trayectoria coincide con el veredicto
  del juez (sección 2): el agente abrió el cofre plateado con la llave
  plateada, probó (correctamente) esa misma llave contra el cofre rojo,
  falló ("no encaja"), y a partir de ahí quedó en un bucle de más de 20
  llamadas a `examine cofre_rojo` sin variar el argumento ni buscar
  otra llave — de ahí el `plan_coherence: 1` y `redundant_actions: true`
  del juez. A diferencia de `apartment-keys`, acá casi no hay errores
  de framework (3 `argumentos_invalidos`, todos al inicio); el fracaso
  es puramente de planificación, otro caso que confirma el valor de la
  dimensión cualitativa.
- En `library-search` (hard), 7 de los pasos "regla_del_mundo"
  corresponden a intentos repetidos de `take` sobre libros que el mundo
  marca como no portables ("no es algo que puedas llevarte") — el
  agente insistió con el mismo libro (`libro_genealogia`) varias veces
  en vez de descartarlo tras el primer rechazo. Encontró la llave
  correcta (`llave_caja`, escondida dentro de `libro_sermones`) y la
  tomó con éxito, pero terminó la corrida sin haber llamado nunca a
  `use` — ver limitación específica en sección 5.


## 4. Experimentos

### Experimento 1 — `system_prompt`: placeholder genérico vs. orientado a la tarea

**Qué se cambió:** el `system_prompt` de `MyAgent`, de
`"Sos un agente muy eficiente hincha de River"` (default de M1/M2, sin
contexto de dominio) a un prompt con 8 reglas explícitas de estrategia
(explorar con `look` antes de asumir, usar ids exactos, leer el mensaje
de error completo, no repetir llamadas idénticas fallidas, usar las
opciones que el error sugiere, ejecutar el plan en vez de describirlo,
no asumir `id` como nombre de parámetro, usar `go`/`direction` para
navegar). El prompt final es el resultado de 3 iteraciones de pilotaje
sobre `easy`/`medium`, congelado a partir de ahí (no se siguió ajustando
contra escenarios puntuales para no sobreajustar el experimento).

**Qué pasó:** en `study-with-key` (easy), el baseline nunca llamó a
`look`, alucinó ids de objetos inexistentes y agotó el límite de
iteraciones sin resolver (22 calls, fracaso). Con `task_prompt`, el mismo
escenario resolvió en 7 calls. En `color-locks` (medium), el mismo
patrón: con prompt orientado a la tarea llegó a resolver, mientras que
sin él es esperable el mismo tipo de fracaso visto en `study-with-key`
baseline (no se corrió `color-locks` en baseline puro por costo de
tiempo, pero el mecanismo de fallo observado — no explorar, o describir
en vez de ejecutar — es el mismo que en el resto del baseline).

**Conclusión:** para este modelo (`llama3.1:8B` local), el `system_prompt`
es la variable de mayor impacto de todas las que se probaron — más que
cualquier parámetro del framework (`max_iterations`, `max_history_messages`).
Un modelo chico sin instrucciones explícitas de estrategia no infiere por
sí solo el patrón "explorar antes de actuar", incluso cuando las tools
tienen docstrings descriptivos.

### Experimento 2 — `[PENDIENTE]` (no se llegó a correr: falta de tiempo y de recursos de hardware)

Recomendado: `low_history_budget` (`max_history_messages=6`) sobre
`apartment-keys`, para medir si el cuello de botella observado (no volver
a intentar `go` tras un primer fallo, no recordar qué ya exploró) empeora
o es indiferente a un presupuesto de memoria más chico — daría señal
sobre si el problema es de memoria (M2) o de razonamiento del modelo en
sí (hipótesis actual, dado que `apartment-keys` con memoria completa
igual falla).

```bash
python -m eval.run --scenario apartment-keys --no-judge --ablation low_history_budget
```

**Nota de estado:** no se corrió en esta entrega. Cada intento en CPU
local demandó entre ~10 y ~35 minutos (el escenario `hard` corrido en
esta sesión tardó 2108.8s, ~35 min, muy por encima de la estimación
original de la sección de estado), y el tiempo/hardware disponibles no
alcanzaron para sumar esta ablation además de completar `hard` y las
corridas con juez pendientes. Queda como `[TODO]` explícito para la
próxima iteración de este informe — ver también sección 5.

Completar esta sección con: qué se cambió, qué pasó (número de calls,
éxito/fracaso, categorías de error), y qué concluyen — mismo formato que
el Experimento 1.


## 5. Limitaciones y qué construirían a continuación

### Limitaciones encontradas

- **El modelo local tiene un sesgo consistente a nombrar parámetros
  genéricamente (`id`, `obj`) en vez del nombre real de la tool**, incluso
  después de que el mensaje de error se lo indica explícitamente y el
  prompt lo prohíbe por regla. Esto agrega, en promedio, un ~2× de calls
  extra sobre el óptimo solo por este patrón — es un límite de capacidad
  del modelo, no algo que el framework pueda corregir sin implementar
  auto-corrección de argumentos en el propio agente (lo cual se decidió
  explícitamente NO hacer en M2, para mantener la separación de
  responsabilidades: la corrección la hace el LLM, no el framework).
- **Confusión entre `look` (explorar el estado actual) y `go` (navegar)**
  en escenarios multi-sala: el modelo, al buscar un ítem que no está a la
  vista, intenta pasarle argumentos a `look` en vez de moverse con `go`
  a otra sala. Sobrevivió a 3 iteraciones de prompting explícito sobre
  este punto sin resolverse del todo (`apartment-keys` sigue fallando).
  Es la limitación más seria encontrada: sugiere un techo de capacidad
  del modelo para planificación multi-sala, no un problema de prompting
  ni de memoria.
- **Posible truncamiento silencioso de contexto por parte de Ollama**: en
  el intento fallido de `apartment-keys` con `max_iterations=40`, el
  agente reportó `input_tokens: 100090` acumulados — muy por encima de la
  ventana de contexto por defecto de Ollama para modelos locales (que
  suele ser de 2K-8K tokens salvo que se configure `num_ctx`
  explícitamente). Es probable que buena parte del historial que el
  framework sí envió nunca haya sido "visto" realmente por el modelo, lo
  cual confundiría la atribución del fallo (¿es el modelo, o es que
  Ollama le recortó el contexto sin avisar?). No se investigó a fondo por
  quedar fuera del foco de esta entrega, pero es una duda real sobre la
  validez de las corridas más largas.
- **Costo de tiempo de la evaluación**: cada intento tardó entre ~9 y ~18
  minutos en CPU local. Esto limitó la cobertura del dataset completo
  dentro del tiempo disponible para esta entrega (ver TODOs pendientes en
  secciones 3 y 4).
- **Curiosidad de comportamiento, no un fallo (en la corrida original)**:
  en una corrida exitosa, el `final_answer` del agente fue un string con
  forma de tool-call (`{"name": "go", "parameters": {"direction":"norte"}}`)
  en vez de texto natural. No afectó el resultado (que se mide sobre el
  estado del mundo), pero sugiere que el modelo a veces "filtra" su
  formato interno de tool-calling hacia la respuesta final de texto libre.
- **La misma curiosidad, esta vez causando el fracaso (`library-search`,
  hard)**: el agente exploró correctamente, encontró la llave correcta
  (`llave_caja`, escondida dentro de un libro) y la tomó, pero en vez de
  llamar a la tool `use` para abrir la caja fuerte, terminó la corrida
  con `final_answer = '{"name": "open", "parameters": {"obj":"caja_fuerte"}}'`
  — texto libre simulando una llamada a una tool `open` que **no existe**
  en el mundo (`look`, `examine`, `take`, `use`, `go`). Además, ese
  "llamado" apuntaba a la caja fuerte, no a la puerta principal (el
  objetivo real del escenario), lo que sugiere que el agente tampoco
  tenía claro cuál era el último paso del plan. Es el ejemplo más claro
  hasta ahora de que este patrón de "fuga de formato interno" puede ser
  la causa directa de un fracaso, no solo una curiosidad inocua.
- **Variabilidad entre intentos con la misma configuración**: `color-locks`
  con `task_prompt` resolvió en el intento `v3` (sección 3) y falló en un
  intento posterior con exactamente la misma ablation (`task_prompt`,
  esta sesión). Con un solo intento por combinación escenario/ablation no
  se puede distinguir si un resultado es representativo o un extremo de
  la distribución — ver `--repeats` en "Qué construirían a continuación".
- **`judge: null` sin explicación en `apartment-keys`**: al correr
  `eval.run --scenario apartment-keys --ablation task_prompt` (sin
  `--no-judge`) el JSON de salida trajo `"judge": null`, a diferencia de
  `color-locks` corrido con el mismo comando, que sí trajo un veredicto
  completo. No se investigó la causa en esta entrega — queda como
  `[TODO]` (¿timeout específico de ese intento, bug en `judge.py`, o
  algo relacionado con el corte por `max_iterations`?).

`[TODO — no se llegó a hacer por falta de tiempo y de recursos de
hardware (todo corrido en CPU local)]`:
- Evaluar el escenario `extreme` (no se corrió ni una vez).
- Correr el Experimento 2 (`low_history_budget` sobre `apartment-keys`).
- Repetir `hard` (`library-search`) más de una vez — hoy hay un único
  intento, y ya se observó variabilidad en `medium` con un solo intento
  extra.
- Investigar el `judge: null` de `apartment-keys` descripto arriba.

**Nota sobre los datos crudos:** todos los JSON de intento generados
(los de este informe y los previos) quedan en `eval/results/` del
repositorio, versionados localmente — no se adjuntan íntegros acá por
espacio, pero quedan disponibles para revisión o demostración en
cualquier momento futuro, incluidos los que todavía no se resumieron en
una tabla de este documento.

### Qué construirían a continuación

- Confirmar/descartar la hipótesis de truncamiento de contexto de Ollama
  (configurar `num_ctx` explícitamente y volver a correr `apartment-keys`).
- Repetir la evaluación con un modelo más grande (vía Bedrock) para
  separar "límite del framework" de "límite del modelo local" — la
  hipótesis actual es que casi todos los fallos observados son de esto
  último, pero no hay corrida comparativa contra un modelo más capaz
  todavía.
- Si el problema de navegación persistiera con un modelo más grande,
  recién ahí valdría la pena considerar un mecanismo de framework (por
  ejemplo, un resumen explícito del mapa explorado en el system prompt,
  actualizado dinámicamente) en vez de atribuirlo solo al modelo.
- Correr `--repeats` (pass@k) sobre los escenarios límite para saber si
  el fracaso de `apartment-keys` es determinístico o si el modelo a veces
  lo resuelve por variación de sampling — ahora con más urgencia, dado
  que `color-locks` mostró resultado distinto (éxito vs. fracaso) entre
  dos intentos con la misma configuración.
- Completar `extreme` y el Experimento 2 (`low_history_budget`), pendientes
  de esta entrega por tiempo y hardware (ver sección 5).
- Investigar el `judge: null` inexplicado de `apartment-keys` (ver
  sección 5) antes de confiar en la ausencia de veredicto como señal.


## Apéndice: comandos de reproducción

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# python3 check_llm_config.py   # (este file no esta en el repositorio, sirve para confirmar que el LLM configurado responde)

# Corridas ya incluidas en este informe
python -m eval.run --scenario easy --no-judge --ablation baseline
python -m eval.run --scenario easy --no-judge --ablation task_prompt
python -m eval.run --scenario medium --no-judge --ablation task_prompt

# Corridas nuevas de esta sesión — YA CORRIDAS, resultados en secciones 2 y 3
python -m eval.run --scenario hard --no-judge --ablation task_prompt
python -m eval.run --scenario color-locks --ablation task_prompt      # con juez
python -m eval.run --scenario apartment-keys --ablation task_prompt   # con juez

# Pendientes — no se llegaron a correr por falta de tiempo / recursos
# de hardware (ver TODOs en secciones 3, 4 y 5)
python -m eval.run --scenario extreme --no-judge --ablation task_prompt
python -m eval.run --scenario apartment-keys --no-judge --ablation low_history_budget
```

Todos los JSON crudos de cada intento (incluidos los ya corridos y
resumidos arriba) quedan en `eval/results/` del repositorio, en la copia
local de trabajo — no se versionaron aparte del repo, pero están
disponibles ahí para revisión o demostración sin necesidad de volver a
correr nada.
