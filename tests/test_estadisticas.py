"""Estadísticas de uso y calificaciones de los usuarios. Responsable: Diana Dure (QA Tester).

El archivo de eventos lo comparten todos los tests de la corrida, así que se comparan
diferencias antes/después y no totales absolutos."""
from __future__ import annotations


def _generar(api_client, documento_salud, formato="Flashcards"):
    body = {
        "documento_titulo": "Protocolo de Bioseguridad",
        "documento_contenido": documento_salud,
        "perfil_destinatario": "Principiante",
        "formato_salida": formato,
        "nicho_sector": "Salud",
    }
    r = api_client.post("/api/v1/adaptar", json=body)
    assert r.status_code == 200, r.text
    return r.json()["almacenamiento_oci"]["objeto_id"]


def _stats(api_client):
    r = api_client.get("/api/v1/estadisticas")
    assert r.status_code == 200
    return r.json()


def _conteo(filas, nombre):
    return next((f["total"] for f in filas if f["nombre"] == nombre), 0)


def test_generar_descargar_y_calificar_se_refleja_en_las_estadisticas(api_client, documento_salud):
    antes = _stats(api_client)
    objeto_id = _generar(api_client, documento_salud)
    assert api_client.get(f"/api/v1/contenidos/{objeto_id}/exportar?formato=docx").status_code == 200
    r = api_client.post("/api/v1/calificaciones", json={"objeto_id": objeto_id, "estrellas": 4, "comentario": "Muy claro"})
    assert r.status_code == 201, r.text

    despues = _stats(api_client)
    assert despues["totales"]["materiales"] == antes["totales"]["materiales"] + 1
    assert despues["totales"]["calificaciones"] == antes["totales"]["calificaciones"] + 1
    assert _conteo(despues["por_formato"], "Flashcards") == _conteo(antes["por_formato"], "Flashcards") + 1
    assert _conteo(despues["por_sector"], "Salud") == _conteo(antes["por_sector"], "Salud") + 1
    assert _conteo(despues["por_origen"], "texto") == _conteo(antes["por_origen"], "texto") + 1
    assert _conteo(despues["descargas_por_tipo"], "docx") == _conteo(antes["descargas_por_tipo"], "docx") + 1
    assert despues["comentarios_recientes"][0]["comentario"] == "Muy claro"
    assert despues["comentarios_recientes"][0]["formato"] == "Flashcards"
    assert despues["actividad_diaria"][-1]["total"] >= 1
    assert len(despues["actividad_diaria"]) == 14


def test_volver_a_calificar_reemplaza_la_calificacion_anterior(api_client, documento_salud):
    objeto_id = _generar(api_client, documento_salud, formato="Quiz")
    api_client.post("/api/v1/calificaciones", json={"objeto_id": objeto_id, "estrellas": 2})
    antes = _stats(api_client)
    api_client.post("/api/v1/calificaciones", json={"objeto_id": objeto_id, "estrellas": 5})
    despues = _stats(api_client)
    assert despues["totales"]["calificaciones"] == antes["totales"]["calificaciones"]
    cinco = lambda s: s["distribucion_estrellas"][0]["total"]  # noqa: E731
    assert cinco(despues) == cinco(antes) + 1


def test_subir_archivo_registra_su_tipo(api_client, documento_salud):
    antes = _stats(api_client)
    files = {"archivo": ("protocolo.md", documento_salud.encode("utf-8"), "text/markdown")}
    data = {"perfil_destinatario": "Principiante", "formato_salida": "Tutorial"}
    assert api_client.post("/api/v1/adaptar/archivo", files=files, data=data).status_code == 200
    assert _conteo(_stats(api_client)["por_origen"], "md") == _conteo(antes["por_origen"], "md") + 1


def test_calificacion_fuera_de_rango_da_422(api_client, documento_salud):
    objeto_id = _generar(api_client, documento_salud)
    for estrellas in (0, 6):
        r = api_client.post("/api/v1/calificaciones", json={"objeto_id": objeto_id, "estrellas": estrellas})
        assert r.status_code == 422


def test_calificar_material_inexistente_da_404(api_client):
    r = api_client.post("/api/v1/calificaciones", json={"objeto_id": "contenidos/no-existe.json", "estrellas": 3})
    assert r.status_code == 404


def test_pagina_de_estadisticas_se_sirve(api_client):
    r = api_client.get("/estadisticas")
    assert r.status_code == 200
    assert "/static/estadisticas.js?v=" in r.text


def test_linea_danada_no_rompe_el_resumen(tmp_path, monkeypatch):
    from nuevamente import estadisticas

    monkeypatch.setattr(estadisticas, "_archivo", lambda: tmp_path / "eventos.jsonl")
    (tmp_path / "eventos.jsonl").write_text('{"tipo": "generacion", "fecha": "2026-01-01T00:00:00+00:00", "formato": "Quiz"}\n{"tipo": "gener', encoding="utf-8")
    assert estadisticas.resumen()["totales"]["materiales"] == 1


def test_el_historial_guardado_se_suma_una_sola_vez(api_client, documento_salud, monkeypatch, tmp_path):
    """Un material guardado antes de que existieran las estadísticas aparece al abrirlas,
    con la fecha de su archivo, y no se vuelve a contar al abrirlas de nuevo."""
    from nuevamente import estadisticas

    objeto_id = _generar(api_client, documento_salud, formato="Tutorial")
    # simula que se creó antes: un archivo de eventos nuevo, sin rastro de esa generación
    monkeypatch.setattr(estadisticas, "_archivo", lambda: tmp_path / "eventos.jsonl")

    primera = _stats(api_client)
    del_historial = [f for f in primera["por_formato"] if f["nombre"] == "Tutorial"]
    assert del_historial and del_historial[0]["total"] >= 1
    assert primera["totales"]["historicos"] == primera["totales"]["materiales"] >= 1
    assert _conteo(primera["por_sector"], "Salud") >= 1  # su umbral de 0.90 delata el sector
    assert _conteo(primera["por_nivel"], "Sin registrar") == primera["totales"]["materiales"]
    eventos = estadisticas.leer_eventos()
    assert any(e.get("objeto_id") == objeto_id and e.get("historico") for e in eventos)

    assert _stats(api_client)["totales"]["materiales"] == primera["totales"]["materiales"]


def test_historial_ilegible_no_rompe_ni_se_relee(api_client, monkeypatch, tmp_path):
    from nuevamente import estadisticas
    from nuevamente.storage.oci_client import get_storage_service

    monkeypatch.setattr(estadisticas, "_archivo", lambda: tmp_path / "eventos.jsonl")
    get_storage_service().subir_texto("contenidos/roto/x.json", "{no es json")
    assert api_client.get("/api/v1/estadisticas").status_code == 200
    ilegibles = [e for e in estadisticas.leer_eventos() if e["tipo"] == "historial_ilegible"]
    assert [e["objeto_id"] for e in ilegibles] == ["contenidos/roto/x.json"]
    api_client.get("/api/v1/estadisticas")
    assert len([e for e in estadisticas.leer_eventos() if e["tipo"] == "historial_ilegible"]) == 1
