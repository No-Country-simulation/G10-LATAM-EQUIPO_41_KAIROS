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


def test_los_textos_no_muestran_los_identificadores_internos_de_los_chunks():
    from nuevamente.schemas.formatos import QuizContenido

    c = QuizContenido(
        titulo="Visitas",
        preguntas=[{
            "enunciado": "Según el chunk 3af0b24977faa74f-c008, ¿cuál es el horario de visitas?",
            "opciones": ["De 10 a 12 (3af0b24977faa74f-c008)", "De 14 a 16", "Libre", "No hay visitas"],
            "indice_correcto": 0,
            "justificacion": "El chunk 3af0b24977faa74f-c011 indica que las visitas son de 10 a 12 "
            "[3af0b24977faa74f-c006, 3af0b24977faa74f-c008].",
            "fuentes": ["3af0b24977faa74f-c008"],
        }],
    )
    p = c.preguntas[0]
    assert p.enunciado == "Según el documento, ¿cuál es el horario de visitas?"
    assert p.opciones[0] == "De 10 a 12"
    assert p.justificacion == "El documento indica que las visitas son de 10 a 12."
    assert p.fuentes == ["3af0b24977faa74f-c008"]  # la trazabilidad no se toca


def test_un_documento_sobre_chunks_conserva_la_palabra():
    from nuevamente.schemas.formatos import FlashcardItem

    item = FlashcardItem(frente="¿Qué es un chunk?", dorso="Un chunk es un fragmento del texto indexado.")
    assert item.frente == "¿Qué es un chunk?" and item.dorso.startswith("Un chunk es")
