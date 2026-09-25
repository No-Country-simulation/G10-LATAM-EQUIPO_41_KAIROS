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


@dataclass(frozen=True)
class Settings:
    # --- Chunking ---
    chunk_size: int = _env_int("CHUNK_SIZE", 900)
    chunk_overlap: int = _env_int("CHUNK_OVERLAP", 150)

    # --- Embeddings / vector store ---
    embeddings_provider: str = os.getenv("EMBEDDINGS_PROVIDER", "local")  # local | gemini
    vectorstore_dir: str = os.getenv("VECTORSTORE_DIR", "data/vectorstore")

    # --- LLM ---
    llm_provider: str = os.getenv("LLM_PROVIDER", "template")  # template | gemini | openai | anthropic
    llm_model: str = os.getenv("LLM_MODEL", "gemini-3.8-flash")
    # Modelos a usar, en orden, si el principal está saturado (lista separada por comas)
    llm_modelos_respaldo: tuple[str, ...] = tuple(
        m.strip() for m in os.getenv("LLM_MODELOS_RESPALDO", "gemini-3.5-flash,gemini-flash-latest").split(",") if m.strip()
    )
    gemini_api_key: str = field(default=os.getenv("GEMINI_API_KEY", ""), repr=False)

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
