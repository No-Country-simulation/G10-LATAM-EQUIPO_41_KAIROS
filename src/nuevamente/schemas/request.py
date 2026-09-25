"""Esquema de la solicitud de adaptación de contenido.

Responsable: Ethan Espinoza Acosta (Backend Developer).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from nuevamente.schemas.enums import (
    FormatoSalida,
    NichoSector,
    NivelDetalle,
    PerfilDestinatario,
)


class SolicitudAdaptacion(BaseModel):
    """Cuerpo de POST /api/v1/adaptar — corresponde 1:1 al ejemplo del enunciado."""

    model_config = ConfigDict(extra="forbid")

    documento_titulo: str = Field(min_length=3, max_length=300)
    documento_contenido: str = Field(
        min_length=20,
        max_length=200_000,
        description="Texto completo del documento fuente (ya extraído de PDF/MD/TXT).",
    )
    perfil_destinatario: PerfilDestinatario
    formato_salida: FormatoSalida
    nicho_sector: NichoSector = NichoSector.GENERAL
    nivel_detalle: NivelDetalle = NivelDetalle.DIDACTICO
    idioma_salida: str = Field(default="es", min_length=2, max_length=5)
