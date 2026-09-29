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


_ENCABEZADO_MD = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
# "1. ACCESO A LA CONSOLA", "2.3 Modos de configuración": encabezados numerados de PDF/texto
_ENCABEZADO_NUMERADO = re.compile(r"^(\d{1,2}(?:\.\d{1,2})*)[.)]?\s+([^\W\d_].{1,90})$")


_PALABRAS_CORTAS = {"a", "al", "de", "del", "e", "el", "en", "la", "las", "lo", "los", "o", "por", "se", "su", "sus", "u", "un", "una", "y", "que", "con", "sin"}


def _titulo_legible(texto: str) -> str:
    """Normaliza un título de sección: sin numeración de origen ("1.", "2.3") para que
    todos los títulos se vean igual, y en tipo oración si venía en mayúsculas
    ("MODOS DE CONFIGURACION"), conservando las siglas cortas ("IP", "OSPF")."""
    texto = " ".join(texto.split()).rstrip(":").strip()
    texto = re.sub(r"^\d{1,2}(?:\.\d{1,2})*[.)]?\s+", "", texto) or texto
    letras = [c for c in texto if c.isalpha()]
    if not letras or sum(c.isupper() for c in letras) / len(letras) <= 0.9:
        return texto
    palabras = []
    for i, p in enumerate(texto.split()):
        sigla = len(p) <= 4 and p.lower() not in _PALABRAS_CORTAS
        if sigla:
            palabras.append(p)
        else:
            palabras.append(p.capitalize() if i == 0 else p.lower())
    return " ".join(palabras)


def _es_encabezado_texto(linea: str) -> str | None:
    """Reconoce encabezados en documentos sin Markdown (PDF, texto plano).

    Acepta títulos numerados ("1. Acceso a la consola") y líneas completas en
    mayúsculas de al menos dos palabras. Devuelve el título legible, o None.
    """
    linea = linea.strip()
    if not linea or len(linea) > 100 or linea[-1] in ".,;":
        return None
    m = _ENCABEZADO_NUMERADO.match(linea)
    # un título no trae comas ni punto seguido; una oración numerada sí suele traerlos
    if m and len(m.group(2).split()) <= 10 and not re.search(r"[,;]|\.\s", m.group(2)):
        return _titulo_legible(m.group(2))
    palabras = linea.split()
    letras = [c for c in linea if c.isalpha()]
    if 2 <= len(palabras) <= 12 and len(letras) >= 6 and all(c.isupper() for c in letras):
        return _titulo_legible(linea)
    return None


def _secciones_desde(contenido: str, marcas: list[tuple[int, int, str]]) -> list[tuple[str, str]]:
    """Arma (título, cuerpo) a partir de las posiciones (inicio, fin, título) de cada encabezado.

    El texto previo al primer encabezado se conserva como "Introducción".
    """
    secciones: list[tuple[str, str]] = []
    preambulo = contenido[: marcas[0][0]].strip()
    if preambulo:
        secciones.append(("Introducción", preambulo))
    for i, (_, fin_titulo, titulo) in enumerate(marcas):
        fin = marcas[i + 1][0] if i + 1 < len(marcas) else len(contenido)
        cuerpo = contenido[fin_titulo:fin].strip()
        if cuerpo:
            secciones.append((titulo, cuerpo))
    return secciones


def _detectar_secciones(contenido: str) -> list[tuple[str, str]]:
    """Divide por encabezados Markdown (#, ##, ###) si existen; si no, por encabezados
    numerados o en mayúsculas (típicos de un PDF); si tampoco hay, una sola sección."""
    marcas = [(m.start(), m.end(), _titulo_legible(m.group(2))) for m in _ENCABEZADO_MD.finditer(contenido)]

    if not marcas:
        posicion = 0
        for linea in contenido.split("\n"):
            titulo = _es_encabezado_texto(linea)
            if titulo:
                marcas.append((posicion, posicion + len(linea), titulo))
            posicion += len(linea) + 1
        if len(marcas) < 2:  # un único "encabezado" suele ser ruido, no estructura
            marcas = []

    secciones = _secciones_desde(contenido, marcas) if marcas else []
    return secciones or [("Documento completo", contenido)]


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
