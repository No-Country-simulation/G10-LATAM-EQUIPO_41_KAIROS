"""Lectores de documentos técnicos (PDF, Markdown, texto plano).

Responsable en el equipo Kairos G10: Gaspar Martinez Paiva (Data Engineer).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

EXTENSIONES_SOPORTADAS = {".pdf", ".md", ".markdown", ".txt"}


class DocumentoInvalidoError(Exception):
    """Se lanza cuando el archivo no se puede leer o no tiene texto extraíble."""


@dataclass
class DocumentoLeido:
    titulo: str
    contenido: str
    fuente: str  # nombre de archivo original, para trazabilidad


def limpiar_texto(texto: str) -> str:
    """Normaliza espacios y líneas en blanco repetidas, preservando párrafos.

    También descarta líneas de cita/nota (que empiezan con '> '): en los
    documentos de este proyecto se usan para avisos editoriales (p. ej. "esto
    es material de demo"), no para contenido que deba indexarse ni citarse
    como evidencia de fidelidad.
    """
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    lineas = [l for l in texto.split("\n") if not l.strip().startswith(">")]
    texto = "\n".join(lineas)
    # colapsa 3+ saltos de línea en 2 (separador de párrafo)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    # colapsa espacios/tabs repetidos
    texto = re.sub(r"[ \t]{2,}", " ", texto)
    return texto.strip()


def leer_txt(path: Path) -> DocumentoLeido:
    texto = path.read_text(encoding="utf-8", errors="replace")
    if not texto.strip():
        raise DocumentoInvalidoError(f"El archivo {path.name} está vacío.")
    return DocumentoLeido(titulo=path.stem, contenido=limpiar_texto(texto), fuente=path.name)


def leer_markdown(path: Path) -> DocumentoLeido:
    # Para el MVP tratamos Markdown como texto: la estructura de encabezados
    # se aprovecha en el chunking (ver chunking.py), no aquí.
    return leer_txt(path)


def leer_pdf(path: Path) -> DocumentoLeido:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Falta instalar pypdf: pip install pypdf") from exc

    reader = PdfReader(str(path))
    paginas_texto = []
    for pagina in reader.pages:
        texto_pagina = pagina.extract_text() or ""
        paginas_texto.append(texto_pagina)

    contenido = "\n\n".join(paginas_texto)
    if not contenido.strip():
        raise DocumentoInvalidoError(
            f"El PDF {path.name} no tiene texto extraíble (posible escaneo sin OCR). "
            "NuevaMente no hace OCR en este MVP."
        )
    return DocumentoLeido(titulo=path.stem, contenido=limpiar_texto(contenido), fuente=path.name)


def leer_documento(path: str | Path) -> DocumentoLeido:
    """Punto de entrada único de ingesta: detecta el tipo por extensión."""
    path = Path(path)
    if not path.exists():
        raise DocumentoInvalidoError(f"No existe el archivo: {path}")

    ext = path.suffix.lower()
    if ext not in EXTENSIONES_SOPORTADAS:
        raise DocumentoInvalidoError(
            f"Formato no soportado: {ext}. Soportados: {sorted(EXTENSIONES_SOPORTADAS)}"
        )

    if ext == ".pdf":
        return leer_pdf(path)
    if ext in (".md", ".markdown"):
        return leer_markdown(path)
    return leer_txt(path)


def leer_texto_plano(titulo: str, contenido: str, fuente: str = "texto_directo") -> DocumentoLeido:
    """Para cuando el contenido llega ya como string (p. ej. desde la API)."""
    if not contenido or not contenido.strip():
        raise DocumentoInvalidoError("El contenido del documento está vacío.")
    return DocumentoLeido(titulo=titulo, contenido=limpiar_texto(contenido), fuente=fuente)
