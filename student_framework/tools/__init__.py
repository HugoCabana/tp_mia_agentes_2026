"""Añadan aquí sus tres herramientas obligatorias (M1).

  1. **Calculadora simple** — dos operandos numéricos y operador +, -, *, %.
  2. **Lector de archivos** — ruta → contenido de archivo de texto.
  3. **Herramienta libre** — la que quieran.

Cada herramienta debe ser un callable que acepte argumentos por palabra clave
correspondientes a los parámetros de su ToolSchema y devuelva una cadena.
Regístrenlas en `student_framework/__init__.py:build_agent`.

Mira `example.py`: callable tipado + `ToolSchema.from_callable(...)`.
Detalle completo en `ENUNCIADO_M1.md`.
"""
from __future__ import annotations

from mia_agents.llm_client import LLMClient
from student_framework.agent import MyAgent
from student_framework.tools.calculadora import calculadora, calculadora_schema
from student_framework.tools.lector_archivo import lector_archivo, lector_archivo_schema
from student_framework.tools.herramienta_libre import conversor_unidades, conversor_unidades_schema

__all__ = [
    "calculadora",
    "calculadora_schema",
    "lector_archivo",
    "lector_archivo_schema",
    "conversor_unidades",
    "conversor_unidades_schema",
]

def build_agent(config: dict | None = None) -> MyAgent:
    config = config or {}
    llm = config.get("llm_client") or LLMClient.from_env()
    agent = MyAgent(
        llm_client=llm,
        system_prompt=config.get("system_prompt", "Sos un agente muy eficiente hincha de River"),
        max_iterations=config.get("max_iterations", 20),
    )
    agent.register_tool(calculadora, calculadora_schema)
    return agent