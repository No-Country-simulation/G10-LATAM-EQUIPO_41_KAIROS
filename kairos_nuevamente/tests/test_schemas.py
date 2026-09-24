"""Tests de validación de esquemas. Responsable: Diana Dure (QA Tester)."""
import pytest
from pydantic import ValidationError

from nuevamente.schemas import (
    FormatoSalida,
    NichoSector,
    PerfilDestinatario,
    SolicitudAdaptacion,
)


def test_solicitud_valida_pasa():
    s = SolicitudAdaptacion(
        documento_titulo="Protocolo de bioseguridad",
        documento_contenido="Contenido suficientemente largo para pasar la validación mínima.",
        perfil_destinatario=PerfilDestinatario.PRINCIPIANTE,
        formato_salida=FormatoSalida.FLASHCARDS,
        nicho_sector=NichoSector.SALUD,
    )
    assert s.nicho_sector == NichoSector.SALUD


def test_solicitud_rechaza_perfil_invalido():
    with pytest.raises(ValidationError):
        SolicitudAdaptacion(
            documento_titulo="Doc",
            documento_contenido="Contenido suficientemente largo para pasar la validación mínima.",
            perfil_destinatario="Estudiante de doctorado",  # no es un valor del enum
            formato_salida=FormatoSalida.FLASHCARDS,
        )


def test_solicitud_rechaza_campos_extra():
    with pytest.raises(ValidationError):
        SolicitudAdaptacion(
            documento_titulo="Doc",
            documento_contenido="Contenido suficientemente largo para pasar la validación mínima.",
            perfil_destinatario=PerfilDestinatario.PRINCIPIANTE,
            formato_salida=FormatoSalida.FLASHCARDS,
            campo_no_existente="x",
        )


def test_solicitud_rechaza_contenido_vacio():
    with pytest.raises(ValidationError):
        SolicitudAdaptacion(
            documento_titulo="Doc",
            documento_contenido="corto",
            perfil_destinatario=PerfilDestinatario.PRINCIPIANTE,
            formato_salida=FormatoSalida.FLASHCARDS,
        )


def test_nicho_salud_es_valor_valido():
    """Requisito del pivot del equipo Kairos G10: Salud debe ser un nicho válido."""
    assert NichoSector.SALUD.value == "Salud"
