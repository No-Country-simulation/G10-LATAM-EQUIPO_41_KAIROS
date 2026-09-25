"""Verificación de fidelidad del contenido generado contra el documento fuente.

Responsable en el equipo Kairos G10: Adrian Gil (ML Engineer), con la rúbrica de
calidad acordada con Diana Dure (QA) — frente que originalmente cubría Data
Scientist en el equipo (ver nota del PM en el plan de trabajo).

Diseño: en producción, el "juez" sería un LLM que recibe la afirmación y los
chunks candidatos y devuelve un veredicto con cita textual. Aquí, sin acceso a
un LLM externo, el juez es una función de similitud (coseno sobre TF-IDF, mismo
mecanismo que el retriever de rag/vectorstore.py) contra el propio chunk de
origen declarado en `fuentes`. Es un juez más simple, pero real: mide de verdad
cuánto se aleja el texto generado del texto fuente, y es 100% auditable porque
siempre cita el chunk_id contra el que se comparó.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from nuevamente.rag.embeddings import LocalTfidfEmbeddings
from nuevamente.rag.vectorstore import ColeccionDocumento
from nuevamente.schemas.enums import VeredictoFidelidad

# Bajo este score de similitud, una afirmación se considera no sustentada.
UMBRAL_NO_SUSTENTADA = 0.08
# Entre este umbral y 1.0, se considera parcialmente sustentada.
UMBRAL_PARCIAL = 0.20

_SEP_ORACIONES = re.compile(r"(?<=[.!?…])\s+")


@dataclass
class VeredictoAfirmacion:
    afirmacion: str
    chunk_id_evidencia: str
    similitud: float
    veredicto: VeredictoFidelidad


@dataclass
class ResultadoFidelidad:
    veredictos: list[VeredictoAfirmacion] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.veredictos)

    @property
    def sustentadas(self) -> int:
        return sum(1 for v in self.veredictos if v.veredicto == VeredictoFidelidad.SUSTENTADA)

    @property
    def parciales(self) -> int:
        return sum(1 for v in self.veredictos if v.veredicto == VeredictoFidelidad.PARCIAL)

    @property
    def no_sustentadas(self) -> list[str]:
        return [v.afirmacion for v in self.veredictos if v.veredicto == VeredictoFidelidad.NO_SUSTENTADA]

    @property
    def score(self) -> float:
        if self.total == 0:
            return 1.0
        return (self.sustentadas + 0.5 * self.parciales) / self.total


def _similitud(afirmacion: str, chunk_texto: str) -> float:
    """Similitud de coseno TF-IDF entre la afirmación y su chunk de evidencia declarado."""
    vect = LocalTfidfEmbeddings()
    vect.fit([afirmacion, chunk_texto])
    matriz = vect.transform([afirmacion, chunk_texto])
    a, b = matriz[0], matriz[1]
    import numpy as np

    denom = (float(np.linalg.norm(a)) * float(np.linalg.norm(b))) or 1e-9
    return float(a @ b) / denom


def verificar_afirmacion(afirmacion: str, chunk_id: str, coleccion: ColeccionDocumento) -> VeredictoAfirmacion:
    chunk = coleccion.get_chunk(chunk_id)
    if chunk is None:
        return VeredictoAfirmacion(
            afirmacion=afirmacion,
            chunk_id_evidencia=chunk_id,
            similitud=0.0,
            veredicto=VeredictoFidelidad.NO_SUSTENTADA,
        )

    similitud = _similitud(afirmacion, chunk.texto)
    if similitud >= UMBRAL_PARCIAL:
        veredicto = VeredictoFidelidad.SUSTENTADA
    elif similitud >= UMBRAL_NO_SUSTENTADA:
        veredicto = VeredictoFidelidad.PARCIAL
    else:
        veredicto = VeredictoFidelidad.NO_SUSTENTADA

    return VeredictoAfirmacion(
        afirmacion=afirmacion, chunk_id_evidencia=chunk_id, similitud=similitud, veredicto=veredicto
    )


def _fuente_mas_cercana(afirmacion: str, fuentes: list[str], coleccion: ColeccionDocumento) -> str:
    """Entre los chunks declarados, devuelve el que mejor sustenta la afirmación."""
    mejor_id, mejor_sim = fuentes[0], -1.0
    for chunk_id in fuentes:
        chunk = coleccion.get_chunk(chunk_id)
        if chunk is None:
            continue
        sim = _similitud(afirmacion, chunk.texto)
        if sim > mejor_sim:
            mejor_id, mejor_sim = chunk_id, sim
    return mejor_id


def extraer_afirmaciones(contenido_adaptado, coleccion: ColeccionDocumento | None = None) -> list[tuple[str, str]]:
    """Extrae pares (afirmacion, chunk_id) de cualquier ContenidoAdaptado.

    Recorre los campos con `fuentes` (items/preguntas/pasos/escenas) según el
    formato. El resumen ejecutivo es síntesis global con una lista de `fuentes`
    para todo el texto: cada oración del resumen es una afirmación, verificada
    contra el chunk declarado que mejor la sustenta (requiere `coleccion`).
    """
    pares: list[tuple[str, str]] = []
    formato = getattr(contenido_adaptado, "formato", "")

    if formato == "Flashcards":
        for item in contenido_adaptado.items:
            if item.fuentes:
                pares.append((item.dorso, item.fuentes[0]))
    elif formato == "Quiz":
        for pregunta in contenido_adaptado.preguntas:
            if pregunta.fuentes:
                pares.append((pregunta.justificacion, pregunta.fuentes[0]))
    elif formato == "Tutorial":
        for paso in contenido_adaptado.pasos:
            if paso.fuentes:
                pares.append((paso.instruccion, paso.fuentes[0]))
    elif formato == "Guion de Clase":
        for escena in contenido_adaptado.escenas:
            if escena.fuentes:
                pares.append((escena.narracion, escena.fuentes[0]))
    elif formato == "Resumen Ejecutivo":
        if contenido_adaptado.fuentes and coleccion is not None:
            for oracion in _SEP_ORACIONES.split(contenido_adaptado.resumen):
                oracion = oracion.strip()
                if len(oracion) > 12:
                    chunk_id = _fuente_mas_cercana(oracion, contenido_adaptado.fuentes, coleccion)
                    pares.append((oracion, chunk_id))

    return pares


def evaluar_fidelidad(contenido_adaptado, coleccion: ColeccionDocumento) -> ResultadoFidelidad:
    resultado = ResultadoFidelidad()
    for afirmacion, chunk_id in extraer_afirmaciones(contenido_adaptado, coleccion):
        resultado.veredictos.append(verificar_afirmacion(afirmacion, chunk_id, coleccion))
    return resultado
