"""Proveedores de embeddings.

Responsable en el equipo Kairos G10: Gaspar Martinez Paiva (Data Engineer),
con Adrian Gil (ML Engineer) definiendo la interfaz para que sea intercambiable.

- `GeminiEmbeddings`: embeddings semánticos densos de Google (`gemini-embedding-001`,
  768 dimensiones). Distingue documentos (`RETRIEVAL_DOCUMENT`) de consultas
  (`RETRIEVAL_QUERY`), pide los textos por lotes y recuerda los ya calculados.
- `LocalTfidfEmbeddings`: TF-IDF local (scikit-learn), determinista, sin red ni costo.
- `EmbeddingsConRespaldo`: usa Gemini y, si falla (cuota, red), pasa la colección
  completa a TF-IDF; nunca mezcla vectores de dos modelos en una misma búsqueda.

EMBEDDINGS_PROVIDER elige: "auto" (Gemini si hay API key, con respaldo local),
"gemini" (igual, pero lo exige) o "local" (solo TF-IDF; lo usan los tests).
"""
from __future__ import annotations

import hashlib
import logging
import threading
from collections import OrderedDict
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


logger = logging.getLogger(__name__)


class EmbeddingsProvider(Protocol):
    nombre: str

    def fit(self, textos: list[str]) -> None: ...
    def transform(self, textos: list[str]) -> np.ndarray: ...


class LocalTfidfEmbeddings:
    """Embeddings locales por TF-IDF, con similitud de coseno.

    No es un embedding semántico "denso" como el de un modelo neuronal, pero es
    real, se ejecuta 100% en local, y para el propósito de anclar afirmaciones a
    fragmentos del MISMO documento (no búsqueda semántica entre documentos
    distintos) da resultados razonables y totalmente verificables/testeables.
    """

    nombre = "tfidf-local"

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


# ---------- Gemini ----------

_SERVICIO = "embeddings:gemini"
_LOTE = 100  # máximo de textos por solicitud que acepta embed_content
_MAX_CACHE = 5000
_cache: OrderedDict[str, np.ndarray] = OrderedDict()  # de proceso: el mismo documento en otro formato no se repide
_candado_cache = threading.Lock()


class GeminiEmbeddings:
    """Embeddings semánticos de Gemini. `fit` embebe los chunks como documentos;
    `transform` reutiliza esos vectores y embebe como consulta los textos nuevos."""

    def __init__(self, api_key: str | None = None, modelo: str | None = None, dimensiones: int | None = None):
        from nuevamente.config import settings

        claves = list(settings.gemini_api_keys) or [settings.gemini_api_key]
        self._api_key = api_key or next((c for c in claves if c), "")
        if not self._api_key:
            raise RuntimeError("GeminiEmbeddings requiere GEMINI_API_KEY.")
        self._modelo = modelo or settings.embeddings_modelo
        self._dimensiones = dimensiones or settings.embeddings_dimensiones
        self._timeout_ms = settings.llm_timeout_s * 1000
        self._documentos: set[str] = set()
        self.nombre = self._modelo
        self._cliente = None

    def _clave(self, texto: str, tarea: str) -> str:
        return hashlib.sha256(f"{self._modelo}|{self._dimensiones}|{tarea}|{texto}".encode("utf-8")).hexdigest()

    def _embeber(self, textos: list[str], tarea: str) -> dict[str, np.ndarray]:
        from google import genai
        from google.genai import types

        resultado: dict[str, np.ndarray] = {}
        faltan = []
        with _candado_cache:
            for t in dict.fromkeys(textos):
                v = _cache.get(self._clave(t, tarea))
                if v is None:
                    faltan.append(t)
                else:
                    resultado[t] = v
        if faltan:
            if self._cliente is None:
                self._cliente = genai.Client(api_key=self._api_key, http_options=types.HttpOptions(timeout=self._timeout_ms))
            config = types.EmbedContentConfig(task_type=tarea, output_dimensionality=self._dimensiones)
            for i in range(0, len(faltan), _LOTE):
                lote = faltan[i : i + _LOTE]
                respuesta = self._cliente.models.embed_content(model=self._modelo, contents=lote, config=config)
                if len(respuesta.embeddings or []) != len(lote):
                    raise RuntimeError("Gemini devolvió una cantidad de embeddings distinta a la pedida.")
                with _candado_cache:
                    for texto, emb in zip(lote, respuesta.embeddings):
                        vector = np.asarray(emb.values, dtype=np.float32)
                        resultado[texto] = vector
                        _cache[self._clave(texto, tarea)] = vector
                        while len(_cache) > _MAX_CACHE:
                            _cache.popitem(last=False)
        return resultado

    def fit(self, textos: list[str]) -> None:
        if not textos:
            raise ValueError("No se puede indexar sin textos.")
        self._vectores_doc = self._embeber(textos, "RETRIEVAL_DOCUMENT")
        self._documentos = set(textos)

    def transform(self, textos: list[str]) -> np.ndarray:
        consultas = [t for t in textos if t not in self._documentos]
        vectores_consulta = self._embeber(consultas, "RETRIEVAL_QUERY") if consultas else {}
        return np.vstack([self._vectores_doc[t] if t in self._documentos else vectores_consulta[t] for t in textos])


class EmbeddingsConRespaldo:
    """Usa el proveedor principal y, si falla, el respaldo para TODA la colección.
    `generacion` aumenta cuando cambia de proveedor: la colección recalcula su matriz."""

    def __init__(self, principal: EmbeddingsProvider, respaldo: EmbeddingsProvider):
        self._principal, self._respaldo = principal, respaldo
        self._activo = principal
        self._textos: list[str] = []
        self.generacion = 0

    @property
    def nombre(self) -> str:
        if self._activo is self._respaldo:
            return f"{self._respaldo.nombre} (respaldo: {self._principal.nombre} no disponible)"
        return self._principal.nombre

    def _pasar_a_respaldo(self, exc: Exception) -> None:
        from nuevamente.llm import disponibilidad

        logger.warning("Embeddings de Gemini no disponibles, se usa TF-IDF local: %s", exc)
        disponibilidad.pausar(_SERVICIO, str(exc))
        self._activo = self._respaldo
        self._respaldo.fit(self._textos)
        self.generacion += 1

    def fit(self, textos: list[str]) -> None:
        self._textos = list(textos)
        try:
            self._activo.fit(textos)
        except Exception as exc:  # cuota, red, clave: se indexa igual, con el respaldo
            if self._activo is self._respaldo:
                raise
            self._pasar_a_respaldo(exc)

    def transform(self, textos: list[str]) -> np.ndarray:
        try:
            return self._activo.transform(textos)
        except Exception as exc:
            if self._activo is self._respaldo:
                raise
            self._pasar_a_respaldo(exc)
            return self._respaldo.transform(textos)


def crear_proveedor_embeddings(nombre: str | None = None) -> EmbeddingsProvider:
    from nuevamente.config import settings
    from nuevamente.llm import disponibilidad

    nombre = (nombre or settings.embeddings_provider).strip().lower()
    if nombre == "local":
        return LocalTfidfEmbeddings()
    if nombre in ("auto", "gemini"):
        hay_clave = bool(settings.gemini_api_key or settings.gemini_api_keys)
        if not hay_clave:
            if nombre == "gemini":
                raise RuntimeError("EMBEDDINGS_PROVIDER=gemini requiere GEMINI_API_KEY.")
            return LocalTfidfEmbeddings()
        if disponibilidad.en_pausa(_SERVICIO):  # falló hace poco: no se lo vuelve a esperar
            return EmbeddingsConRespaldo(_SinServicio(), LocalTfidfEmbeddings())
        return EmbeddingsConRespaldo(GeminiEmbeddings(), LocalTfidfEmbeddings())
    raise ValueError(f"EMBEDDINGS_PROVIDER no válido: '{nombre}'. Usa auto, gemini o local.")


class _SinServicio:
    """Principal que falla al instante: Gemini está en pausa tras un fallo reciente."""

    nombre = "gemini-embedding-001"

    def fit(self, textos: list[str]) -> None:
        raise RuntimeError("embeddings de Gemini en pausa tras un fallo reciente")

    def transform(self, textos: list[str]) -> np.ndarray:
        raise RuntimeError("embeddings de Gemini en pausa tras un fallo reciente")
