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


@pytest.mark.parametrize("formato", ["Resumen Ejecutivo", "Guion de Clase", "Podcast"])
def test_formatos_de_sintesis_se_verifican(documento_salud, formato):
    """Resumen, Guion y Podcast no se aprueban sin verificar: traen afirmaciones con fuente."""
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


def test_si_el_proveedor_falla_se_usa_el_respaldo_local(documento_salud):
    from nuevamente.llm.base import LLMError
    from nuevamente.llm.factory import ConRespaldoLocal
    from nuevamente.llm.template_llm import TemplateLLM

    class SinCuota:
        nombre_modelo = "gemini-prueba"
        llamadas = 0

        def generar_estructurado(self, schema, system, user):
            SinCuota.llamadas += 1
            raise LLMError("429 RESOURCE_EXHAUSTED")

    llm = ConRespaldoLocal(SinCuota(), TemplateLLM())
    r = generar_contenido_educativo(
        "Protocolo", documento_salud, "Principiante", "Podcast", "Salud", "Didáctico", llm=llm
    )
    assert r.evaluacion.aprobado_por_critico
    assert r.metadatos.modelo_llm.startswith("template-extractivo-v1 (respaldo: gemini-prueba")
    assert SinCuota.llamadas == 1  # tras el primer fallo no vuelve a esperar a la API


def test_partes_agrupadas_por_seccion_con_el_titulo_que_corresponde(documento_salud):
    """Un LLM que alterna temas y cita chunks de dos secciones: cada tarjeta queda bajo la
    sección que de verdad sustenta su texto, y las de una misma sección quedan juntas."""
    from nuevamente.llm.template_llm import TemplateLLM
    from nuevamente.schemas.formatos import FlashcardItem, FlashcardsContenido

    ids = {c.seccion: c.chunk_id for c in chunkear_documento("Protocolo", documento_salud)}
    manos, epp, residuos = ids["Lavado de manos"], ids["Equipos de proteccion personal"], ids["Manejo de residuos"]

    class Desordenado(TemplateLLM):
        def generar_estructurado(self, schema, system, user):
            return FlashcardsContenido(
                titulo="Guía",
                introduccion_contextualizada="Intro",
                items=[
                    FlashcardItem(frente="¿Dónde van los residuos?", fuentes=[residuos],
                                  dorso="Los residuos biocontaminados deben separarse en bolsas rojas."),
                    # cita primero un chunk ajeno: la sección sale del que sustenta el texto
                    FlashcardItem(frente="¿Cuánto dura el lavado?", fuentes=[epp, manos],
                                  dorso="El lavado de manos con agua y jabon dura al menos 20 segundos."),
                    FlashcardItem(frente="¿Quién clasifica los residuos?", fuentes=[residuos],
                                  dorso="El personal debe estar capacitado en la clasificacion correcta de residuos."),
                    FlashcardItem(frente="¿Qué es el EPP?", fuentes=[epp],
                                  dorso="Los guantes, mascarillas y batas desechables forman parte del EPP."),
                ],
            )

    r = generar_contenido_educativo(
        "Protocolo", documento_salud, "Principiante", "Flashcards", "Salud", "Didáctico", llm=Desordenado()
    )
    assert [(i.seccion, i.frente) for i in r.contenido.items] == [
        ("Lavado de manos", "¿Cuánto dura el lavado?"),
        ("Equipos de proteccion personal", "¿Qué es el EPP?"),
        ("Manejo de residuos", "¿Dónde van los residuos?"),
        ("Manejo de residuos", "¿Quién clasifica los residuos?"),
    ]


def test_prompt_de_sistema_lleva_la_configuracion_y_las_reglas_de_fidelidad():
    from nuevamente.llm.prompts import construir_prompt_sistema
    from nuevamente.schemas.enums import FormatoSalida, NichoSector, NivelDetalle, PerfilDestinatario

    for perfil in PerfilDestinatario:
        for nicho in NichoSector:
            for nivel in NivelDetalle:
                for formato in FormatoSalida:
                    p = construir_prompt_sistema(formato.value, perfil.value, nicho.value, nivel.value)
                    assert f"- Perfil: {perfil.value}" in p and f"- Sector: {nicho.value}" in p
                    assert f'al formato "{formato.value}"' in p
                    assert "EXCLUSIVAMENTE la evidencia de los chunks" in p
                    # cada regla trae su texto: ningún valor de la web se queda sin prompt
                    assert ":\n\n" not in p and not p.rstrip().endswith("esquema.")


def test_reto_practico_del_tutorial_se_exporta():
    from nuevamente.exports import exportar_markdown
    from nuevamente.exports.documento import generar_documento
    from nuevamente.exports.presentacion import generar_presentacion
    from nuevamente.schemas.formatos import TutorialContenido

    c = TutorialContenido(
        objetivo="Lavarse las manos",
        pasos=[{"orden": 1, "titulo": "Lavado", "instruccion": "Lava tus manos 20 segundos."}],
        reto_practico="Cronometra tu próximo lavado de manos.",
    )
    assert "## Reto práctico\nCronometra" in exportar_markdown(c)
    assert generar_documento(c, "Protocolo") and generar_presentacion(c, "Protocolo")


def test_portada_antes_del_primer_titulo_no_llega_al_redactor():
    from nuevamente.agents.graph import _investigar

    texto = (
        "UNIVERSIDAD NACIONAL\nDD-IA-01\nAlgunos conceptos básicos\n2023\n"
        "# Algoritmo\nUn algoritmo es una fórmula o conjunto de reglas que resuelve un problema paso a paso.\n"
        "# Datos\nLos datos son unidades de información que describen hechos, personas u objetos.\n"
    )
    coleccion = indexar_documento("DD_IA_01", texto)
    evidencia = _investigar(coleccion, coleccion.secciones())
    assert [c["seccion"] for c in evidencia] == ["Algoritmo", "Datos"]


def test_documento_sin_titulos_toma_evidencia_de_todo_el_texto():
    from nuevamente.agents.graph import _EVIDENCIA_OBJETIVO, _investigar

    texto = " ".join(f"El concepto número {n} se explica con su propia definición." for n in range(400))
    coleccion = indexar_documento("Glosario", texto)
    assert len(coleccion.chunks) > _EVIDENCIA_OBJETIVO
    evidencia = _investigar(coleccion, coleccion.secciones())
    assert len(evidencia) == _EVIDENCIA_OBJETIVO
    ordenes = [coleccion.get_chunk(c["chunk_id"]).orden for c in evidencia]
    assert ordenes[0] == 0 and ordenes[-1] >= len(coleccion.chunks) - len(coleccion.chunks) // _EVIDENCIA_OBJETIVO - 1
