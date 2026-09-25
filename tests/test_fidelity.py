"""Tests del verificador de fidelidad. Responsable: Diana Dure (QA Tester)."""
from nuevamente.fidelity.verifier import evaluar_fidelidad, verificar_afirmacion
from nuevamente.rag.vectorstore import indexar_documento
from nuevamente.schemas.enums import VeredictoFidelidad
from nuevamente.schemas.formatos import FlashcardItem, FlashcardsContenido


def test_afirmacion_fiel_queda_sustentada(documento_salud):
    coleccion = indexar_documento("Protocolo", documento_salud)
    chunk_id = coleccion.chunks[0].chunk_id
    v = verificar_afirmacion(
        "El lavado de manos con agua y jabon elimina microorganismos de las manos.",
        chunk_id,
        coleccion,
    )
    assert v.veredicto == VeredictoFidelidad.SUSTENTADA


def test_afirmacion_inventada_queda_no_sustentada(documento_salud):
    coleccion = indexar_documento("Protocolo", documento_salud)
    chunk_id = coleccion.chunks[0].chunk_id  # chunk de "Lavado de manos"
    v = verificar_afirmacion(
        "Los guantes de neopreno reducen el riesgo de electrocucion en quirofano.",
        chunk_id,
        coleccion,
    )
    assert v.veredicto == VeredictoFidelidad.NO_SUSTENTADA


def test_chunk_id_inexistente_es_no_sustentada(documento_salud):
    coleccion = indexar_documento("Protocolo", documento_salud)
    v = verificar_afirmacion("Cualquier afirmación.", "chunk-que-no-existe", coleccion)
    assert v.veredicto == VeredictoFidelidad.NO_SUSTENTADA


def test_score_es_1_cuando_no_hay_afirmaciones():
    from nuevamente.fidelity.verifier import ResultadoFidelidad

    assert ResultadoFidelidad().score == 1.0


def test_evaluar_fidelidad_sobre_flashcards_completas(documento_salud):
    coleccion = indexar_documento("Protocolo", documento_salud)
    chunk_id = coleccion.chunks[0].chunk_id
    contenido = FlashcardsContenido(
        titulo="Prueba",
        introduccion_contextualizada="Intro",
        items=[
            FlashcardItem(
                frente="¿Qué hace el lavado de manos?",
                dorso="El lavado de manos con agua y jabon elimina microorganismos de las manos.",
                fuentes=[chunk_id],
            ),
            FlashcardItem(
                frente="¿Qué reduce la electrocución?",
                dorso="Los guantes de neopreno reducen el riesgo de electrocucion en quirofano.",
                fuentes=[chunk_id],
            ),
        ],
    )
    resultado = evaluar_fidelidad(contenido, coleccion)
    assert resultado.total == 2
    assert resultado.sustentadas == 1
    assert len(resultado.no_sustentadas) == 1
    assert 0.0 <= resultado.score <= 1.0
