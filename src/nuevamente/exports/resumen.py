"""Estructura del Resumen Ejecutivo para las exportaciones.

El esquema del resumen (contrato JSON) guarda texto: la idea central, el contexto y los
hallazgos van en párrafos de `resumen`; los puntos clave como «Título: explicación»; y
los riesgos y recomendaciones con su prefijo en `decisiones_o_riesgos`. Aquí se separa
cada parte para presentarla ordenada, igual que en la interfaz web (renderResumen).
Un resumen sin esa estructura (materiales anteriores) se reparte de la misma forma.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from nuevamente.schemas.formatos import ResumenEjecutivoContenido

_PARRAFOS = re.compile(r"\n\s*\n")
_ORACIONES = re.compile(r"(?<=[.!?…])\s+")
_NUMERACION = re.compile(r"^\d{1,2}(?:\.\d{1,2})*[.)]?\s+")
_PREFIJO = re.compile(r"^\s*(riesgos?|recomendaci[oó]n(?:es)?|decisi[oó]n(?:es)?)\s*:\s*", re.IGNORECASE)


@dataclass
class PartesResumen:
    idea: str
    resto: list[str]
    puntos: list[tuple[str, str]]  # (título, explicación); la explicación puede ir vacía
    riesgos: list[str] = field(default_factory=list)
    recomendaciones: list[str] = field(default_factory=list)
    decisiones: list[str] = field(default_factory=list)


def _punto(texto: str) -> tuple[str, str]:
    limpio = _NUMERACION.sub("", texto.strip())
    corte = limpio.find(": ")
    if 0 < corte <= 80:
        return limpio[:corte], limpio[corte + 2 :]
    return limpio, ""


def partes_resumen(c: ResumenEjecutivoContenido) -> PartesResumen:
    parrafos = [p.strip() for p in _PARRAFOS.split(c.resumen) if p.strip()]
    if len(parrafos) > 1:
        idea, resto = parrafos[0], parrafos[1:]
    else:
        oraciones = _ORACIONES.split(c.resumen.strip())
        idea, resto = oraciones[0], ([" ".join(oraciones[1:])] if len(oraciones) > 1 else [])

    partes = PartesResumen(idea=idea, resto=resto, puntos=[_punto(p) for p in c.puntos_clave])
    for d in c.decisiones_o_riesgos:
        m = _PREFIJO.match(d)
        texto = d[m.end() :] if m else d
        texto = texto[:1].upper() + texto[1:]
        tipo = m.group(1).lower() if m else ""
        if tipo.startswith("riesgo"):
            partes.riesgos.append(texto)
        elif tipo.startswith("recomend"):
            partes.recomendaciones.append(texto)
        else:
            partes.decisiones.append(texto)
    return partes
