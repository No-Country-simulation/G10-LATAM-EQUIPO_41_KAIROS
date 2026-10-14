"""Juez de fidelidad y de coherencia didáctica con IA (HU-37 y HU-38).

Responsable en el equipo Kairos G10: Adrian Gil (ML Engineer).

La similitud TF-IDF (fidelity/verifier.py) es el primer filtro: rápida, sin costo y
auditable, pero no reconoce una paráfrasis fiel ni una traducción. El juez con IA
revisa SOLO las afirmaciones que el TF-IDF dejó como parciales o no sustentadas y, en
la misma solicitud, evalúa la coherencia didáctica del material.

Salvaguarda: el juez solo puede dar por sustentada una afirmación si devuelve una cita
textual que existe en el fragmento citado. Eso se comprueba aquí, en código: una cita
inventada no convence a nadie. Si la IA no está disponible, queda el veredicto TF-IDF.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field

from nuevamente.config import settings
from nuevamente.fidelity.verifier import ResultadoFidelidad
from nuevamente.llm.prompts import construir_prompt_critico
from nuevamente.rag.vectorstore import ColeccionDocumento
from nuevamente.schemas.enums import VeredictoFidelidad

logger = logging.getLogger(__name__)

MAX_AFIRMACIONES_POR_JUICIO = 15
MIN_CARACTERES_CITA = 15
FRAGMENTOS_POR_AFIRMACION = 3  # una oración de síntesis puede apoyarse en varias secciones


class VeredictoIA(BaseModel):
    indice: int = Field(description="índice de la afirmación en la lista recibida")
    veredicto: Literal["sustentada", "parcial", "no_sustentada"]
    citas: list[str] = Field(
        default_factory=list, max_length=6,
        description="un fragmento copiado textualmente de los chunks por cada hecho que afirma",
    )


class JuicioIA(BaseModel):
    veredictos: list[VeredictoIA] = Field(default_factory=list)
    coherencia_didactica: Literal["Alta", "Media", "Baja"]
    comentario_coherencia: str = Field(default="", max_length=600)


_INSTRUCCIONES = (
    "\n\n[TAREA]\n"
    "1. Para cada afirmación de `afirmaciones`, decide si sus `chunks` la sustentan. Una paráfrasis "
    "o una síntesis fiel, o una traducción fiel, cuentan como sustentadas. Si la sustentan, copia en "
    "`citas` un fragmento EXACTO de los chunks (letra por letra, al menos una frase) por cada hecho "
    "que afirma; si algún hecho no está en los chunks, es parcial o no sustentada. No inventes ni "
    "corrijas las citas.\n"
    "2. Evalúa SOLO la coherencia didáctica del `material` para el perfil: orden lógico, claridad, "
    "progresión y adecuación al destinatario. No opines aquí sobre la fidelidad (se juzga en el "
    "punto 1, y no tienes el documento completo). Responde Alta, Media o Baja y explica en una o "
    "dos oraciones, en español, en `comentario_coherencia`."
)


def juez_disponible(llm) -> bool:
    """Hay un modelo de IA real detrás (no el generador local) y el juez está activado."""
    nombre = getattr(llm, "nombre_modelo", "") or ""
    return settings.juez_ia != "off" and "template" not in nombre and "respaldo" not in nombre


def _normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKC", texto or "").lower()
    texto = re.sub(r"[«»\"“”'‘’]", "", texto)
    return re.sub(r"\s+", " ", texto).strip(" .,;:")


def cita_valida(cita: str, chunk_texto: str) -> bool:
    """La cita existe tal cual (salvo espacios, mayúsculas y comillas) en el fragmento."""
    cita = _normalizar(cita)
    return len(cita) >= MIN_CARACTERES_CITA and cita in _normalizar(chunk_texto)


def juzgar(
    llm, contenido, evaluacion: ResultadoFidelidad, coleccion: ColeccionDocumento, *,
    formato: str, perfil: str, nicho: str,
) -> JuicioIA | None:
    """Revisa con IA las afirmaciones dudosas (modifica `evaluacion`) y evalúa la coherencia
    didáctica. Devuelve el juicio, o None si la IA no respondió (queda el TF-IDF)."""
    dudosas = [
        (i, v) for i, v in enumerate(evaluacion.veredictos) if v.veredicto != VeredictoFidelidad.SUSTENTADA
    ][:MAX_AFIRMACIONES_POR_JUICIO]
    afirmaciones, candidatos = [], []
    for k, (_, v) in enumerate(dudosas):
        # el fragmento citado y los más cercanos por significado (con embeddings semánticos)
        citado = coleccion.get_chunk(v.chunk_id_evidencia)
        cercanos = [r.chunk for r in coleccion.buscar(v.afirmacion, top_k=FRAGMENTOS_POR_AFIRMACION)]
        chunks = list({c.chunk_id: c for c in ([citado] if citado else []) + cercanos}.values())
        chunks = chunks[:FRAGMENTOS_POR_AFIRMACION + 1]
        candidatos.append(chunks)
        afirmaciones.append({"indice": k, "afirmacion": v.afirmacion, "chunks": [c.texto for c in chunks]})
    usuario = json.dumps(
        {"perfil": perfil, "formato": formato, "afirmaciones": afirmaciones,
         "material": contenido.model_dump(exclude={"fuentes"}, mode="json")},
        ensure_ascii=False,
    )
    try:
        juicio = llm.generar_estructurado(
            JuicioIA, system=construir_prompt_critico(formato, perfil, nicho) + _INSTRUCCIONES, user=usuario
        )
    except Exception as exc:  # sin cuota, sin red, o un proveedor que no sabe juzgar
        logger.warning("Juez de IA no disponible, queda el veredicto TF-IDF: %s", exc)
        return None

    for respuesta in juicio.veredictos:
        if not 0 <= respuesta.indice < len(dudosas) or respuesta.veredicto == "no_sustentada":
            continue
        _, veredicto = dudosas[respuesta.indice]
        # cada cita tiene que existir en alguno de los fragmentos que vio el juez
        fuentes = [next((c for c in candidatos[respuesta.indice] if cita_valida(cita, c.texto)), None)
                   for cita in respuesta.citas]
        if not fuentes or None in fuentes:
            continue  # sin citas, o alguna inventada: queda el veredicto TF-IDF
        nuevo = VeredictoFidelidad.SUSTENTADA if respuesta.veredicto == "sustentada" else VeredictoFidelidad.PARCIAL
        if nuevo == VeredictoFidelidad.PARCIAL and veredicto.veredicto != VeredictoFidelidad.NO_SUSTENTADA:
            continue  # el juez nunca baja un veredicto
        veredicto.veredicto = nuevo
        veredicto.cita = " … ".join(c.strip() for c in respuesta.citas)
        veredicto.chunk_id_evidencia = fuentes[0].chunk_id
        veredicto.juez = "ia"
    return juicio
