
from __future__ import annotations
from mia_agents.types import ToolSchema
from typing import Annotated
from pydantic import Field

def calculadora (
        a: Annotated[float, Field(description="Primer Operando.")],
        b: Annotated[float, Field(description="Segunda Operando.")],
        operador: Annotated[str, Field(description="Operador aritmetico: +, -, *, /, %")],
) -> str:
    """La calculadora ejecuta operaciones aritmeticas entre dos números."""

    try:
        a_val = float(a)
    except (TypeError, ValueError):
        return f"Error: el primer operando no es un número válido ({a!r})."

    try:
        b_val = float(b)
    except (TypeError, ValueError):
        return f"Error: el segundo operando no es un número válido ({b!r})."

    if operador == "+":
        return str(a_val + b_val)
    
    if operador == "-":
        return str(a_val - b_val)
    
    if operador == "*":
        return str(a_val * b_val)

    if operador == "/":
        if b_val == 0:
            return "Error: división por cero."
        return str(a_val / b_val)

    if operador == "%":
        if b_val == 0:
            return "Error: módulo por cero."
        return str(a_val % b_val)
    
    return f"Operador {operador} no soportado por la presente calculadora"

calculadora_schema = ToolSchema.from_callable(calculadora)