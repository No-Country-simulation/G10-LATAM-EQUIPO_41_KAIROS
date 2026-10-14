"""Caché de contenido aprobado (post-Crítico). Responsable: Ethan Espinoza Acosta."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from nuevamente.agents import graph
from nuevamente.agents.graph import generar_contenido_educativo
from nuevamente.api.app import app
from nuevamente.cache.contenido import ContentCache
from nuevamente.schemas.request import SolicitudAdaptacion
from nuevamente.schemas.enums import FormatoSalida, NichoSector, PerfilDestinatario, NivelDetalle


@pytest.fixture(autouse=True)
def _restaurar_configuracion():
    """Estos tests recargan config y graph con el caché activado: al terminar se apaga y se
    recarga la configuración por defecto, para que el caché no afecte al resto de la suite."""
    yield
    from importlib import reload

    import nuevamente.agents.graph as gph
    import nuevamente.config as cfg

    for variable in [v for v in os.environ if v.startswith("CACHE_")]:
        os.environ.pop(variable)
    reload(cfg)
    reload(gph)
    gph._cache_contenido.clear()


TEXTO_DOC = """# Protocolo de Bioseguridad Clínica

## Introducción
La bioseguridad clínica establece medidas para prevenir infecciones asociadas a la atención sanitaria. Su objetivo es proteger a pacientes, profesionales y visitantes.

## Precauciones estándar
Las precauciones estándar son la base para el control de infecciones. Incluyen higiene de manos, uso de guantes cuando existe riesgo de contacto con fluidos, protección facial y ropa adecuada.

## Precauciones basadas en la transmisión
Se aplican según el modo de transmisión: por gotas, por aire o por contacto. Cada una define elementos de protección específicos para reducir el riesgo de contagio.

## Conclusión
La aplicación sistemática de estas medidas reduce significativamente las infecciones en entornos clínicos.
"""


def test_cache_resumen_salud_hit_en_segunda_generacion(monkeypatch):
    # Activar caché scoped (Resumen Ejecutivo + Salud)
    monkeypatch.setenv("CACHE_CONTENIDO_ACTIVADO", "true")
    monkeypatch.setenv("CACHE_CONTENIDO_SCOPED", "true")
    monkeypatch.setenv("CACHE_CONTENIDO_TTL_S", "3600")
    monkeypatch.setenv("CACHE_CONTENIDO_MAX_ENTRIES", "32")
    monkeypatch.setenv("CACHE_INCLUIR_PROMPTS_SHA", "true")
    monkeypatch.setenv("CACHE_INCLUIR_SCHEMA_SHA", "true")
    from importlib import reload
    import nuevamente.config as cfg
    reload(cfg)
    import nuevamente.agents.graph as gph
    reload(gph)
    graph.settings = gph.settings
    graph._cache_contenido = gph._cache_contenido

    # Limpiar caché
    graph._cache_contenido.clear()

    res1 = generar_contenido_educativo(
        documento_titulo="Protocolo Bioseguridad",
        documento_contenido=TEXTO_DOC,
        perfil="Principiante",
        formato="Resumen Ejecutivo",
        nicho="Salud",
        nivel_detalle="Didáctico",
    )
    assert res1.metadatos.desde_cache is False

    res2 = generar_contenido_educativo(
        documento_titulo="Protocolo Bioseguridad",
        documento_contenido=TEXTO_DOC,
        perfil="Principiante",
        formato="Resumen Ejecutivo",
        nicho="Salud",
        nivel_detalle="Didáctico",
    )
    assert res2.metadatos.desde_cache is True
    # Estructura igual (mismo contenido aprobado)
    assert res2.contenido.formato == "Resumen Ejecutivo"
    assert res2.evaluacion.aprobado_por_critico is True
    assert res2.evaluacion.anclaje_fuente_score >= res2.evaluacion.umbral_aplicado

    stats = graph._cache_contenido.stats()
    assert stats.entries >= 1
    assert stats.hits_total >= 1


def test_cache_no_activa_fuera_de_scope(monkeypatch):
    # Activado pero scoped: otro formato NO debe cachear
    monkeypatch.setenv("CACHE_CONTENIDO_ACTIVADO", "true")
    monkeypatch.setenv("CACHE_CONTENIDO_SCOPED", "true")
    from importlib import reload
    import nuevamente.config as cfg
    reload(cfg)
    import nuevamente.agents.graph as gph
    reload(gph)
    graph.settings = gph.settings
    graph._cache_contenido = gph._cache_contenido

    res1 = generar_contenido_educativo(
        documento_titulo="Protocolo Bioseguridad",
        documento_contenido=TEXTO_DOC,
        perfil="Principiante",
        formato="Flashcards",
        nicho="Salud",
        nivel_detalle="Didáctico",
    )
    assert res1.metadatos.desde_cache is False

    res2 = generar_contenido_educativo(
        documento_titulo="Protocolo Bioseguridad",
        documento_contenido=TEXTO_DOC,
        perfil="Principiante",
        formato="Flashcards",
        nicho="Salud",
        nivel_detalle="Didáctico",
    )
    assert res2.metadatos.desde_cache is False


def test_cache_cambia_por_chunk_ids_distintos(monkeypatch):
    monkeypatch.setenv("CACHE_CONTENIDO_ACTIVADO", "true")
    monkeypatch.setenv("CACHE_CONTENIDO_SCOPED", "true")
    from importlib import reload
    import nuevamente.config as cfg
    reload(cfg)
    import nuevamente.agents.graph as gph
    reload(gph)
    graph.settings = gph.settings
    graph._cache_contenido = gph._cache_contenido

    doc_a = """# Tema\n## A\nContenido A breve para generar evidencia distinta.\n## B\nContenido B breve."""
    doc_b = """# Tema\n## X\nContenido X breve para generar evidencia distinta.\n## Y\nContenido Y breve."""

    res1 = generar_contenido_educativo(
        documento_titulo="Doc A",
        documento_contenido=doc_a,
        perfil="Principiante",
        formato="Resumen Ejecutivo",
        nicho="Salud",
        nivel_detalle="Conciso",
    )
    assert res1.metadatos.desde_cache is False

    res2 = generar_contenido_educativo(
        documento_titulo="Doc B",
        documento_contenido=doc_b,
        perfil="Principiante",
        formato="Resumen Ejecutivo",
        nicho="Salud",
        nivel_detalle="Conciso",
    )
    assert res2.metadatos.desde_cache is False


def test_cache_cambia_por_parametros(monkeypatch):
    monkeypatch.setenv("CACHE_CONTENIDO_ACTIVADO", "true")
    monkeypatch.setenv("CACHE_CONTENIDO_SCOPED", "true")
    from importlib import reload
    import nuevamente.config as cfg
    reload(cfg)
    import nuevamente.agents.graph as gph
    reload(gph)
    graph.settings = gph.settings
    graph._cache_contenido = gph._cache_contenido

    base = TEXTO_DOC

    r1 = generar_contenido_educativo(
        documento_titulo="Bio",
        documento_contenido=base,
        perfil="Principiante",
        formato="Resumen Ejecutivo",
        nicho="Salud",
        nivel_detalle="Didáctico",
    )
    assert r1.metadatos.desde_cache is False

    r2 = generar_contenido_educativo(
        documento_titulo="Bio",
        documento_contenido=base,
        perfil="Desarrollador Junior/Semi Senior",
        formato="Resumen Ejecutivo",
        nicho="Salud",
        nivel_detalle="Didáctico",
    )
    assert r2.metadatos.desde_cache is False


def test_cache_api_stats_endpoint(monkeypatch):
    client = TestClient(app)

    monkeypatch.setenv("CACHE_CONTENIDO_ACTIVADO", "true")
    monkeypatch.setenv("CACHE_CONTENIDO_SCOPED", "true")
    from importlib import reload
    import nuevamente.config as cfg
    reload(cfg)
    import nuevamente.agents.graph as gph
    reload(gph)
    graph.settings = gph.settings
    graph._cache_contenido = gph._cache_contenido

    r = client.get("/api/v1/cache-contenido/stats")
    assert r.status_code == 200
    data = r.json()
    assert "enabled" in data
    assert "scoped" in data
    assert "hits_total" in data
    assert "misses_total" in data
    assert "entries" in data
    assert "hit_rate" in data


def test_cache_solo_post_aprobado(monkeypatch):
    monkeypatch.setenv("CACHE_CONTENIDO_ACTIVADO", "true")
    monkeypatch.setenv("CACHE_CONTENIDO_SCOPED", "true")
    from importlib import reload
    import nuevamente.config as cfg
    reload(cfg)
    import nuevamente.agents.graph as gph
    reload(gph)
    graph.settings = gph.settings
    graph._cache_contenido = gph._cache_contenido

    res = generar_contenido_educativo(
        documento_titulo="Bio",
        documento_contenido=TEXTO_DOC,
        perfil="Principiante",
        formato="Resumen Ejecutivo",
        nicho="Salud",
        nivel_detalle="Didáctico",
    )
    assert res.evaluacion.aprobado_por_critico in (True, False)
    assert res.metadatos.desde_cache is False


def test_cache_key_exacto_con_chunk_ids(monkeypatch):
    monkeypatch.setenv("CACHE_CONTENIDO_ACTIVADO", "true")
    monkeypatch.setenv("CACHE_CONTENIDO_SCOPED", "true")
    from importlib import reload
    import nuevamente.config as cfg
    reload(cfg)
    import nuevamente.agents.graph as gph
    reload(gph)
    graph.settings = gph.settings
    graph._cache_contenido = gph._cache_contenido

    doc = TEXTO_DOC
    res1 = generar_contenido_educativo(
        documento_titulo="Bio",
        documento_contenido=doc,
        perfil="Principiante",
        formato="Resumen Ejecutivo",
        nicho="Salud",
        nivel_detalle="Didáctico",
    )
    assert res1.metadatos.desde_cache is False
    stats1 = graph._cache_contenido.stats()
    entries1 = stats1.entries

    res2 = generar_contenido_educativo(
        documento_titulo="Bio",
        documento_contenido=doc,
        perfil="Principiante",
        formato="Resumen Ejecutivo",
        nicho="Salud",
        nivel_detalle="Didáctico",
    )
    assert res2.metadatos.desde_cache is True
    stats2 = graph._cache_contenido.stats()
    assert stats2.entries == entries1
