#!/usr/bin/env python3
"""Genera requirements.txt con las versiones exactas que usa el proyecto.

Parte de las dependencias de pyproject.toml (y de los extras elegidos), recorre sus
dependencias transitivas y fija cada una a la versión instalada en el entorno actual.
A diferencia de `pip freeze`, solo incluye lo que el proyecto necesita, no todo lo que
haya en el .venv.

Las dependencias que solo aplican a algunas plataformas (uvloop fuera de Windows,
colorama solo en Windows…) llevan su marca `; sys_platform …`, para que el mismo archivo
sirva en macOS, Linux y Windows. Si una de ellas no está instalada aquí (colorama en un
Mac), se conserva la versión que ya tenía requirements.txt.

Uso (con el entorno virtual del proyecto activado):
    python scripts/generar_requirements.py                  # todos los extras
    python scripts/generar_requirements.py --extras dev,ui  # solo esos
    python scripts/generar_requirements.py --check          # falla si no está al día

Requiere Python 3.11 o superior (usa tomllib) y el paquete `packaging`.
"""
from __future__ import annotations

import argparse
import sys
import tomllib
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

RAIZ = Path(__file__).resolve().parents[1]
PYPROJECT = RAIZ / "pyproject.toml"
REQUIREMENTS = RAIZ / "requirements.txt"

#: Plataformas para las que se evalúan las marcas de cada dependencia.
PLATAFORMAS = {"darwin": "Darwin", "linux": "Linux", "win32": "Windows"}


@dataclass
class Paquete:
    nombre: str
    version: str | None  # None: no instalado en este entorno
    plataformas: set[str] = field(default_factory=set)


def _plataformas_de(req: Requirement, extra: str, heredadas: set[str]) -> set[str]:
    """Plataformas (de las heredadas) en las que la dependencia aplica."""
    if req.marker is None:
        return set(heredadas)
    return {
        p
        for p in heredadas
        if req.marker.evaluate({"sys_platform": p, "platform_system": PLATAFORMAS[p], "extra": extra})
    }


def _version_instalada(nombre: str) -> str | None:
    try:
        return metadata.version(nombre)
    except metadata.PackageNotFoundError:
        return None


def _requisitos_del_proyecto(extras: list[str]) -> list[tuple[Requirement, str]]:
    proyecto = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    opcionales = proyecto.get("optional-dependencies", {})
    desconocidos = [e for e in extras if e not in opcionales]
    if desconocidos:
        sys.exit(f"Extras desconocidos: {', '.join(desconocidos)}. Disponibles: {', '.join(opcionales)}")
    reqs = [(Requirement(r), "") for r in proyecto.get("dependencies", [])]
    for extra in extras:
        reqs += [(Requirement(r), "") for r in opcionales[extra]]
    return reqs


def resolver(extras: list[str]) -> dict[str, Paquete]:
    """Recorre el árbol de dependencias desde pyproject.toml."""
    paquetes: dict[str, Paquete] = {}
    # (requisito, extra con el que se evalúa su marca, plataformas heredadas del padre)
    pendientes = [(req, extra, set(PLATAFORMAS)) for req, extra in _requisitos_del_proyecto(extras)]
    visitados: set[tuple[str, frozenset[str], frozenset[str]]] = set()

    while pendientes:
        req, extra, heredadas = pendientes.pop()
        plataformas = _plataformas_de(req, extra, heredadas)
        if not plataformas:
            continue  # no aplica en ninguna plataforma (p. ej. solo para Python antiguos)
        clave = canonicalize_name(req.name)
        version = _version_instalada(req.name)
        paquete = paquetes.setdefault(clave, Paquete(req.name, version))
        paquete.plataformas |= plataformas
        if version is None:
            continue  # sin metadatos locales no se pueden recorrer sus dependencias

        marca = (clave, frozenset(req.extras), frozenset(plataformas))
        if marca in visitados:
            continue
        visitados.add(marca)
        dist = metadata.distribution(req.name)
        paquete.nombre = dist.metadata["Name"]
        for texto in dist.requires or []:
            hijo = Requirement(texto)
            # se sigue la dependencia base ("") y la de cada extra pedido (uvicorn[standard])
            for extra_hijo in ["", *req.extras]:
                if _plataformas_de(hijo, extra_hijo, plataformas):
                    pendientes.append((hijo, extra_hijo, plataformas))
                    break
    paquetes.pop(canonicalize_name("nuevamente"), None)  # el propio proyecto va como "-e ."
    return paquetes


def _marca_de_plataforma(plataformas: set[str]) -> str:
    if plataformas >= set(PLATAFORMAS):
        return ""
    if len(plataformas) == 1:
        return f' ; sys_platform == "{next(iter(plataformas))}"'
    excluidas = sorted(set(PLATAFORMAS) - plataformas)
    return " ; " + " and ".join(f'sys_platform != "{p}"' for p in excluidas)


def _versiones_previas() -> dict[str, str]:
    """Versiones fijadas en el requirements.txt actual, para lo que no está instalado aquí."""
    previas: dict[str, str] = {}
    if REQUIREMENTS.exists():
        for linea in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith(("#", "-")):
                req = Requirement(linea)
                fijada = next((s.version for s in req.specifier if s.operator == "=="), None)
                if fijada:
                    previas[canonicalize_name(req.name)] = fijada
    return previas


def generar(extras: list[str]) -> str:
    paquetes = resolver(extras)
    previas = _versiones_previas()
    lineas = [
        "# Generado por scripts/generar_requirements.py; no editar a mano.",
        f"# Extras incluidos: {', '.join(extras) or 'ninguno'}. Python {sys.version_info.major}.{sys.version_info.minor}.",
        "# Instalar con: pip install -r requirements.txt",
        "",
        "# El propio proyecto (paquete nuevamente), instalado desde la raíz del repo",
        "-e .",
        "",
    ]
    for clave in sorted(paquetes, key=str.lower):
        p = paquetes[clave]
        version = p.version or previas.get(clave)
        if version is None:
            print(f"Aviso: {p.nombre} no está instalado ni fijado; se deja sin versión.", file=sys.stderr)
        lineas.append(f"{p.nombre}{f'=={version}' if version else ''}{_marca_de_plataforma(p.plataformas)}")
    return "\n".join(lineas) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    opcionales = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"].get("optional-dependencies", {})
    parser.add_argument(
        "--extras",
        default=",".join(opcionales),
        help=f"extras de pyproject.toml separados por comas (por defecto: {','.join(opcionales)})",
    )
    parser.add_argument("--check", action="store_true", help="no escribe; falla si requirements.txt no está al día")
    args = parser.parse_args()

    extras = [e.strip() for e in args.extras.split(",") if e.strip()]
    contenido = generar(extras)
    if args.check:
        actual = REQUIREMENTS.read_text(encoding="utf-8") if REQUIREMENTS.exists() else ""
        if actual != contenido:
            print("requirements.txt no está al día: ejecuta python scripts/generar_requirements.py", file=sys.stderr)
            return 1
        print("requirements.txt está al día.")
        return 0
    REQUIREMENTS.write_text(contenido, encoding="utf-8")
    n = sum(1 for l in contenido.splitlines() if l and not l.startswith(("#", "-")))
    print(f"requirements.txt generado: {n} paquetes (extras: {', '.join(extras)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
