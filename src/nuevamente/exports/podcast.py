"""Audio MP3 de un Podcast: la conversación leída con dos voces.

Responsable en el equipo Kairos G10: Dario Higuera Moreno (No Code Developer).

Dos motores de voz:
  - "gemini" (por defecto): Gemini TTS multi-locutor. Lee el diálogo completo con
    voces neuronales (Ana: PODCAST_VOZ_ANA, Leo: PODCAST_VOZ_LEO), con la indicación
    de un tono cálido, pausado y claro, como dos personas conversando. Suena mucho
    más humano que las voces del sistema.
  - "sistema": las voces del sistema operativo (ver exports/narracion.py), Ana con
    la femenina y Leo con la masculina. Es el respaldo si Gemini no está disponible
    (sin API key, sin cuota o sin red), o el motor fijo con PODCAST_VOCES=sistema.

En ambos casos se normaliza el volumen y ffmpeg entrega un MP3.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from nuevamente.config import settings
from nuevamente.exports.narracion import nombre_voz, preparar_texto, sintetizar
from nuevamente.exports.video import VideoError, _ejecutar, _ffmpeg
from nuevamente.llm import disponibilidad
from nuevamente.schemas.formatos import PodcastContenido

logger = logging.getLogger(__name__)

# Se incluye en la clave de caché de la API: al cambiar cómo se genera el audio,
# los podcasts ya guardados se regeneran.
VERSION = 3  # 3: voces naturales de Gemini TTS

VOZ_POR_LOCUTOR = {"Ana": "femenina", "Leo": "masculina"}
PAUSA_ENTRE_TURNOS_SEG = 0.45

# Gemini TTS devuelve PCM lineal de 16 bits, mono, a 24 kHz.
_PCM_HZ = 24000
# Caracteres de diálogo por petición: un episodio normal entra en una sola; uno muy
# largo se divide por turnos completos para no pasar el límite de audio por respuesta.
_MAX_CARACTERES_POR_PETICION = 4500

_INDICACION_GEMINI = (
    "Lee este episodio de podcast educativo en español latinoamericano neutro. Ana y "
    "Leo conversan de forma natural, como dos personas reales que se escuchan: tono "
    "cálido y cercano, ritmo pausado, pronunciación clara, pausas breves entre ideas "
    "y entre turnos. No leas los nombres de los locutores.\n\n"
)


# ---------- Motor "sistema" ----------

def voces_del_podcast() -> dict[str, str] | None:
    """Tipo de voz del sistema que usará cada locutor, o None si no hay ninguna instalada."""
    disponibles = [tipo for tipo in ("femenina", "masculina") if nombre_voz(tipo)]
    if not disponibles:
        return None
    return {
        locutor: tipo if tipo in disponibles else disponibles[0]
        for locutor, tipo in VOZ_POR_LOCUTOR.items()
    }


def _generar_con_sistema(podcast: PodcastContenido, carpeta: Path, ffmpeg: str) -> list[Path]:
    voces = voces_del_podcast()
    if voces is None:
        raise VideoError("No hay voces instaladas en el servidor para narrar el podcast.")
    turnos: list[Path] = []
    for i, intervencion in enumerate(podcast.intervenciones, start=1):
        audio = sintetizar(intervencion.texto, voces[intervencion.locutor], carpeta / f"{i:03d}")
        if audio is None:
            continue  # la voz falló en esta línea: se omite en vez de cortar el episodio
        # mismo formato en todos los turnos (para unirlos sin recodificar), mismo
        # volumen y una pausa al final de cada uno
        turno = carpeta / f"{i:03d}-turno.wav"
        _ejecutar([
            ffmpeg, "-y", "-i", str(audio),
            "-af", f"loudnorm=I=-16:TP=-1.5:LRA=11,apad=pad_dur={PAUSA_ENTRE_TURNOS_SEG}",
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(turno),
        ])
        turnos.append(turno)
    if not turnos:
        raise VideoError("No se pudo sintetizar ninguna intervención del podcast.")
    return turnos


# ---------- Motor "gemini" ----------

_SERVICIO_TTS = "tts:gemini"
# El audio de un bloque de diálogo tarda más que un texto: se le da el doble de tiempo.
_FACTOR_TIMEOUT_TTS = 2


def gemini_tts_configurado() -> bool:
    return settings.podcast_voces == "gemini" and bool(settings.gemini_api_key)


def _bloques_de_dialogo(podcast: PodcastContenido) -> list[str]:
    """El diálogo como "Ana: …\\nLeo: …", en bloques de turnos completos."""
    bloques: list[str] = []
    actual: list[str] = []
    largo = 0
    for intervencion in podcast.intervenciones:
        linea = f"{intervencion.locutor}: {preparar_texto(intervencion.texto)}"
        if actual and largo + len(linea) > _MAX_CARACTERES_POR_PETICION:
            bloques.append("\n".join(actual))
            actual, largo = [], 0
        actual.append(linea)
        largo += len(linea) + 1
    if actual:
        bloques.append("\n".join(actual))
    return bloques


def _sintetizar_gemini(dialogo: str) -> bytes:
    """PCM (s16le, mono, 24 kHz) del diálogo leído por Ana y Leo con Gemini TTS."""
    from google import genai
    from google.genai import types

    def voz(locutor: str, nombre: str):
        return types.SpeakerVoiceConfig(
            speaker=locutor,
            voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=nombre)),
        )

    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                speaker_voice_configs=[
                    voz("Ana", settings.podcast_voz_ana),
                    voz("Leo", settings.podcast_voz_leo),
                ]
            )
        ),
    )
    cliente = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(
            timeout=settings.llm_timeout_s * _FACTOR_TIMEOUT_TTS * 1000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )
    respuesta = cliente.models.generate_content(
        model=settings.podcast_tts_model, contents=_INDICACION_GEMINI + dialogo, config=config
    )
    partes = respuesta.candidates[0].content.parts if respuesta.candidates else []
    pcm = b"".join(p.inline_data.data for p in partes if p.inline_data and p.inline_data.data)
    if not pcm:
        raise VideoError("Gemini TTS no devolvió audio.")
    return pcm


def _generar_con_gemini(podcast: PodcastContenido, carpeta: Path, ffmpeg: str) -> list[Path]:
    turnos: list[Path] = []
    for k, dialogo in enumerate(_bloques_de_dialogo(podcast), start=1):
        crudo = carpeta / f"bloque-{k:02d}.pcm"
        crudo.write_bytes(_sintetizar_gemini(dialogo))
        bloque = carpeta / f"bloque-{k:02d}.wav"
        _ejecutar([
            ffmpeg, "-y", "-f", "s16le", "-ar", str(_PCM_HZ), "-ac", "1", "-i", str(crudo),
            "-af", f"loudnorm=I=-16:TP=-1.5:LRA=11,apad=pad_dur={PAUSA_ENTRE_TURNOS_SEG}",
            "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(bloque),
        ])
        turnos.append(bloque)
    return turnos


# ---------- Ensamblado ----------

def generar_podcast(podcast: PodcastContenido, destino: Path) -> str:
    """Narra la conversación completa en un MP3 en `destino`.

    Devuelve el motor que se usó: "gemini" o "sistema" (si Gemini no estaba
    configurado o falló, se usan las voces del sistema).
    """
    ffmpeg = _ffmpeg()
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="kairos-podcast-") as tmp:
        carpeta = Path(tmp)
        motor = "sistema"
        turnos: list[Path] = []
        # si Gemini TTS falló hace poco, se va directo a las voces del sistema sin esperarlo
        if gemini_tts_configurado() and not disponibilidad.en_pausa(_SERVICIO_TTS):
            try:
                turnos = _generar_con_gemini(podcast, carpeta, ffmpeg)
                motor = "gemini"
                disponibilidad.reanudar(_SERVICIO_TTS)
            except Exception as exc:  # cuota, red, modelo: el episodio sale igual, con otra voz
                logger.warning("Gemini TTS no disponible, se usan las voces del sistema: %s", exc)
                disponibilidad.pausar(_SERVICIO_TTS, str(exc))
                turnos = []
        if not turnos:
            turnos = _generar_con_sistema(podcast, carpeta, ffmpeg)

        lista = carpeta / "turnos.txt"
        lista.write_text("".join(f"file '{t.name}'\n" for t in turnos), encoding="utf-8")
        temporal = carpeta / "podcast.mp3"
        _ejecutar([
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
            "-c:a", "libmp3lame", "-b:a", "128k", "-id3v2_version", "3", str(temporal),
        ])
        shutil.move(str(temporal), destino)
    return motor
