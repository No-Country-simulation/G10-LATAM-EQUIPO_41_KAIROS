"""Orquestación del flujo de generación de contenido educativo, como grafo de LangGraph.

Responsable en el equipo Kairos G10: Bryan Infante (AI Engineer), con Adrian Gil
(ML Engineer) en la capa LLM y el verificador de fidelidad.

Grafo (`StateGraph`), un nodo por agente:

    indexar -> planificar -> investigar -> redactar -> criticar --(aprobado / sin mejora)--> finalizar
                                               ^                        |
                                               +----(reintento con retroalimentación)----+

- indexar: ingesta, chunking y embeddings (RAG).
- planificar: secciones didácticas, conceptos clave y prerrequisitos.
- investigar: evidencia por sección (Investigador RAG).
- redactar: única llamada pesada al LLM, con salida estructurada (Pydantic).
- criticar: verifica cada afirmación contra su chunk; si no alcanza el umbral del
  nicho, devuelve retroalimentación concreta y el grafo vuelve a redactar.
- finalizar: metadatos de aprendizaje y evaluación de calidad.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, TypedDict

from pydantic import Field, create_model

from langgraph.graph import END, START, StateGraph

from nuevamente.config import settings
from nuevamente.ingest.conceptos import extraer_conceptos
from nuevamente.fidelity.juez import JuicioIA, juez_disponible, juzgar
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

    # Conceptos clave derivados de los títulos de secciones sustantivas. Un documento sin
    # títulos queda en "Documento completo", que no es un concepto: entonces se completan
    # con los términos técnicos de su texto ("VCN", "Security Lists").
    conceptos: list[str] = []
    for s in secciones:
        if s and s.lower() != "general" and s not in ("Documento completo", "Introducción") and s not in conceptos:
            conceptos.append(s)
    if len(conceptos) < 3:
        texto = "\n".join(c.texto for c in coleccion.chunks)
        conceptos += extraer_conceptos(texto, maximo=6 - len(conceptos), excluir=set(conceptos))
    if not conceptos:  # ni títulos ni términos técnicos: queda el nombre de la sección
        conceptos = list(secciones)

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
            elif nicho == "Tecnología":
                prerreqs.append("Familiaridad básica con software, sistemas y conceptos digitales.")
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
    # las consultas son los nombres de sección: se embeben todas en una sola solicitud
    coleccion.precalcular_consultas([s for s in secciones if s != "Documento completo"])
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


@lru_cache(maxsize=None)
def _con_metadatos(schema: type) -> type:
    """El esquema del formato más los metadatos de aprendizaje (HU-32), para pedirlos al
    Redactor en la misma llamada en vez de gastar otra solicitud del cupo del LLM."""
    return create_model(
        f"{schema.__name__}ConMetadatos",
        __base__=schema,
        conceptos_clave=(list[str], Field(default_factory=list, max_length=8, description="3 a 6 conceptos centrales")),
        prerrequisitos=(list[str], Field(default_factory=list, max_length=4, description="1 a 3 conocimientos previos")),
    )


def _separar_metadatos(schema: type, respuesta) -> tuple[ContenidoAdaptado, list[str], list[str]]:
    datos = respuesta.model_dump()
    conceptos = [c.strip() for c in datos.pop("conceptos_clave", []) if c and c.strip()]
    prerrequisitos = [p.strip() for p in datos.pop("prerrequisitos", []) if p and p.strip()]
    return schema.model_validate(datos), conceptos[:6], prerrequisitos[:3]


def _redactar(
    llm: LLMClient,
    schema: type,
    titulo: str,
    perfil: str,
    nicho: str,
    nivel_detalle: str,
    chunks_evidencia: list[dict],
    retroalimentacion: str = "",
    idioma: str = "es",
) -> tuple[ContenidoAdaptado, list[str], list[str]]:
    user_payload = {
        "documento_titulo": titulo,
        "perfil": perfil,
        "nicho": nicho,
        "nivel_detalle": nivel_detalle,
        "chunks": chunks_evidencia,
        "retroalimentacion_critico": retroalimentacion,
    }
    formato = schema.model_fields["formato"].default
    system = construir_prompt_sistema(formato, perfil, nicho, nivel_detalle, idioma)
    respuesta = llm.generar_estructurado(
        _con_metadatos(schema), system=system, user=json.dumps(user_payload, ensure_ascii=False)
    )
    return _separar_metadatos(schema, respuesta)


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


def _posiciones_variadas(n: int, rng: random.Random) -> list[int]:
    """Posiciones (0-3) para la respuesta correcta de n preguntas: cada bloque de 4 es una
    permutación al azar de A-D, así quedan repartidas y nunca dos seguidas iguales."""
    posiciones: list[int] = []
    while len(posiciones) < n:
        bloque = rng.sample(range(4), 4)
        if posiciones and bloque[0] == posiciones[-1]:
            bloque = bloque[1:] + bloque[:1]
        posiciones.extend(bloque)
    return posiciones[:n]


def _mezclar_opciones(preguntas: list[dict]) -> None:
    """Reordena las opciones de cada pregunta del quiz para que la correcta no quede siempre
    en la misma letra (un LLM suele ponerla en la A). El orden depende del contenido del
    quiz: el mismo quiz se mezcla igual, uno distinto se mezcla distinto."""
    semilla = hashlib.sha256("\n".join(p["enunciado"] for p in preguntas).encode()).hexdigest()
    rng = random.Random(semilla)
    for p, destino in zip(preguntas, _posiciones_variadas(len(preguntas), rng)):
        correcta = p["opciones"][p["indice_correcto"]]
        distractores = [o for i, o in enumerate(p["opciones"]) if i != p["indice_correcto"]]
        rng.shuffle(distractores)
        distractores.insert(destino, correcta)
        p["opciones"] = distractores
        p["indice_correcto"] = destino


def _depurar(contenido: ContenidoAdaptado) -> ContenidoAdaptado:
    """Quita presuntos duplicados (tarjetas, preguntas, pasos, escenas, intervenciones y
    listas), vuelve a numerar en orden, sin huecos, y reparte la respuesta correcta del
    quiz entre las letras A-D. El Redactor, sobre todo el
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
    if "preguntas" in datos:
        _mezclar_opciones(datos["preguntas"])
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
    """Los títulos de sección del documento; si no tiene títulos útiles (texto pegado, PDF
    sin encabezados), los términos técnicos de su texto ("VCN", "Security Lists")."""
    conceptos: list[str] = []
    for c in chunks_evidencia:
        if c["seccion"] not in conceptos and c["seccion"] not in ("Documento completo", "Introducción"):
            conceptos.append(c["seccion"])
    if len(conceptos) < 3:
        texto = "\n".join(c["texto"] for c in chunks_evidencia)
        conceptos += extraer_conceptos(texto, maximo=maximo - len(conceptos), excluir=set(conceptos))
    return conceptos[:maximo]


# Cómo se adaptó el lenguaje a cada perfil (el ejemplo del enunciado describe la adaptación
# en `observaciones`); va antes del veredicto de fidelidad.
_ADAPTACION_POR_PERFIL = {
    "Principiante": "Lenguaje ajustado con explicaciones simples y analogías para público principiante, sin tecnicismos excesivos. ",
    "Desarrollador Junior/Semi Senior": "Enfoque práctico y paso a paso, orientado a la implementación. ",
    "Líder Técnico/Arquitecto": "Enfoque en criterios de diseño, dependencias y riesgos técnicos. ",
    "Gestor/Ejecutivo": "Enfoque en impacto, riesgos y decisiones, con la jerga técnica justa. ",
}


def _claridad_desde_score(score: float) -> ClaridadPedagogica:
    if score >= 0.85:
        return ClaridadPedagogica.ALTA
    if score >= 0.6:
        return ClaridadPedagogica.MEDIA
    return ClaridadPedagogica.BAJA


class EstadoFlujo(TypedDict, total=False):
    """Estado que comparten los nodos del grafo."""

    # entrada
    documento_titulo: str
    documento_contenido: str
    perfil: str
    formato: str
    nicho: str
    nivel_detalle: str
    idioma: str
    llm: Any
    # producido por los nodos
    t0: float
    tiempos: dict[str, float]
    coleccion: ColeccionDocumento
    schema: type
    plan: PlanPedagogico
    chunks_evidencia: list[dict]
    umbral: float
    intento: int
    contenido: ContenidoAdaptado
    conceptos_ia: list[str]  # redactados por el modelo; vacíos con el generador local
    prerrequisitos_ia: list[str]
    contenido_anterior: ContenidoAdaptado | None
    evaluacion_fidelidad: ResultadoFidelidad
    retroalimentacion: str
    juicio: JuicioIA | None  # del juez de IA, si revisó este intento
    aprobado: bool
    decision: str  # "reintentar" | "terminar"
    resultado: ResultadoGeneracion


def _cronometrar(estado: EstadoFlujo, clave: str, desde: float, escala: float = 1000, acumular: bool = False) -> dict:
    tiempos = dict(estado.get("tiempos", {}))
    valor = (time.perf_counter() - desde) * escala
    tiempos[clave] = round(tiempos.get(clave, 0.0) + valor if acumular else valor, 3 if escala == 1 else 2)
    return tiempos


def _nodo_indexar(estado: EstadoFlujo) -> dict:
    schema = _SCHEMA_POR_FORMATO.get(estado["formato"])
    if schema is None:
        raise ValueError(f"Formato no soportado: {estado['formato']}")
    t = time.perf_counter()
    coleccion = indexar_documento(estado["documento_titulo"], estado["documento_contenido"])
    return {"coleccion": coleccion, "schema": schema, "tiempos": _cronometrar(estado, "indexacion_rag_ms", t)}


def _nodo_planificar(estado: EstadoFlujo) -> dict:
    """Agente Planificador: secuencia didáctica, conceptos clave y prerrequisitos."""
    t = time.perf_counter()
    plan = _planificar(estado["coleccion"], estado["formato"], perfil=estado["perfil"], nicho=estado["nicho"])
    return {"plan": plan, "tiempos": _cronometrar(estado, "planificador_ms", t)}


def _nodo_investigar(estado: EstadoFlujo) -> dict:
    """Agente Investigador RAG: evidencia por sección."""
    t = time.perf_counter()
    chunks_evidencia = _investigar(estado["coleccion"], estado["plan"].secciones)
    if not chunks_evidencia:
        raise LLMError("El Investigador no encontró evidencia recuperable en el documento.")
    return {
        "chunks_evidencia": chunks_evidencia,
        "umbral": settings.fidelity_min_for(estado["nicho"]),
        "intento": 0,
        "retroalimentacion": "",
        "contenido_anterior": None,
        "aprobado": False,
        "tiempos": _cronometrar(estado, "investigador_ms", t),
    }


def _nodo_redactar(estado: EstadoFlujo) -> dict:
    """Agente Redactor: única llamada pesada al LLM generativo estructurado."""
    t = time.perf_counter()
    redactado, conceptos, prerrequisitos = _redactar(
        estado["llm"], estado["schema"], estado["documento_titulo"], estado["perfil"], estado["nicho"],
        estado["nivel_detalle"], estado["chunks_evidencia"], estado["retroalimentacion"],
        estado.get("idioma", "es"),
    )
    contenido = _depurar(redactado)
    return {
        "contenido": contenido,
        "conceptos_ia": conceptos,
        "prerrequisitos_ia": prerrequisitos,
        "contenido_anterior": estado.get("contenido"),
        "intento": estado["intento"] + 1,
        "tiempos": _cronometrar(estado, "redactor_segundos", t, escala=1, acumular=True),
    }


def _retroalimentacion(evaluacion: ResultadoFidelidad, umbral: float) -> str:
    """Lo que el Crítico le pide corregir al Redactor, concreto y específico."""
    partes: list[str] = []
    if evaluacion.no_sustentadas:
        partes.append(
            f"Afirmaciones NO sustentadas por la fuente: {evaluacion.no_sustentadas[:3]}. "
            "Elimínalas o ajústalas para que solo usen la evidencia textual dada."
        )
    parciales = getattr(evaluacion, "parciales_afirmaciones", [])
    if parciales:
        partes.append(
            f"Afirmaciones con anclaje débil o parcial: {parciales[:3]}. "
            "Asegura una conexión conceptual y terminológica más estrecha con el chunk citado."
        )
    if not partes:
        partes.append(
            f"El score de fidelidad ({evaluacion.score:.2f}) no alcanzó el umbral requerido ({umbral:.2f}). "
            "Alinea las afirmaciones con mayor fidelidad a los hechos y términos de los chunks de evidencia."
        )
    return " ".join(partes)


def _nodo_criticar(estado: EstadoFlujo) -> dict:
    """Agente Crítico: verifica la fidelidad y decide si se aprueba o se reintenta."""
    t = time.perf_counter()
    evaluacion = evaluar_fidelidad(estado["contenido"], estado["coleccion"])
    juicio = None
    if evaluacion.total and evaluacion.score < estado["umbral"] and juez_disponible(estado["llm"]):
        # el TF-IDF no alcanza: el juez de IA revisa las dudosas (paráfrasis, traducciones)
        juicio = _juzgar(estado, evaluacion)
    cambios = {
        "evaluacion_fidelidad": evaluacion, "juicio": juicio,
        "tiempos": _cronometrar(estado, "critico_ms", t, acumular=True),
    }
    if evaluacion.total == 0:
        # Sin afirmaciones con fuente no hay nada que verificar: no se aprueba (sería dar
        # por fiel algo que nadie comprobó) y reintentar no lo arregla.
        return {**cambios, "decision": "terminar"}
    if evaluacion.score >= estado["umbral"]:
        return {**cambios, "aprobado": True, "decision": "terminar"}
    sin_intentos = estado["intento"] >= settings.max_reintentos_critico + 1
    # un generador determinista (p. ej. TemplateLLM) ignora la retroalimentación y repetiría lo mismo
    sin_mejora = estado["contenido"] == estado.get("contenido_anterior")
    if sin_intentos or sin_mejora:
        return {**cambios, "decision": "terminar"}
    return {**cambios, "decision": "reintentar", "retroalimentacion": _retroalimentacion(evaluacion, estado["umbral"])}


def _juzgar(estado: EstadoFlujo, evaluacion: ResultadoFidelidad) -> JuicioIA | None:
    return juzgar(
        estado["llm"], estado["contenido"], evaluacion, estado["coleccion"],
        formato=estado["formato"], perfil=estado["perfil"], nicho=estado["nicho"],
    )


def _nodo_finalizar(estado: EstadoFlujo) -> dict:
    """Metadatos de aprendizaje y evaluación de calidad del resultado final."""
    contenido, coleccion, evaluacion_fidelidad = estado["contenido"], estado["coleccion"], estado["evaluacion_fidelidad"]
    juicio = estado.get("juicio")
    if juicio is None and juez_disponible(estado["llm"]):
        # aprobado por el TF-IDF: el juez evalúa la coherencia didáctica (y revisa las parciales)
        juicio = _juzgar(estado, evaluacion_fidelidad)
    perfil, aprobado, plan = estado["perfil"], estado["aprobado"], estado["plan"]
    _asignar_secciones(contenido, coleccion)
    _agrupar_por_seccion(contenido, coleccion)
    sin_afirmaciones = evaluacion_fidelidad.total == 0
    score_final = 0.0 if sin_afirmaciones else evaluacion_fidelidad.score
    tiempos = estado["tiempos"]

    metadatos = Metadatos(
        perfil_aplicado=perfil,
        formato_generado=estado["formato"],
        tiempo_estimado_estudio_minutos=_calcular_tiempo_estudio(contenido),
        # los del modelo (HU-32); si no los dio (generador local), los del Planificador
        conceptos_clave=estado.get("conceptos_ia") or plan.conceptos_clave or _conceptos_clave(estado["chunks_evidencia"]),
        prerrequisitos=estado.get("prerrequisitos_ia") or plan.prerrequisitos,
        tiempo_generacion_segundos=round(time.perf_counter() - estado["t0"], 3),
        modelo_llm=estado["llm"].nombre_modelo,
        modelo_embeddings=coleccion.modelo_embeddings,
        desde_cache=False,
        tiempos_por_agente={
            "indexacion_rag_ms": tiempos.get("indexacion_rag_ms", 0.0),
            "planificador_ms": tiempos.get("planificador_ms", 0.0),
            "investigador_ms": tiempos.get("investigador_ms", 0.0),
            "redactor_segundos": tiempos.get("redactor_segundos", 0.0),
            "critico_ms": tiempos.get("critico_ms", 0.0),
        },
    )
    evaluacion = EvaluacionCalidad(
        anclaje_fuente_score=round(score_final, 4),
        # HU-37: la claridad la da el juez de IA si evaluó la coherencia; si no, se deriva del score
        claridad_pedagogica=juicio.coherencia_didactica if juicio else _claridad_desde_score(score_final),
        observaciones=_ADAPTACION_POR_PERFIL.get(perfil, "") + (
            "Aprobado por el Crítico dentro del umbral de fidelidad."
            if aprobado
            else "El contenido no trae afirmaciones con fuente declarada; no se pudo verificar "
            "su fidelidad contra el documento."
            if sin_afirmaciones
            else "No se alcanzó el umbral de fidelidad tras los reintentos; se devuelve el "
            "mejor resultado con las afirmaciones no sustentadas señaladas."
        ),
        afirmaciones_total=evaluacion_fidelidad.total,
        afirmaciones_sustentadas=evaluacion_fidelidad.sustentadas,
        afirmaciones_no_sustentadas=evaluacion_fidelidad.no_sustentadas,
        umbral_aplicado=estado["umbral"],
        aprobado_por_critico=aprobado,
        juez_fidelidad="tfidf+ia" if juicio else "tfidf",
        coherencia_didactica=juicio.coherencia_didactica if juicio else "",
        comentario_coherencia=juicio.comentario_coherencia if juicio else "",
    )
    return {"resultado": ResultadoGeneracion(contenido=contenido, metadatos=metadatos, evaluacion=evaluacion, coleccion=coleccion)}


def construir_grafo():
    """Compila el grafo de agentes (se compila una vez y se reutiliza)."""
    grafo = StateGraph(EstadoFlujo)
    grafo.add_node("indexar", _nodo_indexar)
    grafo.add_node("planificar", _nodo_planificar)
    grafo.add_node("investigar", _nodo_investigar)
    grafo.add_node("redactar", _nodo_redactar)
    grafo.add_node("criticar", _nodo_criticar)
    grafo.add_node("finalizar", _nodo_finalizar)
    grafo.add_edge(START, "indexar")
    grafo.add_edge("indexar", "planificar")
    grafo.add_edge("planificar", "investigar")
    grafo.add_edge("investigar", "redactar")
    grafo.add_edge("redactar", "criticar")
    grafo.add_conditional_edges("criticar", lambda e: e["decision"], {"reintentar": "redactar", "terminar": "finalizar"})
    grafo.add_edge("finalizar", END)
    return grafo.compile()


GRAFO = construir_grafo()


def generar_contenido_educativo(
    documento_titulo: str,
    documento_contenido: str,
    perfil: str,
    formato: str,
    nicho: str,
    nivel_detalle: str,
    llm: LLMClient | None = None,
    idioma: str = "es",
) -> ResultadoGeneracion:
    """Punto de entrada del flujo completo: ejecuta el grafo de agentes (indexar,
    planificar, investigar, redactar, criticar con reintento y finalizar)."""
    if formato not in _SCHEMA_POR_FORMATO:
        raise ValueError(f"Formato no soportado: {formato}")
    estado = GRAFO.invoke(
        {
            "documento_titulo": documento_titulo,
            "documento_contenido": documento_contenido,
            "perfil": perfil,
            "formato": formato,
            "nicho": nicho,
            "nivel_detalle": nivel_detalle,
            "idioma": idioma,
            "llm": llm or crear_llm(),
            "t0": time.perf_counter(),
            "tiempos": {},
        },
        # el ciclo redactar -> criticar repite 2 nodos por reintento
        {"recursion_limit": 10 + 2 * (settings.max_reintentos_critico + 1)},
    )
    return estado["resultado"]
