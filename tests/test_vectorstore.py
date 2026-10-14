"""Tests de indexación y recuperación. Responsable: Diana Dure (QA Tester)."""
from nuevamente.rag.vectorstore import indexar_documento


def test_recuperacion_devuelve_seccion_mas_relevante(documento_salud):
    coleccion = indexar_documento("Protocolo", documento_salud)
    resultados = coleccion.buscar("como desechar residuos biocontaminados", top_k=1)
    assert resultados[0].chunk.seccion == "Manejo de residuos"


def test_buscar_por_seccion_filtra_correctamente(documento_salud):
    coleccion = indexar_documento("Protocolo", documento_salud)
    resultados = coleccion.buscar_por_seccion("Lavado de manos", "Lavado de manos", top_k=5)
    assert all(r.chunk.seccion == "Lavado de manos" for r in resultados)


def test_secciones_cubren_todo_el_documento(documento_salud):
    coleccion = indexar_documento("Protocolo", documento_salud)
    assert len(coleccion.secciones()) == 3


# ---------- ChromaDB (HU-13) ----------

import dataclasses

import pytest

chromadb = pytest.importorskip("chromadb")


def _chroma():
    from chromadb.config import Settings as ChromaSettings

    return chromadb.EphemeralClient(settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True))


def test_chroma_devuelve_lo_mismo_que_el_store_local(documento_salud):
    from nuevamente.ingest.chunking import chunkear_documento
    from nuevamente.rag.embeddings import LocalTfidfEmbeddings
    from nuevamente.rag.vectorstore import ColeccionChroma, ColeccionDocumento

    chunks = chunkear_documento("Protocolo", documento_salud)
    local = ColeccionDocumento(chunks[0].doc_id, chunks, LocalTfidfEmbeddings())
    chroma = ColeccionChroma(chunks[0].doc_id, chunks, LocalTfidfEmbeddings(), cliente=_chroma())
    consulta = "bolsas rojas para residuos biocontaminados"
    assert [r.chunk.chunk_id for r in chroma.buscar(consulta, 3)] == [r.chunk.chunk_id for r in local.buscar(consulta, 3)]
    assert chroma.buscar(consulta, 1)[0].score == pytest.approx(local.buscar(consulta, 1)[0].score, abs=1e-4)
    # la búsqueda por sección usa el filtro de metadatos de Chroma
    seccion = chunks[0].seccion
    assert all(r.chunk.seccion == seccion for r in chroma.buscar_por_seccion(seccion, consulta, 5))
    assert chroma.buscar_por_seccion("No existe", consulta) == []


def test_el_pipeline_completo_funciona_con_chroma(monkeypatch, documento_salud):
    from nuevamente.agents.graph import generar_contenido_educativo
    from nuevamente.rag import vectorstore

    monkeypatch.setattr(vectorstore, "settings", dataclasses.replace(vectorstore.settings, vector_store="chroma"))
    monkeypatch.setattr(vectorstore, "_cliente_chroma", _chroma)
    r = generar_contenido_educativo("Protocolo", documento_salud, "Principiante", "Quiz", "Salud", "Didáctico")
    assert isinstance(r.coleccion, vectorstore.ColeccionChroma)
    assert r.evaluacion.aprobado_por_critico
