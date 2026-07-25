"""Herramienta obligatoria #2 — Lector de archivos de texto.

M2: errores recuperables con mensajes accionables:
  - ruta vacía / absoluta / con '..' / que escapa del sandbox: se
    explica la regla violada y cómo debe verse una ruta válida.
  - archivo inexistente: si el directorio contenedor existe, se listan
    los archivos disponibles ahí para que el LLM pueda elegir la ruta
    correcta.
  - la ruta apunta a un directorio: se indica y se lista su contenido.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

from pydantic import Field

from mia_agents.types import ToolSchema

_BASE = Path(os.getcwd()).resolve()
_MAX_LISTADO = 30  # tope de entradas a mostrar en un listado de directorio


def _listar_directorio(directorio: Path) -> str:
    try:
        entradas = sorted(p.name + ("/" if p.is_dir() else "") for p in directorio.iterdir())
    except OSError as exc:
        return f"(no se pudo listar el directorio: {exc})"
    if not entradas:
        return "(el directorio está vacío)"
    mostrar = entradas[:_MAX_LISTADO]
    listado = ", ".join(mostrar)
    if len(entradas) > _MAX_LISTADO:
        listado += f", ... (+{len(entradas) - _MAX_LISTADO} más)"
    return listado


def lector_archivo(
    ruta: Annotated[
        str,
        Field(
            description=(
                "Ruta relativa (dentro del directorio de trabajo) al archivo "
                "de texto a leer. No debe ser absoluta ni contener '..'."
            )
        ),
    ],
) -> str:
    """Lee el contenido de un archivo de texto y lo devuelve como string.

    Acceso restringido al directorio de trabajo (sandbox). Ante rutas
    inválidas, archivos inexistentes o rutas que apuntan a un
    directorio, devuelve un mensaje de error accionable en vez de uno
    genérico, incluyendo listados de directorio cuando corresponde para
    que el LLM pueda elegir una ruta válida.
    """
    # -- Validaciones de la ruta cruda, antes de resolverla ---------------
    if not ruta or not ruta.strip():
        return (
            "Error: la ruta no puede estar vacía. Pasá una ruta relativa "
            "dentro del directorio de trabajo, p. ej. 'datos/notas.txt'."
        )

    if os.path.isabs(ruta):
        return (
            f"Error: '{ruta}' es una ruta absoluta y no está permitido. "
            "Usá una ruta relativa al directorio de trabajo, "
            "p. ej. 'datos/notas.txt' (sin '/' inicial)."
        )

    partes = Path(ruta).parts
    if ".." in partes:
        return (
            f"Error: la ruta '{ruta}' contiene '..' y eso permitiría escapar "
            "del directorio permitido (sandbox). Usá una ruta relativa que se "
            "quede dentro del directorio de trabajo, p. ej. 'datos/notas.txt'."
        )

    try:
        target = (_BASE / ruta).resolve()
    except Exception as exc:
        return (
            f"Error al resolver la ruta '{ruta}': {exc}. Probá con una ruta "
            "relativa simple, p. ej. 'datos/notas.txt'."
        )

    try:
        target.relative_to(_BASE)
    except ValueError:
        return (
            f"Error: la ruta '{ruta}' resuelve fuera del directorio permitido "
            f"({_BASE}). Usá una ruta relativa que se quede dentro del "
            "directorio de trabajo."
        )

    # -- El archivo no existe: listar el directorio contenedor si es válido --
    if not target.exists():
        contenedor = target.parent
        if contenedor.exists() and contenedor.is_dir():
            listado = _listar_directorio(contenedor)
            return (
                f"Error: el archivo '{ruta}' no existe en "
                f"'{contenedor.relative_to(_BASE) or '.'}'. "
                f"Archivos disponibles ahí: {listado}."
            )
        return (
            f"Error: el archivo '{ruta}' no existe y su directorio contenedor "
            "tampoco. Verificá la ruta completa."
        )

    # -- La ruta apunta a un directorio, no a un archivo ------------------
    if target.is_dir():
        listado = _listar_directorio(target)
        return (
            f"Error: '{ruta}' es un directorio, no un archivo. "
            f"Contenido de ese directorio: {listado}. "
            "Especificá el archivo dentro de ese directorio que querés leer."
        )

    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return (
            f"Error: '{ruta}' no es texto UTF-8 válido (parece un archivo "
            "binario). Esta herramienta solo puede leer archivos de texto."
        )
    except OSError as exc:
        return f"Error al leer '{ruta}': {exc}."


lector_archivo_schema = ToolSchema.from_callable(lector_archivo)
