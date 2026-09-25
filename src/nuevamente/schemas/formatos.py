"""Esquemas de contenido por formato pedagógico (unión discriminada por `formato`).

Responsable: Ethan Espinoza Acosta (Backend Developer), con Bryan Infante
(AI Engineer) definiendo qué campos necesita cada formato para el grafo de agentes.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FlashcardItem(_Base):
    frente: str = Field(min_length=3, max_length=300)
    dorso: str = Field(min_length=3, max_length=800)
    pista_didactica: str = Field(default="", max_length=300)
    fuentes: list[str] = Field(default_factory=list, description="chunk_id de evidencia")


class FlashcardsContenido(_Base):
    formato: Literal["Flashcards"] = "Flashcards"
    titulo: str
    introduccion_contextualizada: str
    items: list[FlashcardItem] = Field(min_length=1, max_length=15)


class QuizPregunta(_Base):
    enunciado: str
    opciones: list[str] = Field(min_length=4, max_length=4)
    indice_correcto: int = Field(ge=0, le=3)
    justificacion: str
    fuentes: list[str] = Field(default_factory=list)


class QuizContenido(_Base):
    formato: Literal["Quiz"] = "Quiz"
    titulo: str
    preguntas: list[QuizPregunta] = Field(min_length=1, max_length=10)


class TutorialPaso(_Base):
    orden: int
    titulo: str
    instruccion: str
    resultado_esperado: str = ""
    fuentes: list[str] = Field(default_factory=list)


class TutorialContenido(_Base):
    formato: Literal["Tutorial"] = "Tutorial"
    objetivo: str
    prerrequisitos: list[str] = Field(default_factory=list)
    pasos: list[TutorialPaso] = Field(min_length=1)
    errores_comunes: list[str] = Field(default_factory=list)
    checklist_final: list[str] = Field(default_factory=list)


class ResumenEjecutivoContenido(_Base):
    formato: Literal["Resumen Ejecutivo"] = "Resumen Ejecutivo"
    resumen: str = Field(max_length=1800, description="≈250 palabras")
    puntos_clave: list[str] = Field(min_length=1, max_length=5)
    decisiones_o_riesgos: list[str] = Field(default_factory=list)
    impacto_de_negocio: str = ""
    fuentes: list[str] = Field(default_factory=list, description="chunk_id de evidencia del resumen")


class GuionEscena(_Base):
    orden: int
    narracion: str
    apoyo_visual: str = ""
    duracion_seg: int = Field(ge=5, le=600)
    fuentes: list[str] = Field(default_factory=list)


class GuionDeClaseContenido(_Base):
    formato: Literal["Guion de Clase"] = "Guion de Clase"
    duracion_total_min: int = Field(ge=1, le=60)
    escenas: list[GuionEscena] = Field(min_length=1)


ContenidoAdaptado = Annotated[
    Union[
        FlashcardsContenido,
        QuizContenido,
        TutorialContenido,
        ResumenEjecutivoContenido,
        GuionDeClaseContenido,
    ],
    Field(discriminator="formato"),
]
