from nuevamente.agents.graph import _depurar
from nuevamente.ingest.chunking import _detectar_secciones
from nuevamente.schemas.formatos import FlashcardsContenido, GuionDeClaseContenido, QuizContenido


def test_quita_tarjetas_duplicadas():
    contenido = FlashcardsContenido(
        titulo="Guía",
        introduccion_contextualizada="Intro",
        items=[
            {"frente": "¿Qué es el EPP?", "dorso": "El EPP incluye guantes, mascarillas y batas.", "fuentes": ["c1"]},
            # misma idea con otro prefijo de perfil: presunto duplicado
            {"frente": "¿Qué más?", "dorso": "En palabras simples: El EPP incluye guantes, mascarillas y batas.", "fuentes": ["c2"]},
            {"frente": "¿Y los residuos?", "dorso": "Los residuos van en bolsas rojas.", "fuentes": ["c3"]},
        ],
    )
    limpio = _depurar(contenido)
    assert [i.frente for i in limpio.items] == ["¿Qué es el EPP?", "¿Y los residuos?"]


def test_renumera_escenas_tras_quitar_duplicados():
    contenido = GuionDeClaseContenido(
        duracion_total_min=1,
        escenas=[
            {"orden": 1, "narracion": "El lavado de manos dura 20 segundos.", "duracion_seg": 20},
            {"orden": 2, "narracion": "El lavado de manos dura 20 segundos.", "duracion_seg": 20},
            {"orden": 3, "narracion": "Los residuos van en bolsas rojas.", "duracion_seg": 20},
        ],
    )
    limpio = _depurar(contenido)
    assert [e.orden for e in limpio.escenas] == [1, 2]


def test_quiz_reparte_la_respuesta_correcta_entre_las_letras():
    # como suele hacer un LLM: la correcta siempre en la A
    temas = ["el lavado de manos", "los guantes", "la mascarilla", "los residuos", "la bata", "las agujas", "el alcohol", "la limpieza"]
    contenido = QuizContenido(
        titulo="Quiz",
        preguntas=[
            {
                "enunciado": f"¿Qué indica el documento sobre {t}?",
                "opciones": [f"Correcta sobre {t}", f"Falsa uno de {t}", f"Falsa dos de {t}", f"Falsa tres de {t}"],
                "indice_correcto": 0,
                "justificacion": "Lo dice la fuente.",
                "fuentes": ["c1"],
            }
            for t in temas
        ],
    )
    limpio = _depurar(contenido)
    posiciones = [p.indice_correcto for p in limpio.preguntas]
    assert sorted(posiciones) == [0, 0, 1, 1, 2, 2, 3, 3]  # repartidas por igual
    assert all(a != b for a, b in zip(posiciones, posiciones[1:]))  # nunca dos seguidas iguales
    for p, t in zip(limpio.preguntas, temas):
        assert p.opciones[p.indice_correcto] == f"Correcta sobre {t}"
        assert sorted(p.opciones) == sorted([f"Correcta sobre {t}", f"Falsa uno de {t}", f"Falsa dos de {t}", f"Falsa tres de {t}"])
    assert _depurar(contenido).model_dump() == limpio.model_dump()  # el mismo quiz se mezcla igual


def test_titulos_de_seccion_sin_numeracion_de_origen():
    texto = "1. ACCESO A LA CONSOLA\nTexto del acceso.\n\n2. MODOS DE CONFIGURACION IP\nTexto de los modos."
    assert [s for s, _ in _detectar_secciones(texto)] == ["Acceso a la consola", "Modos de configuracion IP"]
