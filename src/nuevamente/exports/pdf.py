"""PDF didáctico a partir de cualquier contenido adaptado.

Responsable en el equipo Kairos G10: Dario Higuera Moreno (No Code Developer).

Mismo diseño que el Word (exports/documento.py): las funciones de cada formato escriben
sobre `_Pdf`, que tiene la misma interfaz que el escritor de Word. Usa Arial (macOS) o
Liberation/DejaVu (Linux) para los acentos y símbolos; si no hay ninguna, Helvetica, y
los caracteres que no admite se cambian por su equivalente más cercano.
"""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

from nuevamente.exports.documento import PIE, _Escritor, _limpio, escribir_material
from nuevamente.schemas.formatos import ContenidoAdaptado

_FAMILIAS = [
    {
        "": "/System/Library/Fonts/Supplemental/Arial.ttf",
        "B": "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "I": "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
        "BI": "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf",
    },
    {
        "": "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "B": "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "I": "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
        "BI": "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
    },
    {
        "": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "B": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "I": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
        "BI": "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
    },
]

PRIMARIO = (0x6C, 0x4E, 0xF5)
CORAL = (0xE0, 0x5A, 0x3A)
TEXTO = (0x2D, 0x24, 0x40)
TEXTO_SUAVE = (0x6E, 0x64, 0x80)

# Helvetica solo cubre latin-1: equivalentes de lo que suele aparecer en un material
_A_LATIN1 = str.maketrans({"—": "-", "–": "-", "“": '"', "”": '"', "‘": "'", "’": "'", "…": "...",
                           "•": "-", "☐": "[ ]", "→": "->", "≥": ">=", "≤": "<="})


class _Pdf(_Escritor):
    def __init__(self, titulo: str) -> None:
        self.pdf = _Paginas()
        self.pdf.set_title(titulo)
        self.pdf.set_author("Kairos")
        self.pdf.set_margins(20, 18, 20)
        self.pdf.set_auto_page_break(True, margin=18)
        self.fuente = "Helvetica"
        for familia in _FAMILIAS:
            if all(Path(r).is_file() for r in familia.values()):
                for estilo, ruta in familia.items():
                    self.pdf.add_font("Kairos", estilo, ruta)
                self.fuente = "Kairos"
                break
        self.pdf.fuente = self.fuente
        self.pdf.add_page()

    def _t(self, texto: str) -> str:
        texto = _limpio(texto).replace("☐", "[ ]")  # ni Arial ni Helvetica traen la casilla
        if self.fuente == "Helvetica":
            texto = texto.translate(_A_LATIN1).encode("latin-1", "replace").decode("latin-1")
        return texto

    def _estilo(self, estilo: str = "", tamano: float = 11, color=TEXTO) -> None:
        self.pdf.set_font(self.fuente, estilo, tamano)
        self.pdf.set_text_color(*color)

    def titulo(self, texto: str) -> None:
        self._estilo("B", 22)
        self.pdf.multi_cell(0, 10, self._t(texto), new_x="LMARGIN", new_y="NEXT")
        self.pdf.ln(2)

    def apartado(self, texto: str) -> None:
        self.pdf.ln(3)
        self._estilo("B", 15, PRIMARIO)
        self.pdf.multi_cell(0, 8, self._t(texto), new_x="LMARGIN", new_y="NEXT")
        self.pdf.ln(1)

    def subtitulo(self, texto: str) -> None:
        self.pdf.ln(1.5)
        self._estilo("B", 12)
        self.pdf.multi_cell(0, 6.5, self._t(texto), new_x="LMARGIN", new_y="NEXT")

    def parrafo(self, texto: str, *, etiqueta: str = "", cursiva=False, suave=False, negrita=False, destacado=False):
        if etiqueta:
            self._estilo("B")
            self.pdf.write(6, self._t(f"{etiqueta} "))
        estilo = ("B" if negrita else "") + ("I" if cursiva else "")
        self._estilo(estilo, color=CORAL if destacado else TEXTO_SUAVE if suave else TEXTO)
        self.pdf.write(6, self._t(texto))
        self.pdf.ln(8)

    def lista(self, textos: list[str], estilo: str = "List Bullet") -> None:
        self._estilo()
        for texto in textos:
            vineta = "" if estilo != "List Bullet" else ("•  " if self.fuente != "Helvetica" else "-  ")
            self.pdf.set_x(self.pdf.l_margin + 4)
            self.pdf.multi_cell(0, 6, self._t(vineta + texto), new_x="LMARGIN", new_y="NEXT")
            self.pdf.ln(1)
        self.pdf.ln(1)

    def salto_de_pagina(self) -> None:
        self.pdf.add_page()
        self.olvidar_seccion()

    def pie(self, texto: str) -> None:
        pass  # el pie va en todas las páginas: lo dibuja _Paginas.footer()

    def guardar(self) -> bytes:
        return bytes(self.pdf.output())


class _Paginas(FPDF):
    fuente = "Helvetica"

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font(self.fuente, "", 8)
        self.set_text_color(*TEXTO_SUAVE)
        self.cell(0, 6, f"{PIE}  ·  {self.page_no()}/{{nb}}" if self.fuente != "Helvetica" else f"{PIE}  -  {self.page_no()}/{{nb}}", align="C")


def generar_pdf(
    contenido: ContenidoAdaptado,
    titulo: str,
    perfil: str = "",
    score_fidelidad: float | None = None,
) -> bytes:
    """Devuelve el PDF del material. `titulo` es el del documento de origen."""
    d = _Pdf(titulo)
    escribir_material(d, contenido, titulo, perfil, score_fidelidad)
    return d.guardar()
