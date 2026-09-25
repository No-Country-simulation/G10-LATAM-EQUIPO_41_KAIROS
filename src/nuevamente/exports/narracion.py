"""Narración en voz alta para el video del Guion de Clase.

Responsable en el equipo Kairos G10: Dario Higuera Moreno (No Code Developer).

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
import platform
import re
import shutil
import subprocess
from pathlib import Path

from nuevamente.config import settings

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


def nombre_voz(tipo: str) -> str | None:
    """Nombre legible de la voz que se usará para `tipo`, o None si no hay ninguna."""
    if settings.video_tts == "off" or tipo not in TIPOS_VOZ:
        return None
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


# ---------- Síntesis ----------

def sintetizar(texto: str, tipo: str, destino: Path) -> Path | None:
    """Genera el audio de `texto` (destino sin extensión); None si no hay voz."""
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
