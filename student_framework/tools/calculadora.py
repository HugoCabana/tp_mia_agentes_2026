
from __future__ import annotations
from mia_agents.types import ToolSchema
from typing import Annotated
from pydantic import Field

def calculadora (
        a: Annotated[float, Field(description="Primer Operando.")],
        b: Annotated[float, Field(description="Segunda Operando.")],
        operador: Annotated[str, Field(description="Operador aritmetico: +, -, *, /")],
) -> str:
    """La calculadora ejecuta operaciones aritmeticas entre dos números."""

    if operador == "+":
        return str(a + b)
    
    if operador == "-":
        return str(a - b)
    
    if operador == "*":
        return str(a * b)

    if operador == "/":
        return str(a / b)
    
    return f"Operador {operador} no soportado por la presente calculadora"

calculadora_schema = ToolSchema.from_callable(calculadora)