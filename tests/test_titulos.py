"""Reconocimiento de títulos, subtítulos y texto en Markdown y PDF.

El material (viñetas, guiones, diapositivas) se arma por secciones: si un título no se
reconoce, su texto queda bajo un título ajeno; si una línea de texto pasa por título,
la sección sale vacía o cortada.
"""
from pathlib import Path

import pytest

from nuevamente.ingest.chunking import _detectar_secciones, chunkear_documento
from nuevamente.ingest.readers import leer_documento, leer_pdf

_TEXTO = (
    "El lavado de manos con agua y jabón elimina la mayoría de los microorganismos de la piel. "
    "Se recomienda hacerlo antes y después de atender a cada paciente, durante al menos veinte segundos."
)


def _secciones(contenido: str) -> list[str]:
    return [titulo for titulo, _ in _detectar_secciones(contenido)]


# ---------- Markdown ----------

def test_markdown_reconoce_todos_los_niveles_y_titulos_subrayados():
    md = (
        "# Guía de **bioseguridad**\n\nIntroducción breve.\n\n"
        "Requisitos\n==========\n\nGuantes y mascarilla.\n\n"
        "## 1. Lavado de manos ##\n\nPaso uno del lavado.\n\n"
        "#### 1.1 Duración\n\nVeinte segundos.\n\n"
        "Secado\n------\n\nCon toalla de papel.\n"
    )
    assert _secciones(md) == ["Guía de bioseguridad", "Requisitos", "Lavado de manos", "Duración", "Secado"]


def test_markdown_comentario_en_bloque_de_codigo_no_es_titulo():
    md = (
        "# Instalación\n\nPasos para instalar.\n\n"
        "```bash\n# instala las dependencias\npip install -r requirements.txt\n```\n\n"
        "# Uso\n\nCómo se usa.\n"
    )
    secciones = _detectar_secciones(md)
    assert [t for t, _ in secciones] == ["Instalación", "Uso"]
    assert "# instala las dependencias" in secciones[0][1]


def test_markdown_separador_tras_parrafo_largo_no_crea_titulo():
    md = "# Tema\n\nUn párrafo con varias líneas\nque termina aquí.\n\n---\n\nOtro párrafo.\n"
    assert _secciones(md) == ["Tema"]


def test_markdown_de_prueba_del_equipo():
    ruta = Path("docs/pruebas/documentos/evidencia_scrum_21_a_24.md")
    if not ruta.is_file():
        pytest.skip("documento de prueba no disponible")
    assert _secciones(leer_documento(ruta).contenido) == [
        "Reporte de Evidencia de Pruebas: Pipeline RAG y Fallback Local (SCRUM 21 a 24)",
        "SCRUM-21 y SCRUM-22: Ingesta de Documentos y Chunking",
        "SCRUM-23: Embeddings Locales (TF-IDF) y Vector Store",
        "SCRUM-24: TemplateLLM (Generador Determinista Offline)",
    ]


# ---------- PDF ----------

def _pdf(tmp_path, bloques, marcadores=()) -> Path:
    """PDF con bloques (tamaño, negrita, texto) y, opcionalmente, marcadores (título, nivel)
    que no se escriben como texto."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    for titulo, nivel in marcadores:
        pdf.start_section(titulo, level=nivel)
    for tamano, negrita, texto in bloques:
        pdf.set_font("Helvetica", "B" if negrita else "", tamano)
        pdf.multi_cell(0, tamano * 0.6, texto)
        pdf.ln(2)
    ruta = tmp_path / "documento.pdf"
    pdf.output(str(ruta))
    return ruta


def test_pdf_titulos_por_tamano_de_letra(tmp_path):
    ruta = _pdf(tmp_path, [
        (20, True, "Manual de bioseguridad"),
        (11, False, _TEXTO),
        (15, True, "Lavado de manos"),
        (11, False, _TEXTO),
        (13, True, "Antes de atender"),
        (11, False, _TEXTO),
        (15, True, "Uso de guantes"),
        (11, False, _TEXTO),
    ])
    contenido = leer_pdf(ruta).contenido
    assert "# Manual de bioseguridad" in contenido and "## Lavado de manos" in contenido
    assert "### Antes de atender" in contenido  # subtítulo: letra intermedia
    assert _secciones(contenido) == ["Manual de bioseguridad", "Lavado de manos", "Antes de atender", "Uso de guantes"]


def test_pdf_titulo_en_negrita_del_mismo_tamano(tmp_path):
    """Sin letra más grande, un renglón entero en negrita es un subtítulo; un rótulo
    terminado en ":" no lo es."""
    ruta = _pdf(tmp_path, [
        (11, True, "Lavado de manos"),
        (11, False, _TEXTO),
        (11, True, "Ejemplos:"),
        (11, False, _TEXTO),
        (11, True, "Uso de guantes"),
        (11, False, _TEXTO),
    ])
    assert _secciones(leer_pdf(ruta).contenido) == ["Lavado de manos", "Uso de guantes"]


def test_pdf_titulo_en_dos_renglones_queda_en_uno(tmp_path):
    ruta = _pdf(tmp_path, [
        (18, True, "Diagnóstico y prevalencia de los trastornos de la personalidad en la atención ambulatoria"),
        (11, False, _TEXTO),
        (18, True, "Resultados"),
        (11, False, _TEXTO),
    ])
    assert _secciones(leer_pdf(ruta).contenido)[0] == (
        "Diagnóstico y prevalencia de los trastornos de la personalidad en la atención ambulatoria"
    )


def test_pdf_con_marcadores_agrega_los_titulos_que_no_estan_como_texto(tmp_path):
    ruta = _pdf(tmp_path, [(11, False, _TEXTO)], marcadores=[("Resumen", 0), ("Palabras clave", 1)])
    contenido = leer_pdf(ruta).contenido
    assert contenido.startswith("# Resumen\n## Palabras clave")


def test_pdf_comentario_de_codigo_no_pasa_por_titulo(tmp_path):
    ruta = _pdf(tmp_path, [
        (16, True, "Instalación"),
        (11, False, "# instala las dependencias"),
        (11, False, _TEXTO),
        (16, True, "Uso"),
        (11, False, _TEXTO),
    ])
    contenido = leer_pdf(ruta).contenido
    assert "\\# instala las dependencias" in contenido
    assert _secciones(contenido) == ["Instalación", "Uso"]


def test_pdf_sin_estilos_sigue_usando_las_reglas_de_texto(tmp_path):
    ruta = _pdf(tmp_path, [
        (11, False, "1. Lavado de manos"),
        (11, False, _TEXTO),
        (11, False, "2. Uso de guantes"),
        (11, False, _TEXTO),
    ])
    assert _secciones(leer_pdf(ruta).contenido) == ["Lavado de manos", "Uso de guantes"]


# Documentos reales de docs/pruebas/documentos/ (se omiten si no están en el equipo)
_DOCUMENTOS = Path("docs/pruebas/documentos")


@pytest.mark.parametrize("archivo, esperados", [
    ("E-Commers.pdf", ["¿Qué es el E-commerce?", "B2C (Business to Consumer)", "Conclusión", "Referencias"]),
    ("Normas de Conducta y Convivencia.pdf", ["Obligaciones y Conducta del Paciente", "Derechos Fundamentales del Paciente"]),
    ("DD_IA_01.pdf", ["Inteligencia Artificial", "Algoritmo", "Macrodatos - Big Data", "Data brokers"]),
    ("IoT-Guia-Basica.pdf", ["¿Qué es la conectividad ?", "Smart cities", "¿Qué es TUYA?"]),
])
def test_pdf_de_prueba_del_equipo(archivo, esperados):
    ruta = _DOCUMENTOS / archivo
    if not ruta.is_file():
        pytest.skip("documento de prueba no disponible")
    secciones = [c.seccion for c in chunkear_documento(archivo, leer_pdf(ruta).contenido)]
    for titulo in esperados:
        assert titulo in secciones
    assert "Documento completo" not in secciones


def test_markdown_cerco_de_codigo_sin_cerrar_no_borra_los_titulos_siguientes():
    md = "# Sintaxis\n\nEjemplo:\n```\n\n# Seguridad\n\nTexto.\n\n# Privacidad\n\nMás texto.\n"
    assert _secciones(md) == ["Sintaxis", "Seguridad", "Privacidad"]
