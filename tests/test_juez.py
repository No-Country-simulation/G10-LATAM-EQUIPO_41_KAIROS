"""Juez de fidelidad y coherencia con IA (HU-37, HU-38). Responsable: Diana Dure (QA Tester)."""
from __future__ import annotations

import dataclasses
import json

from nuevamente.agents import graph
from nuevamente.fidelity import juez
from nuevamente.fidelity.juez import JuicioIA, cita_valida

_PARAFRASIS = "Frotarse las palmas con jabón un buen rato quita casi todos los gérmenes."


def test_la_cita_debe_existir_en_el_fragmento():
    chunk = "El lavado de manos con agua y jabón durante al menos 20 segundos elimina la mayoría de los microorganismos."
    assert cita_valida("con agua y jabón durante al menos 20 segundos", chunk)
    assert cita_valida("«Con agua y JABÓN durante al menos 20 segundos»", chunk)  # comillas y mayúsculas no importan
    assert not cita_valida("con agua tibia durante 60 segundos", chunk)  # inventada
    assert not cita_valida("jabón", chunk)  # demasiado corta para demostrar algo


class _LLMConJuez:
    """Redacta una paráfrasis que el TF-IDF no reconoce y, como juez, la respalda con `cita`."""

    nombre_modelo = "doble-con-juez"

    def __init__(self, *citas: str):
        self.citas = list(citas)
        self.juicios = 0

    def generar_estructurado(self, schema, system, user):
        if schema is JuicioIA:
            self.juicios += 1
            afirmaciones = json.loads(user)["afirmaciones"]
            return JuicioIA(
                veredictos=[{"indice": a["indice"], "veredicto": "sustentada", "citas": self.citas} for a in afirmaciones],
                coherencia_didactica="Alta", comentario_coherencia="Progresión clara para principiantes.",
            )
        chunk = json.loads(user)["chunks"][0]
        return schema.model_validate({
            "titulo": "Repaso", "introduccion_contextualizada": "Tarjetas.",
            "items": [{"frente": "¿Qué logra el lavado?", "dorso": _PARAFRASIS, "fuentes": [chunk["chunk_id"]]}],
        })


def _generar(monkeypatch, documento_salud, llm):
    monkeypatch.setattr(juez, "settings", dataclasses.replace(juez.settings, juez_ia="auto"))
    return graph.generar_contenido_educativo(
        "Protocolo", documento_salud, "Principiante", "Flashcards", "Salud", "Didáctico", llm=llm,
    )


def test_el_juez_aprueba_una_parafrasis_fiel_con_cita_verificada(monkeypatch, documento_salud):
    llm = _LLMConJuez("elimina la mayoria de los microorganismos de las manos")
    r = _generar(monkeypatch, documento_salud, llm)
    assert r.evaluacion.aprobado_por_critico and r.evaluacion.anclaje_fuente_score == 1.0
    assert r.evaluacion.juez_fidelidad == "tfidf+ia"
    assert r.evaluacion.coherencia_didactica == "Alta" and r.evaluacion.claridad_pedagogica == "Alta"
    assert llm.juicios == 1  # una sola solicitud: fidelidad de las dudosas + coherencia


def test_una_cita_inventada_no_convence_al_juez(monkeypatch, documento_salud):
    llm = _LLMConJuez("frotarse con jabón un buen rato elimina todos los gérmenes")
    r = _generar(monkeypatch, documento_salud, llm)
    assert not r.evaluacion.aprobado_por_critico
    assert _PARAFRASIS in r.evaluacion.afirmaciones_no_sustentadas


def test_sin_ia_queda_el_tfidf(documento_salud):
    """Con el generador local (o JUEZ_IA=off) no hay juez: claridad derivada del score."""
    r = graph.generar_contenido_educativo("Protocolo", documento_salud, "Principiante", "Quiz", "Salud", "Didáctico")
    assert r.evaluacion.juez_fidelidad == "tfidf" and r.evaluacion.coherencia_didactica == ""


def test_una_sintesis_necesita_que_todas_sus_citas_existan(monkeypatch, documento_salud):
    """Una oración que une dos secciones se aprueba con una cita real de cada una; si una de
    las citas es inventada, no se aprueba."""
    reales = ("elimina la mayoria de los microorganismos de las manos",
              "deben separarse en bolsas rojas y desecharse")
    r = _generar(monkeypatch, documento_salud, _LLMConJuez(*reales))
    assert r.evaluacion.aprobado_por_critico
    r = _generar(monkeypatch, documento_salud, _LLMConJuez(reales[0], "las bolsas se queman cada semana en el patio"))
    assert not r.evaluacion.aprobado_por_critico
