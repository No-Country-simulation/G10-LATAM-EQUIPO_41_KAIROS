"""Video MP4 narrado a partir de un Guion de Clase.

Responsable en el equipo Kairos G10: Dario Higuera Moreno (No Code Developer).

Cada escena del guion se convierte en una diapositiva (Pillow) con su narración
en voz femenina o masculina (ver exports/narracion.py). La clase abre con un
saludo, enlaza las escenas con transiciones y cierra con una despedida, como lo
haría un docente. Si no hay voz disponible (o VIDEO_TTS=off), cada escena se
muestra en silencio durante su `duracion_seg`. ffmpeg une todo en un MP4
H.264/AAC con volumen normalizado y fundidos suaves entre diapositivas: se usa
el ffmpeg del sistema y, si no hay, el que trae el paquete `imageio-ffmpeg`.
"""
from __future__ import annotations

import functools
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from nuevamente.exports.narracion import sintetizar
from nuevamente.schemas.formatos import GuionDeClaseContenido

# Se incluye en la clave de caché de la API: al cambiar cómo se genera el video,
# los videos ya guardados se regeneran.
VERSION = 2

ANCHO, ALTO = 1280, 720
MARGEN = 80
FPS = 25
DURACION_PORTADA_SEG = 4
DURACION_CIERRE_SEG = 3
PAUSA_FINAL_SEG = 0.9  # respiro tras la narración de cada diapositiva
FUNDIDO_SEG = 0.35

# Paleta de la interfaz web (ver web/styles.css).
FONDO = (255, 248, 241)
TEXTO = (45, 36, 64)
TEXTO_SUAVE = (110, 100, 128)
PRIMARIO = (108, 78, 245)
CORAL = (255, 122, 89)
BLANCO = (255, 255, 255)

_FUENTES_NEGRITA = [
    "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
]
_FUENTES_NORMAL = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
]

class VideoError(Exception):
    """No se pudo generar el video (ffmpeg ausente o falló)."""


# ---------- Herramientas externas ----------

def _ffmpeg() -> str:
    ruta = shutil.which("ffmpeg")
    if ruta:
        return ruta
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # paquete ausente o binario no disponible para la plataforma
        raise VideoError("No se encontró ffmpeg. Instálalo o instala el paquete imageio-ffmpeg.") from exc


def _ejecutar(comando: list[str]) -> None:
    try:
        subprocess.run(comando, check=True, capture_output=True, timeout=180)
    except subprocess.CalledProcessError as exc:
        detalle = exc.stderr.decode("utf-8", errors="replace")[-600:]
        raise VideoError(f"ffmpeg falló: {detalle}") from exc
    except subprocess.TimeoutExpired as exc:
        raise VideoError("ffmpeg tardó demasiado en generar el video.") from exc


def _duracion(ffmpeg: str, archivo: Path) -> float:
    """Duración en segundos de un audio, leída de la salida de `ffmpeg -i`."""
    salida = subprocess.run([ffmpeg, "-i", str(archivo)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", salida)
    if not m:
        raise VideoError(f"No se pudo leer la duración de {archivo.name}")
    horas, minutos, segundos = m.groups()
    return int(horas) * 3600 + int(minutos) * 60 + float(segundos)


# ---------- Guion hablado ----------

_TRANSICIONES = [
    "Sigamos.",
    "Ahora veamos lo siguiente.",
    "Continuemos.",
    "Pasemos al siguiente punto.",
]


def _texto_hablado(indice: int, total: int, narracion: str) -> str:
    """Narración de la escena con la transición que diría un docente."""
    if indice == 1:
        return narracion
    if indice == total:
        return f"Y para terminar. {narracion}"
    return f"{_TRANSICIONES[(indice - 2) % len(_TRANSICIONES)]} {narracion}"


# ---------- Diapositivas ----------

@functools.lru_cache(maxsize=32)
def _fuente(tamano: int, negrita: bool = False) -> ImageFont.FreeTypeFont:
    for ruta in _FUENTES_NEGRITA if negrita else _FUENTES_NORMAL:
        if Path(ruta).exists():
            return ImageFont.truetype(ruta, tamano)
    return ImageFont.load_default(size=tamano)


def _degradado(img: Image.Image, caja: tuple[int, int, int, int], desde, hasta) -> None:
    x0, y0, x1, y1 = caja
    dibujo = ImageDraw.Draw(img)
    for x in range(x0, x1):
        t = (x - x0) / max(1, x1 - x0 - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(desde, hasta))
        dibujo.line([(x, y0), (x, y1)], fill=color)


def _envolver(dibujo: ImageDraw.ImageDraw, texto: str, fuente, ancho_max: int) -> list[str]:
    lineas: list[str] = []
    actual = ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}".strip()
        if dibujo.textlength(prueba, font=fuente) <= ancho_max:
            actual = prueba
        else:
            if actual:
                lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    return lineas


def _texto_ajustado(dibujo, texto: str, ancho: int, alto: int, tamanos, negrita=False):
    """Elige el mayor tamaño de letra con el que el texto cabe en la caja."""
    for tamano in tamanos:
        fuente = _fuente(tamano, negrita)
        lineas = _envolver(dibujo, texto, fuente, ancho)
        interlineado = round(tamano * 1.4)
        if len(lineas) * interlineado <= alto:
            return fuente, lineas, interlineado
    # ni con la letra más chica cabe: se recorta con puntos suspensivos
    maximo = max(1, alto // interlineado)
    lineas = lineas[:maximo]
    lineas[-1] = lineas[-1].rstrip(".,;: ") + "…"
    return fuente, lineas, interlineado


def _portada(titulo: str, total_escenas: int, minutos: int, destino: Path) -> None:
    img = Image.new("RGB", (ANCHO, ALTO), FONDO)
    _degradado(img, (0, 0, ANCHO, ALTO), PRIMARIO, CORAL)
    dibujo = ImageDraw.Draw(img)
    dibujo.text((MARGEN, 110), "GUION DE CLASE", font=_fuente(30, True), fill=BLANCO)
    fuente, lineas, inter = _texto_ajustado(dibujo, titulo, ANCHO - 2 * MARGEN, 300, (72, 64, 56, 48, 40), True)
    y = 170
    for linea in lineas:
        dibujo.text((MARGEN, y), linea, font=fuente, fill=BLANCO)
        y += inter
    dibujo.text(
        (MARGEN, y + 24),
        f"{total_escenas} escenas · aprox. {minutos} min",
        font=_fuente(32),
        fill=BLANCO,
    )
    dibujo.text((MARGEN, ALTO - 90), "Kairos", font=_fuente(34, True), fill=BLANCO)
    img.save(destino)


def _cierre(total_escenas: int, destino: Path) -> None:
    img = Image.new("RGB", (ANCHO, ALTO), FONDO)
    _degradado(img, (0, 0, ANCHO, ALTO), PRIMARIO, CORAL)
    dibujo = ImageDraw.Draw(img)
    dibujo.text((MARGEN, 230), "¡Gracias!", font=_fuente(96, True), fill=BLANCO)
    dibujo.text((MARGEN, 360), f"Repasaste {total_escenas} escenas de esta clase.", font=_fuente(34), fill=BLANCO)
    dibujo.text((MARGEN, ALTO - 90), "Kairos", font=_fuente(34, True), fill=BLANCO)
    img.save(destino)


def _diapositiva(indice: int, total: int, titulo: str, narracion: str, destino: Path) -> None:
    img = Image.new("RGB", (ANCHO, ALTO), FONDO)
    _degradado(img, (0, 0, ANCHO, 130), PRIMARIO, CORAL)
    dibujo = ImageDraw.Draw(img)

    dibujo.text((MARGEN, 26), f"ESCENA {indice} DE {total}", font=_fuente(22, True), fill=BLANCO)
    fuente_titulo, lineas_titulo, _ = _texto_ajustado(dibujo, titulo, ANCHO - 2 * MARGEN, 50, (40, 34, 28), True)
    dibujo.text((MARGEN, 60), lineas_titulo[0], font=fuente_titulo, fill=BLANCO)

    fuente, lineas, inter = _texto_ajustado(
        dibujo, narracion, ANCHO - 2 * MARGEN, ALTO - 130 - 150, (40, 36, 32, 28, 24)
    )
    y = 175
    for linea in lineas:
        dibujo.text((MARGEN, y), linea, font=fuente, fill=TEXTO)
        y += inter

    # barra de avance y pie
    base = ALTO - 70
    dibujo.rounded_rectangle((MARGEN, base, ANCHO - MARGEN, base + 10), radius=5, fill=(240, 226, 211))
    avance = MARGEN + round((ANCHO - 2 * MARGEN) * indice / total)
    dibujo.rounded_rectangle((MARGEN, base, avance, base + 10), radius=5, fill=PRIMARIO)
    dibujo.text((MARGEN, base + 22), "Kairos", font=_fuente(22, True), fill=TEXTO_SUAVE)
    img.save(destino)


# ---------- Ensamblado ----------

def _segmento(ffmpeg: str, imagen: Path, audio: Path | None, duracion_seg: float, destino: Path) -> None:
    """Una diapositiva con su narración (o silencio), con fundido de entrada y salida."""
    total = _duracion(ffmpeg, audio) + PAUSA_FINAL_SEG if audio is not None else float(duracion_seg)
    fundidos = f"fade=t=in:st=0:d={FUNDIDO_SEG},fade=t=out:st={max(0.0, total - FUNDIDO_SEG):.2f}:d={FUNDIDO_SEG}"
    entrada_audio = ["-i", str(audio)] if audio is not None else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    # loudnorm: todas las escenas al mismo volumen; apad: el silencio del respiro final
    filtro_audio = "loudnorm=I=-16:TP=-1.5:LRA=11,apad" if audio is not None else "anull"
    _ejecutar([
        ffmpeg, "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(imagen), *entrada_audio,
        "-vf", fundidos, "-af", filtro_audio,
        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "160k",
        "-t", f"{total:.2f}", str(destino),
    ])


def _titulo_escena(apoyo_visual: str, indice: int) -> str:
    titulo = re.sub(r"^\s*diapositiva\s*:\s*", "", apoyo_visual, flags=re.IGNORECASE).strip()
    if not titulo or titulo == "Documento completo":  # documento sin encabezados
        return f"Parte {indice}"
    return titulo


def generar_video(guion: GuionDeClaseContenido, titulo: str, destino: Path, voz: str = "femenina") -> Path:
    """Renderiza el guion completo a un MP4 en `destino` y devuelve su ruta.

    `voz` es "femenina" o "masculina"; si no hay una voz de ese tipo instalada,
    el video sale sin narración.
    """
    ffmpeg = _ffmpeg()
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    total = len(guion.escenas)

    with tempfile.TemporaryDirectory(prefix="kairos-video-") as tmp:
        carpeta = Path(tmp)
        segmentos: list[Path] = []

        def agregar(nombre: str, dibujar, texto: str, duracion_seg: float) -> None:
            imagen = carpeta / f"{nombre}.png"
            dibujar(imagen)
            audio = sintetizar(texto, voz, carpeta / nombre)
            segmentos.append(carpeta / f"{nombre}.mp4")
            _segmento(ffmpeg, imagen, audio, duracion_seg, segmentos[-1])

        agregar(
            "000",
            lambda ruta: _portada(titulo, total, guion.duracion_total_min, ruta),
            f"Hola, te doy la bienvenida. En esta clase vamos a repasar: {titulo}. ¡Comencemos!",
            DURACION_PORTADA_SEG,
        )
        for i, escena in enumerate(guion.escenas, start=1):
            titulo_escena = _titulo_escena(escena.apoyo_visual, i)
            agregar(
                f"{i:03d}",
                lambda ruta, i=i, t=titulo_escena, n=escena.narracion: _diapositiva(i, total, t, n, ruta),
                _texto_hablado(i, total, escena.narracion),
                escena.duracion_seg,
            )
        agregar(
            "999",
            lambda ruta: _cierre(total, ruta),
            "Eso es todo por esta clase. Gracias por tu atención, y nos vemos en la próxima.",
            DURACION_CIERRE_SEG,
        )

        lista = carpeta / "segmentos.txt"
        lista.write_text("".join(f"file '{s.name}'\n" for s in segmentos), encoding="utf-8")
        temporal = carpeta / "video.mp4"
        _ejecutar([
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
            "-c", "copy", "-movflags", "+faststart", str(temporal),
        ])
        shutil.move(str(temporal), destino)
    return destino


def convertir_a_m4a(texto: str, voz: str, destino: Path) -> Path:
    """Narra `texto` con la voz pedida y lo guarda como M4A (reproducible en el navegador)."""
    ffmpeg = _ffmpeg()
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kairos-voz-") as tmp:
        audio = sintetizar(texto, voz, Path(tmp) / "muestra")
        if audio is None:
            raise VideoError(f"No hay una voz {voz} disponible.")
        temporal = Path(tmp) / "muestra.m4a"
        _ejecutar([
            ffmpeg, "-y", "-i", str(audio), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "aac", "-ar", "44100", "-b:a", "160k", str(temporal),
        ])
        shutil.move(str(temporal), destino)
    return destino
