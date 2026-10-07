"""Esquemas de la respuesta de POST /api/v1/adaptar.

Responsable: Ethan Espinoza Acosta (Backend Developer).

- `RespuestaAdaptacion` es lo que devuelve la API: exactamente la forma del ejemplo del
  enunciado del Hackathon (status, metadatos, contenido_adaptado, evaluacion_calidad,
  almacenamiento_oci), sin campos adicionales.
- `RegistroAdaptacion` es lo que se guarda en OCI: la misma respuesta más lo que el equipo
  necesita internamente (request_id, fuentes y secciones de cada parte, modelo usado y el
  detalle de la verificación de fidelidad). Lo leen la interfaz web
  (GET /api/v1/contenidos/{objeto_id}/detalle) y las exportaciones.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from nuevamente.schemas.enums import ClaridadPedagogica
from nuevamente.schemas.formatos import ContenidoAdaptado, ContenidoPublico, contenido_publico


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
    tiempos_por_agente: dict[str, float] = Field(default_factory=dict)


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


class RegistroAdaptacion(BaseModel):
    """Registro completo de una adaptación (lo que se guarda en OCI)."""

    model_config = ConfigDict(extra="forbid")

    status: str = "exito"
    request_id: str
    metadatos: Metadatos
    contenido_adaptado: ContenidoAdaptado
    evaluacion_calidad: EvaluacionCalidad
    almacenamiento_oci: AlmacenamientoOCI

    def a_publica(self) -> "RespuestaAdaptacion":
        return RespuestaAdaptacion(
            status=self.status,
            metadatos=MetadatosPublicos(
                perfil_aplicado=self.metadatos.perfil_aplicado,
                formato_generado=self.metadatos.formato_generado,
                tiempo_estimado_estudio_minutos=self.metadatos.tiempo_estimado_estudio_minutos,
                conceptos_clave=self.metadatos.conceptos_clave,
            ),
            contenido_adaptado=contenido_publico(self.contenido_adaptado),
            evaluacion_calidad=EvaluacionPublica(
                anclaje_fuente_score=self.evaluacion_calidad.anclaje_fuente_score,
                claridad_pedagogica=self.evaluacion_calidad.claridad_pedagogica,
                observaciones=self.evaluacion_calidad.observaciones,
            ),
            almacenamiento_oci=AlmacenamientoPublico(
                bucket=self.almacenamiento_oci.bucket,
                objeto_id=self.almacenamiento_oci.objeto_id,
                status_upload=self.almacenamiento_oci.status_upload,
            ),
        )


# --- Respuesta pública: la forma exacta del ejemplo del enunciado ---


class MetadatosPublicos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    perfil_aplicado: str
    formato_generado: str
    tiempo_estimado_estudio_minutos: int
    conceptos_clave: list[str] = Field(default_factory=list)


class EvaluacionPublica(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anclaje_fuente_score: float = Field(ge=0.0, le=1.0)
    claridad_pedagogica: ClaridadPedagogica
    observaciones: str = ""


class AlmacenamientoPublico(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket: str
    objeto_id: str
    status_upload: str  # "completado" | "fallido_local"


class RespuestaAdaptacion(BaseModel):
    """Respuesta de la API, con la forma exacta del ejemplo del enunciado."""

    model_config = ConfigDict(extra="forbid")

    status: str = "exito"
    metadatos: MetadatosPublicos
    contenido_adaptado: ContenidoPublico
    evaluacion_calidad: EvaluacionPublica
    almacenamiento_oci: AlmacenamientoPublico


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "error"
    codigo: str
    mensaje_amigable: str
    detalle_tecnico: str = ""
