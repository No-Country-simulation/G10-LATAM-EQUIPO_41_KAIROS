"""Tests de la API REST. Responsable: Diana Dure (QA Tester)."""
import pytest


def test_health_ok(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_adaptar_flashcards_salud(api_client, documento_salud):
    body = {
        "documento_titulo": "Protocolo de Bioseguridad",
        "documento_contenido": documento_salud,
        "perfil_destinatario": "Principiante",
        "formato_salida": "Flashcards",
        "nicho_sector": "Salud",
    }
    r = api_client.post("/api/v1/adaptar", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "exito"
    assert data["evaluacion_calidad"]["umbral_aplicado"] == 0.9
    assert data["almacenamiento_oci"]["status_upload"] in ("completado", "fallido_local")


@pytest.mark.parametrize(
    "formato,perfil",
    [
        ("Flashcards", "Principiante"),
        ("Quiz", "Desarrollador Junior/Semi Senior"),
        ("Tutorial", "Líder Técnico/Arquitecto"),
        ("Resumen Ejecutivo", "Gestor/Ejecutivo"),
        ("Guion de Clase", "Principiante"),
        ("Podcast", "Gestor/Ejecutivo"),
    ],
)
def test_adaptar_todos_los_formatos(api_client, documento_salud, formato, perfil):
    """Checklist del hackathon: probar >= 2 perfiles y >= 2 formatos. Aquí probamos los 6."""
    body = {
        "documento_titulo": "Protocolo de Bioseguridad",
        "documento_contenido": documento_salud,
        "perfil_destinatario": perfil,
        "formato_salida": formato,
        "nicho_sector": "Salud",
    }
    r = api_client.post("/api/v1/adaptar", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["contenido_adaptado"]["formato"] == formato


def test_adaptar_valida_campos_faltantes(api_client):
    r = api_client.post("/api/v1/adaptar", json={"documento_titulo": "x"})
    assert r.status_code == 422
    assert r.json()["codigo"] == "VALIDACION_ENTRADA"


def test_adaptar_rechaza_perfil_no_soportado(api_client, documento_salud):
    body = {
        "documento_titulo": "Doc",
        "documento_contenido": documento_salud,
        "perfil_destinatario": "Doctorado en Medicina",  # no está en el enum
        "formato_salida": "Flashcards",
    }
    r = api_client.post("/api/v1/adaptar", json=body)
    assert r.status_code == 422


def test_adaptar_archivo_txt(api_client, documento_salud):
    files = {"archivo": ("protocolo.txt", documento_salud.encode("utf-8"), "text/plain")}
    data = {
        "perfil_destinatario": "Principiante",
        "formato_salida": "Flashcards",
        "nicho_sector": "Salud",
    }
    r = api_client.post("/api/v1/adaptar/archivo", files=files, data=data)
    assert r.status_code == 200, r.text


def test_adaptar_archivo_demasiado_grande_da_413(api_client):
    grande = b"x" * (11 * 1024 * 1024)
    files = {"archivo": ("grande.txt", grande, "text/plain")}
    data = {"perfil_destinatario": "Principiante", "formato_salida": "Flashcards"}
    r = api_client.post("/api/v1/adaptar/archivo", files=files, data=data)
    assert r.status_code == 413


def test_flujo_completo_guarda_y_recupera(api_client, documento_salud):
    body = {
        "documento_titulo": "Protocolo de Bioseguridad",
        "documento_contenido": documento_salud,
        "perfil_destinatario": "Principiante",
        "formato_salida": "Flashcards",
        "nicho_sector": "Salud",
    }
    r1 = api_client.post("/api/v1/adaptar", json=body)
    objeto_id = r1.json()["almacenamiento_oci"]["objeto_id"]

    r2 = api_client.get(f"/api/v1/contenidos/{objeto_id}")
    assert r2.status_code == 200
    assert r2.json()["request_id"] == r1.json()["request_id"]


def test_contenido_inexistente_da_404(api_client):
    r = api_client.get("/api/v1/contenidos/no-existe.json")
    assert r.status_code == 404


def test_front_end_se_sirve_en_la_raiz(api_client):
    r = api_client.get("/")
    assert r.status_code == 200
    assert "Kairos" in r.text
    assert api_client.get("/static/app.js").status_code == 200
    assert api_client.get("/static/styles.css").status_code == 200


def test_opciones_coinciden_con_los_enums(api_client):
    from nuevamente.schemas.enums import FormatoSalida, PerfilDestinatario

    op = api_client.get("/api/v1/opciones").json()
    assert op["perfiles"] == [p.value for p in PerfilDestinatario]
    assert op["formatos"] == [f.value for f in FormatoSalida]
    assert op["umbral_por_nicho"]["Salud"] == 0.9


def _crear(api_client, documento, formato):
    body = {
        "documento_titulo": "Protocolo de Bioseguridad",
        "documento_contenido": documento,
        "perfil_destinatario": "Principiante",
        "formato_salida": formato,
    }
    return api_client.post("/api/v1/adaptar", json=body).json()["almacenamiento_oci"]["objeto_id"]


def test_video_del_guion_de_clase_es_un_mp4(api_client, documento_salud):
    objeto_id = _crear(api_client, documento_salud, "Guion de Clase")
    r = api_client.get(f"/api/v1/contenidos/{objeto_id}/video", params={"titulo": "Protocolo"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "video/mp4"
    assert r.content[4:8] == b"ftyp"  # cabecera de un contenedor MP4


def test_video_solo_para_guion_de_clase(api_client, documento_salud):
    objeto_id = _crear(api_client, documento_salud, "Flashcards")
    assert api_client.get(f"/api/v1/contenidos/{objeto_id}/video").status_code == 422


def test_video_con_voz_masculina(api_client, documento_salud):
    objeto_id = _crear(api_client, documento_salud, "Guion de Clase")
    r = api_client.get(f"/api/v1/contenidos/{objeto_id}/video", params={"voz": "masculina"})
    assert r.status_code == 200, r.text
    assert r.content[4:8] == b"ftyp"


def test_video_rechaza_voz_desconocida(api_client, documento_salud):
    objeto_id = _crear(api_client, documento_salud, "Guion de Clase")
    assert api_client.get(f"/api/v1/contenidos/{objeto_id}/video", params={"voz": "robot"}).status_code == 422


def test_opciones_informan_voces_y_muestra_sin_voz_da_404(api_client):
    # en los tests VIDEO_TTS=off: no hay voces y la muestra lo dice claramente
    assert api_client.get("/api/v1/opciones").json()["voces"] == {"femenina": None, "masculina": None}
    assert api_client.get("/api/v1/voces/femenina/muestra").status_code == 404


@pytest.mark.parametrize("formato", ["Flashcards", "Quiz", "Tutorial", "Resumen Ejecutivo", "Guion de Clase"])
def test_exportar_presentacion_pptx(api_client, documento_salud, formato):
    import io

    from pptx import Presentation

    objeto_id = _crear(api_client, documento_salud, formato)
    r = api_client.get(f"/api/v1/contenidos/{objeto_id}/exportar", params={"formato": "pptx", "titulo": "Protocolo"})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.presentationml")
    deck = Presentation(io.BytesIO(r.content))
    assert len(deck.slides) >= 3  # portada + contenido + cierre
    textos = " ".join(sh.text_frame.text for s in deck.slides for sh in s.shapes if sh.has_text_frame)
    assert "Protocolo" in textos and "¡Gracias!" in textos
    if formato == "Guion de Clase":  # la narración va en las notas del orador
        assert deck.slides[1].notes_slide.notes_text_frame.text.startswith("Narración")


def test_podcast_alterna_locutores_y_es_solo_audio(api_client, documento_salud):
    objeto_id = _crear(api_client, documento_salud, "Podcast")
    podcast = api_client.get(f"/api/v1/contenidos/{objeto_id}").json()["contenido_adaptado"]
    locutores = [i["locutor"] for i in podcast["intervenciones"]]
    assert locutores[0] == "Ana" and locutores[-1] == "Ana" and "Leo" in locutores
    # solo Leo cita el documento: es lo que verifica el Crítico
    assert all(i["fuentes"] for i in podcast["intervenciones"] if i["locutor"] == "Leo")

    # el podcast se ofrece solo en audio: no se exporta como texto ni diapositivas
    for formato in ("markdown", "anki_csv", "pptx"):
        r = api_client.get(f"/api/v1/contenidos/{objeto_id}/exportar", params={"formato": formato})
        assert r.status_code == 422
        assert "audio" in r.json()["detail"]


def test_podcast_sin_voces_da_503(api_client, documento_salud):
    # en los tests VIDEO_TTS=off: no hay voces con que narrar el episodio
    objeto_id = _crear(api_client, documento_salud, "Podcast")
    r = api_client.get(f"/api/v1/contenidos/{objeto_id}/podcast")
    assert r.status_code == 503
    assert "voces" in r.json()["detail"]


def test_audio_solo_para_podcast(api_client, documento_salud):
    objeto_id = _crear(api_client, documento_salud, "Flashcards")
    assert api_client.get(f"/api/v1/contenidos/{objeto_id}/podcast").status_code == 422


def test_podcast_es_un_mp3_con_una_voz_por_locutor(api_client, documento_salud, monkeypatch):
    import subprocess

    from nuevamente.exports import podcast as modulo
    from nuevamente.exports.video import _ffmpeg

    usadas = []

    def tono(texto, tipo, destino):
        """Sustituye a la voz del sistema: un tono corto, distinto por tipo de voz."""
        usadas.append(tipo)
        audio = destino.with_suffix(".wav")
        frecuencia = 440 if tipo == "femenina" else 220
        subprocess.run(
            [_ffmpeg(), "-y", "-f", "lavfi", "-i", f"sine=frequency={frecuencia}:duration=0.3", str(audio)],
            check=True, capture_output=True,
        )
        return audio

    monkeypatch.setattr(modulo, "voces_del_podcast", lambda: {"Ana": "femenina", "Leo": "masculina"})
    monkeypatch.setattr(modulo, "sintetizar", tono)

    objeto_id = _crear(api_client, documento_salud, "Podcast")
    r = api_client.get(f"/api/v1/contenidos/{objeto_id}/podcast")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.content[:3] == b"ID3"  # cabecera ID3 de un MP3
    assert r.headers["x-podcast-voces"] == "sistema"
    assert set(usadas) == {"femenina", "masculina"}


def test_la_web_se_revalida_siempre(api_client):
    """Sin esto el navegador sigue usando un app.js viejo tras actualizar el código."""
    assert api_client.get("/").headers["cache-control"] == "no-cache"
    assert api_client.get("/static/app.js").headers["cache-control"] == "no-cache"


def test_la_web_pide_archivos_versionados(api_client):
    """La URL de app.js cambia con su contenido: un navegador con caché vieja la descarga igual."""
    import re

    html = api_client.get("/").text
    for archivo in ("app.js", "styles.css"):
        m = re.search(rf'"/static/{re.escape(archivo)}\?v=([0-9a-f]+)"', html)
        assert m, archivo
        assert api_client.get(f"/static/{archivo}?v={m.group(1)}").status_code == 200


def _pcm_de_prueba(segundos: float = 0.5) -> bytes:
    """PCM s16le mono 24 kHz (lo que devuelve Gemini TTS): un tono corto."""
    import math
    import struct

    n = int(24000 * segundos)
    return b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 330 * i / 24000))) for i in range(n))


def test_podcast_con_voces_naturales_de_gemini(api_client, documento_salud, monkeypatch):
    from nuevamente.exports import podcast as modulo

    dialogos = []
    monkeypatch.setattr(modulo, "gemini_tts_configurado", lambda: True)
    monkeypatch.setattr(modulo, "_sintetizar_gemini", lambda d: dialogos.append(d) or _pcm_de_prueba())

    objeto_id = _crear(api_client, documento_salud, "Podcast")
    r = api_client.get(f"/api/v1/contenidos/{objeto_id}/podcast")
    assert r.status_code == 200, r.text
    assert r.headers["x-podcast-voces"] == "gemini"
    assert r.content[:3] == b"ID3"
    # todo el diálogo va en una petición, con cada turno marcado por locutor
    assert len(dialogos) == 1
    assert dialogos[0].startswith("Ana: ") and "\nLeo: " in dialogos[0]


def test_podcast_si_gemini_falla_usa_voces_del_sistema(api_client, documento_salud, monkeypatch):
    import subprocess

    from nuevamente.exports import podcast as modulo
    from nuevamente.exports.video import _ffmpeg

    def sin_cuota(dialogo):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    def tono(texto, tipo, destino):
        audio = destino.with_suffix(".wav")
        subprocess.run(
            [_ffmpeg(), "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.2", str(audio)],
            check=True, capture_output=True,
        )
        return audio

    monkeypatch.setattr(modulo, "gemini_tts_configurado", lambda: True)
    monkeypatch.setattr(modulo, "_sintetizar_gemini", sin_cuota)
    monkeypatch.setattr(modulo, "voces_del_podcast", lambda: {"Ana": "femenina", "Leo": "masculina"})
    monkeypatch.setattr(modulo, "sintetizar", tono)

    objeto_id = _crear(api_client, documento_salud, "Podcast")
    r = api_client.get(f"/api/v1/contenidos/{objeto_id}/podcast")
    assert r.status_code == 200, r.text
    assert r.headers["x-podcast-voces"] == "sistema"


def test_bloques_de_dialogo_respetan_turnos_completos():
    from nuevamente.exports.podcast import _MAX_CARACTERES_POR_PETICION, _bloques_de_dialogo
    from nuevamente.schemas.formatos import PodcastContenido, PodcastIntervencion

    largo = "Esta es una oración de prueba bastante larga. " * 20
    podcast = PodcastContenido(
        titulo="t",
        duracion_total_min=5,
        intervenciones=[
            PodcastIntervencion(orden=i, locutor="Ana" if i % 2 else "Leo", texto=largo) for i in range(1, 13)
        ],
    )
    bloques = _bloques_de_dialogo(podcast)
    assert len(bloques) > 1
    assert all(len(b) <= _MAX_CARACTERES_POR_PETICION for b in bloques)
    assert sum(b.count("\n") + 1 for b in bloques) == 12  # ningún turno se parte ni se pierde
