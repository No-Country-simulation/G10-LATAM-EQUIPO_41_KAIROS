"""Prompts del Redactor: role prompting y ejemplos few-shot. Responsable: Diana Dure (QA Tester)."""
from __future__ import annotations

import pytest

from nuevamente.agents.graph import _SCHEMA_POR_FORMATO
from nuevamente.llm.prompts import EJEMPLO_CHUNK, EJEMPLOS_POR_FORMATO, construir_prompt_sistema


@pytest.mark.parametrize("formato", list(_SCHEMA_POR_FORMATO))
def test_cada_formato_tiene_un_ejemplo_valido_para_su_esquema(formato):
    """Un ejemplo few-shot que no cumpla el esquema enseñaría al modelo una salida inválida."""
    ejemplo = _SCHEMA_POR_FORMATO[formato].model_validate(EJEMPLOS_POR_FORMATO[formato])
    citados = {f for elem in ejemplo.model_dump().values() if isinstance(elem, list) for x in elem
               if isinstance(x, dict) for f in x.get("fuentes", [])} | set(ejemplo.model_dump().get("fuentes", []))
    assert citados == {EJEMPLO_CHUNK["chunk_id"]}  # el ejemplo enseña a citar la fuente


@pytest.mark.parametrize("formato", list(_SCHEMA_POR_FORMATO))
def test_el_prompt_del_redactor_lleva_rol_y_ejemplo(formato):
    prompt = construir_prompt_sistema(formato, "Principiante", "Salud", "Didáctico")
    assert prompt.startswith("Eres ")  # role prompting
    assert "[EJEMPLO]" in prompt and EJEMPLO_CHUNK["chunk_id"] in prompt  # few-shot
    assert "No copies este ejemplo" in prompt
