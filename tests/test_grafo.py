"""Grafo de agentes (LangGraph): estructura y ciclo Crítico -> Redactor. Responsable: Diana Dure (QA Tester)."""
from __future__ import annotations

import dataclasses
import json

from nuevamente.agents import graph


class _LLMQueAprende:
    """Primero inventa (no sustentado); con la retroalimentación del Crítico, cita la fuente."""

    nombre_modelo = "doble-de-prueba"

    def __init__(self):
        self.llamadas: list[str] = []

    def generar_estructurado(self, schema, system, user):
        datos = json.loads(user)
        self.llamadas.append(datos["retroalimentacion_critico"])
        chunk = datos["chunks"][0]
        dorso = (chunk["texto"] if datos["retroalimentacion_critico"]
                 else "Los satélites geoestacionarios orbitan a treinta y seis mil kilómetros de altura.")
        return schema.model_validate({
            "titulo": "Repaso", "introduccion_contextualizada": "Tarjetas de repaso.",
            "items": [{"frente": "¿Qué dice esta sección?", "dorso": dorso, "fuentes": [chunk["chunk_id"]]}],
        })


def test_el_grafo_tiene_un_nodo_por_agente():
    nodos = set(graph.GRAFO.get_graph().nodes)
    assert {"indexar", "planificar", "investigar", "redactar", "criticar", "finalizar"} <= nodos


def test_el_critico_devuelve_al_redactor_con_retroalimentacion(monkeypatch, documento_salud):
    monkeypatch.setattr(graph, "settings", dataclasses.replace(graph.settings, max_reintentos_critico=2))
    llm = _LLMQueAprende()
    resultado = graph.generar_contenido_educativo(
        "Protocolo", documento_salud, "Principiante", "Flashcards", "Salud", "Didáctico", llm=llm,
    )
    assert len(llm.llamadas) == 2  # redactó, el Crítico rechazó, redactó de nuevo
    assert llm.llamadas[0] == "" and "NO sustentadas" in llm.llamadas[1]
    assert resultado.evaluacion.aprobado_por_critico


def test_sin_reintentos_el_critico_no_aprueba_lo_inventado(documento_salud):
    llm = _LLMQueAprende()  # conftest: MAX_REINTENTOS_CRITICO=0
    resultado = graph.generar_contenido_educativo(
        "Protocolo", documento_salud, "Principiante", "Flashcards", "Salud", "Didáctico", llm=llm,
    )
    assert len(llm.llamadas) == 1
    assert not resultado.evaluacion.aprobado_por_critico
    assert resultado.evaluacion.afirmaciones_no_sustentadas


def test_los_metadatos_de_aprendizaje_los_redacta_el_modelo(documento_salud):
    """HU-32: conceptos clave y prerrequisitos salen de la misma respuesta del Redactor."""

    class _LLMConMetadatos:
        nombre_modelo = "doble-de-prueba"

        def generar_estructurado(self, schema, system, user):
            assert "conceptos_clave" in schema.model_fields and "[METADATOS DE APRENDIZAJE]" in system
            chunk = json.loads(user)["chunks"][0]
            return schema.model_validate({
                "titulo": "Repaso", "introduccion_contextualizada": "Tarjetas.",
                "items": [{"frente": "¿Qué dice?", "dorso": chunk["texto"], "fuentes": [chunk["chunk_id"]]}],
                "conceptos_clave": ["Lavado de manos", "EPP"], "prerrequisitos": ["Nociones de higiene"],
            })

    r = graph.generar_contenido_educativo(
        "Protocolo", documento_salud, "Principiante", "Flashcards", "Salud", "Didáctico", llm=_LLMConMetadatos(),
    )
    assert r.metadatos.conceptos_clave == ["Lavado de manos", "EPP"]
    assert r.metadatos.prerrequisitos == ["Nociones de higiene"]
    assert "conceptos_clave" not in r.contenido.model_dump()  # el material no cambia de forma
