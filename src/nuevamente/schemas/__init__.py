"""Esquemas Pydantic de NuevaMente (responsable: Ethan Espinoza Acosta)."""
from nuevamente.schemas.enums import (
    ClaridadPedagogica,
    FormatoSalida,
    NichoSector,
    NivelDetalle,
    PerfilDestinatario,
    VeredictoFidelidad,
)
from nuevamente.schemas.formatos import (
    ContenidoAdaptado,
    FlashcardItem,
    FlashcardsContenido,
    GuionDeClaseContenido,
    GuionEscena,
    PodcastContenido,
    PodcastIntervencion,
    QuizContenido,
    QuizPregunta,
    ResumenEjecutivoContenido,
    TutorialContenido,
    TutorialPaso,
)
from nuevamente.schemas.request import SolicitudAdaptacion
from nuevamente.schemas.response import (
    AlmacenamientoOCI,
    ErrorResponse,
    EvaluacionCalidad,
    Metadatos,
    RespuestaAdaptacion,
)

__all__ = [
    "PerfilDestinatario",
    "FormatoSalida",
    "NichoSector",
    "NivelDetalle",
    "ClaridadPedagogica",
    "VeredictoFidelidad",
    "SolicitudAdaptacion",
    "ContenidoAdaptado",
    "FlashcardsContenido",
    "FlashcardItem",
    "QuizContenido",
    "QuizPregunta",
    "TutorialContenido",
    "TutorialPaso",
    "ResumenEjecutivoContenido",
    "GuionDeClaseContenido",
    "GuionEscena",
    "PodcastContenido",
    "PodcastIntervencion",
    "RespuestaAdaptacion",
    "Metadatos",
    "EvaluacionCalidad",
    "AlmacenamientoOCI",
    "ErrorResponse",
]
