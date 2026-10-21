"""Tests de la narración del video. Responsable: Diana Dure (QA Tester)."""
from nuevamente.exports.narracion import preparar_texto


def test_fechas_iso_se_leen_en_palabras():
    assert "24 de septiembre de 2026" in preparar_texto("Entrega el 2026-09-24.")
    # fecha partida por la extracción del PDF
    assert "2 de octubre de 2026" in preparar_texto("Programa 2026-10- 2 listo")


def test_abreviaturas_y_simbolos_se_expanden():
    texto = preparar_texto("Usar EPP, p. ej. guantes (máx. 10 min) en el 90% de los casos.")
    assert "por ejemplo" in texto
    assert "máximo 10 minutos" in texto
    assert "90 por ciento" in texto
    assert "E P P" in texto  # sigla deletreada
    assert "(" not in texto and ")" not in texto


def test_listas_se_leen_como_frases_separadas():
    assert preparar_texto("- Lavado de manos\n- Uso de **EPP**") == "Lavado de manos. Uso de E P P."


def test_no_pasa_comandos_de_voz_desde_el_documento():
    assert "[[" not in preparar_texto("Texto con [[volm 0]] comandos inyectados")


def test_texto_normal_no_cambia_de_sentido():
    original = "El lavado de manos elimina la mayoría de los microorganismos."
    assert preparar_texto(original) == original


# ---------- Motor de voz: Gemini TTS con respaldo del sistema ----------

import dataclasses
from pathlib import Path

import pytest

from nuevamente.exports import narracion
from nuevamente.llm import disponibilidad


@pytest.fixture
def con_gemini(monkeypatch):
    """Narración activada, con Gemini TTS elegido y una API key de prueba (sin red)."""
    monkeypatch.setattr(narracion, "settings", dataclasses.replace(
        narracion.settings, video_tts="auto", video_voces="gemini", gemini_api_key="clave-de-prueba", gemini_api_keys=(),
        openai_api_key="",
    ))
    disponibilidad.reanudar(narracion.SERVICIO_TTS)
    disponibilidad.reanudar(narracion.SERVICIO_TTS_OPENAI)
    yield
    disponibilidad.reanudar(narracion.SERVICIO_TTS)
    disponibilidad.reanudar(narracion.SERVICIO_TTS_OPENAI)


def _sistema(texto, tipo, destino):
    return Path(f"{destino}.sistema")


def test_con_gemini_toda_la_narracion_usa_la_voz_natural(con_gemini, monkeypatch, tmp_path):
    monkeypatch.setattr(narracion, "_narrar_gemini", lambda textos, tipo: [Path(f"{d}.gemini") for _, d in textos])
    monkeypatch.setattr(narracion, "sintetizar", _sistema)
    audios, motor = narracion.narrar([("Hola.", tmp_path / "a"), ("Adiós.", tmp_path / "b")], "masculina")
    assert motor == "gemini" and all(a.suffix == ".gemini" for a in audios)
    assert narracion.nombre_voz("masculina") == "Charon (voz natural)"


def test_si_un_fragmento_falla_todo_se_narra_con_el_sistema(con_gemini, monkeypatch, tmp_path):
    """Un video nunca mezcla dos voces: si Gemini falla, se narran todas con el sistema."""
    def gemini(textos, tipo):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(narracion, "_narrar_gemini", gemini)
    monkeypatch.setattr(narracion, "sintetizar", _sistema)
    audios, motor = narracion.narrar([("Hola.", tmp_path / "a"), ("Adiós.", tmp_path / "b")], "masculina")
    assert motor == "sistema" and all(a.suffix == ".sistema" for a in audios)
    # en pausa: la siguiente narración no vuelve a esperar a Gemini
    assert narracion.motor_voz() == "sistema"


@pytest.fixture
def con_openai(con_gemini, monkeypatch):
    """Además de Gemini, OpenAI TTS configurado con una clave de prueba (sin red)."""
    monkeypatch.setattr(narracion, "settings", dataclasses.replace(narracion.settings, openai_api_key="clave-de-prueba"))


def _falla(textos, tipo):
    raise RuntimeError("503 UNAVAILABLE")


def test_si_gemini_falla_la_voz_natural_de_openai_toma_la_narracion(con_openai, monkeypatch, tmp_path):
    """Con Gemini saturado no se cae a la voz robótica del sistema si hay OpenAI TTS."""
    monkeypatch.setattr(narracion, "_narrar_gemini", _falla)
    monkeypatch.setattr(narracion, "_narrar_openai", lambda textos, tipo: [Path(f"{d}.openai") for _, d in textos])
    monkeypatch.setattr(narracion, "sintetizar", lambda *a: pytest.fail("no debe usar la voz del sistema"))
    audios, motor = narracion.narrar([("Hola.", tmp_path / "a"), ("Adiós.", tmp_path / "b")], "masculina")
    assert motor == "openai" and all(a.suffix == ".openai" for a in audios)
    # Gemini queda en pausa: la siguiente narración va directo a OpenAI, con su voz masculina
    assert narracion.motor_voz() == "openai"
    assert narracion.nombre_voz("masculina") == "Ash (voz natural de OpenAI)"


def test_si_openai_tambien_falla_se_narra_con_el_sistema(con_openai, monkeypatch, tmp_path):
    monkeypatch.setattr(narracion, "_narrar_gemini", _falla)
    monkeypatch.setattr(narracion, "_narrar_openai", _falla)
    monkeypatch.setattr(narracion, "sintetizar", _sistema)
    audios, motor = narracion.narrar([("Hola.", tmp_path / "a")], "masculina")
    assert motor == "sistema" and audios[0].suffix == ".sistema"


def test_con_voces_openai_no_se_llama_a_gemini(con_openai, monkeypatch, tmp_path):
    monkeypatch.setattr(narracion, "settings", dataclasses.replace(narracion.settings, video_voces="openai"))
    monkeypatch.setattr(narracion, "_narrar_gemini", lambda *a, **k: pytest.fail("no debe usar Gemini"))
    monkeypatch.setattr(narracion, "_narrar_openai", lambda textos, tipo: [Path(f"{d}.openai") for _, d in textos])
    _, motor = narracion.narrar([("Hola.", tmp_path / "a")], "masculina")
    assert motor == "openai"


def test_con_voces_del_sistema_no_se_llama_a_gemini(monkeypatch, tmp_path):
    monkeypatch.setattr(narracion, "settings", dataclasses.replace(narracion.settings, video_tts="auto", video_voces="sistema"))
    monkeypatch.setattr(narracion, "_narrar_gemini", lambda *a, **k: pytest.fail("no debe usar Gemini"))
    monkeypatch.setattr(narracion, "_narrar_openai", lambda *a, **k: pytest.fail("no debe usar OpenAI"))
    monkeypatch.setattr(narracion, "sintetizar", _sistema)
    _, motor = narracion.narrar([("Hola.", tmp_path / "a")], "femenina")
    assert motor == "sistema"


def test_los_cortes_caen_en_la_pausa_larga_y_no_entre_oraciones():
    """Tres fragmentos de igual largo en 30 s: las pausas largas (2 s) están cerca de los
    10 s y los 20 s; las cortas (0,6 s) son pausas entre oraciones y se ignoran."""
    silencios = [(4.0, 4.6), (9.2, 11.2), (14.0, 14.6), (19.5, 21.5), (25.0, 25.6)]
    cortes = narracion.cortes_por_silencio(silencios, 30.0, [100, 100, 100])
    assert cortes == [10.2, 20.5]


def test_sin_pausa_reconocible_no_se_corta_a_ciegas():
    with pytest.raises(ValueError):
        narracion.cortes_por_silencio([(1.0, 1.6)], 30.0, [100, 100])


def test_si_un_modelo_tts_se_queda_sin_cuota_se_usa_el_siguiente(monkeypatch):
    """La cuota gratuita es por día y por modelo: un 429 diario pasa al modelo siguiente."""
    from types import SimpleNamespace

    monkeypatch.setattr(narracion, "settings", dataclasses.replace(
        narracion.settings, podcast_tts_model="tts-a", tts_modelos_respaldo=("tts-b",),
    ))
    pedidos = []

    class _Modelos:
        def generate_content(self, model, contents, config):
            pedidos.append(model)
            if model == "tts-a":
                raise RuntimeError("429 RESOURCE_EXHAUSTED. Please retry in 20h19m54s.")
            parte = SimpleNamespace(inline_data=SimpleNamespace(data=b"\x00\x01"))
            return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[parte]))])

    monkeypatch.setattr(narracion, "_agotados", {})
    cliente = SimpleNamespace(models=_Modelos())
    pcm = narracion.generar_audio_tts(cliente, "Hola.", config=None)
    assert pcm == b"\x00\x01" and pedidos == ["tts-a", "tts-b"]  # no espera 20 h: rota
    narracion.generar_audio_tts(cliente, "Otra vez.", config=None)
    assert pedidos[2:] == ["tts-b"]  # el agotado no se vuelve a probar hasta mañana


def test_modelo_que_exige_locutor_por_parte_se_reintenta_con_ese_formato(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(narracion, "settings", dataclasses.replace(narracion.settings, podcast_tts_model="tts-nuevo", tts_modelos_respaldo=()))
    monkeypatch.setattr(narracion, "_agotados", {})
    recibidos = []

    class _Modelos:
        def generate_content(self, model, contents, config):
            recibidos.append(contents)
            if isinstance(contents, str):
                raise RuntimeError("400 INVALID_ARGUMENT. Multi-speaker generation requests must specify speech_metadata.speaker")
            parte = SimpleNamespace(inline_data=SimpleNamespace(data=b"\x01"))
            return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[parte]))])

    pcm = narracion.generar_audio_tts(SimpleNamespace(models=_Modelos()), "Ana: Hola.", None, por_locutor=["partes"])
    assert pcm == b"\x01" and recibidos == ["Ana: Hola.", ["partes"]]


def test_video_sin_introduccion_hablada(monkeypatch, tmp_path):
    """El video no abre con un saludo ni una prueba de voz: la voz solo lee la narración
    de cada escena, y la portada (título del documento) va en silencio."""
    from nuevamente.exports import video
    from nuevamente.schemas.formatos import GuionDeClaseContenido

    narrados: list[str] = []

    def narrar_falso(textos, voz):
        narrados.extend(texto for texto, _ in textos)
        return [None] * len(textos), "sistema"

    monkeypatch.setattr(video, "narrar", narrar_falso)
    guion = GuionDeClaseContenido(duracion_total_min=1, escenas=[
        {"orden": 1, "narracion": "El lavado de manos elimina microorganismos.", "apoyo_visual": "Diagrama",
         "duracion_seg": 5, "seccion": "Lavado de manos"},
        {"orden": 2, "narracion": "Los guantes se cambian entre pacientes.", "apoyo_visual": "Foto",
         "duracion_seg": 5, "seccion": "Uso de guantes"},
    ])
    video.generar_video(guion, "Bioseguridad", tmp_path / "clase.mp4", "femenina")
    assert narrados == ["El lavado de manos elimina microorganismos.", "Los guantes se cambian entre pacientes."]
    assert (tmp_path / "clase.mp4").stat().st_size > 0
