"""API REST de NuevaMente.

Responsable en el equipo Kairos G10: Ethan Espinoza Acosta (Backend Developer).
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.requests import Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from nuevamente.agents.graph import generar_contenido_educativo
from nuevamente.config import settings
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
    }


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
def exportar_contenido(objeto_id: str, formato: str = "markdown"):
    from fastapi.responses import PlainTextResponse

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

    raise HTTPException(status_code=400, detail="formato debe ser 'markdown' o 'anki_csv'")


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
