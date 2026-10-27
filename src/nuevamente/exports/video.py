"""Video MP4 narrado a partir de un Guion de Clase.

Responsable en el equipo Kairos G10: Dario Higuera Moreno (No Code Developer).

Cada escena del guion se convierte en una diapositiva (Pillow) con su narración
en voz femenina o masculina (ver exports/narracion.py). El video contiene solo
datos del documento: una portada en silencio con su título y, en cada escena, la
sección de la que sale y su narración, sin saludos, transiciones ni despedidas
agregadas, y sin mostrar las indicaciones de apoyo visual. Si no hay voz disponible (o VIDEO_TTS=off), cada escena se
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

from nuevamente.config import settings
from nuevamente.exports.narracion import narrar, revisar_cancelacion
from nuevamente.schemas.formatos import GuionDeClaseContenido

# Se incluye en la clave de caché de la API: al cambiar cómo se genera el video,
# los videos ya guardados se regeneran.
VERSION = 9  # 9: sin el ruido de la cabecera y los metadatos del WAV de Gemini al cambiar de diapositiva

ANCHO, ALTO = 1280, 720          # resolución de dibujo (Pillow): se mantiene
ANCHO_SALIDA, ALTO_SALIDA = 960, 540   # resolución del MP4 final (la reduce ffmpeg)
MARGEN = 80
# Diapositivas fijas: 10 cuadros por segundo bastan para los fundidos y la codificación
# cuesta menos de la mitad que a 25 (importa en servidores con 0,1 CPU, como Render free).
FPS = 10
DURACION_PORTADA_SEG = 3  # portada en silencio, solo con el título del documento
PAUSA_FINAL_SEG = 0.9  # respiro tras la narración de cada diapositiva
FUNDIDO_SEG = 0.35

# CAMBIO 6: factor de escala global del texto que pasa por _texto_ajustado().
# 1.0 = como estaba antes; 0.85 = 15% más pequeño. Ajusta este número para
# agrandar o reducir títulos y cuerpo sin tocar cada lista de tamaños.
ESCALA_TEXTO = 0.85

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


# ---------- Diapositivas ----------

# CAMBIO 1: lru_cache de fuentes 32 -> 8.
@functools.lru_cache(maxsize=8)
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
    # CAMBIO 6: aplicar el factor de escala global a los tamaños candidatos.
    tamanos = [max(10, round(t * ESCALA_TEXTO)) for t in tamanos]

    # CAMBIO 2: variables inicializadas antes del bucle.
    fuente = _fuente(tamanos[-1], negrita)
    lineas = _envolver(dibujo, texto, fuente, ancho)
    interlineado = round(tamanos[-1] * 1.4)
    for tamano in tamanos:
        fuente = _fuente(tamano, negrita)
        lineas = _envolver(dibujo, texto, fuente, ancho)
        interlineado = round(tamano * 1.4)
        if len(lineas) * interlineado <= alto:
            return fuente, lineas, interlineado
    maximo = max(1, alto // interlineado)
    lineas = lineas[:maximo]
    lineas[-1] = lineas[-1].rstrip(".,;: ") + "…"
    return fuente, lineas, interlineado


def _portada(titulo: str, destino: Path) -> None:
    """Portada con el título del documento, sin textos agregados."""
    img = Image.new("RGB", (ANCHO, ALTO), FONDO)
    _degradado(img, (0, 0, ANCHO, ALTO), PRIMARIO, CORAL)
    dibujo = ImageDraw.Draw(img)
    fuente, lineas, inter = _texto_ajustado(dibujo, titulo, ANCHO - 2 * MARGEN, 360, (72, 64, 56, 48, 40), True)
    y = (ALTO - len(lineas) * inter) // 2
    for linea in lineas:
        dibujo.text((MARGEN, y), linea, font=fuente, fill=BLANCO)
        y += inter
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

    base = ALTO - 70
    dibujo.rounded_rectangle((MARGEN, base, ANCHO - MARGEN, base + 10), radius=5, fill=(240, 226, 211))
    avance = MARGEN + round((ANCHO - 2 * MARGEN) * indice / total)
    dibujo.rounded_rectangle((MARGEN, base, avance, base + 10), radius=5, fill=PRIMARIO)
    dibujo.text((MARGEN, base + 22), "Kairos", font=_fuente(22, True), fill=TEXTO_SUAVE)
    img.save(destino)


# ---------- Ensamblado ----------

# Audio de cada escena, sin ruido en el cambio de diapositiva:
#  - dynaudnorm: volumen parejo entre escenas (un tercio de la CPU de loudnorm). m=4 limita
#    cuánto sube las partes bajas: con el valor por defecto (10) el ruido de fondo de la
#    voz se volvía un siseo audible al empezar cada escena.
#  - silenceremove (al inicio, y con areverse al final): quita ese ruido antes y después de la voz.
#  - afade: entrada y salida de 60 ms, para que la voz no empiece ni termine con un golpe.
#  - adelay + apad: un instante de silencio antes de hablar y el respiro final.
_FILTRO_NARRACION = (
    "dynaudnorm=f=150:g=15:m=4,"
    "silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.05:detection=rms,"
    "areverse,"
    "silenceremove=start_periods=1:start_threshold=-40dB:start_silence=0.05:detection=rms,"
    "afade=t=in:d=0.06,"
    "areverse,"
    "afade=t=in:d=0.06,"
    "adelay=150:all=1,"
    "apad"
)


def _segmento(ffmpeg: str, imagen: Path, audio: Path | None, duracion_seg: float, destino: Path) -> None:
    """Una diapositiva con su narración (o silencio), con fundido de entrada y salida."""
    total = _duracion(ffmpeg, audio) + PAUSA_FINAL_SEG if audio is not None else float(duracion_seg)
    # scale + format + loop: la imagen se reduce a la resolución de salida y se pasa a YUV
    # una sola vez, y el filtro loop la repite (con "-loop 1" ffmpeg volvía a decodificar
    # y escalar el PNG en cada cuadro).
    filtro_video = (
        f"scale={ANCHO_SALIDA}:{ALTO_SALIDA},format=yuv420p,loop=-1:1:0,"
        f"fade=t=in:st=0:d={FUNDIDO_SEG},fade=t=out:st={max(0.0, total - FUNDIDO_SEG):.2f}:d={FUNDIDO_SEG}"
    )
    entrada_audio = ["-i", str(audio)] if audio is not None else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono"]
    filtro_audio = _FILTRO_NARRACION if audio is not None else "anull"
    _ejecutar([
        ffmpeg, "-y", "-framerate", str(FPS), "-i", str(imagen), *entrada_audio,
        "-vf", filtro_video, "-af", filtro_audio,
        # un hilo, preset ultrafast y lookahead mínimo: con diapositivas fijas la calidad
        # es la misma y la CPU por escena baja mucho (importa con 0,1 CPU, como Render free)
        "-c:v", "libx264", "-tune", "stillimage", "-preset", "ultrafast",
        "-threads", str(settings.video_hilos),
        "-x264-params", "rc-lookahead=2:sync-lookahead=0",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        # la narración es una sola voz: mono a 96 kbps suena igual y cuesta menos codificarla
        "-c:a", "aac", "-ar", "44100", "-ac", "1", "-b:a", "96k",
        "-t", f"{total:.2f}", str(destino),
    ])


def _titulo_escena(seccion: str, indice: int) -> str:
    """El título de la diapositiva es la sección del documento de la que sale la escena.
    No se usa `apoyo_visual`: son indicaciones para armar la diapositiva («Diagrama de…»),
    no contenido del documento."""
    titulo = (seccion or "").strip()
    if not titulo or titulo == "Documento completo":  # documento sin encabezados
        return f"Parte {indice}"
    return titulo


def generar_video(guion: GuionDeClaseContenido, titulo: str, destino: Path, voz: str = "femenina", cancelado=None) -> str:
    """Renderiza el guion completo a un MP4 en `destino` y devuelve el motor de voz que
    lo narró ("gemini" o "sistema").

    `voz` es "femenina" o "masculina"; si no hay ninguna voz de ese tipo disponible,
    el video sale sin narración. `cancelado` (opcional) se consulta entre escenas: si
    devuelve True, se lanza narracion.Cancelado y no queda ningún archivo.
    """
    ffmpeg = _ffmpeg()
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    total = len(guion.escenas)

    with tempfile.TemporaryDirectory(prefix="kairos-video-") as tmp:
        carpeta = Path(tmp)
        partes: list[tuple[str, object, str, float]] = []

        def agregar(nombre: str, dibujar, texto: str, duracion_seg: float) -> None:
            partes.append((nombre, dibujar, texto, duracion_seg))

        for i, escena in enumerate(guion.escenas, start=1):
            titulo_escena = _titulo_escena(escena.seccion, i)
            agregar(
                f"{i:03d}",
                lambda ruta, i=i, t=titulo_escena, n=escena.narracion: _diapositiva(i, total, t, n, ruta),
                escena.narracion,  # solo la narración del guion: nada de saludos ni transiciones
                escena.duracion_seg,
            )

        # Narrar TODO de una vez (respeta la cuota gratuita de Gemini), pero dibujar y
        # segmentar escena por escena.
        audios, motor = narrar([(texto, carpeta / nombre) for nombre, _, texto, _ in partes], voz, cancelado)

        # la portada solo muestra el título del documento, sin voz
        partes.insert(0, ("000", lambda ruta: _portada(titulo, ruta), "", DURACION_PORTADA_SEG))
        audios = [None, *audios]

        segmentos: list[Path] = []
        for (nombre, dibujar, _, duracion_seg), audio in zip(partes, audios):
            revisar_cancelacion(cancelado)
            imagen = carpeta / f"{nombre}.png"
            dibujar(imagen)
            segmento = carpeta / f"{nombre}.mp4"
            _segmento(ffmpeg, imagen, audio, duracion_seg, segmento)
            segmentos.append(segmento)
            del imagen

        lista = carpeta / "segmentos.txt"
        lista.write_text("".join(f"file '{s.name}'\n" for s in segmentos), encoding="utf-8")
        temporal = carpeta / "video.mp4"
        _ejecutar([
            ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(lista),
            "-c", "copy", "-movflags", "+faststart", str(temporal),
        ])
        shutil.move(str(temporal), destino)
    return motor


def convertir_a_m4a(texto: str, voz: str, destino: Path) -> str:
    """Narra `texto` con la voz pedida, lo guarda como M4A (reproducible en el navegador)
    y devuelve el motor que lo narró ("gemini" o "sistema")."""
    ffmpeg = _ffmpeg()
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="kairos-voz-") as tmp:
        (audio,), motor = narrar([(texto, Path(tmp) / "muestra")], voz)
        if audio is None:
            raise VideoError(f"No hay una voz {voz} disponible.")
        temporal = Path(tmp) / "muestra.m4a"
        _ejecutar([
            ffmpeg, "-y", "-i", str(audio), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "aac", "-ar", "44100", "-b:a", "160k", str(temporal),
        ])
        shutil.move(str(temporal), destino)
    return motor
