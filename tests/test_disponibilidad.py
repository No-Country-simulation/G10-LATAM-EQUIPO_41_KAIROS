import pytest

from nuevamente.llm import disponibilidad
from nuevamente.llm.base import LLMError
from nuevamente.llm.factory import ConRespaldoLocal


class _ProveedorCaido:
    nombre_modelo = "proveedor-caido"

    def __init__(self):
        self.llamadas = 0

    def generar_estructurado(self, schema, system, user):
        self.llamadas += 1
        raise LLMError("saturado (503)")


class _Respaldo:
    nombre_modelo = "respaldo"

    def generar_estructurado(self, schema, system, user):
        return "material local"


def test_tras_un_fallo_las_siguientes_generaciones_no_esperan_al_proveedor():
    disponibilidad.reanudar("llm:_ProveedorCaido")
    caido = _ProveedorCaido()

    primera = ConRespaldoLocal(caido, _Respaldo())
    assert primera.generar_estructurado(None, "", "") == "material local"
    assert caido.llamadas == 1

    # otra solicitud poco después: va directo al respaldo, sin llamar al proveedor
    segunda = ConRespaldoLocal(caido, _Respaldo())
    assert segunda.generar_estructurado(None, "", "") == "material local"
    assert caido.llamadas == 1
    assert "saturado" in segunda.motivo_respaldo
    assert "respaldo" in segunda.nombre_modelo

    disponibilidad.reanudar("llm:_ProveedorCaido")


def test_la_pausa_vence_y_el_proveedor_se_vuelve_a_probar():
    disponibilidad.pausar("prueba", "caído", minutos=0.0001)
    import time

    time.sleep(0.02)
    assert disponibilidad.en_pausa("prueba") is None


def test_pausa_cero_la_desactiva():
    disponibilidad.pausar("prueba-cero", "caído", minutos=0)
    assert disponibilidad.en_pausa("prueba-cero") is None


def test_crear_llm_envuelve_al_proveedor_con_el_respaldo_local(monkeypatch):
    # Gemini con "503 high demand" no debe llegar al usuario como error: se usa el TemplateLLM
    from nuevamente.config import settings
    from nuevamente.llm import factory

    class Saturado:
        nombre_modelo = "gemini-prueba"

        def generar_estructurado(self, schema, system, user):
            raise LLMError("HTTP 503 - This model is currently experiencing high demand.")

    if not settings.llm_respaldo_local:
        pytest.skip("LLM_RESPALDO_LOCAL desactivado en este entorno")
    monkeypatch.setitem(factory._FACTORIES, "gemini", Saturado)
    monkeypatch.setattr(factory, "TemplateLLM", _Respaldo)
    factory.limpiar_cache_llm()
    disponibilidad.reanudar("llm:Saturado")
    try:
        llm = factory.crear_llm("gemini")
        assert isinstance(llm, ConRespaldoLocal)
        assert llm.generar_estructurado(None, "", "") == "material local"
        assert "respaldo: gemini-prueba" in llm.nombre_modelo
    finally:
        factory.limpiar_cache_llm()
        disponibilidad.reanudar("llm:Saturado")
