"""Dimensión cualitativa: LLM-as-judge sobre la trayectoria del agente.

Reutiliza `structured_call` (M2) del propio framework para pedirle al LLM
un veredicto estructurado y validado sobre la trayectoria — no un número
de accuracy, sino una rúbrica de *cómo* resolvió (o no) el escenario:
coherencia del plan, acciones redundantes, uso de herramientas fuera de
contexto.

Por qué LLM-as-judge acá: las métricas cuantitativas (éxito, nº de
llamadas) no distinguen "resolvió de casualidad probando todo" de
"resolvió con un plan claro", ni penalizan específicamente que el agente
llame a `calculadora` en medio de una sala de escape. Un juez de texto
libre puede leer la transcripción completa y opinar sobre eso.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class TrajectoryJudgement(BaseModel):
    """Veredicto estructurado sobre una trayectoria del agente."""

    plan_coherence: int = Field(
        ge=1,
        le=5,
        description=(
            "1 = acciones erráticas o repetidas sin aprender del error; "
            "5 = plan claro, cada acción usa lo aprendido de la anterior."
        ),
    )
    redundant_actions: bool = Field(
        description="True si el agente repitió una acción ya fallida sin cambiar el argumento."
    )
    used_out_of_context_tool: bool = Field(
        description=(
            "True si el agente invocó una herramienta ajena al mundo simulado "
            "(calculadora, lector_archivo, conversor_unidades) sin motivo."
        )
    )
    justification: str = Field(
        description="1-3 oraciones explicando el puntaje, citando pasos concretos por número."
    )


class _StructuredCallAgent(Protocol):
    def structured_call(
        self, prompt: str, schema: type[BaseModel], max_repair_attempts: int = 2
    ) -> BaseModel: ...


_JUDGE_PROMPT_TEMPLATE = """\
Sos un evaluador objetivo de agentes que resuelven salas de escape.

Escenario: {scenario_id} (dificultad: {difficulty})
Objetivo del escenario (goal, formato interno): {goal}
Resultado final: {outcome} el objetivo. Motivo: {goal_reason}

Transcripción de la trayectoria (una línea por paso, en orden):
{transcript}

Evaluá la CALIDAD del proceso de razonamiento y planificación del agente
usando la rúbrica del schema, sin dejarte llevar únicamente por si tuvo
éxito o no: un agente puede fallar con un plan razonable (mala suerte /
límite de pasos) o tener éxito a fuerza de prueba y error sin plan.
"""


def _format_transcript(steps: list[dict[str, Any]], final_answer: str | None) -> str:
    lines = []
    for i, step in enumerate(steps, start=1):
        name = step.get("tool_name")
        args = step.get("tool_input")
        out = step.get("tool_output") or step.get("error") or ""
        out_short = out if len(out) <= 200 else out[:200] + "…"
        lines.append(f"{i}. {name}({args}) -> {out_short}")
    if final_answer:
        answer_short = final_answer if len(final_answer) <= 200 else final_answer[:200] + "…"
        lines.append(f"[respuesta final del agente] {answer_short}")
    return "\n".join(lines) if lines else "(sin pasos registrados)"


def judge_trajectory(
    judge_agent: _StructuredCallAgent,
    record: dict[str, Any],
    max_repair_attempts: int = 2,
) -> TrajectoryJudgement | None:
    """Pide a `judge_agent` (cualquier objeto con `structured_call`, típicamente
    un `MyAgent` fresco apuntando al mismo LLM) un veredicto sobre `record`
    (el dict de intento que produce `eval/run.py`).

    Devuelve `None` si el juicio no se pudo obtener tras agotar los
    reintentos de reparación (no aborta la evaluación completa por esto:
    se registra como intento sin juicio cualitativo).
    """
    transcript = _format_transcript(record.get("steps") or [], record.get("final_answer"))
    prompt = _JUDGE_PROMPT_TEMPLATE.format(
        scenario_id=record["scenario_id"],
        difficulty=record.get("difficulty", "unspecified"),
        goal=record.get("goal"),
        outcome="se cumplió" if record.get("goal_achieved") else "NO se cumplió",
        goal_reason=record.get("goal_reason"),
        transcript=transcript,
    )
    try:
        return judge_agent.structured_call(
            prompt, TrajectoryJudgement, max_repair_attempts=max_repair_attempts
        )
    except Exception:
        return None
