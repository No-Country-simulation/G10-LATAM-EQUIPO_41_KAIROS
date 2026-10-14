"""Vector store por documento, con recuperación top-k y por sección.

Responsable en el equipo Kairos G10: Gaspar Martinez Paiva (Data Engineer).

Decisión de arquitectura: el enunciado sugiere ChromaDB o FAISS. Para este MVP
implementamos un store propio, ligero (numpy puro), aislado por doc_id igual que
pediría una colección de Chroma, con la misma interfaz de recuperación
(`buscar`, `buscar_por_seccion`). Migrar a ChromaDB implica reemplazar esta clase
por una que hable con el cliente de Chroma sin tocar el resto del pipeline.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from nuevamente.config import settings
from nuevamente.ingest.chunking import Chunk
from nuevamente.rag.embeddings import EmbeddingsProvider, crear_proveedor_embeddings

logger = logging.getLogger(__name__)


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


class ColeccionChroma(ColeccionDocumento):
    """La misma colección, con los vectores en ChromaDB (HU-13): una colección persistente por
    documento y modelo de embeddings, en VECTORSTORE_DIR/chroma. Las búsquedas por sección
    usan el filtro de metadatos de Chroma. Los embeddings los sigue poniendo el proveedor
    (Gemini o TF-IDF), así que el resto del pipeline no cambia."""

    def __init__(self, doc_id: str, chunks: list[Chunk], proveedor: EmbeddingsProvider | None = None, cliente=None):
        self._cliente = cliente or _cliente_chroma()
        super().__init__(doc_id, chunks, proveedor)
        self._volcar()

    def _volcar(self) -> None:
        """Escribe los vectores actuales en la colección de Chroma del documento y el modelo."""
        huella = hashlib.sha256(f"{self.modelo_embeddings}|{self._matriz.shape[1]}".encode()).hexdigest()[:10]
        self._coleccion = self._cliente.get_or_create_collection(
            name=f"kairos-{self.doc_id}-{huella}", metadata={"hnsw:space": "cosine"}, embedding_function=None,
        )
        self._coleccion.upsert(
            ids=[c.chunk_id for c in self.chunks],
            embeddings=self._matriz.tolist(),
            documents=[c.texto for c in self.chunks],
            metadatas=[{"seccion": c.seccion, "orden": c.orden} for c in self.chunks],
        )
        self._por_id = {c.chunk_id: c for c in self.chunks}

    def _sincronizar(self) -> None:
        generacion = self._generacion
        super()._sincronizar()
        if self._generacion != generacion:  # pasó a otro modelo: otra colección, con sus vectores
            self._volcar()

    def _consultar(self, consulta: str, top_k: int, seccion: str | None = None) -> list[ResultadoBusqueda]:
        vector = self._vector_consulta(consulta)
        filtro = {"seccion": seccion} if seccion is not None else None
        n = len(self.chunks) if seccion is None else sum(1 for c in self.chunks if c.seccion == seccion)
        if n == 0:
            return []
        r = self._coleccion.query(query_embeddings=[vector.tolist()], n_results=min(top_k, n), where=filtro)
        # Chroma devuelve la distancia coseno (1 - similitud)
        return [
            ResultadoBusqueda(chunk=self._por_id[i], score=float(1 - d))
            for i, d in zip(r["ids"][0], r["distances"][0])
        ]

    def buscar(self, consulta: str, top_k: int = 5) -> list[ResultadoBusqueda]:
        return self._consultar(consulta, top_k)

    def buscar_por_seccion(self, seccion: str, consulta: str, top_k: int = 3) -> list[ResultadoBusqueda]:
        return self._consultar(consulta, top_k, seccion)


_chroma = None


def _cliente_chroma():
    """Cliente persistente de ChromaDB (uno por proceso), sin telemetría."""
    global _chroma
    if _chroma is None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        ruta = Path(settings.vectorstore_dir) / "chroma"
        ruta.mkdir(parents=True, exist_ok=True)
        _chroma = chromadb.PersistentClient(path=str(ruta), settings=ChromaSettings(anonymized_telemetry=False))
    return _chroma


def indexar_documento(titulo: str, contenido: str) -> ColeccionDocumento:
    """Ingesta + chunking + indexación, en un solo paso (usado por la API y la UI)."""
    from nuevamente.ingest.chunking import chunkear_documento

    chunks = chunkear_documento(titulo, contenido)
    if not chunks:
        raise ValueError("El documento no produjo ningún chunk indexable.")
    doc_id = chunks[0].doc_id
    if settings.vector_store == "chroma":
        try:
            return ColeccionChroma(doc_id=doc_id, chunks=chunks)
        except ImportError as exc:
            logger.warning("VECTOR_STORE=chroma pero ChromaDB no está instalado; se usa el store local: %s", exc)
    return ColeccionDocumento(doc_id=doc_id, chunks=chunks)
