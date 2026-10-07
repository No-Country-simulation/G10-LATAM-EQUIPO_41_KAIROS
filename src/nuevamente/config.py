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


def _env_latencias(nombre: str) -> dict[str, float]:
    """Latencia de partida por proveedor, escrita como `gemini:4.0,groq:1.2`.

    Son los tiempos medidos a mano en esta máquina, y solo existen para que la *primera*
    petición no pague un proveedor saturado antes de que el router tenga historial propio.
    A partir de la segunda, manda lo observado (ver llm/salud.py)."""
    salida: dict[str, float] = {}
    for par in (os.getenv(nombre) or "").split(","):
        par = par.strip()
        if not par or ":" not in par:
            continue
        clave, _, valor = par.partition(":")
        try:
            salida[clave.strip().lower()] = float(valor)
        except ValueError:
            continue
    return salida



@dataclass(frozen=True)
class Settings:
    # --- Chunking ---
    chunk_size: int = _env_int("CHUNK_SIZE", 900)
    chunk_overlap: int = _env_int("CHUNK_OVERLAP", 150)

    # --- Embeddings / vector store ---
    embeddings_provider: str = os.getenv("EMBEDDINGS_PROVIDER", "local")  # local | gemini
    vectorstore_dir: str = os.getenv("VECTORSTORE_DIR", "data/vectorstore")

    # --- LLM ---
    llm_provider: str = os.getenv("LLM_PROVIDER", "template")  # template | gemini | claude
    llm_model: str = os.getenv("LLM_MODEL", "gemini-3.5-flash")
    # Modelos a usar, en orden, si el principal está saturado (lista separada por comas)
    llm_modelos_respaldo: tuple[str, ...] = tuple(
        m.strip() for m in os.getenv("LLM_MODELOS_RESPALDO", "gemini-3.1-flash-lite,gemini-flash-latest").split(",") if m.strip()
    )
    # Con LLM_PROVIDER=auto se prueban estos proveedores en orden, de una API a otra.
    # Cada uno tiene su propia cuota, así que agotar una no corta la generación.
    llm_cadena: tuple[str, ...] = tuple(
        p.strip() for p in os.getenv("LLM_CADENA", "gemini,groq,cerebras,openrouter").split(",") if p.strip()
    )

    # --- Enrutado por salud (ver llm/salud.py) ---
    # La cadena de arriba es el orden *deseado*; el router lo reordena en cada petición según
    # cómo se estén portando de verdad. Con esto apagado, la cadena siempre se recorre desde
    # el principio y un proveedor lento se paga entero en cada request.
    salud_activada: bool = os.getenv("LLM_SALUD_ACTIVADA", "true").strip().lower() in ("1", "true", "si", "sí")
    # Fallos *consecutivos* que abren el circuito de un proveedor. Con 2, un 503 aislado no
    # apaga a nadie y una racha de 503 sí lo aparta.
    salud_umbral_fallos: int = _env_int("LLM_SALUD_UMBRAL_FALLOS", 2)
    # Pausa antes de volver a probar un proveedor caído; se dobla en cada apertura hasta el
    # tope, para no gastar cuota insistiendo en un servicio que no vuelve.
    salud_cooldown: float = _env_float("LLM_SALUD_COOLDOWN_S", 45.0)
    salud_cooldown_max: float = _env_float("LLM_SALUD_COOLDOWN_MAX_S", 300.0)
    # Peso de la última latencia en la media móvil. Alto = reacciona rápido a un proveedor que
    # se degrada; bajo = olvida el historial más despacio.
    salud_alfa: float = _env_float("LLM_SALUD_ALFA", 0.3)
    # Latencias medidas a mano, solo para arrancar en frío (ver _env_latencias).
    salud_latencia_inicial: dict[str, float] = field(default_factory=lambda: _env_latencias("LLM_SALUD_LATENCIA"))
    # Carrera: pedir el mismo prompt a los N proveedores más sanos a la vez y quedarse con la
    # primera respuesta. Es lo que hace que nunca se espere a un proveedor lento. Cuesta el
    # doble de llamadas (la perdedora se desperdicia), así que va apagada por defecto.
    carrera_activada: bool = os.getenv("LLM_CARRERA", "false").strip().lower() in ("1", "true", "si", "sí")
    carrera_cuantos: int = _env_int("LLM_CARRERA_CUANTOS", 2)
    # Espera antes de lanzar al segundo de la carrera. 0 = salen los dos juntos (lo más
    # rápido, lo que más cuota gasta); 1.5 = sale el segundo solo si el primero no contestó.
    carrera_espera: float = _env_float("LLM_CARRERA_ESPERA_S", 0.0)
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
    gemini_rpm_delay: float = _env_float("GEMINI_RPM_DELAY", 0.5)
    # Si es True, optimiza variantes 'Pro' a 'Flash' para mayor cuota y throughput
    gemini_preferir_flash: bool = os.getenv("GEMINI_PREFERIR_FLASH", "true").lower() in ("true", "1", "yes")
    gemini_max_reintentos: int = _env_int("GEMINI_MAX_REINTENTOS", 2)
    gemini_delay_base: float = _env_float("GEMINI_DELAY_BASE", 1.0)
    # Timeout de cada llamada a Gemini, en segundos. Con el prompt completo del Redactor
    # (hasta 12 chunks de evidencia) un flash tarda varios segundos en responder.
    gemini_timeout: float = _env_float("GEMINI_TIMEOUT", 90.0)

    # Espera máxima de cada llamada a las voces de Gemini (TTS del podcast, que la multiplica) y
    # minutos que se omite un servicio tras un fallo, para no volver a esperarlo (ver llm/disponibilidad.py).
    llm_timeout_s: int = _env_int("LLM_TIMEOUT_S", 40)
    llm_pausa_min: int = _env_int("LLM_PAUSA_TRAS_FALLO_MIN", 10)

    # Si el proveedor real falla (cuota, saturación, sin red), generar con TemplateLLM
    llm_respaldo_local: bool = os.getenv("LLM_RESPALDO_LOCAL", "true").strip().lower() in ("1", "true", "si", "sí")
    anthropic_api_key: str = field(default=os.getenv("ANTHROPIC_API_KEY", ""), repr=False)
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-opus-5")

    # --- Voces del Podcast ---
    # gemini: voces naturales de Gemini TTS (requiere GEMINI_API_KEY); sistema: voces del SO
    podcast_voces: str = os.getenv("PODCAST_VOCES", "gemini").strip().lower()
    podcast_tts_model: str = os.getenv("PODCAST_TTS_MODEL", "gemini-3.1-flash-tts-preview")
    podcast_voz_ana: str = os.getenv("PODCAST_VOZ_ANA", "Sulafat")  # cálida
    podcast_voz_leo: str = os.getenv("PODCAST_VOZ_LEO", "Charon")  # clara, explicativa

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
