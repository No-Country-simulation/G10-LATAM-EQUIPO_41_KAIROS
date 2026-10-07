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
import math
import re
import time
import uuid
from dataclasses import dataclass, field

from nuevamente.config import settings
from nuevamente.fidelity.verifier import ResultadoFidelidad, _fuente_mas_cercana, evaluar_fidelidad
from nuevamente.llm.base import LLMClient, LLMError
from nuevamente.llm.factory import crear_llm
from nuevamente.llm.prompts import construir_prompt_sistema
from nuevamente.rag.vectorstore import ColeccionDocumento, indexar_documento
from nuevamente.schemas.enums import ClaridadPedagogica
from nuevamente.schemas.formatos import (
    ContenidoAdaptado,
    FlashcardsContenido,
    GuionDeClaseContenido,
    PodcastContenido,
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
    "Podcast": PodcastContenido,
}


@dataclass
class ResultadoGeneracion:
    contenido: ContenidoAdaptado
    metadatos: Metadatos
    evaluacion: EvaluacionCalidad
    coleccion: ColeccionDocumento


@dataclass
class PlanPedagogico:
    secciones: list[str]
    conceptos_clave: list[str] = field(default_factory=list)
    prerrequisitos: list[str] = field(default_factory=list)


_SECCIONES_NO_DIDACTICAS = (
    "índice",
    "indice",
    "tabla de contenido",
    "tabla de contenidos",
    "table of contents",
    "bibliografía",
    "bibliografia",
    "referencias",
    "referencias bibliográficas",
    "notas legales",
    "aviso legal",
    "créditos",
)


def _planificar(
    coleccion: ColeccionDocumento,
    formato: str,
    perfil: str = "Principiante",
    nicho: str = "Salud",
) -> PlanPedagogico:
    """Agente Planificador (Híbrido / Local - Latencia < 1ms):
    Analiza la estructura del documento fuente, el formato pedagógico, el perfil
    y el nicho. Descarta secciones no didácticas (índices, tablas de contenidos),
    define la secuencia pedagógica, extrae conceptos clave y formula prerrequisitos.
    """
    secciones_crudas = coleccion.secciones()
    # Filtrar activamente índices y metadatos para evitar preguntas triviales
    secciones_didacticas = [
        s
        for s in secciones_crudas
        if not any(
            nd == s.strip().lower() or s.strip().lower().startswith(nd)
            for nd in _SECCIONES_NO_DIDACTICAS
        )
    ]
    secciones = secciones_didacticas or secciones_crudas

    # Conceptos clave derivados de los títulos de secciones sustantivas
    conceptos: list[str] = []
    for s in secciones:
        if s and s.lower() != "general" and s not in conceptos:
            conceptos.append(s)
    if not conceptos and coleccion.titulo:
        conceptos.append(coleccion.titulo)

    # Inferir prerrequisitos pedagógicos según perfil y nicho
    prerreqs: list[str] = []
    for s in secciones:
        s_low = s.lower()
        if any(kw in s_low for kw in ("introduc", "fundamento", "requisito", "conceptos previos", "definici", "norma")):
            prerreqs.append(f"Lectura previa de: {s}")

    if not prerreqs:
        if perfil == "Principiante":
            if nicho == "Salud":
                prerreqs.append("Conceptos básicos de higiene y bioseguridad sanitaria.")
            elif nicho == "Fintech":
                prerreqs.append("Familiaridad con términos financieros básicos.")
            elif nicho == "E-commerce":
                prerreqs.append("Comprensión general de comercio electrónico y ventas.")
            else:
                prerreqs.append("Comprensión lectora general del tema.")
        elif perfil == "Desarrollador Junior/Semi Senior":
            prerreqs.append("Conocimiento técnico fundamental del flujo y la arquitectura base.")
        elif perfil == "Líder Técnico/Arquitecto":
            prerreqs.append("Criterio en diseño de sistemas, estándares de seguridad y dependencias.")
        elif perfil == "Gestor/Ejecutivo":
            prerreqs.append("Visión general de impacto operacional, gestión de riesgos y normativas.")

    return PlanPedagogico(
        secciones=secciones,
        conceptos_clave=conceptos[:6],
        prerrequisitos=prerreqs[:3],
    )


# Cuántos chunks de evidencia recibe el Redactor en total (los formatos usan hasta 8-12).
_EVIDENCIA_OBJETIVO = 12


def _es_texto_corrido(texto: str) -> bool:
    """Si el fragmento trae al menos una oración de verdad (8+ palabras terminadas en
    punto). Una portada o unos créditos son rótulos sueltos: título, institución, código, año."""
    return any(len(o.split()) >= 8 for o in re.split(r"(?<=[.!?])\s+", texto) if o.rstrip().endswith((".", "!", "?")))


def _investigar(coleccion: ColeccionDocumento, secciones: list[str], top_k_por_seccion: int | None = None) -> list[dict]:
    """Recupera evidencia por sección (no un único top-k global) y arma la lista
    de chunks que verá el Redactor, con su chunk_id para trazabilidad.

    El top-k por sección se reparte según cuántas secciones hay: un documento sin
    encabezados (p. ej. un PDF) es una sola sección y necesita más de 2 chunks
    para que el material cubra el documento. La evidencia se devuelve en el orden
    del documento, que es el orden natural de un tutorial o una clase.
    """
    if top_k_por_seccion is None:
        top_k_por_seccion = max(2, math.ceil(_EVIDENCIA_OBJETIVO / max(1, len(secciones))))
    seleccionados = {}
    for seccion in secciones:
        if seccion == "Documento completo":
            # Sin títulos no hay consulta útil (el nombre de la sección no dice nada del
            # texto): se toman fragmentos repartidos por todo el documento, no los primeros.
            todos = [c for c in coleccion.chunks if c.seccion == seccion]
            cupo = max(_EVIDENCIA_OBJETIVO, top_k_por_seccion)
            paso = max(1, len(todos) / cupo)
            elegidos = [todos[int(i * paso)] for i in range(min(cupo, len(todos)))]
        elif seccion == "Introducción" and len(secciones) > 1:
            # Lo que va antes del primer título: portada, créditos o una presentación.
            # Aporta como mucho un fragmento, y solo si es texto corrido.
            elegidos = [
                r.chunk for r in coleccion.buscar_por_seccion(seccion, consulta=seccion, top_k=top_k_por_seccion)
                if _es_texto_corrido(r.chunk.texto)
            ][:1]
        else:
            elegidos = [r.chunk for r in coleccion.buscar_por_seccion(seccion, consulta=seccion, top_k=top_k_por_seccion)]
        for chunk in elegidos:
            seleccionados.setdefault(chunk.chunk_id, chunk)
    return [
        {"chunk_id": c.chunk_id, "texto": c.texto, "seccion": c.seccion}
        for c in sorted(seleccionados.values(), key=lambda c: c.orden)
    ]


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
    formato = schema.model_fields["formato"].default
    system = construir_prompt_sistema(formato, perfil, nicho, nivel_detalle)
    return llm.generar_estructurado(schema, system=system, user=json.dumps(user_payload, ensure_ascii=False))


def _normalizar(texto: str) -> set[str]:
    """Palabras de un texto, en minúsculas y sin puntuación ni el prefijo que agrega el perfil."""
    texto = re.sub(r"^(En palabras simples|Lo importante para la gestión|La fuente indica):\s*", "", texto)
    return set(re.findall(r"\w+", texto.lower()))


def _es_duplicado(texto: str, vistos: list[set[str]]) -> bool:
    """Presunto duplicado: el mismo texto, o uno que comparte casi todas sus palabras
    con otro ya incluido (el solapamiento del chunking repite oraciones entre chunks)."""
    palabras = _normalizar(texto)
    if not palabras:
        return False
    for otro in vistos:
        comunes = len(palabras & otro)
        if comunes / min(len(palabras), len(otro)) >= 0.85:
            return True
    vistos.append(palabras)
    return False


def _sin_repetidos(textos: list[str]) -> list[str]:
    vistos: list[set[str]] = []
    return [t for t in textos if t.strip() and not _es_duplicado(t, vistos)]


def _depurar(contenido: ContenidoAdaptado) -> ContenidoAdaptado:
    """Quita presuntos duplicados (tarjetas, preguntas, pasos, escenas, intervenciones y
    listas) y vuelve a numerar en orden, sin huecos. El Redactor, sobre todo el
    extractivo, puede repetir una misma idea que aparece en dos chunks solapados."""
    datos = contenido.model_dump()
    vistos: list[set[str]] = []

    if "items" in datos:
        datos["items"] = [x for x in datos["items"] if not _es_duplicado(x["dorso"], vistos)]
    if "preguntas" in datos:
        datos["preguntas"] = [
            p for p in datos["preguntas"] if not _es_duplicado(p["opciones"][p["indice_correcto"]], vistos)
        ]
    if "pasos" in datos:
        datos["pasos"] = [p for p in datos["pasos"] if not _es_duplicado(p["instruccion"], vistos)]
    if "escenas" in datos:
        datos["escenas"] = [e for e in datos["escenas"] if not _es_duplicado(e["narracion"], vistos)]
    if "intervenciones" in datos:
        # si se quita una respuesta repetida de Leo, se quita también la pregunta de Ana que la introducía
        limpias: list[dict] = []
        for x in datos["intervenciones"]:
            if x["locutor"] == "Leo" and x["fuentes"] and _es_duplicado(x["texto"], vistos):
                if len(limpias) > 1 and limpias[-1]["locutor"] == "Ana" and not limpias[-1]["fuentes"]:
                    limpias.pop()
                continue
            limpias.append(x)
        datos["intervenciones"] = limpias

    for campo in ("items", "preguntas"):
        if campo in datos and not datos[campo]:
            return contenido  # nunca dejar el material vacío
    for campo in ("pasos", "escenas", "intervenciones"):
        for i, parte in enumerate(datos.get(campo, []), start=1):
            parte["orden"] = i

    for campo in ("prerrequisitos", "errores_comunes", "checklist_final", "puntos_clave", "decisiones_o_riesgos"):
        if campo in datos:
            datos[campo] = _sin_repetidos(datos[campo]) or datos[campo]
    if "escenas" in datos:
        datos["duracion_total_min"] = max(1, min(60, round(sum(e["duracion_seg"] for e in datos["escenas"]) / 60)))

    return type(contenido).model_validate(datos)


_CAMPOS_DE_TEXTO = ("dorso", "justificacion", "instruccion", "narracion", "texto")


def _asignar_secciones(contenido: ContenidoAdaptado, coleccion: ColeccionDocumento) -> None:
    """Anota en cada parte generada (tarjeta, pregunta, paso, escena, intervención) la
    sección del documento de la que sale. Así la interfaz y las exportaciones pueden
    mostrar el título de cada parte. No lo decide el LLM.

    Si una parte cita chunks de varias secciones, su sección es la del chunk que de
    verdad sustenta su texto (no simplemente el primero que citó), para que el título
    bajo el que aparece corresponda a lo que dice.
    """
    partes = []
    for campo in ("items", "preguntas", "pasos", "escenas", "intervenciones"):
        partes.extend(getattr(contenido, campo, None) or [])
    for parte in partes:
        fuentes = [f for f in parte.fuentes if coleccion.get_chunk(f)]
        if len(fuentes) > 1:
            texto = next((getattr(parte, c) for c in _CAMPOS_DE_TEXTO if getattr(parte, c, "")), "")
            fuentes = [_fuente_mas_cercana(texto, fuentes, coleccion)]
        parte.seccion = coleccion.get_chunk(fuentes[0]).seccion if fuentes else ""


def _agrupar_por_seccion(contenido: ContenidoAdaptado, coleccion: ColeccionDocumento) -> None:
    """Deja juntas las partes de una misma sección, en el orden del documento, y vuelve a
    numerar. Un LLM puede alternar temas (sección A, B, A…): en pantalla el mismo título
    aparecería varias veces con los contenidos entremezclados. Dentro de cada sección se
    respeta el orden que eligió el Redactor. El podcast no se toca: es una conversación."""
    posicion = {s: i for i, s in enumerate(coleccion.secciones())}
    for campo in ("items", "preguntas", "pasos", "escenas"):
        partes = getattr(contenido, campo, None)
        if not partes:
            continue
        claves, anterior = [], 0
        for parte in partes:
            # una parte sin sección conocida se queda junto a la que la precede
            anterior = posicion.get(parte.seccion, anterior)
            claves.append(anterior)
        ordenadas = [p for _, p in sorted(zip(claves, partes), key=lambda par: par[0])]
        for i, parte in enumerate(ordenadas, start=1):
            if hasattr(parte, "orden"):
                parte.orden = i
        setattr(contenido, campo, ordenadas)


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

    t_idx0 = time.perf_counter()
    coleccion = indexar_documento(documento_titulo, documento_contenido)
    t_idx = round((time.perf_counter() - t_idx0) * 1000, 2)

    schema = _SCHEMA_POR_FORMATO.get(formato)
    if schema is None:
        raise ValueError(f"Formato no soportado: {formato}")

    # 1. Agente Planificador: traza secuencia didáctica, conceptos clave y prerrequisitos (< 1ms)
    t_plan0 = time.perf_counter()
    plan = _planificar(coleccion, formato, perfil=perfil, nicho=nicho)
    t_plan = round((time.perf_counter() - t_plan0) * 1000, 2)

    # 2. Agente Investigador: recupera evidencia por sección mediante RAG local (< 5ms)
    t_inv0 = time.perf_counter()
    chunks_evidencia = _investigar(coleccion, plan.secciones)
    t_inv = round((time.perf_counter() - t_inv0) * 1000, 2)
    if not chunks_evidencia:
        raise LLMError("El Investigador no encontró evidencia recuperable en el documento.")

    umbral = settings.fidelity_min_for(nicho)
    retroalimentacion = ""
    contenido = None
    contenido_anterior = None
    evaluacion_fidelidad: ResultadoFidelidad | None = None
    aprobado = False

    t_red_total = 0.0
    t_crit_total = 0.0

    intentos = settings.max_reintentos_critico + 1
    for intento in range(1, intentos + 1):
        # 3. Agente Redactor: única llamada pesada al LLM generativo estructurado
        t_red0 = time.perf_counter()
        contenido = _depurar(
            _redactar(llm, schema, documento_titulo, perfil, nicho, nivel_detalle, chunks_evidencia, retroalimentacion)
        )
        t_red_total += (time.perf_counter() - t_red0)

        # 4. Agente Crítico Guardián: evaluación matemática instantánea de fidelidad (< 2ms)
        t_crit0 = time.perf_counter()
        evaluacion_fidelidad = evaluar_fidelidad(contenido, coleccion)
        t_crit_total += (time.perf_counter() - t_crit0)

        if evaluacion_fidelidad.total == 0:
            # Sin afirmaciones con fuente no hay nada que verificar: no se aprueba
            # (sería dar por fiel algo que nadie comprobó) y reintentar no lo arregla.
            break

        if evaluacion_fidelidad.score >= umbral:
            aprobado = True
            break

        # El Crítico rechaza y da retroalimentación concreta y específica para el reintento
        no_sustentadas = evaluacion_fidelidad.no_sustentadas
        parciales = getattr(evaluacion_fidelidad, "parciales_afirmaciones", [])
        partes_retro: list[str] = []
        if no_sustentadas:
            partes_retro.append(
                f"Afirmaciones NO sustentadas por la fuente: {no_sustentadas[:3]}. "
                "Elimínalas o ajústalas para que solo usen la evidencia textual dada."
            )
        if parciales:
            partes_retro.append(
                f"Afirmaciones con anclaje débil o parcial: {parciales[:3]}. "
                "Asegura una conexión conceptual y terminológica más estrecha con el chunk citado."
            )
        if not partes_retro:
            partes_retro.append(
                f"El score de fidelidad ({evaluacion_fidelidad.score:.2f}) no alcanzó el umbral requerido ({umbral:.2f}). "
                "Alinea las afirmaciones con mayor fidelidad a los hechos y términos de los chunks de evidencia."
            )
        retroalimentacion = " ".join(partes_retro)

        if contenido == contenido_anterior:
            # Generador determinista (p. ej. TemplateLLM): ignora la retroalimentación
            # y repetiría el mismo resultado, así que reintentar no aporta nada.
            break
        contenido_anterior = contenido

    _asignar_secciones(contenido, coleccion)
    _agrupar_por_seccion(contenido, coleccion)
    tiempo_generacion = round(time.perf_counter() - t0, 3)
    sin_afirmaciones = evaluacion_fidelidad is None or evaluacion_fidelidad.total == 0
    score_final = 0.0 if sin_afirmaciones else evaluacion_fidelidad.score

    tiempos_por_agente = {
        "indexacion_rag_ms": t_idx,
        "planificador_ms": t_plan,
        "investigador_ms": t_inv,
        "redactor_segundos": round(t_red_total, 3),
        "critico_ms": round(t_crit_total * 1000, 2),
    }

    metadatos = Metadatos(
        perfil_aplicado=perfil,
        formato_generado=formato,
        tiempo_estimado_estudio_minutos=_calcular_tiempo_estudio(contenido),
        conceptos_clave=plan.conceptos_clave or _conceptos_clave(chunks_evidencia),
        prerrequisitos=plan.prerrequisitos,
        tiempo_generacion_segundos=tiempo_generacion,
        modelo_llm=llm.nombre_modelo,
        desde_cache=False,
        tiempos_por_agente=tiempos_por_agente,
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
