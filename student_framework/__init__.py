"""student_framework — Milestone 1.

Paquete propio del grupo. Implementen el agente en `agent.py` y registren
sus herramientas en `build_agent`. Tanto el runner de la CLI como los tests
de conformidad llaman a `build_agent`, por lo que esta es la única puerta
de entrada pública de su entrega.

Único punto de entrada público: ``build_agent``.
"""

from __future__ import annotations

from typing import Any

from mia_agents.llm_client import LLMClient
from student_framework.agent import MyAgent
from student_framework.tools.calculadora import calculadora, calculadora_schema
from student_framework.tools.lector_archivo import lector_archivo, lector_archivo_schema
from student_framework.tools.herramienta_libre import conversor_unidades, conversor_unidades_schema

__all__ = ["build_agent"]


def build_agent(config: dict[str, Any] | None = None) -> MyAgent:
    """Construye y devuelve una instancia de ``MyAgent`` lista para usar.

    Parámetros opcionales via ``config``:
    - ``"llm_client"``      : cliente LLM (real o mock). Si no se provee,
                              se construye desde variables de entorno.
    - ``"system_prompt"``   : system prompt del agente (str).
    - ``"max_iterations"``  : límite de iteraciones del bucle (int, defecto 20).
    - ``"max_history_messages"``: tope de mensajes en el historial (int, defecto 100).

    Las tres herramientas obligatorias de M1 se registran automáticamente.
    """
    config = config or {}

    llm = config.get("llm_client") or LLMClient.from_env()

    agent = MyAgent(
        llm_client=llm,
        system_prompt=config.get("system_prompt", "Sos un agente muy eficiente hincha de River"),
        max_iterations=config.get("max_iterations", 20),
        max_history_messages=config.get("max_history_messages", 100),
    )

    agent.register_tool(calculadora, calculadora_schema)
    agent.register_tool(lector_archivo, lector_archivo_schema)
    agent.register_tool(conversor_unidades, conversor_unidades_schema)

    return agent
