"""Enums cerrados del contrato de datos.

Responsable en el equipo Kairos G10: Ethan Espinoza Acosta (Backend Developer).
Estos valores son EXACTAMENTE los del enunciado del Hackathon ONE G10 (Proyecto 1
NuevaMente), más "Salud" ya incluido como nicho de foco del equipo.
"""
from __future__ import annotations

import unicodedata
from enum import Enum


def _clave(texto: str) -> str:
    """Forma comparable de una opción: sin tildes, en minúsculas y con los espacios unificados."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return " ".join(sin_tildes.lower().replace(" / ", "/").split())


class _OpcionFlexible(str, Enum):
    """Acepta el valor escrito sin tildes o con otras mayúsculas: el ejemplo de solicitud del
    enunciado envía "Didactico", y un cliente puede escribir "lider tecnico/arquitecto". La
    respuesta siempre usa el valor canónico ("Didáctico")."""

    @classmethod
    def _missing_(cls, valor):
        if isinstance(valor, str):
            for opcion in cls:
                if _clave(opcion.value) == _clave(valor):
                    return opcion
        return None


class PerfilDestinatario(_OpcionFlexible):
    PRINCIPIANTE = "Principiante"
    DESARROLLADOR_JUNIOR = "Desarrollador Junior/Semi Senior"
    LIDER_TECNICO = "Líder Técnico/Arquitecto"
    GESTOR_EJECUTIVO = "Gestor/Ejecutivo"


#: Nombre que ve el usuario de cada perfil (interfaz y exportaciones). El valor del enum no
#: cambia: es el que espera la API (contrato JSON). Igual que PERFILES en web/app.js.
NOMBRE_VISIBLE_PERFIL = {
    PerfilDestinatario.PRINCIPIANTE.value: "Inicial/Básico (Principiante-Junior)",
    PerfilDestinatario.DESARROLLADOR_JUNIOR.value: "Intermedio (semisénior)",
    PerfilDestinatario.LIDER_TECNICO.value: "Avanzado (Senior-Arquitecto-Técnico)",
    PerfilDestinatario.GESTOR_EJECUTIVO.value: "Experto / Directivo (Lead, Ejecutivo, Gestor)",
}


class FormatoSalida(_OpcionFlexible):
    TUTORIAL = "Tutorial"
    FLASHCARDS = "Flashcards"
    QUIZ = "Quiz"
    RESUMEN_EJECUTIVO = "Resumen Ejecutivo"
    GUION_DE_CLASE = "Guion de Clase"
    PODCAST = "Podcast"


class NichoSector(_OpcionFlexible):
    GENERAL = "General"
    FINTECH = "Fintech"
    SALUD = "Salud"
    ECOMMERCE = "E-commerce"
    TECNOLOGIA = "Tecnología"


class NivelDetalle(_OpcionFlexible):
    CONCISO = "Conciso"
    DIDACTICO = "Didáctico"
    PROFUNDO = "Profundo"


class ClaridadPedagogica(str, Enum):
    ALTA = "Alta"
    MEDIA = "Media"
    BAJA = "Baja"


class VeredictoFidelidad(str, Enum):
    SUSTENTADA = "sustentada"
    PARCIAL = "parcial"
    NO_SUSTENTADA = "no_sustentada"
