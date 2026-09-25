"""Esquema de la respuesta de POST /api/v1/adaptar.

Responsable: Ethan Espinoza Acosta (Backend Developer).
La forma sigue el ejemplo exacto del enunciado del Hackathon (metadatos,
contenido_adaptado, evaluacion_calidad, almacenamiento_oci), con los campos
adicionales que el equipo decidió agregar (prerrequisitos, trazabilidad de
generación, y el detalle de afirmaciones no sustentadas para el nicho Salud).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from nuevamente.schemas.enums import ClaridadPedagogica
from nuevamente.schemas.formatos import ContenidoAdaptado


class Metadatos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    perfil_aplicado: str
    formato_generado: str
    tiempo_estimado_estudio_minutos: int
    conceptos_clave: list[str] = Field(default_factory=list)
    prerrequisitos: list[str] = Field(default_factory=list)
    tiempo_generacion_segundos: float = 0.0
    modelo_llm: str = ""
    desde_cache: bool = False


class EvaluacionCalidad(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anclaje_fuente_score: float = Field(ge=0.0, le=1.0)
    claridad_pedagogica: ClaridadPedagogica
    observaciones: str = ""
    afirmaciones_total: int = 0
    afirmaciones_sustentadas: int = 0
    afirmaciones_no_sustentadas: list[str] = Field(default_factory=list)
    umbral_aplicado: float = 0.0
    aprobado_por_critico: bool = True


class AlmacenamientoOCI(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket: str
    objeto_id: str
    objeto_documento_original: str = ""
    status_upload: str  # "completado" | "fallido_local"


class RespuestaAdaptacion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "exito"
    request_id: str
    metadatos: Metadatos
    contenido_adaptado: ContenidoAdaptado
    evaluacion_calidad: EvaluacionCalidad
    almacenamiento_oci: AlmacenamientoOCI


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "error"
    codigo: str
    mensaje_amigable: str
    detalle_tecnico: str = ""
