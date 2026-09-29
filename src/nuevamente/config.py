"""Configuración central de NuevaMente.

Responsable de este módulo en el equipo Kairos G10: Juan Pablo Calla (PM/arquitecto),
con apoyo de Gaspar Martinez Paiva (Data Engineer) para las variables de OCI.

Todas las variables se leen de entorno (.env en desarrollo). Nada de esto contiene
secretos: los valores por defecto son seguros para correr en modo local/demo.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Carga .env ANTES de definir Settings, porque sus valores por defecto se evalúan
# al importar. Primero el .env del directorio actual y luego el de la raíz del repo;
# las variables ya definidas en el entorno siempre tienen prioridad.
load_dotenv(find_dotenv(usecwd=True))
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_tuple_keys(*names: str) -> tuple[str, ...]:
    encontradas: list[str] = []
    for name in names:
        val = os.getenv(name)
        if val:
            for k in val.split(","):
                k = k.strip()
                if k and k not in encontradas:
                    encontradas.append(k)
    return tuple(encontradas)



@dataclass(frozen=True)
class Settings:
    # --- Chunking ---
    chunk_size: int = _env_int("CHUNK_SIZE", 900)
    chunk_overlap: int = _env_int("CHUNK_OVERLAP", 150)

    # --- Embeddings / vector store ---
    embeddings_provider: str = os.getenv("EMBEDDINGS_PROVIDER", "local")  # local | gemini
    vectorstore_dir: str = os.getenv("VECTORSTORE_DIR", "data/vectorstore")

    # --- LLM ---
    llm_provider: str = os.getenv("LLM_PROVIDER", "template")  # template|gemini|groq|cerebras|openrouter|auto
    llm_model: str = os.getenv("LLM_MODEL", "gemini-3.8-flash")
    # Modelos a usar, en orden, si el principal está saturado (lista separada por comas)
    llm_modelos_respaldo: tuple[str, ...] = tuple(
        m.strip() for m in os.getenv("LLM_MODELOS_RESPALDO", "gemini-3.5-flash,gemini-flash-latest").split(",") if m.strip()
    )
    # Con LLM_PROVIDER=auto se prueban estos proveedores en orden, de una API a otra.
    # Cada uno tiene su propia cuota, así que agotar una no corta la generación.
    llm_cadena: tuple[str, ...] = tuple(
        p.strip() for p in os.getenv("LLM_CADENA", "gemini,groq,cerebras,openrouter").split(",") if p.strip()
    )
    # Claves de Gemini: admite una sola clave o varias separadas por coma para rotar si se agota la cuota
    gemini_api_keys: tuple[str, ...] = field(
        default_factory=lambda: _env_tuple_keys("GEMINI_API_KEYS", "GEMINI_API_KEY"),
        repr=False,
    )
    gemini_api_key: str = field(
        default_factory=lambda: (
            _env_tuple_keys("GEMINI_API_KEYS", "GEMINI_API_KEY")[0]
            if _env_tuple_keys("GEMINI_API_KEYS", "GEMINI_API_KEY")
            else ""
        ),
        repr=False,
    )
    groq_api_key: str = field(default=os.getenv("GROQ_API_KEY", ""), repr=False)
    cerebras_api_key: str = field(default=os.getenv("CEREBRAS_API_KEY", ""), repr=False)
    openrouter_api_key: str = field(default=os.getenv("OPENROUTER_API_KEY", ""), repr=False)

    # --- Control de tasa (RPM / TPM) y optimización Gemini ---
    # Pausa prudente mínima en segundos entre llamadas consecutivas a la API
    gemini_rpm_delay: float = _env_float("GEMINI_RPM_DELAY", 1.5)
    # Si es True, optimiza variantes 'Pro' a 'Flash' para mayor cuota y throughput
    gemini_preferir_flash: bool = os.getenv("GEMINI_PREFERIR_FLASH", "true").lower() in ("true", "1", "yes")
    gemini_max_reintentos: int = _env_int("GEMINI_MAX_REINTENTOS", 5)
    gemini_delay_base: float = _env_float("GEMINI_DELAY_BASE", 2.0)


    # --- Fidelidad ---
    # Umbral general del enunciado vs. umbral reforzado para el nicho Salud (ver plan de trabajo).
    fidelity_min_general: float = _env_float("FIDELITY_MIN_GENERAL", 0.85)
    fidelity_min_salud: float = _env_float("FIDELITY_MIN_SALUD", 0.90)
    max_reintentos_critico: int = _env_int("MAX_REINTENTOS_CRITICO", 2)

    # --- OCI Object Storage ---
    oci_config_file: str = os.getenv("OCI_CONFIG_FILE", "~/.oci/config")
    oci_profile: str = os.getenv("OCI_PROFILE", "DEFAULT")
    oci_compartment_id: str = os.getenv("OCI_COMPARTMENT_ID", "")
    oci_bucket: str = os.getenv("OCI_BUCKET", "nuevamente-contenidos-educativos")

    # --- Fallback local (cuando OCI no está configurado o falla) ---
    fallback_dir: str = os.getenv("FALLBACK_DIR", "data/fallback")

    # --- Video del Guion de Clase ---
    video_tts: str = os.getenv("VIDEO_TTS", "auto")  # auto (voz del sistema si hay) | off (sin narración)
    videos_dir: str = os.getenv("VIDEOS_DIR", "data/videos")

    # --- Límites de ingesta ---
    max_upload_mb: int = _env_int("MAX_UPLOAD_MB", 10)

    def fidelity_min_for(self, nicho_sector: str) -> float:
        """Devuelve el umbral de fidelidad correcto según el nicho.

        Salud usa un umbral más estricto (ver docs/demo/ y el plan de trabajo
        entregado por el PM): un dato mal anclado en un material de capacitación de
        salud pesa más que en un nicho general.
        """
        if nicho_sector.strip().lower() == "salud":
            return self.fidelity_min_salud
        return self.fidelity_min_general


settings = Settings()
