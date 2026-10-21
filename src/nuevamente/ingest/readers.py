"""Lectores de documentos técnicos (PDF, Word, Markdown, texto plano).

Responsable en el equipo Kairos G10: Gaspar Martinez Paiva (Data Engineer).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

EXTENSIONES_SOPORTADAS = {".pdf", ".docx", ".md", ".markdown", ".txt"}


class DocumentoInvalidoError(Exception):
    """Se lanza cuando el archivo no se puede leer o no tiene texto extraíble."""


@dataclass
class DocumentoLeido:
    titulo: str
    contenido: str
    fuente: str  # nombre de archivo original, para trazabilidad


# Fin de oración o de rótulo pegado a la mayúscula siguiente ("físicos.Dado", "EPP):Uso").
_PEGADO = re.compile(r"(?<=[a-záéíóúñ)])[.:!?](?=[A-ZÁÉÍÓÚÑ¿¡])")
_SIMBOLO = "[\U0001F300-\U0001FAFF\u2600-\u27BF]\uFE0F?"
_SOLO_VINETA = re.compile(r"^\s*[•●▪◦‣∙·]\s*$")
_PIE_DE_PAGINA = re.compile(r"\b(P[áa]gina|Page)\s+\d+\s+(de|of)\s+\d+\s*$", re.IGNORECASE)
# entrada de un índice: "Algoritmo ........ 4", "Datos …… 12"
_ENTRADA_DE_INDICE = re.compile(r"^.{2,120}?\s*(?:\.{4,}|…{2,}|(?:\. ){3,})\s*\d{1,4}\s*$")
# aviso legal o de créditos: "© 2023 Universidad X", "Todos los derechos reservados", "ISBN 978-..."
_AVISO_LEGAL = re.compile(
    r"^\s*(?:©|\(c\)\s|copyright\b|isbn\b|dep[óo]sito legal\b)"
    r"|todos los derechos reservados|all rights reserved"
    r"|(?:esta obra|este documento|este material) est[áa] (?:bajo|sujet[oa] a) una licencia",
    re.IGNORECASE,
)
# línea que solo trae un correo o un dato de contacto ("Contacto: info@x.org", "Web: www.x.org").
# Una URL sola no se quita: en un tutorial puede ser el paso ("Ingresa a https://...").
_CONTACTO = re.compile(
    r"^\s*(?:(?:contacto|correo|e-?mail|email|web|sitio web|p[áa]gina web)\s*:\s*\S+"
    r"|[\w.+-]+@[\w-]+\.[\w.]+)\s*$",
    re.IGNORECASE,
)
# número de página suelto: "12", "- 12 -", "Pág. 12"
_NUMERO_DE_PAGINA = re.compile(r"^\s*(?:-\s*)?(?:p[áa]g(?:ina)?\.?\s*)?\d{1,4}(?:\s*-)?\s*$", re.IGNORECASE)


def _es_ruido(linea: str) -> bool:
    """Línea sin valor pedagógico: viñeta sola, pie de página, índice, aviso legal o contacto."""
    return bool(
        _SOLO_VINETA.match(linea)
        or _PIE_DE_PAGINA.search(linea)
        or _ENTRADA_DE_INDICE.match(linea)
        or _AVISO_LEGAL.search(linea)
        or _CONTACTO.match(linea)
    )


def _restaurar_saltos(texto: str) -> str:
    """Devuelve los saltos de línea a un texto que los perdió al copiarlo de una web o
    un chat ("...BioseguridadProtocolo de BioseguridadUn protocolo...", "físicos.Dado").

    Sin ellos el documento entero es un solo párrafo: no se reconocen sus apartados y
    cada fragmento mezcla el final de un tema con el principio del siguiente. Solo
    actúa si el texto muestra el síntoma varias veces, para no tocar un documento normal.
    """
    if len(_PEGADO.findall(texto)) < 3:
        return texto
    # símbolo que abre un apartado: "comunes:🏥 1. Ámbito de la Salud"
    texto = re.sub(rf"\s*({_SIMBOLO}\s*)(?=\d{{1,2}}[.)]\s|[A-ZÁÉÍÓÚÑ])", r"\n\1", texto)
    # título pegado al párrafo que le sigue: "Laboratorios ClínicosEn consultorios"
    texto = re.sub(r"(?<=[a-záéíóúñ])(?=[A-ZÁÉÍÓÚÑ][a-záéíóúñ])", "\n", texto)
    texto = re.sub(r"(?<=[a-záéíóúñ)])([.!?])(?=[A-ZÁÉÍÓÚÑ¿¡])", r"\1\n", texto)
    return re.sub(r"(?<=[a-záéíóúñ)]):(?=[A-ZÁÉÍÓÚÑ¿¡])", ": ", texto)


def limpiar_texto(texto: str) -> str:
    """Normaliza espacios y líneas en blanco repetidas, preservando párrafos.

    También descarta líneas de cita/nota (que empiezan con '> '): en los
    documentos de este proyecto se usan para avisos editoriales (p. ej. "esto
    es material de demo"), no para contenido que deba indexarse ni citarse
    como evidencia de fidelidad.
    """
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")
    # una viñeta sola, un pie de página ("... Página 1 de 3"), una entrada del índice, un
    # aviso legal o un dato de contacto no son contenido: se citarían como si lo fueran
    lineas = [l for l in texto.split("\n") if not l.strip().startswith(">") and not _es_ruido(l)]
    texto = _restaurar_saltos("\n".join(lineas))
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


def _clave_de_borde(linea: str) -> str:
    """Forma de una línea sin sus números, para reconocer "Manual IA · 3" y "Manual IA · 4" como la misma."""
    return re.sub(r"\d+", "#", linea.lower()).strip()


def _sin_bordes_repetidos(paginas: list[list[str]]) -> list[list[str]]:
    """Quita de cada página los encabezados y pies que se repiten en muchas páginas y los
    números de página sueltos. Solo se quitan desde el borde de la página hacia dentro
    (hasta dos líneas por lado) y se para en la primera que es contenido: una línea del
    cuerpo nunca se toca. Una línea que termina en punto es una oración, no un encabezado."""
    def bordes(lineas: list[str]) -> list[int]:
        llenas = [i for i, l in enumerate(lineas) if l]
        return llenas[:2] + llenas[-2:]

    repetidas: set[str] = set()
    if len(paginas) >= 3:
        conteo: dict[str, int] = {}
        for lineas in paginas:
            for clave in {_clave_de_borde(lineas[i]) for i in bordes(lineas) if not lineas[i].endswith(".")}:
                conteo[clave] = conteo.get(clave, 0) + 1
        minimo = max(3, len(paginas) // 2)
        repetidas = {clave for clave, n in conteo.items() if n >= minimo and clave != "#"}

    def es_borde(linea: str) -> bool:
        return bool(_NUMERO_DE_PAGINA.match(linea)) or (
            not linea.endswith(".") and _clave_de_borde(linea) in repetidas
        )

    limpias = []
    for lineas in paginas:
        llenas = [i for i, l in enumerate(lineas) if l]
        quitar: set[int] = set()
        for orden in (llenas[:2], llenas[::-1][:2]):
            for i in orden:
                if not es_borde(lineas[i]):
                    break
                quitar.add(i)
        limpias.append([l for i, l in enumerate(lineas) if i not in quitar])
    return limpias


# ---------- Títulos y subtítulos de un PDF ----------
#
# Un PDF no marca qué es título: solo guarda texto con su letra y su posición. Se
# reconocen, en este orden, por:
#   1. los marcadores del PDF (el índice lateral que crea Word con los estilos de título);
#   2. el tamaño de la letra (más grande que el texto corrido) o un renglón en negrita;
#   3. si nada de lo anterior aparece, las reglas de texto del chunking (títulos
#      numerados o en mayúsculas).
# Los títulos de 1 y 2 salen como encabezados Markdown ("## Título"), igual que los de
# Word, y el chunking arma las secciones con ellos.

@dataclass
class _Fragmento:
    texto: str
    tamano: float  # tamaño real en la página (puntos), redondeado a 0,5
    negrita: bool
    y: float  # altura en la página (0 = abajo)


_NEGRITA = re.compile(r"bold|black|heavy|semibold|demi", re.IGNORECASE)
_NUMERACION = re.compile(r"^\d{1,2}(?:\.\d{1,2})*\s*[-.)]?\s*[^\W\d_]")
_MIN_TITULOS = 2  # con menos, no hay estructura que aprovechar
_LARGO_MEDIO_TITULO = 80  # caracteres: con trozos más largos en promedio, ese tamaño no es de títulos
_MAX_PARTE_TITULOS = 0.12  # parte del texto del documento que pueden ocupar los títulos...
_MAX_TITULOS_CON_MUCHO_TEXTO = 30  # ...cuando son muchos (un documento corto puede superarla)
# entrada de un índice que remite a una página: "6.1-CANVAS DE CONTENIDO Pag 21."
_PAGINA_DEL_INDICE = re.compile(r"\bp[áa]g(?:ina)?\.?\s*\d{1,4}\.?\s*$", re.IGNORECASE)


def _es_entrada_de_indice(texto: str) -> bool:
    return bool(_ENTRADA_DE_INDICE.match(texto) or _PAGINA_DEL_INDICE.search(texto))


def _normalizar(texto: str) -> str:
    """Forma de comparación: sin espacios ni mayúsculas (pypdf no siempre pone los espacios igual)."""
    return re.sub(r"\s+", "", texto).lower()


def _visitante(fragmentos: list[_Fragmento]):
    """Recoge cada trozo de texto de una página con su tamaño, si es negrita y su altura."""
    def visitar(texto, cm, tm, fuente, tamano_fuente):
        if not texto or not texto.strip() or not tamano_fuente:
            return
        # tamaño en la página = tamaño de la fuente x escala de las matrices de texto y de dibujo
        c = tm[2] * cm[0] + tm[3] * cm[2]
        d = tm[2] * cm[1] + tm[3] * cm[3]
        escala = (c * c + d * d) ** 0.5 or 1.0
        nombre = str(fuente.get("/BaseFont", "")) if hasattr(fuente, "get") else ""
        y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        fragmentos.append(_Fragmento(texto, round(tamano_fuente * escala * 2) / 2, bool(_NEGRITA.search(nombre)), y))
    return visitar


def _estilos_pdf(reader) -> list[list[_Fragmento]]:
    paginas: list[list[_Fragmento]] = []
    for pagina in reader.pages:
        fragmentos: list[_Fragmento] = []
        try:
            pagina.extract_text(visitor_text=_visitante(fragmentos))
        except Exception:  # una página que pypdf no puede recorrer queda sin títulos
            fragmentos = []
        paginas.append(fragmentos)
    return paginas


def _tramos(fragmentos: list[_Fragmento]) -> list[_Fragmento]:
    """Junta los trozos seguidos con el mismo tamaño y grosor; un título que ocupa dos
    renglones (mismo estilo, renglones contiguos) queda como uno solo."""
    tramos: list[_Fragmento] = []
    for f in fragmentos:
        ultimo = tramos[-1] if tramos else None
        if ultimo and ultimo.tamano == f.tamano and ultimo.negrita == f.negrita:
            salto = abs(ultimo.y - f.y)
            if salto <= f.tamano * 1.8:  # mismo renglón o el de abajo
                ultimo.texto += ("" if salto < f.tamano * 0.5 else " ") + f.texto
                ultimo.y = f.y
                continue
        tramos.append(_Fragmento(f.texto, f.tamano, f.negrita, f.y))
    return tramos


def _tamano_del_texto(paginas: list[list[_Fragmento]]) -> float:
    """El tamaño de letra con más caracteres en el documento: el del texto corrido."""
    conteo: dict[float, int] = {}
    for fragmentos in paginas:
        for f in fragmentos:
            conteo[f.tamano] = conteo.get(f.tamano, 0) + len(f.texto.strip())
    return max(conteo, key=conteo.get) if conteo else 0.0


def _parece_titulo(texto: str) -> bool:
    """Numerado ("5.2-BLOQUES DE DATOS") o en mayúsculas, según las reglas del chunking."""
    from nuevamente.ingest.chunking import _es_encabezado_texto

    return bool(_NUMERACION.match(texto)) or _es_encabezado_texto(texto.rstrip(":")) is not None


def _titulos_por_letra(paginas: list[list[_Fragmento]]) -> list[dict[str, int]]:
    """Por página, {texto normalizado: nivel} de los títulos y subtítulos según la letra.

    - Letra al menos un 10 % más grande que el texto corrido: título; el nivel sale del
      tamaño (el más grande es 1).
    - Renglón entero en negrita del tamaño del texto: subtítulo, salvo que sea un rótulo
      ("Ejemplos:"). Si el documento ya tiene títulos más grandes, la negrita suele ser
      énfasis o la cabecera de una tabla, y solo cuenta si además parece título
      (numerado o en mayúsculas).
    Lo que se repite en muchas páginas es un encabezado de página, no un título."""
    cuerpo = _tamano_del_texto(paginas)
    if not cuerpo:
        return [{} for _ in paginas]
    tramos = [_tramos(f) for f in paginas]

    paginas_por_texto: dict[str, set[int]] = {}
    for n, lista in enumerate(tramos):
        for t in lista:
            paginas_por_texto.setdefault(_normalizar(t.texto), set()).add(n)
    repetido = {k for k, v in paginas_por_texto.items() if len(v) >= 3}

    def candidato(lista: list[_Fragmento], k: int) -> str | None:
        texto = " ".join(lista[k].texto.split())
        if sum(c.isalpha() for c in texto) < 2 or len(texto) > 150 or texto[-1] in ",;":
            return None
        if _normalizar(texto) in repetido or _es_entrada_de_indice(texto):
            return None
        siguiente = lista[k + 1].texto.lstrip() if k + 1 < len(lista) else ""
        if siguiente[:1].islower():  # la oración sigue en la línea de abajo: no es un título
            return None
        return texto

    # Los títulos son trozos cortos y pocos. Un tamaño con trozos largos, o con muchos que
    # suman buena parte del documento, es otra parte del cuerpo (la prosa junto al código,
    # que va más chico), no el de los títulos.
    largos: dict[float, list[int]] = {}
    for lista in tramos:
        for t in lista:
            largos.setdefault(t.tamano, []).append(len(" ".join(t.texto.split())))
    total = sum(map(sum, largos.values())) or 1

    def es_de_titulo(tam: float, l: list[int]) -> bool:
        mucho = len(l) > _MAX_TITULOS_CON_MUCHO_TEXTO and sum(l) / total > _MAX_PARTE_TITULOS
        return tam >= cuerpo * 1.1 and sum(l) / len(l) <= _LARGO_MEDIO_TITULO and not mucho

    de_titulo = {tam for tam, l in largos.items() if es_de_titulo(tam, l)}
    grandes = {
        (t.tamano, _normalizar(t.texto))
        for lista in tramos for k, t in enumerate(lista)
        if t.tamano in de_titulo and candidato(lista, k)
    }
    tamanos = sorted({tam for tam, _ in grandes}, reverse=True)
    negrita_libre = len(grandes) <= 2  # sin títulos grandes, la negrita es la estructura

    resultado: list[dict[str, int]] = []
    for lista in tramos:
        titulos: dict[str, int] = {}
        for k, t in enumerate(lista):
            texto = candidato(lista, k)
            if not texto:
                continue
            if t.tamano in tamanos and len(texto.split()) <= 20:
                nivel = min(tamanos.index(t.tamano) + 1, 3)
            elif (
                t.negrita and abs(t.tamano - cuerpo) <= 0.5 and len(texto.split()) <= 12
                and not texto.endswith(".")
                and (_parece_titulo(texto) or (negrita_libre and not texto.endswith(":")))
            ):
                nivel = min(len(tamanos) + 1, 3)
            else:
                continue
            titulos.setdefault(_normalizar(texto), nivel)
        resultado.append(titulos)
    return resultado


@dataclass
class _Marcador:
    titulo: str
    nivel: int
    arriba: float | None  # altura del título en la página; None = principio de la página


def _marcadores(reader) -> list[list[_Marcador]]:
    """Marcadores del PDF agrupados por página (vacío si no tiene)."""
    por_pagina: list[list[_Marcador]] = [[] for _ in reader.pages]

    def recorrer(items, nivel: int) -> None:
        for item in items:
            if isinstance(item, list):
                recorrer(item, nivel + 1)
                continue
            try:
                pagina = reader.get_destination_page_number(item)
                titulo = " ".join(str(item.title or "").split())
                arriba = getattr(item, "top", None)
            except Exception:
                continue
            if _es_entrada_de_indice(titulo):  # marcador que apunta a la línea del índice
                continue
            if titulo and 0 <= pagina < len(por_pagina):
                por_pagina[pagina].append(_Marcador(titulo, min(nivel, 3), float(arriba) if arriba is not None else None))

    try:
        recorrer(reader.outline, 1)
    except Exception:  # marcadores dañados: se sigue sin ellos
        return [[] for _ in reader.pages]
    return por_pagina


def _alturas(lineas: list[str], fragmentos: list[_Fragmento]) -> list[float | None]:
    """Altura en la página de cada línea, buscando su texto entre los trozos con posición."""
    texto, inicio_de = "", []
    for f in fragmentos:
        inicio_de.append(len(texto))
        texto += _normalizar(f.texto)
    alturas: list[float | None] = []
    pos, anterior = 0, None
    for linea in lineas:
        clave = _normalizar(linea)[:24]
        encontrado = texto.find(clave, pos) if clave else -1
        if encontrado != -1:
            i = max(k for k, ini in enumerate(inicio_de) if ini <= encontrado)
            anterior, pos = fragmentos[i].y, encontrado + len(clave)
        alturas.append(anterior)
    return alturas


def _marcar_titulos(
    lineas: list[str], titulos: dict[str, int], marcadores: list[_Marcador], fragmentos: list[_Fragmento]
) -> list[str]:
    """Convierte en encabezados Markdown ("## Título") las líneas que son títulos de la
    página; un título partido en varias líneas queda en una. Un marcador cuyo título no
    está como texto (algunos PDF lo dibujan aparte) se agrega donde indica el marcador.
    Un "#" que el PDF trae al principio de una línea (un comentario de código) se escapa
    para que no pase por título."""
    titulos = dict(titulos)
    for m in marcadores:  # el marcador manda sobre el nivel calculado por la letra
        titulos[_normalizar(m.titulo)] = m.nivel
    pendientes = [m for m in marcadores]

    salida: list[str] = []
    alturas = _alturas(lineas, fragmentos) if marcadores else [None] * len(lineas)

    def insertar_hasta(altura: float | None) -> None:
        while pendientes and (altura is None or (pendientes[0].arriba or 1e9) > altura + 1):
            m = pendientes.pop(0)
            salida.append(f"{'#' * m.nivel} {m.titulo}")
            if altura is None:
                break

    i = 0
    while i < len(lineas):
        linea = lineas[i]
        encontrado = None
        if linea and titulos:
            for n in range(1, 5):  # el título puede ocupar hasta cuatro líneas
                grupo = lineas[i : i + n]
                if len(grupo) < n or not all(grupo):
                    break
                clave = _normalizar("".join(grupo))
                if clave in titulos:
                    encontrado = (n, titulos[clave], " ".join(grupo), clave)
                    break
        if encontrado:
            n, nivel, texto, clave = encontrado
            pendientes = [m for m in pendientes if _normalizar(m.titulo) != clave]
        if pendientes and linea and alturas[i] is not None:
            insertar_hasta(alturas[i])
        if encontrado:
            salida.append(f"{'#' * nivel} {texto}")
            i += n
            continue
        salida.append("\\" + linea if linea.startswith("#") else linea)
        i += 1
    for m in pendientes:  # marcadores al final de la página, sin texto debajo
        salida.append(f"{'#' * m.nivel} {m.titulo}")
    return salida


def _paginas_pdf(reader, **opciones) -> list[list[str]]:
    """Líneas de cada página, sin la sangría con la que el modo "layout" reproduce la
    posición, ni los encabezados, pies y números de página."""
    paginas = [
        [l.strip() for l in (pagina.extract_text(**opciones) or "").split("\n")] for pagina in reader.pages
    ]
    return _sin_bordes_repetidos(paginas)


def _texto_pdf(reader, **opciones) -> str:
    return "\n\n".join("\n".join(lineas) for lineas in _paginas_pdf(reader, **opciones))


def _texto_pdf_con_titulos(reader) -> str:
    """Texto con los títulos como encabezados Markdown, o "" si el PDF no los distingue."""
    estilos = _estilos_pdf(reader)
    titulos = _titulos_por_letra(estilos)
    marcadores = _marcadores(reader)
    if sum(map(len, titulos)) + sum(map(len, marcadores)) < _MIN_TITULOS:
        return ""
    paginas = [
        _marcar_titulos(lineas, t, m, f)
        for lineas, t, m, f in zip(_paginas_pdf(reader), titulos, marcadores, estilos)
    ]
    texto = "\n\n".join("\n".join(lineas) for lineas in paginas)
    return texto if len(_ENCABEZADO_MARCADO.findall(texto)) >= _MIN_TITULOS else ""


def _encabezados_apilados(texto: str) -> int:
    """Cuántos encabezados van seguidos de otro encabezado, sin texto propio entre ambos."""
    from nuevamente.ingest.chunking import _es_encabezado_texto

    lineas = [l for l in texto.split("\n") if l.strip()]
    es_titulo = [_es_encabezado_texto(l) is not None for l in lineas]
    return sum(1 for a, b in zip(es_titulo, es_titulo[1:]) if a and b)


_ENCABEZADO_MARCADO = re.compile(r"^#{1,3} \S", re.MULTILINE)


def _sin_espacios(texto: str) -> bool:
    """Texto que el PDF guardó sin espacios entre palabras ("Diagnósticoyprevalencia..."):
    no se puede leer bien ni citar."""
    letras = sum(c.isalpha() for c in texto)
    return letras > 500 and texto.count(" ") < letras / 25


def leer_pdf(path: Path) -> DocumentoLeido:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Falta instalar pypdf: pip install pypdf") from exc

    reader = PdfReader(str(path))
    contenido = _texto_pdf_con_titulos(reader)
    if not contenido:
        # sin títulos reconocibles por letra ni marcadores: texto plano, y el chunking
        # busca títulos numerados o en mayúsculas
        contenido = _texto_pdf(reader)
        if _encabezados_apilados(contenido):
            # El PDF guarda los títulos antes que el texto de la página, así que salen
            # juntos y separados de su contenido. El modo "layout" lee por posición en
            # la página; se usa solo si de verdad deja cada título sobre su texto.
            try:
                por_posicion = _texto_pdf(reader, extraction_mode="layout")
            except Exception:  # el modo layout no soporta todos los PDF
                por_posicion = ""
            if por_posicion.strip() and _encabezados_apilados(por_posicion) < _encabezados_apilados(contenido):
                contenido = por_posicion
    if not contenido.strip():
        # PDF escaneado (solo imágenes): se transcribe con OCR (HU-08)
        contenido = ocr_pdf(path)
    elif _sin_espacios(contenido):
        # texto sin espacios entre palabras: se intenta leer con OCR; si no se puede,
        # se usa el texto tal como viene
        try:
            contenido = ocr_pdf(path)
        except DocumentoInvalidoError:
            pass
    return DocumentoLeido(titulo=path.stem, contenido=limpiar_texto(contenido), fuente=path.name)


_MIN_CARACTERES_OCR = 40
_INDICACION_OCR = (
    "Este PDF es un documento escaneado. Transcribe TODO su texto, página por página y en el orden "
    "de lectura, tal como está escrito: no resumas, no traduzcas, no corrijas ni agregues nada. "
    "Escribe cada título en su propia línea, marcado como en Markdown: «## » para los títulos y «### » "
    "para los subtítulos. No copies los encabezados ni pies que se repiten en cada página ni los números "
    "de página. Si una página no tiene texto, omítela. Devuelve solo el texto."
)


def ocr_pdf(path: Path) -> str:
    """Texto de un PDF escaneado, leído por Gemini (sin programas de OCR en el servidor).

    Lanza DocumentoInvalidoError si el OCR está apagado, no hay API key o no se reconoce
    texto suficiente."""
    from nuevamente.config import settings

    claves = [c for c in (*settings.gemini_api_keys, settings.gemini_api_key) if c]
    if settings.ocr == "off" or not claves:
        raise DocumentoInvalidoError(
            f"El PDF {path.name} no tiene texto extraíble (posible escaneo). Para leerlo con OCR hace "
            "falta configurar GEMINI_API_KEY; o sube una versión del documento con texto."
        )
    from google import genai
    from google.genai import types

    cliente = genai.Client(api_key=claves[0], http_options=types.HttpOptions(timeout=settings.llm_timeout_s * 3 * 1000))
    parte_pdf = types.Part.from_bytes(data=path.read_bytes(), mime_type="application/pdf")
    ultimo: Exception | None = None
    for modelo in dict.fromkeys((settings.llm_model, *settings.llm_modelos_respaldo)):
        try:
            respuesta = cliente.models.generate_content(model=modelo, contents=[parte_pdf, _INDICACION_OCR])
            texto = (respuesta.text or "").strip()
            break
        except Exception as exc:  # sin cuota o saturado: se prueba el modelo siguiente
            ultimo, texto = exc, None
    if texto is None:
        raise DocumentoInvalidoError(
            f"El PDF {path.name} está escaneado y no se pudo leer con OCR en este momento ({ultimo}). "
            "Intenta más tarde o sube una versión del documento con texto."
        )
    if len(texto) < _MIN_CARACTERES_OCR:
        raise DocumentoInvalidoError(
            f"El OCR no reconoció texto suficiente en {path.name}. Revisa que el escaneo sea legible "
            "o sube una versión del documento con texto."
        )
    return texto


def _nivel_de_titulo(parrafo) -> int:
    """Nivel del estilo de título de Word ("Heading 2", "Título 2" -> 2; "Title" -> 1), o 0."""
    estilo = (parrafo.style.name if parrafo.style is not None else "") or ""
    if estilo.lower() in ("title", "título", "titulo"):
        return 1
    m = re.match(r"^(?:heading|t[íi]tulo)\s*(\d)$", estilo.strip(), re.IGNORECASE)
    return int(m.group(1)) if m else 0


def _texto_docx(documento) -> str:
    """Párrafos y tablas en el orden del documento. Los títulos de Word pasan a
    encabezados Markdown ("## ...") para que el chunking reconozca las secciones."""
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    bloques: list[str] = []
    for elemento in documento.iter_inner_content():
        if isinstance(elemento, Paragraph):
            texto = elemento.text.strip()
            if not texto:
                continue
            nivel = _nivel_de_titulo(elemento)
            bloques.append(f"{'#' * min(nivel, 3)} {texto}" if nivel else texto)
        elif isinstance(elemento, Table):
            for fila in elemento.rows:
                celdas: list[str] = []
                for celda in fila.cells:  # una celda combinada se repite: se toma una vez
                    texto = " ".join(celda.text.split())
                    if texto and (not celdas or celdas[-1] != texto):
                        celdas.append(texto)
                if celdas:
                    bloques.append(" | ".join(celdas))
    return "\n\n".join(bloques)


def leer_docx(path: Path) -> DocumentoLeido:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Falta instalar python-docx: pip install python-docx") from exc

    try:
        documento = Document(str(path))
    except Exception as exc:  # archivo dañado o que no es un .docx real
        raise DocumentoInvalidoError(f"No se pudo leer el documento Word {path.name}.") from exc
    contenido = _texto_docx(documento)
    if not contenido.strip():
        raise DocumentoInvalidoError(f"El documento Word {path.name} no tiene texto.")
    return DocumentoLeido(titulo=path.stem, contenido=limpiar_texto(contenido), fuente=path.name)


def leer_documento(path: str | Path) -> DocumentoLeido:
    """Punto de entrada único de ingesta: detecta el tipo por extensión."""
    path = Path(path)
    if not path.exists():
        raise DocumentoInvalidoError(f"No existe el archivo: {path}")

    ext = path.suffix.lower()
    if ext not in EXTENSIONES_SOPORTADAS:
        pista = " Ábrelo en Word y guárdalo como .docx." if ext == ".doc" else ""
        raise DocumentoInvalidoError(
            f"El formato {ext or 'sin extensión'} no es compatible. Vuelve a cargar el archivo en "
            f"un formato correcto: PDF, Word (.docx), Markdown (.md) o texto (.txt).{pista}"
        )

    if ext == ".pdf":
        return leer_pdf(path)
    if ext == ".docx":
        return leer_docx(path)
    if ext in (".md", ".markdown"):
        return leer_markdown(path)
    return leer_txt(path)


def leer_texto_plano(titulo: str, contenido: str, fuente: str = "texto_directo") -> DocumentoLeido:
    """Para cuando el contenido llega ya como string (p. ej. desde la API)."""
    if not contenido or not contenido.strip():
        raise DocumentoInvalidoError("El contenido del documento está vacío.")
    return DocumentoLeido(titulo=titulo, contenido=limpiar_texto(contenido), fuente=fuente)
