"""Fábrica de proveedores LLM. Responsable: Adrian Gil (ML Engineer)."""
from __future__ import annotations

import logging

from nuevamente.config import settings
from nuevamente.llm import disponibilidad
from nuevamente.llm.base import LLMClient, LLMError
from nuevamente.llm.template_llm import TemplateLLM

logger = logging.getLogger(__name__)


class ConRespaldoLocal:
    """Usa el proveedor principal y, si falla (cuota, saturación, sin red), el TemplateLLM.

    Tras el primer fallo se queda con el respaldo el resto de la generación, para no
    esperar de nuevo a la API en cada reintento del Crítico. `nombre_modelo` indica
    siempre qué generó el contenido, así los metadatos no ocultan el cambio.
    """

    def __init__(self, principal: LLMClient, respaldo: LLMClient) -> None:
        self._principal = principal
        self._respaldo = respaldo
        self._servicio = f"llm:{type(principal).__name__}"
        self.nombre_modelo = principal.nombre_modelo
        # si el proveedor falló hace poco, se va directo al respaldo sin volver a esperarlo
        self.motivo_respaldo = disponibilidad.en_pausa(self._servicio) or ""
        self._usar_respaldo = bool(self.motivo_respaldo)

    def generar_estructurado(self, schema, system: str, user: str):
        if not self._usar_respaldo:
            try:
                resultado = self._principal.generar_estructurado(schema, system, user)
                self.nombre_modelo = self._principal.nombre_modelo
                disponibilidad.reanudar(self._servicio)
                return resultado
            except LLMError as exc:
                logger.warning(
                    "Proveedor principal no disponible, se usa el respaldo local por %s min: %s",
                    settings.llm_pausa_min, exc,
                )
                self._usar_respaldo = True
                self.motivo_respaldo = str(exc)
                disponibilidad.pausar(self._servicio, self.motivo_respaldo)
        self.nombre_modelo = f"{self._respaldo.nombre_modelo} (respaldo: {self._principal.nombre_modelo} no disponible)"
        return self._respaldo.generar_estructurado(schema, system, user)


def crear_llm(proveedor: str | None = None) -> LLMClient:
    proveedor = proveedor or settings.llm_provider
    if proveedor == "template":
        return TemplateLLM()
    if proveedor == "gemini":
        # Import diferido: google-genai es una dependencia opcional (extra "gemini").
        from nuevamente.llm.gemini_llm import GeminiLLM

        if settings.llm_respaldo_local:
            try:
                return ConRespaldoLocal(GeminiLLM(), TemplateLLM())
            except LLMError as exc:  # sin SDK o sin API key: directamente el respaldo
                logger.warning("Gemini no configurado, se usa el respaldo local: %s", exc)
                return TemplateLLM()
        return GeminiLLM()
    if proveedor == "claude":
        # Import diferido: anthropic es una dependencia opcional (extra "claude").
        from nuevamente.llm.claude_llm import ClaudeLLM

        if settings.llm_respaldo_local:
            try:
                return ConRespaldoLocal(ClaudeLLM(), TemplateLLM())
            except LLMError as exc:  # sin SDK o sin API key: directamente el respaldo
                logger.warning("Claude no configurado, se usa el respaldo local: %s", exc)
                return TemplateLLM()
        return ClaudeLLM()
    raise NotImplementedError(
        f"Proveedor LLM '{proveedor}' no implementado. Usa 'template', 'gemini' o 'claude', o "
        "implementa una clase con la interfaz LLMClient (ver llm/base.py) y regístrala aquí."
    )
