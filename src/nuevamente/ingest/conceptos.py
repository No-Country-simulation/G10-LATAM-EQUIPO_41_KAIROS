"""Extracción determinista de conceptos clave de un texto, sin LLM.

Responsable en el equipo Kairos G10: Gaspar Martinez Paiva (Data Engineer).

Un documento sin títulos (texto pegado, muchos PDF) queda en una sola sección, "Documento
completo", y ese nombre no sirve como concepto clave ni como tema de una tarjeta. Aquí se
toman los términos técnicos que el propio texto marca: siglas ("VCN", "API"), nombres de
varias palabras con mayúscula ("Security Lists", "Organización Mundial de la Salud") y la
sigla que acompaña a su nombre largo ("Virtual Cloud Network (VCN)" -> "VCN").
"""
from __future__ import annotations

import re
import unicodedata

_MAYUS = "A-ZÁÉÍÓÚÑÜ"
_PALABRA = rf"(?:[{_MAYUS}][\w-]*)"
# palabras con mayúscula seguidas, con "de", "del", "de la"... entre ellas ("Ministerio de Salud");
# "y" no une: "NAT Gateways y Security Lists" son dos conceptos
_FRASE = re.compile(rf"{_PALABRA}(?:\s+(?:(?:de|del|de la|de las|de los)\s+)?{_PALABRA}){{0,4}}")
_SIGLA_TRAS_NOMBRE = re.compile(r"\s*\(([A-ZÁÉÍÓÚÑ]{2,8}s?)\)")
# inicio de oración o de línea, también tras las marcas de Markdown ("# ", "**", "- ", "1. ")
_INICIO_ORACION = re.compile(r"(?:^|[.!?:;][*_]*\s+|\n)[\s#>*_\-|]*(?:\d+[.)]\s+)?[*_]*$")
# artículos y palabras que llevan mayúscula solo por empezar la oración
_COMUNES = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "este", "esta", "estos", "estas", "ese",
    "esa", "en", "con", "para", "por", "de", "del", "al", "y", "o", "si", "no", "se", "su", "sus",
    "es", "son", "como", "cada", "todo", "toda", "todos", "todas", "también", "además", "sin",
    "similar", "según", "cuando", "donde", "que", "qué", "porque", "aunque", "mientras",
}


def _quitar_comunes_iniciales(frase: str) -> str:
    palabras = frase.split()
    while palabras and palabras[0].lower() in _COMUNES:
        palabras = palabras[1:]
    while palabras and palabras[-1].lower() in _COMUNES:
        palabras = palabras[:-1]
    return " ".join(palabras)


def extraer_conceptos(texto: str, maximo: int = 6, excluir: set[str] | None = None) -> list[str]:
    """Conceptos clave en el orden en que aparecen, sin repetidos (sin distinguir mayúsculas)."""
    texto = unicodedata.normalize("NFC", texto)  # "Prevencio\u0301n" -> "Prevención"
    excluir = {e.lower() for e in (excluir or set())}
    conceptos: list[str] = []
    vistos: set[str] = set()

    def agregar(concepto: str) -> None:
        clave = concepto.lower().rstrip("s")
        if concepto and clave not in vistos and concepto.lower() not in excluir:
            vistos.add(clave)
            conceptos.append(concepto)

    for m in _FRASE.finditer(texto):
        frase = m.group(0)
        sigla = _SIGLA_TRAS_NOMBRE.match(texto, m.end())
        if sigla:  # "Virtual Cloud Network (VCN)": la sigla es el nombre corto del concepto
            vistos.add(_quitar_comunes_iniciales(frase).lower().rstrip("s"))
            agregar(sigla.group(1))
            continue
        frase = _quitar_comunes_iniciales(frase)
        if not frase:
            continue
        es_sigla = frase.isupper() and len(frase) >= 2
        al_inicio = bool(_INICIO_ORACION.search(texto[: m.start()]))
        # una sola palabra con mayúscula al empezar la oración suele ser una palabra común
        if " " not in frase and not es_sigla and (al_inicio or len(frase) < 4):
            continue
        agregar(frase)
        if len(conceptos) >= maximo:
            break
    return conceptos[:maximo]
