"""Enums cerrados del contrato de datos.

Responsable en el equipo Kairos G10: Ethan Espinoza Acosta (Backend Developer).
Estos valores son EXACTAMENTE los del enunciado del Hackathon ONE G10 (Proyecto 1
NuevaMente), más "Salud" ya incluido como nicho de foco del equipo.
"""
from __future__ import annotations

from enum import Enum


class PerfilDestinatario(str, Enum):
    PRINCIPIANTE = "Principiante"
    DESARROLLADOR_JUNIOR = "Desarrollador Junior/Semi Senior"
    LIDER_TECNICO = "Líder Técnico/Arquitecto"
    GESTOR_EJECUTIVO = "Gestor/Ejecutivo"


class FormatoSalida(str, Enum):
    TUTORIAL = "Tutorial"
    FLASHCARDS = "Flashcards"
    QUIZ = "Quiz"
    RESUMEN_EJECUTIVO = "Resumen Ejecutivo"
    GUION_DE_CLASE = "Guion de Clase"


class NichoSector(str, Enum):
    GENERAL = "General"
    FINTECH = "Fintech"
    SALUD = "Salud"
    ECOMMERCE = "E-commerce"


class NivelDetalle(str, Enum):
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
