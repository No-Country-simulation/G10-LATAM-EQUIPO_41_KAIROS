"""Fábrica de proveedores LLM. Responsable: Adrian Gil (ML Engineer).

Un registro con una entrada por proveedor, en vez de una cadena de `if`, para que añadir
una API sea agregar una línea. Las llamadas a los proveedores que necesitan un SDK propio
van diferidas dentro de su factory: así importar este módulo nunca falla por una
dependencia opcional que no esté instalada.

`LLM_PROVIDER=auto` devuelve una `CadenaLLM` (ver cadena_llm.py) que va cayendo de una
API a la siguiente según `LLM_CADENA`, que es lo que evita que la generación se corte
cuando se acaba la cuota diaria de un proveedor gratuito.
"""
from __future__ import annotations

from collections.abc import Callable

from nuevamente.config import settings
from nuevamente.llm.base import LLMClient
from nuevamente.llm.template_llm import TemplateLLM


def _crear_gemini() -> LLMClient:
    from nuevamente.llm.gemini_llm import GeminiLLM

    return GeminiLLM()


def _crear_groq() -> LLMClient:
    from nuevamente.llm.openai_compat_llm import crear_groq

    return crear_groq()


def _crear_cerebras() -> LLMClient:
    from nuevamente.llm.openai_compat_llm import crear_cerebras

    return crear_cerebras()


def _crear_openrouter() -> LLMClient:
    from nuevamente.llm.openai_compat_llm import crear_openrouter

    return crear_openrouter()


def _crear_cadena() -> LLMClient:
    from nuevamente.llm.cadena_llm import crear_cadena

    return crear_cadena()


#: Proveedores disponibles, por nombre de `LLM_PROVIDER` / `LLM_CADENA`.
_FACTORIES: dict[str, Callable[[], LLMClient]] = {
    "template": TemplateLLM,
    "gemini": _crear_gemini,
    "groq": _crear_groq,
    "cerebras": _crear_cerebras,
    "openrouter": _crear_openrouter,
    "auto": _crear_cadena,
}


def crear_llm(proveedor: str | None = None) -> LLMClient:
    proveedor = (proveedor or settings.llm_provider).strip().lower()
    if proveedor not in _FACTORIES:
        raise NotImplementedError(
            f"Proveedor LLM '{proveedor}' no implementado. Usa "
            f"{', '.join(sorted(_FACTORIES))}, o implementa una clase con la interfaz "
            "LLMClient (ver llm/base.py) y regístrala en _FACTORIES."
        )
    return _FACTORIES[proveedor]()
