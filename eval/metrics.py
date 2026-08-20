"""Métricas cuantitativas y taxonomía de errores para la evaluación de M3.

Este módulo es puro (no llama al LLM ni al agente): opera sobre los
registros JSON-serializables que produce `eval/run.py`, así que se puede
testear y re-ejecutar sobre resultados ya guardados sin volver a correr
el agente.
"""

from __future__ import annotations

import statistics
from typing import Any

# Nº óptimo de tool calls por escenario (columna "Optimal" del enunciado
# de M3). No es parte del motor fijo (`mia_world`), así que vive acá: es
# el número contra el que medimos eficiencia, no una regla del mundo.
OPTIMAL_CALLS: dict[str, int] = {
    "study-with-key": 3,
    "color-locks": 11,
    "apartment-keys": 7,
    "library-search": 7,
    "office-sequence": 13,
    "extreme-archive": 4,
    "vault-combination": 21,
    "backtracking-vault": 18,
}

# Categorías de error para el desglose cualitativo del análisis de errores.
ERROR_CATEGORIES = (
    "sin_error",
    "herramienta_inexistente",
    "argumentos_invalidos",
    "regla_del_mundo",  # error "de juego": objeto no encaja, no es visible, etc.
    "bug_inesperado",
)


def classify_step_error(step: dict[str, Any]) -> str:
    """Clasifica el resultado de un `AgentStep` (dict) en una categoría.

    `step` es el dict producido por `dataclasses.asdict(AgentStep(...))`:
    tiene `tool_name`, `tool_input`, `tool_output`, `error`.

    Distinguimos:
    - `sin_error`: el step no reporta error de framework y el output no
      empieza con "Error" (heurística: las tools de `mia_world` y las de
      M1 prefijan sus mensajes recuperables con "Error").
    - `herramienta_inexistente` / `argumentos_invalidos`: errores que
      levanta el propio agente (`_invoke_tool`) antes de correr la tool.
    - `regla_del_mundo`: la tool corrió pero el mundo rechazó la acción
      (target no visible, no encaja, ya está abierta, etc.) — el agente
      llamó bien a la herramienta pero con un argumento no válido *para
      el estado actual del mundo*, no un bug.
    - `bug_inesperado`: excepción no manejada dentro de una tool.
    """
    error = step.get("error")
    output = step.get("tool_output") or ""

    if error:
        lower = error.lower()
        if "herramienta no encontrada" in lower:
            return "herramienta_inexistente"
        if "no es json válido" in lower or "argumentos inválidos" in lower or "llamada inválida" in lower:
            return "argumentos_invalidos"
        if "falló inesperadamente" in lower:
            return "bug_inesperado"
        return "bug_inesperado"

    if output.startswith("Error"):
        return "regla_del_mundo"

    return "sin_error"


def summarize_attempt(record: dict[str, Any]) -> dict[str, Any]:
    """Resume un intento (una corrida de un escenario) a métricas planas.

    `record` es el dict que `eval/run.py` serializa por intento: incluye
    `scenario_id`, `difficulty`, `goal_achieved`, `steps` (lista de
    AgentStep como dict), `input_tokens`, `output_tokens`, `latency_s`,
    y opcionalmente `harness_error` si el propio harness abortó el
    intento (excepción no capturada por el agente).
    """
    steps = record.get("steps") or []
    calls = len(steps)
    optimal = OPTIMAL_CALLS.get(record["scenario_id"])
    efficiency_ratio = (calls / optimal) if (optimal and calls) else None

    error_counts = {cat: 0 for cat in ERROR_CATEGORIES}
    for step in steps:
        error_counts[classify_step_error(step)] += 1

    return {
        "scenario_id": record["scenario_id"],
        "difficulty": record.get("difficulty", "unspecified"),
        "attempt": record.get("attempt", 0),
        "success": bool(record.get("goal_achieved")),
        "harness_error": record.get("harness_error"),
        "tool_calls": calls,
        "optimal_calls": optimal,
        "efficiency_ratio": efficiency_ratio,
        "error_counts": error_counts,
        "input_tokens": record.get("input_tokens"),
        "output_tokens": record.get("output_tokens"),
        "latency_s": record.get("latency_s"),
    }


def aggregate(attempt_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    """Agrega métricas por-intento a nivel global y por dificultad/escenario."""

    def _agg_group(rows: list[dict[str, Any]]) -> dict[str, Any]:
        n = len(rows)
        successes = sum(1 for r in rows if r["success"])
        ratios = [r["efficiency_ratio"] for r in rows if r["efficiency_ratio"] is not None]
        latencies = [r["latency_s"] for r in rows if r["latency_s"] is not None]
        in_toks = [r["input_tokens"] for r in rows if r["input_tokens"] is not None]
        out_toks = [r["output_tokens"] for r in rows if r["output_tokens"] is not None]
        error_totals = {cat: 0 for cat in ERROR_CATEGORIES}
        for r in rows:
            for cat, cnt in r["error_counts"].items():
                error_totals[cat] += cnt
        return {
            "n": n,
            "success_rate": successes / n if n else None,
            "mean_efficiency_ratio": statistics.fmean(ratios) if ratios else None,
            "mean_latency_s": statistics.fmean(latencies) if latencies else None,
            "mean_input_tokens": statistics.fmean(in_toks) if in_toks else None,
            "mean_output_tokens": statistics.fmean(out_toks) if out_toks else None,
            "error_counts": error_totals,
        }

    by_difficulty: dict[str, list[dict[str, Any]]] = {}
    by_scenario: dict[str, list[dict[str, Any]]] = {}
    for row in attempt_summaries:
        by_difficulty.setdefault(row["difficulty"], []).append(row)
        by_scenario.setdefault(row["scenario_id"], []).append(row)

    return {
        "overall": _agg_group(attempt_summaries),
        "by_difficulty": {k: _agg_group(v) for k, v in sorted(by_difficulty.items())},
        "by_scenario": {k: _agg_group(v) for k, v in sorted(by_scenario.items())},
    }
