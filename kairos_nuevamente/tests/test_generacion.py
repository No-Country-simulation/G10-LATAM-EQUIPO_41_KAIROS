"""Tests del generador y del flujo del Crítico. Responsable: Diana Dure (QA Tester)."""
import pytest

from nuevamente.agents.graph import generar_contenido_educativo
from nuevamente.fidelity.verifier import evaluar_fidelidad
from nuevamente.ingest.chunking import chunkear_documento
from nuevamente.rag.vectorstore import indexar_documento
from nuevamente.schemas.formatos import GuionDeClaseContenido, GuionEscena, ResumenEjecutivoContenido


def _generar(documento, formato, nivel="Didáctico"):
    return generar_contenido_educativo(
        documento_titulo="Protocolo",
        documento_contenido=documento,
        perfil="Principiante",
        formato=formato,
        nicho="Salud",
        nivel_detalle=nivel,
    )


@pytest.mark.parametrize("formato", ["Resumen Ejecutivo", "Guion de Clase"])
def test_formatos_de_sintesis_se_verifican(documento_salud, formato):
    """Resumen y Guion ya no se aprueban sin verificar: traen afirmaciones con fuente."""
    r = _generar(documento_salud, formato)
    assert r.evaluacion.afirmaciones_total > 0
    assert r.evaluacion.aprobado_por_critico


def test_resumen_con_oracion_inventada_queda_no_sustentada(documento_salud):
    coleccion = indexar_documento("Protocolo", documento_salud)
    ids = [c.chunk_id for c in coleccion.chunks]
    contenido = ResumenEjecutivoContenido(
        resumen=(
            "El lavado de manos con agua y jabon durante al menos 20 segundos elimina la mayoria "
            "de los microorganismos. Los guantes de neopreno reducen el riesgo de electrocucion en quirofano."
        ),
        puntos_clave=["Lavado de manos"],
        fuentes=ids,
    )
    resultado = evaluar_fidelidad(contenido, coleccion)
    assert resultado.total == 2
    assert resultado.no_sustentadas == [
        "Los guantes de neopreno reducen el riesgo de electrocucion en quirofano."
    ]


def test_guion_sin_fuentes_no_se_aprueba(documento_salud, monkeypatch):
    """Si el generador no declara fuentes, no hay fidelidad que medir: no se aprueba ni vale 1.0."""
    from nuevamente.llm.template_llm import TemplateLLM

    class SinFuentes(TemplateLLM):
        def generar_estructurado(self, schema, system, user):
            return GuionDeClaseContenido(
                duracion_total_min=1,
                escenas=[GuionEscena(orden=1, narracion="Texto cualquiera.", duracion_seg=30)],
            )

    r = generar_contenido_educativo(
        "Protocolo", documento_salud, "Principiante", "Guion de Clase", "Salud", "Didáctico", llm=SinFuentes()
    )
    assert r.evaluacion.aprobado_por_critico is False
    assert r.evaluacion.anclaje_fuente_score == 0.0


def test_quiz_opciones_distintas_con_documento_de_un_chunk():
    r = _generar("El lavado de manos con agua y jabon elimina la mayoria de los microorganismos.", "Quiz")
    for pregunta in r.contenido.preguntas:
        assert len(set(pregunta.opciones)) == 4
        assert all("\n" not in o for o in pregunta.opciones)


def test_nivel_de_detalle_cambia_la_extension(documento_salud):
    def palabras(r):
        return sum(len(i.dorso.split()) for i in r.contenido.items)

    conciso = _generar(documento_salud * 2, "Flashcards", "Conciso")
    profundo = _generar(documento_salud * 2, "Flashcards", "Profundo")
    assert palabras(profundo) > palabras(conciso)


def test_doc_id_distingue_documentos_que_difieren_despues_del_inicio():
    base = "a" * 600
    assert chunkear_documento("Doc", base + "x")[0].doc_id != chunkear_documento("Doc", base + "y")[0].doc_id
