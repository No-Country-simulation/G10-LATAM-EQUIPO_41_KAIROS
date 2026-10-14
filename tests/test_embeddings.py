"""Proveedores de embeddings y su respaldo. Responsable: Diana Dure (QA Tester).

Sin red: Gemini se reemplaza por dobles que fallan o responden con vectores fijos."""
from __future__ import annotations

import numpy as np
import pytest

from nuevamente.ingest.chunking import chunkear_documento
from nuevamente.rag.embeddings import EmbeddingsConRespaldo, LocalTfidfEmbeddings, crear_proveedor_embeddings
from nuevamente.rag.vectorstore import ColeccionDocumento


class _Falla:
    """Doble de Gemini: falla al indexar ("fit") o en la primera consulta ("consulta");
    mientras funciona, devuelve vectores de 4 dimensiones."""

    nombre = "gemini-embedding-001"

    def __init__(self, en: str):
        self.en = en
        self._indexado: set[str] = set()

    def fit(self, textos):
        if self.en == "fit":
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        self._indexado = set(textos)

    def transform(self, textos):
        if self.en == "consulta" and any(t not in self._indexado for t in textos):
            raise RuntimeError("sin red")
        return np.ones((len(textos), 4))


def _coleccion(documento_salud, proveedor):
    chunks = chunkear_documento("Protocolo", documento_salud)
    return ColeccionDocumento(doc_id=chunks[0].doc_id, chunks=chunks, proveedor=proveedor)


def test_si_gemini_falla_al_indexar_se_usa_tfidf(documento_salud):
    coleccion = _coleccion(documento_salud, EmbeddingsConRespaldo(_Falla("fit"), LocalTfidfEmbeddings()))
    assert "tfidf-local" in coleccion.modelo_embeddings and "respaldo" in coleccion.modelo_embeddings
    mejor = coleccion.buscar("bolsas rojas residuos biocontaminados", top_k=1)[0]
    assert "residuos" in mejor.chunk.texto.lower()


def test_si_gemini_falla_en_una_consulta_la_coleccion_entera_pasa_a_tfidf(documento_salud):
    """No se mezclan vectores: la matriz de los chunks se recalcula con TF-IDF."""
    coleccion = _coleccion(documento_salud, EmbeddingsConRespaldo(_Falla("consulta"), LocalTfidfEmbeddings()))
    assert coleccion._matriz.shape[1] == 4  # vectores del "Gemini" de prueba
    mejor = coleccion.buscar("lavado de manos con agua y jabon", top_k=1)[0]
    assert coleccion._matriz.shape[1] != 4
    assert "lavado" in mejor.chunk.texto.lower()


def test_local_no_usa_la_red():
    assert isinstance(crear_proveedor_embeddings("local"), LocalTfidfEmbeddings)


def test_auto_sin_clave_usa_tfidf(monkeypatch):
    import dataclasses

    from nuevamente import config

    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, gemini_api_key="", gemini_api_keys=()))
    assert isinstance(crear_proveedor_embeddings("auto"), LocalTfidfEmbeddings)
    with pytest.raises(RuntimeError):
        crear_proveedor_embeddings("gemini")


def test_proveedor_desconocido_da_error():
    with pytest.raises(ValueError):
        crear_proveedor_embeddings("otro")
