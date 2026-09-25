"""TemplateLLM: generador estructurado determinista, sin llamadas de red.

Responsable en el equipo Kairos G10: Adrian Gil (ML Engineer).

Por qué existe: este entorno de desarrollo no tiene acceso de red a las APIs de
Gemini/OpenAI/Anthropic (ver <network_configuration> del sandbox), así que no es
posible ejecutar aquí una llamada real a un LLM externo. En vez de simular la
respuesta con datos inventados, TemplateLLM hace generación EXTRACTIVA real:
selecciona y reordena oraciones de los chunks recuperados (RAG), con heurísticas
por perfil y nicho, y siempre etiqueta de qué chunk_id sale cada afirmación.

Esto cumple dos cosas a la vez:
  1. El pipeline completo (ingesta -> RAG -> generación -> fidelidad -> OCI)
     corre de verdad, con datos derivados del documento real, no mockeados.
  2. Cuando el equipo agregue su GEMINI_API_KEY en su propia máquina, basta con
     implementar `GeminiLLMClient` con la misma interfaz `LLMClient` (ver
     llm/base.py) y cambiar LLM_PROVIDER=gemini en el .env: el resto del código
     (agents/, fidelity/, api/) no cambia.
"""
from __future__ import annotations

import hashlib
import json
import re

from nuevamente.llm.base import LLMError
from nuevamente.schemas.formatos import (
    ContenidoAdaptado,
    FlashcardItem,
    FlashcardsContenido,
    GuionDeClaseContenido,
    GuionEscena,
    QuizContenido,
    QuizPregunta,
    ResumenEjecutivoContenido,
    TutorialContenido,
    TutorialPaso,
)

_RELLENO_QUIZ = [
    "No se menciona en el documento proporcionado.",
    "El documento no aborda este punto.",
    "Ninguna de las otras opciones.",
]

_SEP_ORACIONES = re.compile(r"(?<=[.!?])\s+")

_ANALOGIA_POR_NICHO = {
    "Salud": "Piénsalo como un protocolo que protege tanto al paciente como al personal.",
    "Fintech": "Piénsalo como una regla que protege tanto al cliente como a la entidad financiera.",
    "E-commerce": "Piénsalo como una regla que protege tanto al comprador como a la tienda.",
    "General": "Piénsalo como una regla práctica que evita errores costosos.",
}

_RIESGO_POR_NICHO = {
    "Salud": "Un error aquí puede afectar la seguridad del paciente o incumplir normativa sanitaria.",
    "Fintech": "Un error aquí puede generar pérdidas económicas o incumplimiento regulatorio.",
    "E-commerce": "Un error aquí puede afectar la experiencia del cliente o generar pérdidas.",
    "General": "Un error aquí puede generar retrabajo o confusión en el equipo.",
}


def _oraciones(texto: str) -> list[str]:
    # " ".join(o.split()) quita los saltos de línea internos del Markdown fuente
    partes = [" ".join(o.split()) for o in _SEP_ORACIONES.split(texto) if o.strip()]
    partes = [o for o in partes if len(o) > 12]
    # Por el solapamiento del chunking, un chunk puede empezar a mitad de una
    # oración de la anterior. Si el primer fragmento no arranca con mayúscula
    # y hay más fragmentos disponibles, se descarta para no mostrar una frase
    # cortada como si fuera el inicio de la afirmación.
    if len(partes) > 1 and partes[0] and not partes[0][0].isupper():
        partes = partes[1:]
    return partes


def _primeras(texto: str, n: int = 1) -> str:
    oraciones = _oraciones(texto)
    if not oraciones:
        return texto[:200].strip()
    return " ".join(oraciones[:n])


def _hash_int(texto: str) -> int:
    return int(hashlib.sha256(texto.encode("utf-8")).hexdigest(), 16)


def _oraciones_por_nivel(base: int, nivel_detalle: str) -> int:
    """Conciso recorta a 1 oración, Profundo agrega una más, Didáctico deja la base."""
    if nivel_detalle == "Conciso":
        return 1
    if nivel_detalle == "Profundo":
        return base + 1
    return base


def _adaptar_por_perfil(texto: str, perfil: str, nivel_detalle: str = "Didáctico") -> str:
    """Ajusta el nivel de detalle según el perfil, de forma determinista y trazable."""
    if perfil == "Principiante":
        return f"En palabras simples: {_primeras(texto, _oraciones_por_nivel(1, nivel_detalle))}"
    if perfil == "Gestor/Ejecutivo":
        return f"Lo importante para la gestión: {_primeras(texto, _oraciones_por_nivel(1, nivel_detalle))}"
    # Líder Técnico/Arquitecto y Desarrollador Junior/Semi Senior
    return _primeras(texto, _oraciones_por_nivel(2, nivel_detalle))


class TemplateLLM:
    """Implementación de LLMClient sin red, usada como proveedor por defecto."""

    def __init__(self) -> None:
        self.nombre_modelo = "template-extractivo-v1"

    def generar_estructurado(self, schema: type, system: str, user: str):
        try:
            payload = json.loads(user)
        except json.JSONDecodeError as exc:
            raise LLMError(f"El prompt de usuario no es JSON válido: {exc}") from exc

        chunks: list[dict] = payload.get("chunks", [])
        if not chunks:
            raise LLMError("No hay chunks de evidencia para generar contenido (RAG vacío).")

        perfil = payload.get("perfil", "Principiante")
        nicho = payload.get("nicho", "General")
        titulo = payload.get("documento_titulo", "Documento")
        nivel = payload.get("nivel_detalle", "Didáctico")

        if schema is FlashcardsContenido:
            return self._flashcards(titulo, perfil, nicho, nivel, chunks)
        if schema is QuizContenido:
            return self._quiz(titulo, chunks)
        if schema is TutorialContenido:
            return self._tutorial(titulo, nicho, chunks)
        if schema is ResumenEjecutivoContenido:
            return self._resumen_ejecutivo(titulo, nicho, nivel, chunks)
        if schema is GuionDeClaseContenido:
            return self._guion_de_clase(titulo, nivel, chunks)

        raise LLMError(f"TemplateLLM no soporta el esquema {schema!r}")

    # ---- Flashcards ----
    def _flashcards(self, titulo, perfil, nicho, nivel, chunks) -> FlashcardsContenido:
        items = []
        for c in chunks[:12]:
            dorso = _adaptar_por_perfil(c["texto"], perfil, nivel)
            items.append(
                FlashcardItem(
                    frente=f"¿Qué debes saber sobre \"{c['seccion']}\"?",
                    dorso=dorso,
                    pista_didactica=_ANALOGIA_POR_NICHO.get(nicho, _ANALOGIA_POR_NICHO["General"]),
                    fuentes=[c["chunk_id"]],
                )
            )
        return FlashcardsContenido(
            titulo=f"Guía rápida: {titulo}",
            introduccion_contextualizada=(
                f"Este material resume, en tarjetas de estudio, los puntos clave de \"{titulo}\", "
                f"adaptado para el perfil {perfil}."
            ),
            items=items,
        )

    # ---- Quiz ----
    def _quiz(self, titulo, chunks) -> QuizContenido:
        preguntas = []
        primeras_por_chunk = [_primeras(c["texto"], 1) for c in chunks]
        for i, c in enumerate(chunks[:10]):
            correcta = primeras_por_chunk[i]
            # Distractores sin repetidos ni iguales a la correcta; si el documento no da
            # suficientes, se completan con opciones de relleno distintas entre sí.
            candidatos = [s for s in primeras_por_chunk if s != correcta] + _RELLENO_QUIZ
            distractores = list(dict.fromkeys(candidatos))[:3]
            posicion_correcta = _hash_int(c["chunk_id"]) % 4
            opciones = distractores[:]
            opciones.insert(posicion_correcta, correcta)
            opciones = opciones[:4]
            preguntas.append(
                QuizPregunta(
                    enunciado=f"Según el documento, ¿qué afirmación sobre \"{c['seccion']}\" es correcta?",
                    opciones=opciones,
                    indice_correcto=posicion_correcta,
                    justificacion=f"La fuente indica: {correcta}",
                    fuentes=[c["chunk_id"]],
                )
            )
        return QuizContenido(titulo=f"Quiz: {titulo}", preguntas=preguntas)

    # ---- Tutorial ----
    def _tutorial(self, titulo, nicho, chunks) -> TutorialContenido:
        pasos = []
        for i, c in enumerate(chunks[:10], start=1):
            oraciones = _oraciones(c["texto"])
            instruccion = oraciones[0] if oraciones else c["texto"][:200]
            resultado = oraciones[1] if len(oraciones) > 1 else ""
            pasos.append(
                TutorialPaso(
                    orden=i,
                    titulo=c["seccion"],
                    instruccion=instruccion,
                    resultado_esperado=resultado,
                    fuentes=[c["chunk_id"]],
                )
            )
        return TutorialContenido(
            objetivo=f"Aplicar correctamente los pasos descritos en \"{titulo}\".",
            prerrequisitos=[],
            pasos=pasos,
            errores_comunes=[
                f"Omitir un paso porque parece obvio. {_RIESGO_POR_NICHO.get(nicho, _RIESGO_POR_NICHO['General'])}"
            ],
            # una sección puede aportar varios chunks: el checklist lista cada sección una vez
            checklist_final=[f"Verificado: {s}" for s in dict.fromkeys(c["seccion"] for c in chunks[:10])],
        )

    # ---- Resumen Ejecutivo ----
    def _resumen_ejecutivo(self, titulo, nicho, nivel, chunks) -> ResumenEjecutivoContenido:
        n_chunks = {"Conciso": 4, "Profundo": 8}.get(nivel, 6)
        usados = chunks[:n_chunks]
        oraciones = [_primeras(c["texto"], 1) for c in usados]
        resumen = " ".join(oraciones)
        if len(resumen) > 1700:
            resumen = resumen[:1700].rsplit(" ", 1)[0] + "…"
        puntos_clave: list[str] = []
        for c in chunks:
            if c["seccion"] not in puntos_clave:
                puntos_clave.append(c["seccion"])
            if len(puntos_clave) >= 5:
                break
        return ResumenEjecutivoContenido(
            resumen=resumen or f"Resumen de \"{titulo}\".",
            puntos_clave=puntos_clave or [titulo],
            decisiones_o_riesgos=[_RIESGO_POR_NICHO.get(nicho, _RIESGO_POR_NICHO["General"])],
            impacto_de_negocio=(
                f"Adoptar lo descrito en \"{titulo}\" reduce el riesgo operativo y facilita "
                f"el cumplimiento en el sector {nicho}."
            ),
            fuentes=[c["chunk_id"] for c in usados],
        )

    # ---- Guion de Clase ----
    def _guion_de_clase(self, titulo, nivel, chunks) -> GuionDeClaseContenido:
        escenas = []
        duracion_total = 0
        for i, c in enumerate(chunks[:8], start=1):
            narracion = _primeras(c["texto"], _oraciones_por_nivel(2, nivel))
            # ~11 caracteres por segundo: ritmo medido de la narración del video (exports/video.py)
            duracion = max(10, min(120, round(len(narracion) / 11)))
            duracion_total += duracion
            escenas.append(
                GuionEscena(
                    orden=i,
                    narracion=narracion,
                    apoyo_visual=f"Diapositiva: {c['seccion']}",
                    duracion_seg=duracion,
                    fuentes=[c["chunk_id"]],
                )
            )
        return GuionDeClaseContenido(
            duracion_total_min=max(1, round(duracion_total / 60)),
            escenas=escenas,
        )
