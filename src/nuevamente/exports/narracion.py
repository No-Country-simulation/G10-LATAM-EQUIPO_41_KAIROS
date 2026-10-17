"""Narración en voz alta para el video del Guion de Clase.

Responsable en el equipo Kairos G10: Dario Higuera Moreno (No Code Developer).

Tres motores de voz, en este orden:
  - "gemini" (por defecto): voces naturales de Gemini TTS (VIDEO_VOZ_FEMENINA y
    VIDEO_VOZ_MASCULINA). Cada fragmento es una petición; se piden varios a la vez.
  - "openai": voces naturales de OpenAI TTS (VIDEO_VOZ_OPENAI_FEMENINA y
    VIDEO_VOZ_OPENAI_MASCULINA), si hay OPENAI_API_KEY. Es el respaldo cuando Gemini está
    saturado o sin cuota, para no caer a una voz robótica; con VIDEO_VOCES=openai va primero.
  - "sistema": `say` en macOS o `espeak-ng` en Linux. Es el último respaldo, o el motor
    fijo con VIDEO_VOCES=sistema.
    Si un fragmento falla con un motor, TODA la narración se rehace con el siguiente: un
    video nunca mezcla dos voces.

Tres piezas:
  1. Elegir una voz del sistema según el tipo pedido (femenina o masculina):
     `say` en macOS, `espeak-ng` en Linux. Se prefieren voces de calidad
     "mejorada/premium" si están instaladas, y acento latinoamericano.
  2. Preparar el texto para leerlo en voz alta: el texto del guion sale de un
     documento (tablas, fechas ISO, siglas, abreviaturas), y una voz lo lee
     literalmente si no se adapta antes.
  3. Sintetizar con ritmo de clase: algo más pausado que el habitual y con
     silencios entre oraciones.
"""
from __future__ import annotations

import functools
import logging
import platform
import re
import shutil
import subprocess
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from nuevamente.config import settings

logger = logging.getLogger(__name__)

TIPOS_VOZ = ("femenina", "masculina")

# Nombres base de las voces de macOS por tipo, en orden de preferencia. Las voces
# clásicas (Paulina, Juan…) suenan más naturales que las "de personaje" (Flo, Eddy…).
_VOCES_MACOS = {
    "femenina": ["Paulina", "Mónica", "Marisol", "Angélica", "Francisca", "Isabela", "Soledad", "Flo", "Sandy", "Shelley"],
    "masculina": ["Juan", "Jorge", "Diego", "Carlos", "Eddy", "Reed", "Rocko"],
}
_ACENTOS = ["es_MX", "es_419", "es_US", "es_CO", "es_AR", "es_CL", "es_ES"]
_PAISES = {"es_MX": "México", "es_ES": "España", "es_AR": "Argentina", "es_CO": "Colombia", "es_CL": "Chile", "es_US": "EE. UU."}
_CALIDAD_ALTA = re.compile(r"premium|prémium|enhanced|mejorada", re.IGNORECASE)

# Ritmo de lectura (palabras por minuto) y pausas, pensados para una clase.
_VELOCIDAD_SAY = 160
_VELOCIDAD_ESPEAK = 145
_PAUSA_ORACION_MS = 380
_PAUSA_DOS_PUNTOS_MS = 220


# ---------- Voces disponibles ----------

@functools.lru_cache(maxsize=1)
def _voces_macos() -> tuple[tuple[str, str], ...]:
    """(nombre completo para `say -v`, locale) de cada voz en español instalada."""
    if platform.system() != "Darwin" or not shutil.which("say"):
        return ()
    try:
        salida = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ()
    voces = []
    for linea in salida.splitlines():
        m = re.match(r"^(.+?)\s+(es_[A-Z0-9]+)\s", linea)
        if m:
            voces.append((m.group(1).strip(), m.group(2)))
    return tuple(voces)


def _espeak() -> str | None:
    return shutil.which("espeak-ng") or shutil.which("espeak")


@functools.lru_cache(maxsize=4)
def _voz_macos(tipo: str) -> tuple[str, str] | None:
    preferidas = _VOCES_MACOS[tipo]
    candidatas = []
    for nombre, locale in _voces_macos():
        base = nombre.split(" (")[0]
        if base not in preferidas:
            continue
        acento = _ACENTOS.index(locale) if locale in _ACENTOS else len(_ACENTOS)
        calidad = 0 if _CALIDAD_ALTA.search(nombre) else 1
        candidatas.append(((calidad, preferidas.index(base), acento), nombre, locale))
    if not candidatas:
        return None
    _, nombre, locale = min(candidatas)
    return nombre, locale


def _voz_gemini(tipo: str) -> str:
    return settings.video_voz_femenina if tipo == "femenina" else settings.video_voz_masculina


def _voz_openai(tipo: str) -> str:
    return settings.video_voz_openai_femenina if tipo == "femenina" else settings.video_voz_openai_masculina


def gemini_configurado() -> bool:
    """Gemini TTS está elegido y hay API key (aunque ahora pueda estar en pausa)."""
    return settings.video_voces == "gemini" and bool(settings.gemini_api_key or settings.gemini_api_keys)


def openai_configurado() -> bool:
    """OpenAI TTS está permitido (VIDEO_VOCES gemini u openai) y hay API key."""
    return settings.video_voces in ("gemini", "openai") and bool(settings.openai_api_key)


def motores_disponibles() -> list[str]:
    """Motores de voz en orden de preferencia, sin los que fallaron hace poco. Siempre
    termina en "sistema", el respaldo que no depende de la red."""
    from nuevamente.llm import disponibilidad

    motores = []
    if gemini_configurado() and not disponibilidad.en_pausa(SERVICIO_TTS):
        motores.append("gemini")
    if openai_configurado() and not disponibilidad.en_pausa(SERVICIO_TTS_OPENAI):
        motores.append("openai")
    return [*motores, "sistema"]


def motor_voz() -> str:
    """Motor que se intentará usar ahora: el primero configurado que no falló hace poco."""
    return motores_disponibles()[0]


def nombre_voz(tipo: str, motor: str | None = None) -> str | None:
    """Nombre legible de la voz que se usará para `tipo`, o None si no hay ninguna."""
    if settings.video_tts == "off" or tipo not in TIPOS_VOZ:
        return None
    motor = motor or motor_voz()
    if motor == "gemini":
        return f"{_voz_gemini(tipo)} (voz natural)"
    if motor == "openai":
        return f"{_voz_openai(tipo).capitalize()} (voz natural de OpenAI)"
    if voz := _voz_macos(tipo):
        nombre, locale = voz
        base = nombre.split(" (")[0]
        pais = _PAISES.get(locale)
        return f"{base} ({pais})" if pais else base
    if _espeak():
        return f"eSpeak {tipo}"
    return None


# ---------- Texto para leer en voz alta ----------

_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

_REEMPLAZOS = [
    (r"\bp\.\s?ej\.", "por ejemplo"),
    (r"\betc\.", "etcétera"),
    (r"\baprox\.", "aproximadamente"),
    (r"\bmáx\.", "máximo"),
    (r"\bmín\.", "mínimo"),
    (r"\bDra\.", "doctora"),
    (r"\bDr\.", "doctor"),
    (r"\bSra\.", "señora"),
    (r"\bSr\.", "señor"),
    (r"\bvs\.?(?=\s)", "versus"),
    (r"\b[Nn][º°]\s?", "número "),
    (r"(\d)\s?%", r"\1 por ciento"),
    (r"(\d)\s?min\b\.?", r"\1 minutos"),
    (r"(\d)\s?seg\b\.?", r"\1 segundos"),
    (r"\s[&+]\s", " y "),
]

# Siglas que se leen como palabra; el resto de siglas cortas se deletrea (EPP → "E P P").
_SIGLAS_PALABRA = {"ONU", "OTAN", "OMS", "UNESCO", "UNICEF", "SIDA", "COVID", "ONE"}


def _fecha_en_palabras(m: re.Match) -> str:
    anio, mes, dia = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if 1 <= mes <= 12 and 1 <= dia <= 31:
        return f"{dia} de {_MESES[mes - 1]} de {anio}"
    return m.group(0)


def _deletrear(m: re.Match) -> str:
    sigla = m.group(0)
    return sigla if sigla in _SIGLAS_PALABRA else " ".join(sigla)


def _item_de_lista(m: re.Match) -> str:
    item = m.group(1)
    return item if item[-1:] in ".!?:;" else f"{item}."


def preparar_texto(texto: str) -> str:
    """Adapta un texto escrito para que una voz lo lea como lo diría una persona."""
    t = texto.replace("[[", " ").replace("]]", " ")  # nunca pasar comandos de `say` desde el documento
    t = re.sub(r"https?://\S+", "el enlace indicado", t)
    t = re.sub(r"\b(\d{4})-(\d{1,2})-\s?(\d{1,2})\b", _fecha_en_palabras, t)
    for patron, reemplazo in _REEMPLAZOS:
        t = re.sub(patron, reemplazo, t)
    # cada viñeta o ítem numerado se lee como una frase aparte
    t = re.sub(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+(.*?)\s*$", _item_de_lista, t)
    t = re.sub(r"[#*_`>|]", " ", t)  # restos de Markdown y de tablas
    t = re.sub(r"\s+[—–-]\s+|[—–]", ", ", t)  # guiones de inciso: pausa corta
    t = re.sub(r"[()\[\]{}]", ", ", t)  # los paréntesis se leen como un inciso
    t = re.sub(r"(?<=\w)/(?=\w)", " o ", t)
    if sum(c.islower() for c in t) > sum(c.isupper() for c in t):
        t = re.sub(r"\b[A-ZÁÉÍÓÚÑ]{2,4}\b", _deletrear, t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+([,.;:!?])", r"\1", t)
    t = re.sub(r"([,;:])(?:\s*[,;:])+", r"\1", t)  # comas repetidas por los reemplazos
    t = re.sub(r"(^|[.!?]\s*),\s*", r"\1", t)  # coma al inicio de oración
    t = t.strip(" ,;:")
    if t and t[-1] not in ".!?…":
        t += "."
    return t


def _con_pausas_say(texto: str) -> str:
    t = re.sub(r"(?<=[.!?…])\s+", f" [[slnc {_PAUSA_ORACION_MS}]] ", texto)
    return re.sub(r":\s+", f": [[slnc {_PAUSA_DOS_PUNTOS_MS}]] ", t)


# ---------- Síntesis con Gemini TTS ----------
#
# El plan gratuito de Gemini TTS admite muy pocas solicitudes por minuto, así que toda
# la narración de un video va en UNA solicitud: los fragmentos se leen seguidos, con un
# silencio largo entre uno y otro, y el audio se corta después en esos silencios. Cada
# corte se busca cerca de donde debería caer según el largo del texto, para no
# confundirlo con la pausa normal entre dos oraciones.

SERVICIO_TTS = "tts:gemini"  # el mismo que pausa el podcast: si falla uno, el otro no lo espera
SERVICIO_TTS_OPENAI = "tts:openai"
# Indicación de estilo para OpenAI TTS (gpt-4o-mini-tts la sigue): voz de docente, no de locutor.
_INDICACION_OPENAI = (
    "Habla en español latinoamericano neutro, como un docente cercano que explica una clase "
    "a sus estudiantes: voz humana y natural, tono cálido, ritmo pausado, entonación expresiva "
    "y pausas breves entre ideas. Nada de tono de locutor ni de lectura robótica."
)
_HILOS_OPENAI = 4  # fragmentos que se piden a la vez
_GEMINI_HZ = 24000  # Gemini TTS devuelve PCM lineal de 16 bits, mono, a 24 kHz
_MAX_CARACTERES_POR_PETICION = 4000  # más largo, se divide en bloques de fragmentos completos
_ESPERA_MAXIMA_SEG = 45  # si Gemini pide esperar (límite por minuto) hasta esto, se espera
_SILENCIO_MINIMO_SEG = 0.5
_INDICACION_GEMINI = (
    "Lee en español latinoamericano neutro, como un profesor que explica a su clase: "
    "tono cálido y cercano, ritmo pausado, pronunciación clara y pausas breves entre ideas. "
    "Lee solo el texto, sin agregar nada."
)


def _cliente_gemini():
    from google import genai
    from google.genai import types

    clave = next((c for c in (*settings.gemini_api_keys, settings.gemini_api_key) if c), "")
    return genai.Client(
        api_key=clave,
        http_options=types.HttpOptions(timeout=settings.llm_timeout_s * 3 * 1000, retry_options=types.HttpRetryOptions(attempts=1)),
    )


_agotados: dict[str, float] = {}  # modelo -> hasta cuándo (time.monotonic) no tiene cuota


def modelos_tts() -> list[str]:
    """Modelos TTS en orden de preferencia, sin los que se quedaron sin cuota hace poco."""
    ahora = time.monotonic()
    todos = list(dict.fromkeys((settings.podcast_tts_model, *settings.tts_modelos_respaldo)))
    return [m for m in todos if _agotados.get(m, 0) <= ahora] or todos


def _segundos_de_espera(mensaje: str) -> float | None:
    """La espera que pide Gemini en un 429 ("retry in 25.6s", "retry in 20h19m54s")."""
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", mensaje)
    if not m:
        return None
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3))


def generar_audio_tts(cliente, contenido, config, por_locutor=None) -> bytes:
    """PCM de Gemini TTS, rotando de modelo cuando uno se queda sin cuota (429) o no
    está disponible (404/503). Si Gemini pide esperar poco (límite por minuto), espera.

    `por_locutor` es el mismo diálogo con cada parte marcada con su locutor
    (`speech_metadata`): los modelos TTS más nuevos lo exigen para varias voces y lo
    piden con un 400; entonces se reintenta el mismo modelo con ese formato."""
    ultimo: Exception | None = None
    for modelo in modelos_tts():
        entrada = contenido
        for intento in range(3):
            try:
                respuesta = cliente.models.generate_content(model=modelo, contents=entrada, config=config)
                partes = respuesta.candidates[0].content.parts if respuesta.candidates else []
                pcm = b"".join(p.inline_data.data for p in partes if p.inline_data and p.inline_data.data)
                if not pcm:
                    raise RuntimeError(f"{modelo} no devolvió audio.")
                return pcm
            except Exception as exc:
                ultimo = exc
                if por_locutor is not None and entrada is contenido and "speech_metadata" in str(exc):
                    entrada = por_locutor  # el modelo quiere cada parte marcada con su locutor
                    continue
                espera = _segundos_de_espera(str(exc))
                if intento < 2 and espera is not None and espera <= _ESPERA_MAXIMA_SEG:
                    time.sleep(espera + 1)  # límite por minuto: se espera lo que pide
                    continue
                if espera is not None:  # cuota diaria: no se vuelve a probar hasta que se renueve
                    _agotados[modelo] = time.monotonic() + espera
                logger.warning("Gemini TTS %s no disponible, se prueba el siguiente modelo: %s", modelo, str(exc)[:200])
                break
    raise RuntimeError(f"Ningún modelo de Gemini TTS disponible: {ultimo}")


def _pcm_gemini(parrafos: list[str], tipo: str, cliente) -> bytes:
    """PCM de los párrafos leídos seguidos por la voz de Gemini, con silencios largos entre ellos."""
    from google.genai import types

    indicacion = _INDICACION_GEMINI
    if len(parrafos) > 1:
        indicacion += f" Son {len(parrafos)} párrafos: después de cada uno haz un silencio de dos segundos."
    config = types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=_voz_gemini(tipo)),
        )),
    )
    return generar_audio_tts(cliente, indicacion + "\n\n" + "\n\n".join(parrafos), config)


def _escribir_wav(pcm: bytes, destino: Path) -> Path:
    with wave.open(str(destino), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(_GEMINI_HZ)
        wav.writeframes(pcm)
    return destino


def _silencios(ffmpeg: str, audio: Path) -> list[tuple[float, float]]:
    """(inicio, fin) de cada silencio del audio, según `silencedetect` de ffmpeg."""
    salida = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(audio), "-af", f"silencedetect=noise=-38dB:d={_SILENCIO_MINIMO_SEG}", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    ).stderr
    inicios = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", salida)]
    fines = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", salida)]
    return list(zip(inicios, fines))


def cortes_por_silencio(silencios: list[tuple[float, float]], total: float, largos: list[int]) -> list[float]:
    """Dónde cortar un audio de `total` segundos en len(largos) fragmentos.

    Para cada frontera se calcula dónde debería caer según el largo del texto y se elige
    el silencio más largo cerca de ese punto. Lanza ValueError si no encuentra uno."""
    cortes: list[float] = []
    acumulado, suma = 0, sum(largos)
    previo = 0.0
    for largo in largos[:-1]:
        acumulado += largo
        esperado = total * acumulado / suma
        tolerancia = max(2.0, 0.4 * total / len(largos))
        candidatos = [
            (fin - ini, (ini + fin) / 2) for ini, fin in silencios
            if (ini + fin) / 2 > previo + 0.5 and abs((ini + fin) / 2 - esperado) <= tolerancia
        ]
        if not candidatos:
            raise ValueError("No se encontró la pausa entre dos fragmentos de la narración.")
        # el más largo, y entre parecidos el más cercano a lo esperado
        _, corte = max(candidatos, key=lambda c: c[0] - 0.1 * abs(c[1] - esperado) / tolerancia)
        cortes.append(corte)
        previo = corte
    return cortes


def _narrar_gemini(textos: list[tuple[str, Path]], tipo: str) -> list[Path]:
    """Narra todos los fragmentos con Gemini en el menor número de solicitudes posible."""
    from nuevamente.exports.video import _ejecutar, _ffmpeg

    ffmpeg = _ffmpeg()
    cliente = _cliente_gemini()
    preparados = [(preparar_texto(texto), Path(destino)) for texto, destino in textos]
    bloques: list[list[tuple[str, Path]]] = [[]]
    for par in preparados:
        if bloques[-1] and sum(len(t) for t, _ in bloques[-1]) + len(par[0]) > _MAX_CARACTERES_POR_PETICION:
            bloques.append([])
        bloques[-1].append(par)

    audios: list[Path] = []
    for k, bloque in enumerate(bloques):
        completo = _escribir_wav(_pcm_gemini([t for t, _ in bloque], tipo, cliente), bloque[0][1].with_name(f"narracion-{k}.wav"))
        if len(bloque) == 1:
            audios.append(completo)
            continue
        total = len(completo.read_bytes()) / (2 * _GEMINI_HZ)
        cortes = cortes_por_silencio(_silencios(ffmpeg, completo), total, [len(t) for t, _ in bloque])
        limites = [0.0, *cortes, total]
        for (_, destino), desde, hasta in zip(bloque, limites, limites[1:]):
            audio = destino.with_suffix(".wav")
            # cada fragmento sin el silencio largo de los bordes (silenceremove)
            _ejecutar([
                ffmpeg, "-y", "-loglevel", "error", "-i", str(completo), "-ss", f"{desde:.3f}", "-to", f"{hasta:.3f}",
                "-af", "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                       "silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                str(audio),
            ])
            audios.append(audio)
    return audios


def _audio_openai(texto: str, tipo: str, destino: Path) -> Path:
    """Un fragmento narrado con OpenAI TTS, guardado como WAV."""
    import httpx

    respuesta = httpx.post(
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json={
            "model": settings.openai_tts_model,
            "voice": _voz_openai(tipo),
            "input": texto,
            "instructions": _INDICACION_OPENAI,
            "response_format": "wav",
        },
        timeout=settings.llm_timeout_s * 3,
    )
    if respuesta.status_code != 200:
        raise RuntimeError(f"OpenAI TTS respondió {respuesta.status_code}: {respuesta.text[:200]}")
    audio = Path(destino).with_suffix(".wav")
    audio.write_bytes(respuesta.content)
    return audio


def _narrar_openai(textos: list[tuple[str, Path]], tipo: str) -> list[Path]:
    """Narra cada fragmento con OpenAI TTS (una petición por fragmento, varias a la vez)."""
    preparados = [(preparar_texto(texto), Path(destino)) for texto, destino in textos]
    with ThreadPoolExecutor(max_workers=_HILOS_OPENAI) as hilos:
        return list(hilos.map(lambda par: _audio_openai(par[0], tipo, par[1]), preparados))


_NARRADORES = {"gemini": ("_narrar_gemini", SERVICIO_TTS), "openai": ("_narrar_openai", SERVICIO_TTS_OPENAI)}


def narrar(textos: list[tuple[str, Path]], tipo: str) -> tuple[list[Path | None], str]:
    """Narra varios fragmentos (texto, destino sin extensión) con una sola voz.

    Devuelve los audios (None donde no hay voz) y el motor que de verdad se usó. Prueba
    los motores en orden (Gemini, OpenAI, sistema): si uno falla, se pausa ese servicio y
    TODA la narración se rehace con el siguiente, para que no se mezclen dos voces.
    """
    from nuevamente.llm import disponibilidad

    if settings.video_tts == "off" or not textos:
        return [None] * len(textos), "sistema"
    for motor in motores_disponibles()[:-1]:
        funcion, servicio = _NARRADORES[motor]
        try:
            audios = globals()[funcion](textos, tipo)
            disponibilidad.reanudar(servicio)
            return audios, motor
        except Exception as exc:  # cuota, red, modelo o pausas irreconocibles: sale igual, con otra voz
            logger.warning("%s TTS no disponible, se prueba la siguiente voz: %s", motor.capitalize(), exc)
            disponibilidad.pausar(servicio, str(exc))
    return [sintetizar(texto, tipo, destino) for texto, destino in textos], "sistema"


# ---------- Síntesis con las voces del sistema ----------

def sintetizar(texto: str, tipo: str, destino: Path) -> Path | None:
    """Genera el audio de `texto` con la voz del sistema (destino sin extensión); None si no hay voz."""
    if settings.video_tts == "off" or tipo not in TIPOS_VOZ:
        return None
    texto = preparar_texto(texto)
    if not texto:
        return None
    destino = Path(destino)
    guion_txt = destino.with_suffix(".txt")  # por archivo: el texto nunca pasa como argumento
    try:
        if voz := _voz_macos(tipo):
            guion_txt.write_text(_con_pausas_say(texto), encoding="utf-8")
            audio = destino.with_suffix(".aiff")
            subprocess.run(
                ["say", "-v", voz[0], "-r", str(_VELOCIDAD_SAY), "-f", str(guion_txt), "-o", str(audio)],
                check=True, capture_output=True, timeout=180,
            )
            return audio
        if espeak := _espeak():
            guion_txt.write_text(texto, encoding="utf-8")
            audio = destino.with_suffix(".wav")
            variante = "es+f3" if tipo == "femenina" else "es+m3"
            subprocess.run(
                [espeak, "-v", variante, "-s", str(_VELOCIDAD_ESPEAK), "-g", "4",
                 "-f", str(guion_txt), "-w", str(audio)],
                check=True, capture_output=True, timeout=180,
            )
            return audio
    except (OSError, subprocess.SubprocessError):
        pass  # sin voz: la escena queda en silencio
    return None
