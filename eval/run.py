"""Infraestructura de evaluación reproducible para M3.

Uso:

    python -m eval.run                              # todos los escenarios, 1 intento c/u
    python -m eval.run --scenario easy               # un escenario por id/dificultad
    python -m eval.run --repeats 3                   # pass@k: 3 intentos por escenario
    python -m eval.run --ablation no_m1_tools         # corre una variante experimental
    python -m eval.run --no-judge                     # salta el juicio cualitativo (más rápido/barato)

Requiere un proveedor LLM configurado vía `.env` (Bedrock u Ollama, ver
`mia_agents.llm_client.LLMClient.from_env`) — es el mismo mecanismo que
usa `mia_world.cli`.

Salida: por cada corrida se crea `eval/results/<run_id>/` con:
  - `<scenario_id>__attempt<k>.json`  (registro crudo por intento)
  - `summary.json`                    (métricas agregadas, machine-readable)
  - `summary.md`                      (resumen legible para pegar en el informe)
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mia_world.goals import check_goal
from mia_world.scenarios import list_scenarios, load_scenario
from mia_world.state import Scenario
from mia_world.tools import make_world_tools

from eval.judge import judge_trajectory
from eval.metrics import aggregate, summarize_attempt

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCENARIOS_DIR = REPO_ROOT / "scenarios"
DEFAULT_RESULTS_DIR = Path(__file__).resolve().parent / "results"


# ---------------------------------------------------------------------------
# Variantes experimentales (ablations)
#
# Cada builder recibe el `build_agent` del módulo del estudiante y devuelve
# un agente ya configurado para la corrida. Viven acá (no en
# student_framework) porque son decisiones de la infraestructura de
# evaluación, no del framework en sí.
# ---------------------------------------------------------------------------


def _ablation_baseline(build_agent: Callable[..., Any]) -> Any:
    """Agente tal cual lo entrega `build_agent()`, sin cambios."""
    return build_agent()


def _ablation_no_m1_tools(build_agent: Callable[..., Any]) -> Any:
    """Ídem baseline, pero sin las 3 tools de M1 registradas (calculadora,
    lector_archivo, conversor_unidades) — solo quedarán las del mundo.

    `build_agent()` las registra internamente sin exponer un flag para
    desactivarlas, así que construimos `MyAgent` directamente en vez de
    pasar por `build_agent`. Mide si esas herramientas "de ruido" (fuera
    de contexto para una sala de escape) le cuestan calls o confusión al
    agente frente a tenerlas disponibles sin necesidad.
    """
    from mia_agents.llm_client import LLMClient
    from student_framework.agent import MyAgent

    return MyAgent(
        llm_client=LLMClient.from_env(),
        system_prompt="Sos un agente muy eficiente hincha de River",
        max_iterations=20,
        max_history_messages=100,
    )


def _ablation_low_history_budget(build_agent: Callable[..., Any]) -> Any:
    """Ídem baseline, pero con `max_history_messages` muy chico (6).

    Mide si la ventana deslizante de M2 sostiene la coherencia en
    escenarios largos (p. ej. `vault-combination`, 21 calls óptimas)
    cuando el presupuesto de contexto es mucho más agresivo que el
    default (100).
    """
    return build_agent({"max_history_messages": 6})


def _ablation_tight_max_iterations(build_agent: Callable[..., Any]) -> Any:
    """Ídem baseline, pero con `max_iterations` ajustado a un margen mínimo
    sobre el peor caso conocido — mide qué tan cerca del óptimo necesita
    operar el agente para no chocar contra el límite de pasos."""
    return build_agent({"max_iterations": 8})


ABLATIONS: dict[str, Callable[[Callable[..., Any]], Any]] = {
    "baseline": _ablation_baseline,
    "no_m1_tools": _ablation_no_m1_tools,
    "low_history_budget": _ablation_low_history_budget,
    "tight_max_iterations": _ablation_tight_max_iterations,
}


# ---------------------------------------------------------------------------
# Ejecución de un intento
# ---------------------------------------------------------------------------


def _run_one_attempt(
    scenario_path: Path,
    build_agent: Callable[..., Any],
    ablation: str,
    attempt_index: int,
) -> dict[str, Any]:
    scenario: Scenario = load_scenario(scenario_path)
    world = scenario.initial_world

    agent = ABLATIONS[ablation](build_agent)
    for fn, schema in make_world_tools(world):
        agent.register_tool(fn, schema)

    record: dict[str, Any] = {
        "scenario_id": scenario.id,
        "difficulty": scenario.difficulty,
        "ablation": ablation,
        "attempt": attempt_index,
        "user_message": scenario.user_message,
        "goal": scenario.goal,
    }

    start = time.perf_counter()
    try:
        result = agent.run(scenario.user_message)
    except Exception as exc:  # el harness nunca debe abortar la corrida completa
        record["harness_error"] = f"{type(exc).__name__}: {exc}"
        record["goal_achieved"] = False
        record["goal_reason"] = "el agente lanzó una excepción no manejada"
        record["steps"] = []
        record["final_answer"] = None
        record["input_tokens"] = None
        record["output_tokens"] = None
        record["latency_s"] = time.perf_counter() - start
        return record

    latency = time.perf_counter() - start
    achieved, reason = check_goal(world, scenario.goal)

    record["goal_achieved"] = achieved
    record["goal_reason"] = reason
    record["steps"] = [asdict(s) for s in result.steps]
    record["final_answer"] = result.answer
    record["input_tokens"] = result.input_tokens
    record["output_tokens"] = result.output_tokens
    record["latency_s"] = latency
    record["error"] = result.error
    return record


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _resolve_scenario_paths(spec: str | None, scenarios_dir: Path) -> list[Path]:
    all_paths = sorted(scenarios_dir.glob("*.json"))
    if spec is None or spec == "all":
        return all_paths

    by_path = {p: p for p in all_paths}
    candidate = Path(spec)
    if candidate in by_path:
        return [candidate]

    scenarios = {p: load_scenario(p) for p in all_paths}
    by_id = {sc.id: p for p, sc in scenarios.items()}
    if spec in by_id:
        return [by_id[spec]]

    by_diff = [p for p, sc in scenarios.items() if sc.difficulty == spec]
    if by_diff:
        return by_diff

    available = ", ".join(sorted(by_id)) or "(ninguno)"
    raise SystemExit(f"No se encontró el escenario {spec!r}. Disponibles: {available}.")


def _write_summary_md(path: Path, agg: dict[str, Any], run_id: str, ablation: str) -> None:
    lines = [f"# Resultados de evaluación — `{run_id}` (ablation: `{ablation}`)", ""]

    overall = agg["overall"]
    lines.append("## Global")
    lines.append("")
    lines.append(f"- Intentos: {overall['n']}")
    sr = overall["success_rate"]
    lines.append(f"- Success rate: {sr:.1%}" if sr is not None else "- Success rate: n/d")
    eff = overall["mean_efficiency_ratio"]
    lines.append(
        f"- Eficiencia media (calls / óptimo): {eff:.2f}×" if eff is not None else "- Eficiencia media: n/d"
    )
    lat = overall["mean_latency_s"]
    lines.append(f"- Latencia media: {lat:.1f}s" if lat is not None else "- Latencia media: n/d")
    lines.append("")

    lines.append("## Por dificultad")
    lines.append("")
    lines.append("| Dificultad | n | Success rate | Eficiencia media |")
    lines.append("|---|---:|---:|---:|")
    for diff, row in agg["by_difficulty"].items():
        sr = f"{row['success_rate']:.1%}" if row["success_rate"] is not None else "n/d"
        eff = f"{row['mean_efficiency_ratio']:.2f}×" if row["mean_efficiency_ratio"] is not None else "n/d"
        lines.append(f"| {diff} | {row['n']} | {sr} | {eff} |")
    lines.append("")

    lines.append("## Por escenario")
    lines.append("")
    lines.append("| Escenario | n | Success rate | Eficiencia media | Errores (por categoría) |")
    lines.append("|---|---:|---:|---:|---|")
    for sc_id, row in agg["by_scenario"].items():
        sr = f"{row['success_rate']:.1%}" if row["success_rate"] is not None else "n/d"
        eff = f"{row['mean_efficiency_ratio']:.2f}×" if row["mean_efficiency_ratio"] is not None else "n/d"
        errs = ", ".join(f"{k}={v}" for k, v in row["error_counts"].items() if v)
        lines.append(f"| {sc_id} | {row['n']} | {sr} | {eff} | {errs or '—'} |")
    lines.append("")

    lines.append("## Taxonomía de errores (global)")
    lines.append("")
    for cat, cnt in overall["error_counts"].items():
        lines.append(f"- {cat}: {cnt}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval.run")
    parser.add_argument(
        "--scenarios-dir", default=str(DEFAULT_SCENARIOS_DIR),
        help="Directorio con los .json de escenarios (default: ./scenarios).",
    )
    parser.add_argument(
        "--module", default="student_framework",
        help="Módulo que expone build_agent (default: student_framework).",
    )
    parser.add_argument(
        "--scenario", default=None,
        help="Id, dificultad o path de un escenario puntual. Default: todos.",
    )
    parser.add_argument(
        "--repeats", type=int, default=1,
        help="Intentos por escenario (pass@k). Default: 1.",
    )
    parser.add_argument(
        "--ablation", choices=sorted(ABLATIONS), default="baseline",
        help="Variante experimental a correr (ver eval/run.py). Default: baseline.",
    )
    parser.add_argument(
        "--no-judge", action="store_true",
        help="Salta el juicio cualitativo LLM-as-judge (ahorra llamadas al LLM).",
    )
    parser.add_argument(
        "--out-dir", default=str(DEFAULT_RESULTS_DIR),
        help="Directorio raíz de resultados (default: eval/results).",
    )
    args = parser.parse_args(argv)

    module = importlib.import_module(args.module)
    if not hasattr(module, "build_agent"):
        raise SystemExit(f"El módulo {args.module!r} no exporta build_agent.")
    build_agent = module.build_agent

    scenario_paths = _resolve_scenario_paths(args.scenario, Path(args.scenarios_dir))

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{args.ablation}"
    out_dir = Path(args.out_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    attempt_summaries: list[dict[str, Any]] = []
    print(f"# run_id={run_id}  ablation={args.ablation}  escenarios={len(scenario_paths)}  repeats={args.repeats}", file=sys.stderr)

    judge_agent = None
    if not args.no_judge:
        judge_agent = build_agent({"system_prompt": "Sos un evaluador riguroso y objetivo."})

    for scenario_path in scenario_paths:
        for attempt_index in range(args.repeats):
            record = _run_one_attempt(scenario_path, build_agent, args.ablation, attempt_index)

            if judge_agent is not None and not record.get("harness_error"):
                verdict = judge_trajectory(judge_agent, record)
                record["judge"] = verdict.model_dump() if verdict else None

            raw_path = out_dir / f"{record['scenario_id']}__attempt{attempt_index}.json"
            raw_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")

            summary_row = summarize_attempt(record)
            attempt_summaries.append(summary_row)

            status = "OK " if summary_row["success"] else "FAIL"
            print(
                f"[{status}] {record['scenario_id']:<20} intento {attempt_index}  "
                f"calls={summary_row['tool_calls']}  "
                f"latencia={summary_row['latency_s']:.1f}s"
                if summary_row["latency_s"] is not None
                else f"[{status}] {record['scenario_id']:<20} intento {attempt_index}  calls={summary_row['tool_calls']}",
                file=sys.stderr,
            )

    agg = aggregate(attempt_summaries)
    (out_dir / "summary.json").write_text(
        json.dumps(agg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    _write_summary_md(out_dir / "summary.md", agg, run_id, args.ablation)

    print(file=sys.stderr)
    print(f"Resultados en: {out_dir}", file=sys.stderr)
    overall = agg["overall"]
    sr = overall["success_rate"]
    print(
        f"Success rate global: {sr:.1%}" if sr is not None else "Success rate global: n/d",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
