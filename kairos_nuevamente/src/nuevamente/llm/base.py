"""Interfaz común para cualquier proveedor de LLM.

Responsable en el equipo Kairos G10: Adrian Gil (ML Engineer).

Cualquier proveedor (Gemini, OpenAI, Anthropic, Ollama o el TemplateLLM usado en
este entorno de desarrollo sin API keys) implementa `LLMClient.generar_estructurado`,
que siempre devuelve una instancia validada del modelo Pydantic pedido. Así el resto
del pipeline (agents/) nunca sabe qué proveedor está usando de verdad.
"""
from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """Error de proveedor LLM (cuota, red, JSON irreparable, etc.)."""


class LLMClient(Protocol):
    nombre_modelo: str

    def generar_estructurado(
        self,
        schema: type[T],
        system: str,
        user: str,
    ) -> T:
        """Devuelve una instancia de `schema` generada a partir del prompt.

        Implementaciones reales deben reintentar con backoff y, si el JSON no
        valida, reenviar el error de validación al modelo antes de fallar con
        LLMError (ver docstring del prompt maestro / README para el diseño
        completo con Gemini en producción).
        """
        ...
