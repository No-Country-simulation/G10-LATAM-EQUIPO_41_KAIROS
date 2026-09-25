"""Fábrica de proveedores LLM. Responsable: Adrian Gil (ML Engineer)."""
from __future__ import annotations

from nuevamente.config import settings
from nuevamente.llm.base import LLMClient
from nuevamente.llm.template_llm import TemplateLLM


def crear_llm(proveedor: str | None = None) -> LLMClient:
    proveedor = proveedor or settings.llm_provider
    if proveedor == "template":
        return TemplateLLM()
    if proveedor == "gemini":
        # Import diferido: google-genai es una dependencia opcional (extra "gemini").
        from nuevamente.llm.gemini_llm import GeminiLLM

        return GeminiLLM()
    raise NotImplementedError(
        f"Proveedor LLM '{proveedor}' no implementado. Usa 'template' o 'gemini', o "
        "implementa una clase con la interfaz LLMClient (ver llm/base.py) y regístrala aquí."
    )
