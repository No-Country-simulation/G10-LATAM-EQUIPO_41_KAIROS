"""Proveedor de embeddings.

Responsable en el equipo Kairos G10: Gaspar Martinez Paiva (Data Engineer),
con Adrian Gil (ML Engineer) definiendo la interfaz para que sea intercambiable.

Decisión de arquitectura (documentada también en el README): en este entorno de
desarrollo no hay acceso de red a APIs de embeddings (Gemini/OpenAI), así que el
proveedor por defecto es un TF-IDF local (scikit-learn), 100% determinista y sin
costo. La interfaz `EmbeddingsProvider` es la misma que usaría un proveedor real,
así que cambiar a Gemini en la máquina del equipo (con API key) es solo cuestión
de implementar `GeminiEmbeddings` con la misma firma y ajustar EMBEDDINGS_PROVIDER.
"""
from __future__ import annotations

from typing import Protocol

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

# Lista breve de stopwords en español (evita que palabras funcionales infladas
# por baja diversidad de vocabulario en documentos cortos distorsionen la
# similitud de coseno). No pretende ser exhaustiva; scikit-learn no trae una
# lista de español incorporada.
STOPWORDS_ES = {
    "a", "al", "algo", "algunas", "algunos", "ante", "asi", "aunque", "cada",
    "como", "con", "contra", "cual", "cuando", "de", "del", "desde", "donde",
    "durante", "e", "el", "ella", "ellas", "ellos", "en", "entre", "era",
    "es", "esa", "esas", "ese", "eso", "esos", "esta", "estas", "este",
    "esto", "estos", "fue", "ha", "hay", "la", "las", "le", "les", "lo",
    "los", "mas", "me", "mi", "mientras", "muy", "no", "nos", "o", "para",
    "pero", "poco", "por", "porque", "que", "quien", "se", "segun", "ser",
    "si", "sin", "sobre", "son", "su", "sus", "tambien", "tras", "tu", "un",
    "una", "uno", "unos", "y", "ya", "yo",
}


class EmbeddingsProvider(Protocol):
    def fit(self, textos: list[str]) -> None: ...
    def transform(self, textos: list[str]) -> np.ndarray: ...


class LocalTfidfEmbeddings:
    """Embeddings locales por TF-IDF, con similitud de coseno.

    No es un embedding semántico "denso" como el de un modelo neuronal, pero es
    real, se ejecuta 100% en local, y para el propósito de anclar afirmaciones a
    fragmentos del MISMO documento (no búsqueda semántica entre documentos
    distintos) da resultados razonables y totalmente verificables/testeables.
    """

    def __init__(self) -> None:
        self._vectorizer = TfidfVectorizer(
            lowercase=True,
            strip_accents="unicode",
            ngram_range=(1, 2),
            min_df=1,
            stop_words=list(STOPWORDS_ES),
        )
        self._fitted = False

    def fit(self, textos: list[str]) -> None:
        if not textos:
            raise ValueError("No se puede entrenar el vectorizador sin textos.")
        self._vectorizer.fit(textos)
        self._fitted = True

    def transform(self, textos: list[str]) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("Llama a fit() antes de transform().")
        matriz = self._vectorizer.transform(textos)
        return matriz.toarray()


def crear_proveedor_embeddings(nombre: str | None = None) -> EmbeddingsProvider:
    from nuevamente.config import settings

    nombre = nombre or settings.embeddings_provider
    if nombre == "local":
        return LocalTfidfEmbeddings()
    raise NotImplementedError(
        f"Proveedor de embeddings '{nombre}' no implementado en este MVP. "
        "Usa EMBEDDINGS_PROVIDER=local, o implementa GeminiEmbeddings con la "
        "misma interfaz EmbeddingsProvider."
    )
