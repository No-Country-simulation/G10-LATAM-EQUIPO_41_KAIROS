"""Orquestación del flujo de generación de contenido educativo.

Responsable en el equipo Kairos G10: Bryan Infante (AI Engineer), con Adrian Gil
(ML Engineer) en la capa LLM y el verificador de fidelidad.

Implementa el flujo objetivo del proyecto (Planificador -> Investigador RAG ->
Redactor -> Verificador de fidelidad -> Crítico, con reintento) como una
función Python secuencial, no como un grafo de LangGraph. Es una decisión de
alcance documentada: en este entorno no hay acceso a paquetes que requieran
red más allá de PyPI, y priorizamos tener el FLUJO completo funcionando de
verdad sobre usar una librería de orquestación específica. La forma de las
etapas (planificar, investigar, redactar, verificar, criticar, reintentar)
es la misma que pediría un StateGraph de LangGraph; migrar es un cambio de
"cómo se llaman las funciones entre sí", no de arquitectura.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field

from nuevamente.config import settings
from nuevamente.fidelity.verifier import ResultadoFidelidad, evaluar_fidelidad
from nuevamente.llm.base import LLMClient, LLMError
from nuevamente.llm.factory import crear_llm
from nuevamente.rag.vectorstore import ColeccionDocumento, indexar_documento
from nuevamente.schemas.enums import ClaridadPedagogica
from nuevamente.schemas.formatos import (
    ContenidoAdaptado,
    FlashcardsContenido,
    GuionDeClaseContenido,
    QuizContenido,
    ResumenEjecutivoContenido,
    TutorialContenido,
)
from nuevamente.schemas.response import EvaluacionCalidad, Metadatos

_SCHEMA_POR_FORMATO = {
    "Flashcards": FlashcardsContenido,
    "Quiz": QuizContenido,
    "Tutorial": TutorialContenido,
    "Resumen Ejecutivo": ResumenEjecutivoContenido,
    "Guion de Clase": GuionDeClaseContenido,
}


@dataclass
class ResultadoGeneracion:
    contenido: ContenidoAdaptado
    metadatos: Metadatos
    evaluacion: EvaluacionCalidad
    coleccion: ColeccionDocumento


def _planificar(coleccion: ColeccionDocumento, formato: str) -> list[str]:
    """Devuelve el orden de secciones a cubrir.

    Para formatos de síntesis (Resumen Ejecutivo, Guion de Clase) se recorren
    TODAS las secciones del documento, no solo las más similares a una única
    consulta — así se evita el problema de cobertura de un RAG top-k plano.
    """
    secciones = coleccion.secciones()
    if formato in ("Resumen Ejecutivo", "Guion de Clase"):
        return secciones
    return secciones  # en este MVP todos los formatos cubren todas las secciones


def _investigar(coleccion: ColeccionDocumento, secciones: list[str], top_k_por_seccion: int = 2) -> list[dict]:
    """Recupera evidencia por sección (no un único top-k global) y arma la lista
    de chunks que verá el Redactor, con su chunk_id para trazabilidad."""
    chunks_evidencia: list[dict] = []
    vistos: set[str] = set()
    for seccion in secciones:
        resultados = coleccion.buscar_por_seccion(seccion, consulta=seccion, top_k=top_k_por_seccion)
        for r in resultados:
            if r.chunk.chunk_id in vistos:
                continue
            vistos.add(r.chunk.chunk_id)
            chunks_evidencia.append(
                {"chunk_id": r.chunk.chunk_id, "texto": r.chunk.texto, "seccion": r.chunk.seccion}
            )
    return chunks_evidencia


def _redactar(
    llm: LLMClient,
    schema: type,
    titulo: str,
    perfil: str,
    nicho: str,
    nivel_detalle: str,
    chunks_evidencia: list[dict],
    retroalimentacion: str = "",
) -> ContenidoAdaptado:
    user_payload = {
        "documento_titulo": titulo,
        "perfil": perfil,
        "nicho": nicho,
        "nivel_detalle": nivel_detalle,
        "chunks": chunks_evidencia,
        "retroalimentacion_critico": retroalimentacion,
    }
    system = (
        "Eres el agente Redactor de NuevaMente. Genera contenido educativo usando "
        "EXCLUSIVAMENTE la evidencia de los chunks recibidos. No agregues datos, "
        "dosis, cifras ni indicaciones que no estén en esos chunks."
    )
    return llm.generar_estructurado(schema, system=system, user=json.dumps(user_payload, ensure_ascii=False))


def _calcular_tiempo_estudio(contenido: ContenidoAdaptado) -> int:
    """Heurística simple: ~1 minuto por cada ~120 palabras de contenido generado,
    con un mínimo de 1 minuto. No lo decide el LLM (evita que se autoevalúe)."""
    texto_total = json.dumps(contenido.model_dump(), ensure_ascii=False)
    palabras = len(texto_total.split())
    return max(1, round(palabras / 120))


def _conceptos_clave(chunks_evidencia: list[dict], maximo: int = 6) -> list[str]:
    vistos: list[str] = []
    for c in chunks_evidencia:
        if c["seccion"] not in vistos:
            vistos.append(c["seccion"])
        if len(vistos) >= maximo:
            break
    return vistos


def _claridad_desde_score(score: float) -> ClaridadPedagogica:
    if score >= 0.85:
        return ClaridadPedagogica.ALTA
    if score >= 0.6:
        return ClaridadPedagogica.MEDIA
    return ClaridadPedagogica.BAJA


def generar_contenido_educativo(
    documento_titulo: str,
    documento_contenido: str,
    perfil: str,
    formato: str,
    nicho: str,
    nivel_detalle: str,
    llm: LLMClient | None = None,
) -> ResultadoGeneracion:
    """Punto de entrada del flujo completo: indexa, planifica, investiga, redacta,
    verifica fidelidad y aplica el ciclo de reintento del Crítico."""
    t0 = time.perf_counter()
    llm = llm or crear_llm()

    coleccion = indexar_documento(documento_titulo, documento_contenido)
    schema = _SCHEMA_POR_FORMATO.get(formato)
    if schema is None:
        raise ValueError(f"Formato no soportado: {formato}")

    secciones = _planificar(coleccion, formato)
    chunks_evidencia = _investigar(coleccion, secciones)
    if not chunks_evidencia:
        raise LLMError("El Investigador no encontró evidencia recuperable en el documento.")

    umbral = settings.fidelity_min_for(nicho)
    retroalimentacion = ""
    contenido = None
    contenido_anterior = None
    evaluacion_fidelidad: ResultadoFidelidad | None = None
    aprobado = False

    intentos = settings.max_reintentos_critico + 1
    for intento in range(1, intentos + 1):
        contenido = _redactar(
            llm, schema, documento_titulo, perfil, nicho, nivel_detalle, chunks_evidencia, retroalimentacion
        )
        evaluacion_fidelidad = evaluar_fidelidad(contenido, coleccion)

        if evaluacion_fidelidad.total == 0:
            # Sin afirmaciones con fuente no hay nada que verificar: no se aprueba
            # (sería dar por fiel algo que nadie comprobó) y reintentar no lo arregla.
            break

        if evaluacion_fidelidad.score >= umbral:
            aprobado = True
            break

        # El Crítico rechaza y da retroalimentación concreta para el reintento.
        no_sustentadas = evaluacion_fidelidad.no_sustentadas
        retroalimentacion = (
            f"El intento anterior tuvo afirmaciones no sustentadas por la fuente: "
            f"{no_sustentadas}. Elimínalas o ajústalas para que solo usen la evidencia dada."
        )
        if contenido == contenido_anterior:
            # Generador determinista (p. ej. TemplateLLM): ignora la retroalimentación
            # y repetiría el mismo resultado, así que reintentar no aporta nada.
            break
        contenido_anterior = contenido

    tiempo_generacion = round(time.perf_counter() - t0, 3)
    sin_afirmaciones = evaluacion_fidelidad is None or evaluacion_fidelidad.total == 0
    score_final = 0.0 if sin_afirmaciones else evaluacion_fidelidad.score

    metadatos = Metadatos(
        perfil_aplicado=perfil,
        formato_generado=formato,
        tiempo_estimado_estudio_minutos=_calcular_tiempo_estudio(contenido),
        conceptos_clave=_conceptos_clave(chunks_evidencia),
        prerrequisitos=[],
        tiempo_generacion_segundos=tiempo_generacion,
        modelo_llm=llm.nombre_modelo,
        desde_cache=False,
    )

    evaluacion = EvaluacionCalidad(
        anclaje_fuente_score=round(score_final, 4),
        claridad_pedagogica=_claridad_desde_score(score_final),
        observaciones=(
            "Aprobado por el Crítico dentro del umbral de fidelidad."
            if aprobado
            else "El contenido no trae afirmaciones con fuente declarada; no se pudo verificar "
            "su fidelidad contra el documento."
            if sin_afirmaciones
            else "No se alcanzó el umbral de fidelidad tras los reintentos; se devuelve el "
            "mejor resultado con las afirmaciones no sustentadas señaladas."
        ),
        afirmaciones_total=evaluacion_fidelidad.total if evaluacion_fidelidad else 0,
        afirmaciones_sustentadas=evaluacion_fidelidad.sustentadas if evaluacion_fidelidad else 0,
        afirmaciones_no_sustentadas=evaluacion_fidelidad.no_sustentadas if evaluacion_fidelidad else [],
        umbral_aplicado=umbral,
        aprobado_por_critico=aprobado,
    )

    return ResultadoGeneracion(
        contenido=contenido, metadatos=metadatos, evaluacion=evaluacion, coleccion=coleccion
    )
