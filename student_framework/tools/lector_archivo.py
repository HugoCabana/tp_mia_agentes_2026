"""Herramienta obligatoria #2 — Lector de archivos de texto.
"""

import os
from pathlib import Path
from typing import Annotated

from pydantic import Field

from mia_agents.types import ToolSchema

_BASE = Path(os.getcwd()).resolve()


def lector_archivo(
    ruta: Annotated[
        str,
        Field(
            description=(
                "Ruta relativa al archivo de texto a leer. "
                "Solo se permiten rutas dentro del directorio de trabajo."
            )
        ),
    ],
) -> str:
    """Lee el contenido de un archivo de texto y lo devuelve como string.

    Acceso restringido al directorio de trabajo para evitar lecturas
    fuera del alcance permitido. Devuelve un mensaje de error descriptivo
    si el archivo no existe, está fuera del alcance o no puede leerse.
    """
    try:
        target = (_BASE / ruta).resolve()
    except Exception as exc:
        return f"Error al resolver la ruta: {exc}"

    if not str(target).startswith(str(_BASE)):
        return f"Error: acceso denegado — '{ruta}' está fuera del directorio permitido."

    if not target.exists():
        return f"Error: el archivo '{ruta}' no existe."

    if not target.is_file():
        return f"Error: '{ruta}' no es un archivo."

    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: '{ruta}' no es texto UTF-8 válido."
    except OSError as exc:
        return f"Error al leer '{ruta}': {exc}"


lector_archivo_schema = ToolSchema.from_callable(lector_archivo)
