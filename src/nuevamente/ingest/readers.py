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


def _texto_pdf(reader, **opciones) -> str:
    """Texto de todas las páginas, sin la sangría con la que el modo "layout" reproduce la
    posición, ni los encabezados, pies y números de página."""
    paginas = [
        [l.strip() for l in (pagina.extract_text(**opciones) or "").split("\n")] for pagina in reader.pages
    ]
    return "\n\n".join("\n".join(lineas) for lineas in _sin_bordes_repetidos(paginas))


def _encabezados_apilados(texto: str) -> int:
    """Cuántos encabezados van seguidos de otro encabezado, sin texto propio entre ambos."""
    from nuevamente.ingest.chunking import _es_encabezado_texto

    lineas = [l for l in texto.split("\n") if l.strip()]
    es_titulo = [_es_encabezado_texto(l) is not None for l in lineas]
    return sum(1 for a, b in zip(es_titulo, es_titulo[1:]) if a and b)


def leer_pdf(path: Path) -> DocumentoLeido:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Falta instalar pypdf: pip install pypdf") from exc

    reader = PdfReader(str(path))
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
