"""Tests de ingesta y chunking. Responsable: Diana Dure (QA Tester)."""
import pytest

from nuevamente.ingest.chunking import chunkear_documento
from nuevamente.ingest.readers import DocumentoInvalidoError, leer_texto_plano


def test_chunking_respeta_secciones(documento_salud):
    chunks = chunkear_documento("Protocolo", documento_salud)
    secciones = {c.seccion for c in chunks}
    assert "Lavado de manos" in secciones
    assert "Equipos de proteccion personal" in secciones
    assert "Manejo de residuos" in secciones


def test_chunking_genera_chunk_ids_unicos(documento_salud):
    chunks = chunkear_documento("Protocolo", documento_salud)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


def test_chunking_documento_corto_da_un_solo_chunk():
    chunks = chunkear_documento("Doc corto", "Una sola oración corta de prueba.")
    assert len(chunks) == 1


def test_leer_texto_plano_rechaza_vacio():
    with pytest.raises(DocumentoInvalidoError):
        leer_texto_plano("Doc", "   ")


def test_leer_texto_plano_ok():
    doc = leer_texto_plano("Doc", "Contenido real del documento.")
    assert doc.titulo == "Doc"
    assert "real" in doc.contenido
