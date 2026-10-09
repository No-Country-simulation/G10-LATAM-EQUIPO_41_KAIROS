"""Caché en memoria de contenido generado ya aprobado por el Crítico.

Diseño (alineado con CONTEXTO_PROYECTO.txt, sección 11):
- Solo guarda contenido APROBADO (fidelidad >= umbral). Nunca guarda salida cruda de _redactar.
- Clave EXACTA (no semántica). Debe incluir doc_id, chunk_ids, 4 variables, umbral, versiones de prompts/schema.
- Lookup ANTES del bucle de reintentos (para no leer lo mismo dentro del reintento y romper MAX_REINTENTOS_CRITICO).
- Alcance: in-memory por proceso. Multi-worker Uvicorn tendrá caché por worker (aceptable para MVP/Hackathon).
- Thread-safe con RLock. LRU implícito por tamaño (max_entries) + TTL por entrada.
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nuevamente.schemas.formatos import ContenidoAdaptado


def _sha_archivo(ruta: Path) -> str:
    """SHA256 corto (10 hex) del contenido del archivo para versionar clave de caché."""
    try:
        if not ruta.exists():
            return "0"
        h = hashlib.sha256(ruta.read_bytes()).hexdigest()
        return h[:10]
    except Exception:
        return "0"


def sha_prompts() -> str:
    base = Path(__file__).resolve().parents[2]
    return _sha_archivo(base / "src" / "nuevamente" / "llm" / "prompts.py")


def sha_formatos() -> str:
    base = Path(__file__).resolve().parents[2]
    return _sha_archivo(base / "src" / "nuevamente" / "schemas" / "formatos.py")


def sha_schemas_response() -> str:
    base = Path(__file__).resolve().parents[2]
    return _sha_archivo(base / "src" / "nuevamente" / "schemas" / "response.py")


def version_prompts_formatos() -> str:
    return f"{sha_prompts()}:{sha_formatos()}:{sha_schemas_response()}"


@dataclass
class CacheEntry:
    key: str
    creado_ts: float
    expira_ts: float
    hits: int = 0
    ultimo_hit_ts: float | None = None

    contenido_json: dict[str, Any] = field(default_factory=dict)
    evaluacion_json: dict[str, Any] = field(default_factory=dict)
    metadatos_base_json: dict[str, Any] = field(default_factory=dict)

    doc_id: str = ""
    chunk_ids: list[str] = field(default_factory=list)
    secciones_plan: list[str] = field(default_factory=list)
    conceptos_clave_plan: list[str] = field(default_factory=list)
    prerrequisitos_plan: list[str] = field(default_factory=list)
    umbral_aplicado: float = 0.0
    aprobado_por_critico: bool = True
    score_final: float = 0.0
    afirmaciones_total: int = 0
    afirmaciones_sustentadas: int = 0
    afirmaciones_no_sustentadas: list[str] = field(default_factory=list)

    def viva(self, ahora: float) -> bool:
        return ahora < self.expira_ts

    def tocar(self, ahora: float) -> None:
        self.hits += 1
        self.ultimo_hit_ts = ahora


@dataclass
class CacheStats:
    enabled: bool
    max_entries: int
    ttl_s: int
    entries: int
    hits_total: int
    misses_total: int
    hit_rate: float
    entries_expirados_limpieza: int


class ContentCache:
    """Caché de contenido aprobado (post-Crítico)."""

    def __init__(self, max_entries: int = 32, ttl_s: int = 3600) -> None:
        self._max_entries = max(1, max_entries)
        self._ttl_s = max(60, ttl_s)
        self._lock = threading.RLock()
        self._map: dict[str, CacheEntry] = {}
        self._hits_total = 0
        self._misses_total = 0
        self._limpiezas = 0

    @property
    def max_entries(self) -> int:
        return self._max_entries

    @property
    def ttl_s(self) -> int:
        return self._ttl_s

    def _limpiar_expirados(self, ahora: float) -> int:
        expirados = [k for k, e in self._map.items() if not e.viva(ahora)]
        for k in expirados:
            self._map.pop(k, None)
        if expirados:
            self._limpiezas += 1
        return len(expirados)

    def _evitar_sobrecarga(self) -> None:
        if len(self._map) <= self._max_entries:
            return
        ordenadas = sorted(
            self._map.values(),
            key=lambda e: (e.ultimo_hit_ts or e.creado_ts, e.creado_ts),
        )
        a_borrar = len(self._map) - self._max_entries + 1
        for e in ordenadas[: max(1, a_borrar)]:
            self._map.pop(e.key, None)

    def make_key(
        self,
        *,
        doc_id: str,
        perfil: str,
        formato: str,
        nicho: str,
        nivel_detalle: str,
        umbral_fidelidad: float,
        chunk_ids: list[str],
        prompts_sha: str | None = None,
    ) -> str:
        chunk_list = ",".join(sorted(c.strip() for c in chunk_ids if c.strip()))
        vpf = prompts_sha or version_prompts_formatos()
        base = "|".join(
            [
                "v1",
                doc_id or "",
                perfil or "",
                formato or "",
                nicho or "",
                nivel_detalle or "",
                f"{umbral_fidelidad:.4f}",
                chunk_list,
                vpf,
            ]
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]

    def get(self, key: str) -> CacheEntry | None:
        ahora = time.time()
        with self._lock:
            self._limpiar_expirados(ahora)
            e = self._map.get(key)
            if e is None:
                self._misses_total += 1
                return None
            if not e.viva(ahora):
                self._map.pop(key, None)
                self._misses_total += 1
                return None
            e.tocar(ahora)
            self._hits_total += 1
            return e

    def set(self, key: str, entry: CacheEntry) -> None:
        ahora = time.time()
        with self._lock:
            self._limpiar_expirados(ahora)
            self._map[key] = entry
            self._evitar_sobrecarga()

    def stats(self) -> CacheStats:
        ahora = time.time()
        with self._lock:
            self._limpiar_expirados(ahora)
            total = self._hits_total + self._misses_total
            hit_rate = round(self._hits_total / total, 4) if total else 0.0
            return CacheStats(
                enabled=True,
                max_entries=self._max_entries,
                ttl_s=self._ttl_s,
                entries=len(self._map),
                hits_total=self._hits_total,
                misses_total=self._misses_total,
                hit_rate=hit_rate,
                entries_expirados_limpieza=self._limpiezas,
            )

    def clear(self) -> None:
        with self._lock:
            self._map.clear()
            self._hits_total = 0
            self._misses_total = 0
            self._limpiezas = 0

    @staticmethod
    def entry_from_aprobado(
        *,
        key: str,
        ttl_s: int,
        doc_id: str,
        chunk_ids: list[str],
        secciones_plan: list[str],
        conceptos_clave_plan: list[str],
        prerrequisitos_plan: list[str],
        contenido: ContenidoAdaptado,
        evaluacion_json: dict[str, Any],
        metadatos_base_json: dict[str, Any],
        umbral_aplicado: float,
        score_final: float,
        afirmaciones_total: int,
        afirmaciones_sustentadas: int,
        afirmaciones_no_sustentadas: list[str],
        aprobado_por_critico: bool,
    ) -> CacheEntry:
        ahora = time.time()
        exp = ahora + max(60, ttl_s)
        return CacheEntry(
            key=key,
            creado_ts=ahora,
            expira_ts=exp,
            hits=0,
            ultimo_hit_ts=None,
            contenido_json=contenido.model_dump(mode="json"),
            evaluacion_json=evaluacion_json,
            metadatos_base_json=metadatos_base_json,
            doc_id=doc_id,
            chunk_ids=list(chunk_ids),
            secciones_plan=list(secciones_plan),
            conceptos_clave_plan=list(conceptos_clave_plan),
            prerrequisitos_plan=list(prerrequisitos_plan),
            umbral_aplicado=umbral_aplicado,
            aprobado_por_critico=aprobado_por_critico,
            score_final=score_final,
            afirmaciones_total=afirmaciones_total,
            afirmaciones_sustentadas=afirmaciones_sustentadas,
            afirmaciones_no_sustentadas=list(afirmaciones_no_sustentadas),
        )
