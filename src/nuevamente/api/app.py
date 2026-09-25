"""API REST de NuevaMente.

Responsable en el equipo Kairos G10: Ethan Espinoza Acosta (Backend Developer).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from nuevamente.agents.graph import generar_contenido_educativo
from nuevamente.config import settings
from nuevamente.exports.narracion import TIPOS_VOZ, nombre_voz
from nuevamente.ingest.readers import DocumentoInvalidoError, leer_documento
from nuevamente.llm.base import LLMError
from nuevamente.schemas.enums import FormatoSalida, NichoSector, NivelDetalle, PerfilDestinatario
from nuevamente.schemas.request import SolicitudAdaptacion
from nuevamente.schemas.response import AlmacenamientoOCI, ErrorResponse, RespuestaAdaptacion
from nuevamente.storage.oci_client import get_storage_service

app = FastAPI(
    title="Kairos API",
    description=(
        "Sistema Inteligente de Adaptación y Generación de Contenido Educativo — "
        "Hackathon ONE G10 (Kairos G10), nicho de foco: Salud."
    ),
    version="0.1.0",
)

# Front end web (HTML/CSS/JS sin build), servido por la misma API.
WEB_DIR = Path(__file__).resolve().parents[1] / "web"
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse(WEB_DIR / "index.html")


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
        "oci_disponible": storage.disponible_oci(),
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
        # nombre de la voz que narrará el video de cada tipo, o null si no hay ninguna instalada
        "voces": {tipo: nombre_voz(tipo) for tipo in TIPOS_VOZ},
    }


_MUESTRA_VOZ = "Hola. Así sonará la narración de tu clase: clara, pausada y en español."


@app.get("/api/v1/voces/{voz}/muestra")
def muestra_voz(voz: Literal["femenina", "masculina"]):
    """Audio corto (M4A) para escuchar la voz antes de generar el video."""
    from nuevamente.exports.video import VideoError, convertir_a_m4a

    nombre = nombre_voz(voz)
    if nombre is None:
        raise HTTPException(status_code=404, detail=f"No hay una voz {voz} instalada en el servidor")
    huella = hashlib.sha256(f"{voz}::{nombre}::{_MUESTRA_VOZ}".encode("utf-8")).hexdigest()[:16]
    destino = Path(settings.videos_dir) / f"muestra-{huella}.m4a"
    if not destino.is_file():
        try:
            convertir_a_m4a(_MUESTRA_VOZ, voz, destino)
        except VideoError as exc:
            raise HTTPException(status_code=500, detail=f"No se pudo generar la muestra: {exc}") from exc
    return FileResponse(destino, media_type="audio/mp4")


@app.post("/api/v1/adaptar", response_model=RespuestaAdaptacion)
def adaptar(solicitud: SolicitudAdaptacion):
    return _procesar_adaptacion(
        titulo=solicitud.documento_titulo,
        contenido=solicitud.documento_contenido,
        perfil=solicitud.perfil_destinatario.value,
        formato=solicitud.formato_salida.value,
        nicho=solicitud.nicho_sector.value,
        nivel_detalle=solicitud.nivel_detalle.value,
    )


@app.post("/api/v1/adaptar/archivo", response_model=RespuestaAdaptacion)
async def adaptar_archivo(
    archivo: UploadFile,
    perfil_destinatario: PerfilDestinatario = Form(...),
    formato_salida: FormatoSalida = Form(...),
    nicho_sector: NichoSector = Form(NichoSector.GENERAL),
    nivel_detalle: NivelDetalle = Form(NivelDetalle.DIDACTICO),
):
    contenido_bytes = await archivo.read()
    limite_bytes = settings.max_upload_mb * 1024 * 1024
    if len(contenido_bytes) > limite_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"El archivo supera el límite de {settings.max_upload_mb} MB permitido.",
        )

    import tempfile

    sufijo = Path(archivo.filename or "documento.txt").suffix or ".txt"
    with tempfile.NamedTemporaryFile(suffix=sufijo, delete=False) as tmp:
        tmp.write(contenido_bytes)
        tmp_path = tmp.name

    try:
        documento = leer_documento(tmp_path)
    except DocumentoInvalidoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return _procesar_adaptacion(
        titulo=documento.titulo,
        contenido=documento.contenido,
        perfil=perfil_destinatario.value,
        formato=formato_salida.value,
        nicho=nicho_sector.value,
        nivel_detalle=nivel_detalle.value,
    )


def _procesar_adaptacion(
    *, titulo: str, contenido: str, perfil: str, formato: str, nicho: str, nivel_detalle: str
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
        )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"Fallo del generador de contenido: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    storage = get_storage_service()

    slug_formato = formato.lower().replace(" ", "-")
    slug_perfil = perfil.lower().replace("/", "-").replace(" ", "-")
    objeto_id = f"contenidos/{resultado.coleccion.doc_id}/{slug_formato}-{slug_perfil}-{request_id[:8]}.json"
    objeto_original_id = f"originals/{resultado.coleccion.doc_id}.txt"

    respuesta = RespuestaAdaptacion(
        request_id=request_id,
        metadatos=resultado.metadatos,
        contenido_adaptado=resultado.contenido,
        evaluacion_calidad=resultado.evaluacion,
        almacenamiento_oci=AlmacenamientoOCI(bucket="", objeto_id="", status_upload="pendiente"),
    )

    storage.subir_texto(objeto_original_id, contenido, content_type="text/plain")
    subida = storage.subir_json(objeto_id, respuesta.model_dump(mode="json"))

    respuesta.almacenamiento_oci = AlmacenamientoOCI(
        bucket=subida.bucket,
        objeto_id=subida.objeto_id,
        objeto_documento_original=objeto_original_id,
        status_upload=subida.status_upload,
    )
    return respuesta


@app.get("/api/v1/contenidos/{objeto_id:path}/exportar")
def exportar_contenido(objeto_id: str, formato: str = "markdown", titulo: str = ""):
    from fastapi.responses import PlainTextResponse, Response

    from nuevamente.exports import exportar_anki_csv, exportar_markdown
    from nuevamente.schemas.response import RespuestaAdaptacion

    storage = get_storage_service()
    crudo = storage.descargar_texto(objeto_id)
    if crudo is None:
        raise HTTPException(status_code=404, detail="Contenido no encontrado")

    try:
        respuesta = RespuestaAdaptacion.model_validate_json(crudo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="El objeto no es un contenido adaptado exportable") from exc

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

    raise HTTPException(status_code=400, detail="formato debe ser 'markdown', 'anki_csv' o 'pptx'")


@app.get("/api/v1/contenidos/{objeto_id:path}/video")
def video_contenido(
    objeto_id: str,
    titulo: str = "Guion de clase",
    voz: Literal["femenina", "masculina"] = "femenina",
):
    """MP4 narrado de un Guion de Clase guardado. Se genera la primera vez y queda en caché."""
    from nuevamente.exports.video import VERSION, VideoError, generar_video

    storage = get_storage_service()
    crudo = storage.descargar_texto(objeto_id)
    if crudo is None:
        raise HTTPException(status_code=404, detail="Contenido no encontrado")
    try:
        respuesta = RespuestaAdaptacion.model_validate_json(crudo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="El objeto no es un contenido adaptado") from exc
    if respuesta.contenido_adaptado.formato != "Guion de Clase":
        raise HTTPException(status_code=422, detail="Solo se puede generar video a partir de un Guion de Clase")

    titulo = titulo.strip()[:200] or "Guion de clase"
    clave = f"v{VERSION}::{objeto_id}::{titulo}::{voz}::{nombre_voz(voz)}"
    huella = hashlib.sha256(clave.encode("utf-8")).hexdigest()[:16]
    destino = Path(settings.videos_dir) / f"{huella}.mp4"
    if not destino.is_file():
        try:
            generar_video(respuesta.contenido_adaptado, titulo, destino, voz=voz)
        except VideoError as exc:
            raise HTTPException(status_code=500, detail=f"No se pudo generar el video: {exc}") from exc
    return FileResponse(destino, media_type="video/mp4", filename="guion_de_clase.mp4", content_disposition_type="inline")


@app.get("/api/v1/contenidos/{objeto_id:path}")
def obtener_contenido(objeto_id: str):
    storage = get_storage_service()
    contenido = storage.descargar_texto(objeto_id)
    if contenido is None:
        raise HTTPException(status_code=404, detail="Contenido no encontrado")
    try:
        return json.loads(contenido)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="El objeto no es un contenido JSON") from exc
