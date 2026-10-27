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


_ENCABEZADO_MD = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")
# título "subrayado" de Markdown: la línea de abajo es solo "===" (nivel 1) o "---" (nivel 2)
_SUBRAYADO_MD = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")
_CERCO_MD = re.compile(r"^ {0,3}(```|~~~)")
# numeración de origen al principio de un título: "1. ", "2.3 ", "5.2-", "4 - "
_NUMERACION_TITULO = re.compile(r"^\d{1,2}(?:\.\d{1,2})*(?:\s*[-–.)]\s*|\s+)(?=\S)")
# "1. ACCESO A LA CONSOLA", "2.3 Modos de configuración": encabezados numerados de PDF/texto
# "1 Objetivos", "1. Objetivos", "1) Objetivos" y también con guion o raya: "1 - Objetivos", "1 – Objetivos"
_ENCABEZADO_NUMERADO = re.compile(r"^(\d{1,2}(?:\.\d{1,2})*)(?:[.)]|\s*[-–—])?\s+([^\W\d_].{1,90})$")


# emoji o símbolo decorativo delante de un título ("🏥 1. Ámbito de la Salud")
_SIMBOLO_INICIAL = re.compile(r"^(?:[\U0001F300-\U0001FAFF\u2600-\u27BF]\uFE0F?\s*)+")

_PALABRAS_CORTAS = {
    "a", "al", "de", "del", "e", "el", "en", "la", "las", "lo", "los", "o", "por", "se", "su", "sus",
    "u", "un", "una", "y", "que", "con", "sin", "no", "si", "sí", "ya", "mi", "tu", "es", "le", "nos", "para",
}
# siglas frecuentes en documentación técnica y de salud que tienen vocales y más de 2 letras
_SIGLAS_CONOCIDAS = {
    "API", "APIS", "OCI", "OSPF", "LAN", "WAN", "VLAN", "VCN", "EPP", "OMS", "OPS", "IOT", "IOS", "AWS", "GCP", "ERP",
    "CRM", "SAP", "UCI", "UTI", "ONU", "UNESCO", "COVID", "SIDA", "RAG", "LLM", "JSON", "YAML", "HTML", "CSS", "URL",
    "USB", "RAM", "CPU", "GPU", "SSD", "NAT", "DHCP", "BGP", "EIGRP", "RIP", "MPLS", "ACL", "IDE", "SDK", "UI", "UX",
}
_VOCALES = set("AEIOUÁÉÍÓÚÜ")
_ROTULO_Y_ORACION = re.compile(
    r":\s+(?:el|la|los|las|un|una|unos|unas|este|esta|estos|estas|ese|esa|se|es|son|en|su|sus|al|del)\s",
    re.IGNORECASE,
)
_PALABRA_MAYUS = re.compile(r"\b[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9]{1,7}\b")
_PALABRA = re.compile(r"[^\W\d_]{2,}")


@dataclass(frozen=True)
class _Siglas:
    """Cómo escribe el documento cada palabra fuera de los títulos: "OSPF" en mayúsculas
    es una sigla; "guía" en minúsculas es una palabra común aunque un título diga "GUÍA"."""

    en_mayusculas: frozenset[str] = frozenset()
    en_minusculas: frozenset[str] = frozenset()
    # nombres propios: con mayúscula inicial en medio de una oración ("de Rodrigo Espinoza")
    nombres: frozenset[str] = frozenset()


def _siglas_del_documento(contenido: str) -> _Siglas:
    mayus: set[str] = set()
    minus: set[str] = set()
    nombres: set[str] = set()
    for linea in contenido.split("\n"):
        letras = [c for c in linea if c.isalpha()]
        # solo el texto corrido: un título en mayúsculas no dice qué palabras son siglas
        if len(linea.split()) < 4 or not letras or sum(c.isupper() for c in letras) / len(letras) > 0.5:
            continue
        mayus.update(_PALABRA_MAYUS.findall(linea))
        minus.update(p for p in _PALABRA.findall(linea) if p.islower())
        anterior = ""
        for token in linea.split():
            palabra = token.strip("()[]«»\"'.,;:¿?¡!")
            if anterior and anterior[-1] not in ".:!?¿¡" and len(palabra) > 2 and palabra[:1].isupper() and palabra[1:].islower():
                nombres.add(palabra)
            anterior = token
    return _Siglas(frozenset(mayus), frozenset(minus), frozenset(nombres - {m.capitalize() for m in minus}))


def _es_sigla(palabra: str, siglas: _Siglas) -> bool:
    nucleo = palabra.strip("()[]«»\"'.,;:¿?¡!")
    if not nucleo or nucleo.lower() in _PALABRAS_CORTAS:
        return False
    if nucleo in siglas.en_mayusculas:
        return True
    if nucleo.lower() in siglas.en_minusculas:
        return False
    return (
        any(c.isdigit() or c == "/" for c in nucleo)  # TCP/IP, IPv4, 5G
        or len(nucleo) <= 2  # IP, TI, IA
        or not (set(nucleo.upper()) & _VOCALES)  # BGP, SSH, DNS, HTTP
        or nucleo.upper() in _SIGLAS_CONOCIDAS
    )


def _titulo_legible(texto: str, siglas: _Siglas | None = None) -> str:
    """Normaliza un título de sección: sin numeración de origen ("1.", "2.3") para que
    todos los títulos se vean igual, y en tipo oración si venía en mayúsculas
    ("MODOS DE CONFIGURACION"), conservando las siglas ("IP", "OSPF"). Qué palabra es
    sigla lo decide el propio documento (`siglas`) y, si no la usa fuera del título,
    su forma: sin vocales, con números, de dos letras o una sigla técnica conocida."""
    siglas = siglas or _Siglas()
    texto = " ".join(texto.split()).rstrip(":").strip()
    # sin marcas de Markdown: **negrita**, `código`, [enlace](url)
    texto = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", texto)
    texto = re.sub(r"(\*\*|__|`)", "", texto).strip().rstrip(":").strip() or texto
    texto = _NUMERACION_TITULO.sub("", texto) or texto
    letras = [c for c in texto if c.isalpha()]
    if not letras or sum(c.isupper() for c in letras) / len(letras) <= 0.9:
        return texto
    palabras = []
    for i, p in enumerate(texto.split()):
        nucleo = p.strip("()[]«»\"'.,;:¿?¡!")
        if _es_sigla(p, siglas):
            palabras.append(p)
        elif i == 0 or nucleo.capitalize() in siglas.nombres:
            palabras.append(p.replace(nucleo, nucleo.capitalize()) if nucleo else p.capitalize())
        else:
            palabras.append(p.lower())
    return " ".join(palabras)


def _es_encabezado_texto(linea: str, siglas: _Siglas | None = None) -> str | None:
    """Reconoce encabezados en documentos sin Markdown (PDF, texto plano).

    Acepta títulos numerados ("1. Acceso a la consola") y líneas completas en
    mayúsculas de al menos dos palabras. Devuelve el título legible, o None.
    """
    linea = _SIMBOLO_INICIAL.sub("", linea.strip())
    if not linea or len(linea) > 100 or linea[-1] in ".,;":
        return None
    m = _ENCABEZADO_NUMERADO.match(linea)
    # un título no trae comas ni punto seguido; una oración numerada sí suele traerlos,
    # y si termina en ":" es un punto de una lista que presenta lo que sigue. "Rótulo: La
    # oración…" también es un punto de lista: tras los dos puntos empieza una oración.
    if (
        m and len(m.group(2).split()) <= 10
        and not re.search(r"[,;]|\.\s|:$", m.group(2))
        and not _ROTULO_Y_ORACION.search(m.group(2))
    ):
        return _titulo_legible(m.group(2), siglas)
    palabras = linea.split()
    letras = [c for c in linea if c.isalpha()]
    if 2 <= len(palabras) <= 12 and len(letras) >= 6 and all(c.isupper() for c in letras):
        return _titulo_legible(linea, siglas)
    return None


def _nivel_numerado(linea: str) -> int:
    """Profundidad de la numeración de un encabezado: "2 Visitas" -> 1, "2.3 Modos" -> 2, sin número -> 0."""
    m = _ENCABEZADO_NUMERADO.match(_SIMBOLO_INICIAL.sub("", linea.strip()))
    return m.group(1).count(".") + 1 if m else 0


# Más títulos seguidos que estos son un índice, no apartados que compartan texto.
_MAX_TITULOS_APILADOS = 3


def _secciones_desde(contenido: str, marcas: list[tuple]) -> list[tuple[str, str]]:
    """Arma (título, cuerpo) a partir de las posiciones (inicio, fin, título[, nivel]) de cada encabezado.

    El texto previo al primer encabezado se conserva como "Introducción".

    Algunos PDF entregan juntos los títulos de una página ("1 Conducta", "2 Visitas") y
    después el texto de todos ellos. No se puede saber qué parte del texto es de cada
    título, así que la sección lleva los títulos apilados ("Conducta · Visitas"): antes
    quedaba todo bajo el último, con un título que no correspondía al contenido.
    """
    secciones: list[tuple[str, str]] = []
    preambulo = contenido[: marcas[0][0]].strip()
    if preambulo:
        secciones.append(("Introducción", preambulo))
    niveles = [m[3] if len(m) > 3 else 0 for m in marcas]
    titulos = [m[2] for m in marcas]
    apilados: list[str] = []
    for i, (_, fin_titulo, titulo, *_resto) in enumerate(marcas):
        fin = marcas[i + 1][0] if i + 1 < len(marcas) else len(contenido)
        cuerpo = contenido[fin_titulo:fin].strip()
        if not cuerpo:
            # numerado, no vuelve a aparecer (no es un índice) y lo que sigue no es un
            # subapartado suyo ("5 OSPF" / "5.1 Arranque"): su texto quedó en la sección siguiente
            hermano = niveles[i] and i + 1 < len(marcas) and niveles[i + 1] <= niveles[i]
            apilados = [*apilados, titulo] if hermano and titulo not in titulos[i + 1 :] else []
            continue
        if apilados and len(apilados) < _MAX_TITULOS_APILADOS:
            titulo = " · ".join([*apilados, titulo])
        apilados = []
        secciones.append((titulo, cuerpo))
    return secciones


def _encabezados_markdown(contenido: str, siglas: _Siglas) -> list[tuple[int, int, str]]:
    """(inicio, fin, título) de cada encabezado Markdown: "# …" a "###### …" y los títulos
    subrayados con "===" o "---". Lo que está dentro de un bloque de código (```) no es
    un título aunque empiece con "#": es un comentario."""
    marcas: list[tuple[int, int, str]] = []
    lineas = contenido.split("\n")
    # un bloque de código solo cuenta si se cierra: un "```" suelto (por ejemplo, copiado
    # de un PDF) no debe dejar el resto del documento sin títulos
    cercos = [i for i, l in enumerate(lineas) if _CERCO_MD.match(l)]
    if len(cercos) % 2:
        cercos.pop()
    cercos_validos = set(cercos)
    inicio = 0
    en_codigo = False
    anterior: tuple[int, str] | None = None  # (inicio, texto) de la línea previa, si puede ser título
    tras_blanco = True  # la línea previa estaba vacía (o es el principio del documento)
    for n, linea in enumerate(lineas):
        fin = inicio + len(linea)
        if n in cercos_validos:
            en_codigo, anterior = not en_codigo, None
        elif not en_codigo:
            m = _ENCABEZADO_MD.match(linea)
            if m and m.group(2).strip("#").strip():
                marcas.append((inicio, fin, _titulo_legible(m.group(2), siglas)))
                anterior = None
            elif anterior and _SUBRAYADO_MD.match(linea) and len(linea.strip()) >= 2:
                marcas.append((anterior[0], fin, _titulo_legible(anterior[1], siglas)))
                anterior = None
            else:
                texto = linea.strip()
                # solo una línea suelta (con una línea vacía antes) puede ser un título
                # subrayado: no una viñeta ni el final de un párrafo
                suelta = tras_blanco and texto and len(texto) <= 120 and not re.match(r"[-*+>|]", texto)
                anterior = (inicio, texto) if suelta else None
        tras_blanco = not linea.strip()
        inicio = fin + 1
    return marcas


def _detectar_secciones(contenido: str) -> list[tuple[str, str]]:
    """Divide por encabezados Markdown (#, ##, ###) si existen; si no, por encabezados
    numerados o en mayúsculas (típicos de un PDF); si tampoco hay, una sola sección."""
    siglas = _siglas_del_documento(contenido)
    marcas = _encabezados_markdown(contenido, siglas)

    if not marcas:
        lineas = contenido.split("\n")
        inicios = [0]
        for linea in lineas[:-1]:
            inicios.append(inicios[-1] + len(linea) + 1)
        i = 0
        while i < len(lineas):
            linea = lineas[i]
            titulo = _es_encabezado_texto(linea, siglas)
            siguiente = next((l.strip() for l in lineas[i + 1 :] if l.strip()), "")
            if titulo and siguiente[:1].islower() and not linea.rstrip().endswith(":"):
                titulo = None  # una oración que el PDF partió en dos líneas, no un título
            if titulo:
                inicio, fin = inicios[i], inicios[i] + len(linea)
                # un título en mayúsculas que sigue en la línea de abajo ("... EN CASO" / "COMPLEJO (...)")
                if not _nivel_numerado(linea) and i + 1 < len(lineas) and lineas[i + 1].strip():
                    continuacion = lineas[i + 1]
                    if not _nivel_numerado(continuacion) and _es_encabezado_texto(continuacion, siglas):
                        titulo = _titulo_legible(f"{linea.strip()} {continuacion.strip()}", siglas)
                        fin = inicios[i + 1] + len(continuacion)
                        i += 1
                marcas.append((inicio, fin, titulo, _nivel_numerado(linea)))
            i += 1
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
