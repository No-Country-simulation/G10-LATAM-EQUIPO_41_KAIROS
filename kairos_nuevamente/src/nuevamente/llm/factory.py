"""Fábrica de proveedores LLM. Responsable: Adrian Gil (ML Engineer)."""
from __future__ import annotations

from nuevamente.config import settings
from nuevamente.llm.base import LLMClient
from nuevamente.llm.template_llm import TemplateLLM


def crear_llm(proveedor: str | None = None) -> LLMClient:
    proveedor = proveedor or settings.llm_provider
    if proveedor == "template":
        return TemplateLLM()
    raise NotImplementedError(
        f"Proveedor LLM '{proveedor}' no implementado en este entorno (sin acceso de "
        "red a APIs externas). Implementa una clase con la interfaz LLMClient "
        "(ver llm/base.py) y regístrala aquí. Ejemplo objetivo para producción: "
        "GeminiLLMClient usando el SDK google-genai con GEMINI_API_KEY."
    )
