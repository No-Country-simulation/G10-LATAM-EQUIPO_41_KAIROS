from nuevamente.exports.resumen import partes_resumen
from nuevamente.schemas.formatos import ResumenEjecutivoContenido


def test_separa_idea_central_puntos_riesgos_y_recomendaciones():
    c = ResumenEjecutivoContenido(
        resumen="El lavado de manos evita infecciones.\n\nEl protocolo regula la higiene.\n\nLos guantes se cambian.",
        puntos_clave=["Lavado de manos: dura 20 segundos.", "2. Residuos"],
        decisiones_o_riesgos=["Riesgo: contagio cruzado.", "Recomendación: auditar cada mes.", "Revisar cada año."],
        fuentes=["c1"],
    )
    p = partes_resumen(c)
    assert p.idea == "El lavado de manos evita infecciones."
    assert p.resto == ["El protocolo regula la higiene.", "Los guantes se cambian."]
    assert p.puntos == [("Lavado de manos", "dura 20 segundos."), ("Residuos", "")]
    assert p.riesgos == ["Contagio cruzado."]
    assert p.recomendaciones == ["Auditar cada mes."]
    assert p.decisiones == ["Revisar cada año."]


def test_resumen_sin_parrafos_toma_la_primera_oracion_como_idea_central():
    c = ResumenEjecutivoContenido(resumen="Primera idea. Segunda idea. Tercera.", puntos_clave=["Tema"], fuentes=["c1"])
    p = partes_resumen(c)
    assert p.idea == "Primera idea."
    assert p.resto == ["Segunda idea. Tercera."]
