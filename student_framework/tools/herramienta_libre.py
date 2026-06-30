"""Herramienta obligatoria #3 — Conversor de unidades de medida.
"""

from typing import Annotated, Literal

from pydantic import Field

from mia_agents.types import ToolSchema

_LONG = "longitud"
_MASA = "masa"
_TEMP = "temperatura"

_META: dict[str, tuple[str, float]] = {
    "km":  (_LONG, 1_000),
    "m":   (_LONG, 1),
    "cm":  (_LONG, 0.01),
    "mm":  (_LONG, 0.001),
    "mi":  (_LONG, 1_609.344),
    "ft":  (_LONG, 0.3048),
    "in":  (_LONG, 0.0254),
    "kg":  (_MASA, 1),
    "g":   (_MASA, 0.001),
    "mg":  (_MASA, 1e-6),
    "lb":  (_MASA, 0.453592),
    "oz":  (_MASA, 0.0283495),
    "C":   (_TEMP, 1),
    "F":   (_TEMP, 1),
    "K":   (_TEMP, 1),
}

UnidadLiteral = Literal[
    "km", "m", "cm", "mm", "mi", "ft", "in",
    "kg", "g", "mg", "lb", "oz",
    "C", "F", "K",
]


def _convertir_temperatura(valor: float, origen: str, destino: str) -> float:
    if origen == "C":
        celsius = valor
    elif origen == "F":
        celsius = (valor - 32) * 5 / 9
    else:
        celsius = valor - 273.15

    if destino == "C":
        return celsius
    elif destino == "F":
        return celsius * 9 / 5 + 32
    else:
        return celsius + 273.15


def conversor_unidades(
    valor: Annotated[float, Field(description="Valor numérico a convertir.")],
    unidad_origen: Annotated[UnidadLiteral, Field(description="Unidad de origen.")],
    unidad_destino: Annotated[UnidadLiteral, Field(description="Unidad de destino.")],
) -> str:
    """Convierte un valor entre unidades de longitud, masa o temperatura.

    Longitud: km, m, cm, mm, mi, ft, in.
    Masa:     kg, g, mg, lb, oz.
    Temperatura: C (Celsius), F (Fahrenheit), K (Kelvin).

    Devuelve el resultado formateado, o un mensaje de error si las
    unidades son incompatibles o desconocidas.
    """
    if unidad_origen not in _META or unidad_destino not in _META:
        return f"Error: unidad desconocida '{unidad_origen}' o '{unidad_destino}'."

    mag_origen, factor_origen = _META[unidad_origen]
    mag_destino, factor_destino = _META[unidad_destino]

    if mag_origen != mag_destino:
        return (
            f"Error: no se puede convertir '{unidad_origen}' a '{unidad_destino}' "
            f"(magnitudes distintas: {mag_origen} vs {mag_destino})."
        )

    if mag_origen == _TEMP:
        resultado = _convertir_temperatura(valor, unidad_origen, unidad_destino)
    else:
        resultado = valor * factor_origen / factor_destino

    return f"{valor} {unidad_origen} = {round(resultado, 9)} {unidad_destino}"


conversor_unidades_schema = ToolSchema.from_callable(conversor_unidades)
