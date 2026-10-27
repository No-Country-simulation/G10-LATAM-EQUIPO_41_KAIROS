"""API REST de NuevaMente.

Responsable en el equipo Kairos G10: Ethan Espinoza Acosta (Backend Developer).
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import re
import shutil
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from nuevamente import VERSION_VISIBLE, __version__, estadisticas
from nuevamente.agents.graph import generar_contenido_educativo
from nuevamente.cache.contenido import version_prompts_formatos
from nuevamente.config import settings
from nuevamente.exports.narracion import TIPOS_VOZ, motor_voz, nombre_voz
from nuevamente.ingest.readers import EXTENSIONES_SOPORTADAS, DocumentoInvalidoError, leer_documento
from nuevamente.llm.base import LLMError
from nuevamente.schemas.enums import FormatoSalida, NichoSector, NivelDetalle, PerfilDestinatario
from nuevamente.schemas.request import SolicitudAdaptacion, SolicitudCalificacion
from nuevamente.schemas.response import AlmacenamientoOCI, ErrorResponse, RegistroAdaptacion, RespuestaAdaptacion
from nuevamente.storage.oci_client import get_storage_service

app = FastAPI(
    title="Kairos API",
    description=(
        "Sistema Inteligente de Adaptación y Generación de Contenido Educativo — "
        "Hackathon ONE G10 (Kairos G10), nicho de foco: Salud."
    ),
    version=__version__,
)

# Front end web (HTML/CSS/JS sin build), servido por la misma API.
WEB_DIR = Path(__file__).resolve().parents[1] / "web"
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.middleware("http")
async def sin_cache_para_la_web(request: Request, call_next):
    """La página y sus archivos se revalidan siempre (ETag), para que el navegador no
    siga usando un app.js viejo después de actualizar el código."""
    respuesta = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        respuesta.headers["Cache-Control"] = "no-cache"
    return respuesta


def _con_version(html: str, archivo: str) -> str:
    """/static/app.js -> /static/app.js?v=<huella del contenido>: si el archivo cambia,
    cambia la URL y ningún navegador puede seguir usando una copia vieja."""
    huella = hashlib.sha256((WEB_DIR / archivo).read_bytes()).hexdigest()[:10]
    return html.replace(f'"/static/{archivo}"', f'"/static/{archivo}?v={huella}"')


def _pagina(nombre: str, scripts: tuple[str, ...]) -> HTMLResponse:
    html = (WEB_DIR / nombre).read_text(encoding="utf-8").replace("{{version}}", VERSION_VISIBLE)
    for archivo in (*scripts, "styles.css"):
        html = _con_version(html, archivo)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/", include_in_schema=False)
def inicio():
    return _pagina("index.html", ("app.js",))


@app.get("/estadisticas", include_in_schema=False)
def pagina_estadisticas():
    return _pagina("estadisticas.html", ("estadisticas.js",))


def _error_payload(codigo: str, mensaje: str, detalle: str = "") -> dict:
    return ErrorResponse(codigo=codigo, mensaje_amigable=mensaje, detalle_tecnico=detalle).model_dump()


@app.exception_handler(RequestValidationError)
async def manejador_validacion(request: Request, exc: RequestValidationError):
    """Errores 422 amigables en vez de la traza cruda de Pydantic."""
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            codigo="VALIDACION_ENTRADA",
            mensaje="Algunos campos de la solicitud no son válidos. Revisa perfil, formato y nicho.",
            detalle=str(exc.errors()),
        ),
    )


@app.get("/health")
def health():
    storage = get_storage_service()
    return {
        "status": "ok",
        "version": __version__,
        "oci_disponible": storage.disponible_oci(),
        # por qué se guarda en el respaldo local ("" si OCI funciona)
        "oci_motivo": storage.motivo_oci(),
    }


@app.get("/api/v1/opciones")
def opciones():
    """Valores válidos de cada campo, para que el front no los duplique."""
    return {
        "perfiles": [p.value for p in PerfilDestinatario],
        "formatos": [f.value for f in FormatoSalida],
        "nichos": [n.value for n in NichoSector],
        "niveles": [n.value for n in NivelDetalle],
        "umbral_por_nicho": {n.value: settings.fidelity_min_for(n.value) for n in NichoSector},
        "max_upload_mb": settings.max_upload_mb,
        "extensiones": sorted(EXTENSIONES_SOPORTADAS),
        "version": VERSION_VISIBLE,
        # Qué API va a generar y, con LLM_PROVIDER=auto, el orden de rotación. Solo lectura:
        # el proveedor se cambia en el .env, no por petición.
        "llm": {
            "proveedor": settings.llm_provider,
            "cadena": list(settings.llm_cadena),
            "con_credenciales": [
                nombre
                for nombre, clave in (
                    ("gemini", settings.gemini_api_key),
                    ("groq", settings.groq_api_key),
                    ("cerebras", settings.cerebras_api_key),
                    ("openrouter", settings.openrouter_api_key),
                    ("cohere", settings.cohere_api_key),
                    ("openai", settings.openai_api_key),
                )
                if clave
            ],
            "carrera": settings.carrera_activada,
        },
        # nombre de la voz que narrará el video de cada tipo, o null si no hay ninguna instalada
        "voces": {tipo: nombre_voz(tipo) for tipo in TIPOS_VOZ},
    }


@app.get("/api/v1/salud-llm")
def salud_llm():
    """Cómo se han portado los proveedores en este proceso: estado del circuito, latencia
    media observada y cuándo se vuelve a probar al que está caído.

    El router de salud (llm/salud.py) vive en la cadena que se construye por petición, así
    que el estado se guarda en un módulo aparte, de nivel de proceso, para que estas
    métricas sirvan de verdad y no salgan siempre a cero."""
    from nuevamente.llm.salud import registrar_y_ver

    return registrar_y_ver()


@app.get("/api/v1/cache-contenido/stats")
def cache_contenido_stats():
    """Estadísticas del caché de contenido aprobado (post-Crítico)."""
    from nuevamente.agents.graph import _cache_contenido

    s = _cache_contenido.stats()
    return {
        "enabled": settings.cache_contenido_activado,
        "scoped": settings.cache_contenido_scoped,
        "scope_actual": ["Resumen Ejecutivo", "Salud"] if settings.cache_contenido_scoped else "global",
        "max_entries": s.max_entries,
        "ttl_s": s.ttl_s,
        "entries": s.entries,
        "hits_total": s.hits_total,
        "misses_total": s.misses_total,
        "hit_rate": s.hit_rate,
        "entries_expirados_limpieza": s.entries_expirados_limpieza,
        "version_prompts_formatos": version_prompts_formatos(),
    }


_MUESTRA_VOZ = "Hola. Así sonará la narración de tu clase: clara, pausada y en español."


@app.get("/api/v1/voces/{voz}/muestra")
def muestra_voz(voz: Literal["femenina", "masculina"]):
    """Audio corto (M4A) para escuchar la voz antes de generar el video."""
    from nuevamente.exports.video import VideoError, convertir_a_m4a

    if nombre_voz(voz) is None:
        raise HTTPException(status_code=404, detail=f"No hay una voz {voz} instalada en el servidor")

    def archivo(motor: str) -> Path:  # el nombre de la voz incluye el motor
        huella = hashlib.sha256(f"{voz}::{nombre_voz(voz, motor)}::{_MUESTRA_VOZ}".encode("utf-8")).hexdigest()[:16]
        return Path(settings.videos_dir) / f"muestra-{huella}.m4a"

    preferido = motor_voz()
    if not archivo(preferido).is_file():
        with tempfile.TemporaryDirectory(prefix="kairos-voz-") as tmp:
            temporal = Path(tmp) / "muestra.m4a"
            try:
                preferido = convertir_a_m4a(_MUESTRA_VOZ, voz, temporal)
            except VideoError as exc:
                raise HTTPException(status_code=500, detail=f"No se pudo generar la muestra: {exc}") from exc
            archivo(preferido).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(temporal), archivo(preferido))
    return FileResponse(archivo(preferido), media_type="audio/mp4")


@app.post("/api/v1/adaptar", response_model=RespuestaAdaptacion)
def adaptar(solicitud: SolicitudAdaptacion):
    return _procesar_adaptacion(
        titulo=solicitud.documento_titulo,
        contenido=solicitud.documento_contenido,
        perfil=solicitud.perfil_destinatario.value,
        formato=solicitud.formato_salida.value,
        nicho=solicitud.nicho_sector.value,
        nivel_detalle=solicitud.nivel_detalle.value,
        idioma=solicitud.idioma_salida,
    )


@app.post("/api/v1/adaptar/archivo", response_model=RespuestaAdaptacion)
async def adaptar_archivo(
    archivo: UploadFile,
    perfil_destinatario: PerfilDestinatario = Form(...),
    formato_salida: FormatoSalida = Form(...),
    nicho_sector: NichoSector = Form(NichoSector.GENERAL),
    nivel_detalle: NivelDetalle = Form(NivelDetalle.DIDACTICO),
    idioma_salida: str = Form("es", min_length=2, max_length=5),
):
    contenido_bytes = await archivo.read()
    limite_bytes = settings.max_upload_mb * 1024 * 1024
    if len(contenido_bytes) > limite_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"El archivo supera el límite de {settings.max_upload_mb} MB permitido.",
        )

    sufijo = Path(archivo.filename or "documento.txt").suffix or ".txt"
    with tempfile.NamedTemporaryFile(suffix=sufijo, delete=False) as tmp:
        tmp.write(contenido_bytes)
        tmp_path = tmp.name

    try:
        documento = leer_documento(tmp_path)
    except DocumentoInvalidoError as exc:
        # el lector nombra el archivo temporal (tmpXXXX.pdf): el usuario reconoce el suyo
        mensaje = str(exc).replace(Path(tmp_path).name, archivo.filename or "el archivo")
        raise HTTPException(status_code=400, detail=mensaje) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    # el lector ve el archivo temporal (tmpXXXX.pdf): el título sale del nombre que subió el usuario
    titulo = Path(archivo.filename or "").stem.strip() or "Documento sin título"
    return _procesar_adaptacion(
        titulo=titulo,
        contenido=documento.contenido,
        perfil=perfil_destinatario.value,
        formato=formato_salida.value,
        nicho=nicho_sector.value,
        nivel_detalle=nivel_detalle.value,
        origen=sufijo.lstrip(".").lower() or "txt",
        documento_nombre=Path(archivo.filename or "").name,
        idioma=idioma_salida,
        archivo_original=(contenido_bytes, archivo.content_type or "application/octet-stream"),
    )


def _nombre_seguro(nombre: str) -> str:
    """Nombre de archivo apto para un objeto: sin rutas ni caracteres raros."""
    nombre = re.sub(r"[^\w.\- ]", "_", Path(nombre or "documento").name).strip() or "documento"
    return nombre[:150]


def _procesar_adaptacion(
    *, titulo: str, contenido: str, perfil: str, formato: str, nicho: str, nivel_detalle: str,
    origen: str = "texto", documento_nombre: str = "", idioma: str = "es",
    archivo_original: tuple[bytes, str] | None = None,
) -> RespuestaAdaptacion:
    request_id = str(uuid.uuid4())
    try:
        resultado = generar_contenido_educativo(
            documento_titulo=titulo,
            documento_contenido=contenido,
            perfil=perfil,
            formato=formato,
            nicho=nicho,
            nivel_detalle=nivel_detalle,
            idioma=idioma,
        )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"Fallo del generador de contenido: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    storage = get_storage_service()

    slug_formato = formato.lower().replace(" ", "-")
    slug_perfil = perfil.lower().replace("/", "-").replace(" ", "-")
    objeto_id = f"contenidos/{resultado.coleccion.doc_id}/{slug_formato}-{slug_perfil}.json"
    objeto_original_id = f"originals/{resultado.coleccion.doc_id}.txt"

    # El registro completo (con fuentes, secciones y el detalle de fidelidad) es lo que se
    # guarda; la API devuelve su forma pública. Se guarda ya con el destino previsto, y si
    # la subida a OCI falla se vuelve a escribir con el estado real (el respaldo local).
    almacenamiento = AlmacenamientoOCI(
        bucket=settings.oci_bucket,
        objeto_id=objeto_id,
        objeto_documento_original=objeto_original_id,
        documento_nombre=documento_nombre or titulo,
        tipo_origen=origen,
        objeto_archivo_original=(
            f"originals/{resultado.coleccion.doc_id}/{_nombre_seguro(documento_nombre)}" if archivo_original else ""
        ),
        status_upload="completado" if storage.disponible_oci() else "fallido_local",
    )
    registro = RegistroAdaptacion(
        request_id=request_id,
        metadatos=resultado.metadatos,
        contenido_adaptado=resultado.contenido,
        evaluacion_calidad=resultado.evaluacion,
        almacenamiento_oci=almacenamiento,
    )

    storage.subir_texto(objeto_original_id, contenido, content_type="text/plain")
    if archivo_original:  # HU-55: además del texto extraído, el archivo que subió el usuario
        storage.subir_bytes(almacenamiento.objeto_archivo_original, archivo_original[0], archivo_original[1])
    subida = storage.subir_json(objeto_id, registro.model_dump(mode="json"))
    if subida.status_upload != almacenamiento.status_upload:
        registro.almacenamiento_oci = almacenamiento.model_copy(update={"status_upload": subida.status_upload})
        storage.subir_json(objeto_id, registro.model_dump(mode="json"))
    estadisticas.registrar(
        "generacion",
        objeto_id=objeto_id,
        formato=formato,
        perfil=perfil,
        nicho=nicho,
        nivel_detalle=nivel_detalle,
        origen=origen,
        fidelidad=resultado.evaluacion.anclaje_fuente_score,
        aprobado=resultado.evaluacion.aprobado_por_critico,
        tiempo_generacion_s=round(resultado.metadatos.tiempo_generacion_segundos, 2),
        tiempo_estudio_min=resultado.metadatos.tiempo_estimado_estudio_minutos,
        modo_local="respaldo" in resultado.metadatos.modelo_llm,
    )
    return registro.a_publica()


@app.post("/api/v1/calificaciones", status_code=201)
def calificar(solicitud: SolicitudCalificacion):
    """Calificación del usuario (1 a 5 estrellas y comentario opcional) sobre un material
    guardado. Si vuelve a calificar el mismo material, cuenta la última."""
    registro, _ = _leer_registro(solicitud.objeto_id)
    if registro is None:
        raise HTTPException(status_code=422, detail="El objeto no es un contenido adaptado")
    estadisticas.registrar(
        "calificacion",
        objeto_id=solicitud.objeto_id,
        estrellas=solicitud.estrellas,
        comentario=solicitud.comentario.strip(),
        formato=registro.contenido_adaptado.formato,
        perfil=registro.metadatos.perfil_aplicado,
    )
    return {"status": "ok"}


@app.get("/api/v1/estadisticas")
def ver_estadisticas():
    """Datos de uso a nivel de usuario final: materiales creados, formatos, perfiles y
    sectores elegidos, descargas, calificaciones y comentarios. Los muestra /estadisticas.
    Antes de resumir suma los materiales del historial que aún no estén contados."""
    estadisticas.importar_historial()
    return estadisticas.resumen()


@app.get("/api/v1/contenidos/{objeto_id:path}/exportar")
def exportar_contenido(objeto_id: str, formato: str = "markdown", titulo: str = ""):
    from fastapi.responses import PlainTextResponse, Response

    from nuevamente.exports import exportar_anki_csv, exportar_markdown
    storage = get_storage_service()
    crudo = storage.descargar_texto(objeto_id)
    if crudo is None:
        raise HTTPException(status_code=404, detail="Contenido no encontrado")

    try:
        respuesta = RegistroAdaptacion.model_validate_json(crudo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="El objeto no es un contenido adaptado exportable") from exc
    if respuesta.contenido_adaptado.formato == "Podcast":
        raise HTTPException(
            status_code=422,
            detail="El podcast solo está disponible en audio: usa /api/v1/contenidos/{objeto_id}/podcast",
        )

    if formato in ("markdown", "anki_csv", "pptx", "docx", "pdf"):
        estadisticas.registrar("descarga", objeto_id=objeto_id, formato=formato)
    if formato == "markdown":
        texto = exportar_markdown(respuesta.contenido_adaptado)
        return PlainTextResponse(texto, media_type="text/markdown")
    if formato == "anki_csv":
        texto = exportar_anki_csv(respuesta.contenido_adaptado)
        return PlainTextResponse(texto, media_type="text/csv")
    if formato == "pptx":
        from nuevamente.exports.presentacion import generar_presentacion

        titulo = titulo.strip()[:200] or "Material de estudio"
        datos = generar_presentacion(
            respuesta.contenido_adaptado,
            titulo,
            perfil=respuesta.metadatos.perfil_aplicado,
            score_fidelidad=respuesta.evaluacion_calidad.anclaje_fuente_score,
        )
        return Response(
            datos,
            media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            headers={"Content-Disposition": 'attachment; filename="presentacion.pptx"'},
        )

    if formato == "docx":
        from nuevamente.exports.documento import generar_documento

        datos = generar_documento(
            respuesta.contenido_adaptado,
            titulo.strip()[:200] or "Material de estudio",
            perfil=respuesta.metadatos.perfil_aplicado,
            score_fidelidad=respuesta.evaluacion_calidad.anclaje_fuente_score,
        )
        return Response(
            datos,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": 'attachment; filename="material.docx"'},
        )

    if formato == "pdf":
        from nuevamente.exports.pdf import generar_pdf

        datos = generar_pdf(
            respuesta.contenido_adaptado,
            titulo.strip()[:200] or "Material de estudio",
            perfil=respuesta.metadatos.perfil_aplicado,
            score_fidelidad=respuesta.evaluacion_calidad.anclaje_fuente_score,
        )
        return Response(
            datos, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="material.pdf"'}
        )

    raise HTTPException(status_code=400, detail="formato debe ser 'markdown', 'anki_csv', 'pptx', 'docx' o 'pdf'")


# ---------- Video y podcast: archivos pesados ----------
# Generarlos tarda minutos y usa mucha memoria (ffmpeg + voces). Para que un servidor
# pequeño (Render gratis: 512 MB) no se caiga ni corte la conexión (error 502):
#   - se genera uno a la vez por proceso;
#   - con ?asincrono=1 la solicitud responde 202 "generando" al instante y el archivo se
#     produce en segundo plano; la interfaz vuelve a pedirlo hasta recibirlo.
_un_archivo_a_la_vez = threading.Lock()
_trabajos: dict[str, dict] = {}
_candado_trabajos = threading.Lock()


def _fabricar(generar, destino_de, prefijo: str, extension: str, cancelado=None) -> str:
    """Genera el archivo en un temporal y lo mueve a su destino según el motor que lo narró.
    Si se cancela, la carpeta temporal se borra y no queda ningún archivo."""
    from nuevamente.exports.narracion import revisar_cancelacion

    with _un_archivo_a_la_vez, tempfile.TemporaryDirectory(prefix=prefijo) as tmp:
        revisar_cancelacion(cancelado)  # pudo cancelarse mientras esperaba su turno
        temporal = Path(tmp) / f"archivo{extension}"  # ffmpeg elige el formato por la extensión
        motor = generar(temporal, cancelado)
        revisar_cancelacion(cancelado)  # cancelado al final: no se guarda en la caché
        # se guarda con el motor que de verdad lo narró: si Gemini falló, la próxima vez
        # se vuelve a intentar con la voz natural
        destino_de(motor).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temporal), destino_de(motor))
    return motor


def _producir(clave: str, generar, destino_de, *, asincrono: bool, que: str, prefijo: str, extension: str):
    """Devuelve el motor con que quedó el archivo, o una respuesta 202 si sigue en curso.
    La respuesta 202 trae el identificador del trabajo, para poder cancelarlo."""
    from nuevamente.exports.narracion import Cancelado
    from nuevamente.exports.video import VideoError

    if not asincrono:
        try:
            return _fabricar(generar, destino_de, prefijo, extension)
        except VideoError as exc:
            raise HTTPException(status_code=500, detail=f"No se pudo generar el {que}: {exc}") from exc

    with _candado_trabajos:
        trabajo = _trabajos.get(clave)
        if trabajo and trabajo["estado"] == "listo":
            _trabajos.pop(clave)
            return trabajo["motor"]
        if trabajo and trabajo["estado"] == "error":
            _trabajos.pop(clave)  # la próxima solicitud lo vuelve a intentar
            raise HTTPException(status_code=500, detail=trabajo["detalle"])
        if trabajo is None:
            senal = threading.Event()
            _trabajos[clave] = {"estado": "generando", "cancelar": senal}

            def tarea():
                try:
                    resultado = {"estado": "listo", "motor": _fabricar(generar, destino_de, prefijo, extension, senal.is_set)}
                except Cancelado:
                    resultado = None  # cancelado: se olvida, y la próxima solicitud empieza de cero
                except Exception as exc:  # ffmpeg, voces, disco: el error llega a la interfaz
                    resultado = {"estado": "error", "detalle": f"No se pudo generar el {que}: {exc}"}
                with _candado_trabajos:
                    if resultado is None:
                        _trabajos.pop(clave, None)
                    else:
                        _trabajos[clave] = resultado

            threading.Thread(target=tarea, name=f"kairos-{clave[:24]}", daemon=True).start()
    return JSONResponse(
        status_code=202, content={"estado": "generando", "mensaje": f"Generando el {que}…", "trabajo": clave},
    )


@app.delete("/api/v1/trabajos/{trabajo:path}")
def cancelar_trabajo(trabajo: str):
    """Cancela un video o podcast que se está generando en segundo plano («Cancelar video»).
    La generación se detiene en la siguiente escena y no queda ningún archivo. Si ya
    terminó, el archivo se conserva."""
    with _candado_trabajos:
        actual = _trabajos.get(trabajo)
        if actual is None:
            raise HTTPException(status_code=404, detail="No hay ninguna generación en curso con ese identificador")
        if actual["estado"] != "generando":
            return {"estado": actual["estado"], "mensaje": "La generación ya había terminado."}
        actual["cancelar"].set()
        actual["estado"] = "cancelando"
    que = trabajo.split("::", 1)[0]
    estadisticas.registrar("cancelacion", formato=que)
    return {"estado": "cancelando", "mensaje": "Generación cancelada."}


@app.get("/api/v1/contenidos/{objeto_id:path}/video")
def video_contenido(
    objeto_id: str,
    titulo: str = "Guion de clase",
    voz: Literal["femenina", "masculina"] = "femenina",
    asincrono: bool = False,
):
    """MP4 narrado de un Guion de Clase guardado. Se genera la primera vez y queda en caché.
    Con asincrono=1 responde 202 mientras se genera (ver _producir)."""
    from nuevamente.exports.video import VERSION, generar_video

    storage = get_storage_service()
    crudo = storage.descargar_texto(objeto_id)
    if crudo is None:
        raise HTTPException(status_code=404, detail="Contenido no encontrado")
    try:
        respuesta = RegistroAdaptacion.model_validate_json(crudo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="El objeto no es un contenido adaptado") from exc
    if respuesta.contenido_adaptado.formato != "Guion de Clase":
        raise HTTPException(status_code=422, detail="Solo se puede generar video a partir de un Guion de Clase")

    titulo = titulo.strip()[:200] or "Guion de clase"

    def archivo(motor: str) -> Path:
        clave = f"v{VERSION}::{objeto_id}::{titulo}::{voz}::{motor}::{nombre_voz(voz, motor)}"
        return Path(settings.videos_dir) / f"{hashlib.sha256(clave.encode('utf-8')).hexdigest()[:16]}.mp4"

    def entregar(motor: str):
        estadisticas.registrar("descarga", objeto_id=objeto_id, formato="video")
        return FileResponse(
            archivo(motor), media_type="video/mp4", filename="guion_de_clase.mp4",
            content_disposition_type="inline", headers={"X-Video-Voces": motor},
        )

    preferido = motor_voz()
    if archivo(preferido).is_file():
        return entregar(preferido)
    motor = _producir(
        f"video::{archivo(preferido).name}",
        lambda temporal, cancelado: generar_video(respuesta.contenido_adaptado, titulo, temporal, voz=voz, cancelado=cancelado),
        archivo, asincrono=asincrono, que="video", prefijo="kairos-video-", extension=".mp4",
    )
    return motor if isinstance(motor, JSONResponse) else entregar(motor)


@app.get("/api/v1/contenidos/{objeto_id:path}/podcast")
def podcast_contenido(objeto_id: str, asincrono: bool = False):
    """MP3 de un Podcast guardado, con Ana y Leo en voces distintas. Queda en caché.

    La cabecera X-Podcast-Voces indica con qué se narró: "gemini" (voces naturales)
    o "sistema" (voces del sistema operativo, el respaldo).
    """
    from nuevamente.exports.podcast import (
        VERSION,
        gemini_tts_configurado,
        generar_podcast,
        voces_del_podcast,
    )

    storage = get_storage_service()
    crudo = storage.descargar_texto(objeto_id)
    if crudo is None:
        raise HTTPException(status_code=404, detail="Contenido no encontrado")
    try:
        respuesta = RegistroAdaptacion.model_validate_json(crudo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="El objeto no es un contenido adaptado") from exc
    if respuesta.contenido_adaptado.formato != "Podcast":
        raise HTTPException(status_code=422, detail="Solo se puede generar audio a partir de un Podcast")

    def archivo(motor: str) -> Path:
        if motor == "gemini":
            voces = f"{settings.podcast_tts_model}:{settings.podcast_voz_ana}:{settings.podcast_voz_leo}"
        else:
            voces = ":".join(f"{t}={nombre_voz(t, 'sistema')}" for t in ("femenina", "masculina"))
        huella = hashlib.sha256(f"v{VERSION}::{objeto_id}::{motor}::{voces}".encode("utf-8")).hexdigest()[:16]
        return Path(settings.videos_dir) / f"podcast-{motor}-{huella}.mp3"

    def entregar(motor: str):
        estadisticas.registrar("descarga", objeto_id=objeto_id, formato="podcast")
        return FileResponse(
            archivo(motor), media_type="audio/mpeg", filename="podcast.mp3",
            content_disposition_type="inline", headers={"X-Podcast-Voces": motor},
        )

    preferido = "gemini" if gemini_tts_configurado() else "sistema"
    if archivo(preferido).is_file():
        return entregar(preferido)
    if preferido == "sistema" and voces_del_podcast() is None:
        raise HTTPException(status_code=503, detail="No hay voces instaladas en el servidor para narrar el podcast.")

    motor = _producir(
        f"podcast::{archivo(preferido).name}",
        lambda temporal, cancelado: generar_podcast(respuesta.contenido_adaptado, temporal),
        archivo, asincrono=asincrono, que="podcast", prefijo="kairos-podcast-", extension=".mp3",
    )
    return motor if isinstance(motor, JSONResponse) else entregar(motor)


def _leer_registro(objeto_id: str) -> tuple[RegistroAdaptacion | None, str]:
    """El registro guardado y su texto crudo. Validar el registro limpia los textos de un
    material guardado antes (ver schemas/formatos.py); a los guardados antes de registrar
    su destino se les completa el almacenamiento."""
    storage = get_storage_service()
    crudo = storage.descargar_texto(objeto_id)
    if crudo is None:
        raise HTTPException(status_code=404, detail="Contenido no encontrado")
    try:
        registro = RegistroAdaptacion.model_validate_json(crudo)
    except ValueError:
        return None, crudo
    if not registro.almacenamiento_oci.objeto_id:
        registro.almacenamiento_oci = AlmacenamientoOCI(
            bucket=settings.oci_bucket,
            objeto_id=objeto_id,
            status_upload="completado" if storage.disponible_oci() else "fallido_local",
        )
    if not registro.almacenamiento_oci.tipo_origen:
        # guardado antes de registrar el tipo de documento: lo dicen las estadísticas de uso
        tipo = estadisticas.origen_de(objeto_id)
        if not tipo and registro.almacenamiento_oci.objeto_archivo_original:
            tipo = Path(registro.almacenamiento_oci.objeto_archivo_original).suffix.lstrip(".").lower()
        if tipo:
            registro.almacenamiento_oci = registro.almacenamiento_oci.model_copy(update={"tipo_origen": tipo})
    if not registro.almacenamiento_oci.objeto_documento_original:
        # guardado antes de registrar el original: está en originals/<doc_id>.txt
        partes = objeto_id.split("/")
        original = f"originals/{partes[1]}.txt" if len(partes) >= 3 and partes[0] == "contenidos" else ""
        if original and storage.descargar_texto(original) is not None:
            registro.almacenamiento_oci = registro.almacenamiento_oci.model_copy(
                update={"objeto_documento_original": original}
            )
    return registro, crudo


@app.get("/api/v1/contenidos/{objeto_id:path}/original")
def descargar_original(objeto_id: str):
    """El documento original de un material: el archivo tal como se subió (PDF, Word…)
    o, si se pegó texto, el texto."""
    from fastapi.responses import Response

    registro, _ = _leer_registro(objeto_id)
    if registro is None:
        raise HTTPException(status_code=422, detail="El objeto no es un contenido adaptado")
    al = registro.almacenamiento_oci
    storage = get_storage_service()
    for objeto, tipo in ((al.objeto_archivo_original, None), (al.objeto_documento_original, "text/plain; charset=utf-8")):
        datos = storage.descargar_bytes(objeto) if objeto else None
        if datos is not None:
            nombre = Path(objeto).name if tipo is None else f"{Path(al.documento_nombre or 'documento').stem}.txt"
            media = tipo or mimetypes.guess_type(nombre)[0] or "application/octet-stream"
            return Response(datos, media_type=media, headers={"Content-Disposition": _adjunto(nombre)})
    raise HTTPException(status_code=404, detail="El documento original de este material no está guardado")


def _adjunto(nombre: str) -> str:
    from urllib.parse import quote

    return f"attachment; filename=\"documento\"; filename*=UTF-8''{quote(nombre)}"


@app.get("/api/v1/contenidos/{objeto_id:path}/detalle", include_in_schema=False)
def obtener_detalle(objeto_id: str):
    """Registro completo (fuentes, secciones, detalle de fidelidad), para la interfaz web."""
    registro, _ = _leer_registro(objeto_id)
    if registro is None:
        raise HTTPException(status_code=422, detail="El objeto no es un contenido adaptado")
    return registro.model_dump(mode="json")


@app.get("/api/v1/contenidos/{objeto_id:path}", response_model=None)
def obtener_contenido(objeto_id: str):
    """El contenido guardado, con la misma forma pública que devuelve /api/v1/adaptar."""
    registro, crudo = _leer_registro(objeto_id)
    if registro is not None:
        return registro.a_publica().model_dump(mode="json")
    try:
        return json.loads(crudo)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="El objeto no es un contenido JSON") from exc
