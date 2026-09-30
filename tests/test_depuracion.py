from nuevamente.agents.graph import _depurar
from nuevamente.ingest.chunking import _detectar_secciones
from nuevamente.schemas.formatos import FlashcardsContenido, GuionDeClaseContenido


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


def test_titulos_de_seccion_sin_numeracion_de_origen():
    texto = "1. ACCESO A LA CONSOLA\nTexto del acceso.\n\n2. MODOS DE CONFIGURACION IP\nTexto de los modos."
    assert [s for s, _ in _detectar_secciones(texto)] == ["Acceso a la consola", "Modos de configuracion IP"]
