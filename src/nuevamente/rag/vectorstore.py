"""Vector store por documento, con recuperación top-k y por sección.

Responsable en el equipo Kairos G10: Gaspar Martinez Paiva (Data Engineer).

Decisión de arquitectura: el enunciado sugiere ChromaDB o FAISS. Para este MVP
implementamos un store propio, ligero (numpy puro), aislado por doc_id igual que
pediría una colección de Chroma, con la misma interfaz de recuperación
(`buscar`, `buscar_por_seccion`). Migrar a ChromaDB implica reemplazar esta clase
por una que hable con el cliente de Chroma sin tocar el resto del pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from nuevamente.ingest.chunking import Chunk
from nuevamente.rag.embeddings import EmbeddingsProvider, crear_proveedor_embeddings


@dataclass
class ResultadoBusqueda:
    chunk: Chunk
    score: float


def _cosine_sim(matriz: np.ndarray, vector: np.ndarray) -> np.ndarray:
    norm_m = np.linalg.norm(matriz, axis=1)
    norm_v = np.linalg.norm(vector)
    denom = norm_m * norm_v
    denom[denom == 0] = 1e-9
    return (matriz @ vector) / denom


class ColeccionDocumento:
    """Equivalente a "una colección de Chroma por doc_id"."""

    def __init__(self, doc_id: str, chunks: list[Chunk], proveedor: EmbeddingsProvider | None = None):
        self.doc_id = doc_id
        self.chunks = chunks
        self.proveedor = proveedor or crear_proveedor_embeddings()
        textos = [c.texto for c in chunks]
        self.proveedor.fit(textos)
        self._matriz = self.proveedor.transform(textos)
        self._generacion = getattr(self.proveedor, "generacion", 0)

    def _sincronizar(self) -> None:
        # si el proveedor pasó a su respaldo, la matriz se recalcula con el mismo modelo
        if getattr(self.proveedor, "generacion", 0) != self._generacion:
            self._matriz = self.proveedor.transform([c.texto for c in self.chunks])
            self._generacion = self.proveedor.generacion

    def _vector_consulta(self, consulta: str) -> np.ndarray:
        vector = self.proveedor.transform([consulta])[0]
        self._sincronizar()
        return vector

    def precalcular_consultas(self, consultas: list[str]) -> None:
        """Embebe varias consultas en una sola solicitud (quedan en la caché del proveedor)."""
        if consultas:
            self.proveedor.transform(consultas)
            self._sincronizar()

    @property
    def modelo_embeddings(self) -> str:
        return getattr(self.proveedor, "nombre", "desconocido")

    def buscar(self, consulta: str, top_k: int = 5) -> list[ResultadoBusqueda]:
        vector = self._vector_consulta(consulta)
        sims = _cosine_sim(self._matriz, vector)
        idx_orden = np.argsort(-sims)[:top_k]
        return [ResultadoBusqueda(chunk=self.chunks[i], score=float(sims[i])) for i in idx_orden]

    def buscar_por_seccion(self, seccion: str, consulta: str, top_k: int = 3) -> list[ResultadoBusqueda]:
        indices = [i for i, c in enumerate(self.chunks) if c.seccion == seccion]
        if not indices:
            return []
        vector = self._vector_consulta(consulta)
        sub_matriz = self._matriz[indices]
        sims = _cosine_sim(sub_matriz, vector)
        orden_local = np.argsort(-sims)[:top_k]
        return [
            ResultadoBusqueda(chunk=self.chunks[indices[i]], score=float(sims[i])) for i in orden_local
        ]

    def secciones(self) -> list[str]:
        vistas: list[str] = []
        for c in self.chunks:
            if c.seccion not in vistas:
                vistas.append(c.seccion)
        return vistas

    def texto_completo_por_seccion(self) -> dict[str, str]:
        agrupado: dict[str, list[str]] = {}
        for c in self.chunks:
            agrupado.setdefault(c.seccion, []).append(c.texto)
        return {sec: " ".join(textos) for sec, textos in agrupado.items()}

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        for c in self.chunks:
            if c.chunk_id == chunk_id:
                return c
        return None


def indexar_documento(titulo: str, contenido: str) -> ColeccionDocumento:
    """Ingesta + chunking + indexación, en un solo paso (usado por la API y la UI)."""
    from nuevamente.ingest.chunking import chunkear_documento

    chunks = chunkear_documento(titulo, contenido)
    if not chunks:
        raise ValueError("El documento no produjo ningún chunk indexable.")
    doc_id = chunks[0].doc_id
    return ColeccionDocumento(doc_id=doc_id, chunks=chunks)
