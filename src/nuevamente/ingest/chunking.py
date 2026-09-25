"""Chunking del documento con solapamiento y metadatos de trazabilidad.

Responsable en el equipo Kairos G10: Gaspar Martinez Paiva (Data Engineer).

Cada chunk conserva un chunk_id estable, la sección aproximada (por encabezado
Markdown o por posición) y el índice de párrafo, para que el módulo de fidelidad
(Adrian, ML Engineer) pueda citar exactamente de dónde salió cada afirmación.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from nuevamente.config import settings
from nuevamente.ingest.readers import limpiar_texto


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    texto: str
    seccion: str
    orden: int


def _doc_id(titulo: str, contenido: str) -> str:
    """ID determinista del documento, para aislar su colección en el vector store.

    Se calcula sobre el contenido completo: dos documentos que solo difieren
    después del carácter 500 no deben compartir colección ni objeto original.
    """
    h = hashlib.sha256(f"{titulo}::{contenido}".encode("utf-8"))
    return h.hexdigest()[:16]


def _detectar_secciones(contenido: str) -> list[tuple[str, str]]:
    """Divide por encabezados Markdown (#, ##, ###) si existen; si no, una sola sección."""
    patron = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    matches = list(patron.finditer(contenido))
    if not matches:
        return [("Documento completo", contenido)]

    secciones: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        titulo_seccion = m.group(2).strip()
        inicio = m.end()
        fin = matches[i + 1].start() if i + 1 < len(matches) else len(contenido)
        cuerpo = contenido[inicio:fin].strip()
        if cuerpo:
            secciones.append((titulo_seccion, cuerpo))
    if not secciones:
        return [("Documento completo", contenido)]
    return secciones


def _partir_con_solapamiento(texto: str, tamano: int, solapamiento: int) -> list[str]:
    """Parte un texto largo en fragmentos de `tamano` caracteres con `solapamiento`,
    intentando no cortar a mitad de una oración cuando es posible."""
    texto = texto.strip()
    if len(texto) <= tamano:
        return [texto] if texto else []

    fragmentos = []
    inicio = 0
    n = len(texto)
    while inicio < n:
        fin = min(inicio + tamano, n)
        if fin < n:
            # 1) intenta cortar en el último punto seguido antes de `fin`
            corte = texto.rfind(". ", inicio, fin)
            if corte != -1 and corte > inicio + tamano // 2:
                fin = corte + 1
            else:
                # 2) si no hay una oración completa, corta en el último espacio
                # antes de `fin` para no partir una palabra a la mitad
                corte_espacio = texto.rfind(" ", inicio, fin)
                if corte_espacio != -1 and corte_espacio > inicio:
                    fin = corte_espacio
        fragmento = texto[inicio:fin].strip()
        if fragmento:
            fragmentos.append(fragmento)
        if fin >= n:
            break
        inicio = max(fin - solapamiento, inicio + 1)
        # evita que el siguiente fragmento empiece a mitad de una palabra
        if inicio < n and texto[inicio - 1] not in (" ", "\n"):
            siguiente_espacio = texto.find(" ", inicio, min(inicio + 50, n))
            if siguiente_espacio != -1:
                inicio = siguiente_espacio + 1
    return fragmentos


def chunkear_documento(
    titulo: str,
    contenido: str,
    tamano: int | None = None,
    solapamiento: int | None = None,
) -> list[Chunk]:
    """Punto de entrada del pipeline de ingesta: documento -> lista de Chunk."""
    tamano = tamano or settings.chunk_size
    solapamiento = solapamiento or settings.chunk_overlap
    contenido = limpiar_texto(contenido)
    doc_id = _doc_id(titulo, contenido)

    chunks: list[Chunk] = []
    orden = 0
    for seccion, cuerpo in _detectar_secciones(contenido):
        for fragmento in _partir_con_solapamiento(cuerpo, tamano, solapamiento):
            chunk_id = f"{doc_id}-c{orden:03d}"
            chunks.append(
                Chunk(chunk_id=chunk_id, doc_id=doc_id, texto=fragmento, seccion=seccion, orden=orden)
            )
            orden += 1
    return chunks
