"""Tests de indexación y recuperación. Responsable: Diana Dure (QA Tester)."""
from nuevamente.rag.vectorstore import indexar_documento


def test_recuperacion_devuelve_seccion_mas_relevante(documento_salud):
    coleccion = indexar_documento("Protocolo", documento_salud)
    resultados = coleccion.buscar("como desechar residuos biocontaminados", top_k=1)
    assert resultados[0].chunk.seccion == "Manejo de residuos"


def test_buscar_por_seccion_filtra_correctamente(documento_salud):
    coleccion = indexar_documento("Protocolo", documento_salud)
    resultados = coleccion.buscar_por_seccion("Lavado de manos", "Lavado de manos", top_k=5)
    assert all(r.chunk.seccion == "Lavado de manos" for r in resultados)


def test_secciones_cubren_todo_el_documento(documento_salud):
    coleccion = indexar_documento("Protocolo", documento_salud)
    assert len(coleccion.secciones()) == 3
