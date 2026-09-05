# Informe — Milestone 3: Evaluación sobre un problema objetivo

**Proyecto:** tp_mia_agentes_2026  
**Autores:** Hugo Cabaña, Oscar Carrizo  
**Repositorio:** [HugoCabana/tp_mia_agentes_2026](https://github.com/HugoCabana/tp_mia_agentes_2026)  
**Proveedor LLM usado en la evaluación:** Claude Sonnet 4.6 via API de Anthropic (`claude-sonnet-4-6`)

> **Nota:** esta es una reentrega del informe original. La entrega anterior
> se realizó con `llama3.1:8B` corriendo en CPU local, lo que limitó
> severamente la cobertura experimental. En esta versión se usó Claude Sonnet
> via API de Anthropic, se corrieron los 8 escenarios completos con 3
> repeticiones cada uno y se implementaron 4 experimentos con conclusiones
> concretas.

---

## 1. Aproximación

Se reutilizó el framework de M1+M2 sin modificar su fachada externa
(`build_agent`, `register_tool`, `run`, `structured_call`). El agente
resuelve escenarios del mundo simulado (`mia_world/`) registrando las
tools del mundo (`look`, `examine`, `take`, `use`, y `go` en escenarios
multi-sala) sobre un `MyAgent` igual al usado en M1/M2.

El hecho de que no haya sido necesario tocar `agent.py` para que funcione
con el nuevo dominio valida que el diseño de M1/M2 (tools genéricas +
memoria + errores accionables) generaliza a un problema no visto durante
su construcción.

### Especializaciones hechas para M3

Toda la lógica nueva vive en `eval/`, no en el framework:

- **`eval/run.py`**: harness de evaluación reproducible con 4 variantes
  (`baseline`, `no_m1_tools`, `low_history_budget`, `tight_max_iterations`).
- **`eval/metrics.py`**: taxonomía de errores + agregación de métricas.
- **`eval/judge.py`**: dimensión cualitativa vía LLM-as-judge, reutilizando
  `structured_call` de M2.

### Cambio de modelo: de llama3.1 local a Claude Sonnet

El cambio más impactante de esta reentrega fue reemplazar `llama3.1:8B`
corriendo en CPU local por Claude Sonnet via API de Anthropic. Para esto
se implementó `student_framework/anthropic_provider.py`, una clase
`AnthropicClient` que satisface el protocolo `LLMClient` del framework
sin modificar `mia_agents/llm_client.py`. El provider se activa
automáticamente en `build_agent()` cuando detecta la variable de entorno
`ANTHROPIC_API_KEY`.

### Corrección al system prompt

El `system_prompt` por defecto de `MyAgent` era un placeholder informal
(`"Sos un agente muy eficiente hincha de River"`) heredado de M1/M2 sin
contexto de dominio. Se reemplazó por un prompt orientado a la tarea de
sala de escape:

```
"Sos un agente que resuelve salas de escape usando herramientas.
Reglas estrictas:
1. Siempre empezá con 'look' para ver los objetos y sus ids exactos.
2. Usá 'examine <id>' con el id exacto que viste en 'look'.
3. Usá 'take <id>' con el id exacto del objeto que querés agarrar.
4. Usá 'use <id_item> <id_target>' para usar un objeto sobre otro.
NUNCA inventes ids — solo usá los que aparecen en las respuestas."
```

---

## 2. Métricas

### Cuantitativa: success rate + eficiencia (calls / óptimo)

- **Success rate**: `goal_achieved` según `mia_world.goals.check_goal`
  sobre el estado final del mundo — no sobre el texto del agente. Métrica
  primaria porque es binaria, objetiva y no requiere juicio humano.
- **Eficiencia** (`tool_calls / OPTIMAL_CALLS[escenario]`): mide qué tan
  lejos del camino óptimo operó el agente, incluso en corridas exitosas.
  Captura el "ruido" (reintentos, redundancia) en el camino.

Ambas se calculan en `eval/metrics.py::summarize_attempt` / `aggregate`,
agregadas global / por dificultad / por escenario.

### Cualitativa: LLM-as-judge sobre la trayectoria

`eval/judge.py` pide, vía `structured_call` (M2), un veredicto
(`TrajectoryJudgement`: `plan_coherence` 1-5, `redundant_actions`,
`used_out_of_context_tool`, `justification`) sobre la transcripción
completa de cada intento.

Se justifica porque el success rate no distingue una trayectoria que
resolvió con un plan claro de una que resolvió por prueba y error. El
judge captura esa diferencia — un agente puede fallar con un plan
razonable (límite de pasos) o tener éxito de forma errática.

### Taxonomía de errores (complementaria)

`classify_step_error` categoriza cada `AgentStep` en 5 clases:
`sin_error`, `herramienta_inexistente`, `argumentos_invalidos`,
`regla_del_mundo`, `bug_inesperado`.

---

## 3. Resultados

### Baseline con Claude Sonnet (1 intento por escenario, con judge)

| Escenario | Dificultad | Éxito | Calls | Óptimo | Eficiencia | Latencia | plan_coherence |
|---|---|:---:|---:|---:|---:|---:|---:|
| study-with-key | easy | ✅ | 6 | 3 | 2.00× | 17.1s | 5/5 |
| color-locks | medium | ✅ | 19 | 11 | 1.73× | 41.0s | — |
| apartment-keys | medium | ✅ | 10 | 7 | 1.43× | 26.4s | — |
| library-search | hard | ✅ | 18 | 7 | 2.57× | 38.2s | — |
| office-sequence | hard | ✅ | 21 | 13 | 1.62× | 45.3s | — |
| extreme-archive | extreme | ✅ | 25 | 4 | 6.25× | 28.8s | — |
| vault-combination | extreme | ❌ | 22 | 21 | 1.05× | 44.4s | 5/5 |
| backtracking-vault | extreme | ❌ | 24 | 18 | 1.33× | 49.0s | — |

**Success rate global: 75%**  
**Eficiencia media: 2.25×**  
**Latencia media: 36.3s**

### Resultado destacado del judge

El caso más revelador es `vault-combination` (FAIL):
- `plan_coherence: 5` → plan perfecto
- `redundant_actions: false` → sin acciones repetidas
- `justification`: *"el fracaso se debe al límite de pasos, no a errores
  de planificación — el agente estaba a 1-2 pasos de resolverlo"*

Esto demuestra el valor del judge: el success rate dice FAIL pero el
agente razonó perfectamente. El problema fue el límite de `max_iterations`,
no la estrategia.

### Baseline con 3 repeticiones (sin judge)

| Dificultad | n | Success rate | Eficiencia media |
|---|---:|---:|---:|
| easy | 3 | 100% | 2.00× |
| medium | 6 | 100% | 1.63× |
| hard | 6 | 83.3% | 2.09× |
| extreme | 9 | 22.2% | 3.17× |
| **Global** | **24** | **58.3%** | **2.25×** |

La variabilidad entre intentos es real — `office-sequence` resolvió 1/3
veces y `extreme-archive` resolvió 1/3 veces. Esto confirma la importancia
de `--repeats` para tener resultados representativos.

### Taxonomía de errores (baseline, 1 intento)

| Categoría | Total |
|---|---:|
| sin_error | 144 |
| herramienta_inexistente | 0 |
| argumentos_invalidos | 0 |
| regla_del_mundo | 1 |
| bug_inesperado | 0 |

Con Claude Sonnet casi no hay errores de argumentos — a diferencia de
`llama3.1` que generaba ~22 errores de `regla_del_mundo` por escenario.

---

## 4. Experimentos

Se corrieron 4 ablations con 3 repeticiones cada una para tener resultados
estadísticamente más representativos.

### Resumen comparativo

| Ablation | Success Rate | vs. baseline | Conclusión |
|---|---:|---:|---|
| baseline | 58.3% | — | punto de referencia |
| no_m1_tools | 75.0% | +16.7% | sin herramientas de ruido mejora |
| low_history_budget | 37.5% | -20.8% | poca memoria perjudica |
| tight_max_iterations | 16.7% | -41.6% | pocas iteraciones destruye el performance |

### Experimento 1 — `no_m1_tools`: ¿las herramientas del M1 confunden al agente?

**Qué se cambió:** se removieron las 3 herramientas del M1 (calculadora,
lector de archivos, conversor de unidades) — el agente solo tiene las 5
tools del mundo simulado.

**Qué pasó:** el success rate subió de 58.3% a 75.0%. `extreme-archive`
pasó de inconsistente (1/3) a consistente (3/3).

**Conclusión:** tener herramientas irrelevantes para el contexto confunde
al LLM. Cuando el agente tiene disponible una calculadora en una sala de
escape, el LLM le dedica atención en su razonamiento aunque nunca la use.
Eliminarlas mejora el foco en las herramientas relevantes.

### Experimento 2 — `low_history_budget`: ¿qué pasa con memoria reducida?

**Qué se cambió:** `max_history_messages` de 100 a 6.

**Qué pasó:** el success rate bajó de 58.3% a 37.5%. Los escenarios más
afectados fueron `color-locks` (de 100% a 33%) y `office-sequence` (de
33% a 0%). El easy se mantuvo estable.

**Conclusión:** la memoria del M2 es crítica para escenarios que requieren
más de 6 pasos. Con solo 6 mensajes en el contexto el agente pierde el
hilo de lo que ya exploró y empieza a repetir acciones. Los escenarios
simples (easy, 3 calls óptimas) no se ven afectados porque entran dentro
del presupuesto.

### Experimento 3 — `tight_max_iterations`: ¿cuántos escenarios pierde el agente con menos pasos?

**Qué se cambió:** `max_iterations` de 20 a 8.

**Qué pasó:** el success rate se desplomó de 58.3% a 16.7%. Solo `easy`
(óptimo 3 calls) se resolvió consistentemente. Todos los escenarios
medium, hard y extreme fallaron.

**Conclusión:** el límite de iteraciones es la variable más crítica para
escenarios complejos. Con 8 iteraciones es matemáticamente imposible
resolver escenarios cuyo óptimo supera ese número (color-locks necesita
11, apartment-keys 7, office-sequence 13). Esto confirma que los fallos
en `vault-combination` y `backtracking-vault` del baseline son
recuperables si se aumentan las iteraciones — el agente tiene la
estrategia correcta pero le falta tiempo.

---

## 5. Limitaciones y qué construirían a continuación

### Limitaciones encontradas

- **Variabilidad entre intentos**: el mismo escenario con la misma
  configuración puede dar resultados distintos. `office-sequence` resolvió
  1/3 veces en el baseline. Esto es inherente a la naturaleza probabilística
  del LLM.
- **Escenarios extreme diseñados para fallar**: `vault-combination` y
  `backtracking-vault` requieren 21 y 18 calls óptimas respectivamente,
  pero el judge confirma que el agente tiene la estrategia correcta —
  solo le falta un mayor límite de iteraciones.
- **`extreme-archive`** resolvió de forma inconsistente (1/3 en baseline,
  3/3 en `no_m1_tools`) — sugiere que las herramientas de ruido impactan
  más en este escenario por su alta densidad de texto (~16K tokens).
- **Costo de la API**: correr todas las ablations con 3 repeticiones
  consume créditos significativos. No es viable para iteración rápida.

### Qué construirían a continuación

- **Aumentar `max_iterations`** para `vault-combination` y
  `backtracking-vault` — el judge confirma que el agente razona bien,
  solo necesita más pasos.
- **Combinar `no_m1_tools` con más iteraciones** para ver si se pueden
  resolver los extreme.
- **Correr con judge todas las ablations** para tener veredictos
  cualitativos en cada experimento.
- **Implementar un sistema de memoria explícita del mapa** para escenarios
  multi-sala — el agente a veces pierde track de qué salas ya exploró.
- **Probar pass@3 con judge** para medir si la variabilidad es del modelo
  o del framework.

---

## Apéndice: comandos de reproducción

```bash
# Setup
cd tp_mia_agentes_2026
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# Baseline con judge (1 intento)
python -m eval.run --ablation baseline --repeats 1

# Baseline sin judge (3 intentos)
python -m eval.run --no-judge --ablation baseline --repeats 3

# Ablations (3 intentos cada una)
python -m eval.run --no-judge --ablation no_m1_tools --repeats 3
python -m eval.run --no-judge --ablation low_history_budget --repeats 3
python -m eval.run --no-judge --ablation tight_max_iterations --repeats 3
```

Todos los JSON crudos de cada intento quedan en `eval/results/` del
repositorio, disponibles para revisión sin necesidad de volver a correr.