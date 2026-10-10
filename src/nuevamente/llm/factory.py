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
import logging
import os
import threading

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

    @property
    def router(self):
        """El router de salud del principal (si es una cadena), para /api/v1/salud-llm."""
        return getattr(self._principal, "router", None)

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


def _crear_gemini() -> LLMClient:
    from nuevamente.llm.gemini_llm import GeminiLLM

    return GeminiLLM()


def _crear_claude() -> LLMClient:
    from nuevamente.llm.claude_llm import ClaudeLLM

    return ClaudeLLM()


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
    "claude": _crear_claude,
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
    if proveedor == "template" or not settings.llm_respaldo_local:
        return _con_cache(proveedor, _FACTORIES[proveedor])
    # Con LLM_RESPALDO_LOCAL, si el proveedor falla (cuota, "503 high demand", sin red) el
    # material se genera igual con el TemplateLLM en lugar de devolver un error al usuario.
    # El envoltorio es nuevo en cada generación (recuerda si ya cayó al respaldo en *esta*
    # generación); el cliente de la API sí sale de la cache.
    try:
        principal = _con_cache(proveedor, _FACTORIES[proveedor])
    except LLMError as exc:  # sin SDK o sin API key: directamente el respaldo
        logger.warning("Proveedor '%s' no configurado, se usa el respaldo local: %s", proveedor, exc)
        return TemplateLLM()
    return ConRespaldoLocal(principal, TemplateLLM())


# --- Cache de clientes -------------------------------------------------------
# Los clientes se construyen por petición, pero construir uno es caro: abrir la cadena
# costaba ~460 ms y, con Gemini dentro, crear su `genai.Client` y su `httpx.Client` sumaba
# unos ~700 ms más de handshake TLS. Reconstruirlos en cada request era overhead puro.
#
# Reutilizarlos además es lo correcto por diseño, no solo por velocidad: la rotación de
# claves de Gemini (rotacion.py) y el historial de salud de los proveedores (salud.py)
# viven en el objeto. Un cliente por petición los tiraría a la basura en cada llamada y el
# sistema no podría aprender de lo que le pasó en la anterior.
_clientes: dict[tuple, LLMClient] = {}
_cargo_lock = threading.Lock()

#: Variables que cambian cómo se construye un cliente. Si cambia alguna, la cache no sirve.
_VARIABLES_DE_CLIENTE = (
    "LLM_MODEL",
    "LLM_MODELOS_RESPALDO",
    "LLM_CADENA",
    "LLM_MODELOS_GROQ",
    "LLM_MODELOS_CEREBRAS",
    "LLM_MODELOS_OPENROUTER",
    "GEMINI_API_KEY",
    "GEMINI_API_KEYS",
    "GROQ_API_KEY",
    "CEREBRAS_API_KEY",
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_PREFERIR_FLASH",
    "GEMINI_MAX_REINTENTOS",
    "GEMINI_RPM_DELAY",
    "GEMINI_TIMEOUT",
    "GEMINI_DELAY_BASE",
    "CLAUDE_MODEL",
)


def _huella(proveedor: str) -> tuple:
    return (proveedor, *(os.getenv(v, "") for v in _VARIABLES_DE_CLIENTE))


def _con_cache(proveedor: str, construir: Callable[[], LLMClient]) -> LLMClient:
    huella = _huella(proveedor)
    cliente = _clientes.get(huella)
    if cliente is not None:
        return cliente
    with _cargo_lock:
        cliente = _clientes.get(huella)
        if cliente is None:
            cliente = construir()
            _clientes[huella] = cliente
    return cliente


def limpiar_cache_llm() -> None:
    """Vacía la cache de clientes. Para los tests y para recuperar tras un cambio de credenciales."""
    with _cargo_lock:
        _clientes.clear()
