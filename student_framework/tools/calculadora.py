"""Herramienta obligatoria #1 — Calculadora simple.

M2: errores recuperables con mensajes accionables (qué parámetro falló,
qué valor recibió, por qué, y cómo corregirlo) en lugar de mensajes
genéricos.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from mia_agents.types import ToolSchema

_OPERADORES = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
    "/": lambda a, b: a / b,
    "%": lambda a, b: a % b,
}
_OPERADORES_DIV_CERO = {"/", "%"}


def _parse_operando(valor: object, etiqueta: str) -> tuple[float | None, str | None]:
    """Intenta convertir `valor` a float. Devuelve (número, None) o
    (None, mensaje de error accionable) indicando qué parámetro falló,
    qué valor recibió y por qué no es válido."""
    if isinstance(valor, bool):
        # bool es subclase de int en Python; lo tratamos como inválido
        # porque no es un operando numérico con el que un usuario opere.
        return None, (
            f"Error en el parámetro '{etiqueta}': se recibió un booleano "
            f"({valor!r}), no un número. Pasá un valor numérico, p. ej. 3 o 3.5."
        )
    try:
        return float(valor), None
    except (TypeError, ValueError):
        return None, (
            f"Error en el parámetro '{etiqueta}': el valor recibido ({valor!r}, "
            f"tipo {type(valor).__name__}) no es un número válido. "
            f"Enviá '{etiqueta}' como número (int o float), p. ej. 3 o 3.5."
        )


def calculadora(
    a: Annotated[float, Field(description="Primer operando.")],
    b: Annotated[float, Field(description="Segundo operando.")],
    operador: Annotated[
        str, Field(description="Operador aritmético: +, -, *, /, %")
    ],
) -> str:
    """La calculadora ejecuta operaciones aritméticas entre dos números.

    Operadores soportados: +, -, *, /, %. Ante operandos no numéricos,
    operador no soportado o división/módulo por cero devuelve un mensaje
    de error accionable en lugar de fallar silenciosamente.
    """
    a_val, err_a = _parse_operando(a, "a")
    if err_a:
        return err_a

    b_val, err_b = _parse_operando(b, "b")
    if err_b:
        return err_b

    if operador not in _OPERADORES:
        permitidos = ", ".join(sorted(_OPERADORES))
        return (
            f"Error: operador '{operador}' no soportado. "
            f"Operadores permitidos: {permitidos}."
        )

    if operador in _OPERADORES_DIV_CERO and b_val == 0:
        if operador == "/":
            return (
                "Error: no se puede dividir por cero (b=0). La división por "
                "cero no está definida; probá con un valor de 'b' distinto de 0."
            )
        return (
            "Error: no se puede calcular el módulo con divisor cero (b=0). "
            "El operador '%' requiere que 'b' sea distinto de 0."
        )

    resultado = _OPERADORES[operador](a_val, b_val)
    return str(resultado)


calculadora_schema = ToolSchema.from_callable(calculadora)
