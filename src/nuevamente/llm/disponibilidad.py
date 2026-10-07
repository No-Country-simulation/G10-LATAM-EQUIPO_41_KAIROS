"""Pausa de servicios externos que acaban de fallar (patrón "circuit breaker").

Si Gemini está saturado o sin cuota, cada solicitud esperaría de nuevo sus
tiempos de espera antes de caer al respaldo. Tras un fallo, el servicio queda en
pausa unos minutos (LLM_PAUSA_TRAS_FALLO_MIN) y las solicitudes siguientes van
directo al respaldo, sin esperar.
"""
from __future__ import annotations

import threading
import time

from nuevamente.config import settings

_pausas: dict[str, tuple[float, str]] = {}
_candado = threading.Lock()


def pausar(servicio: str, motivo: str, minutos: float | None = None) -> None:
    minutos = settings.llm_pausa_min if minutos is None else minutos
    if minutos <= 0:
        return
    with _candado:
        _pausas[servicio] = (time.monotonic() + minutos * 60, motivo)


def en_pausa(servicio: str) -> str | None:
    """Devuelve el motivo si el servicio está en pausa; None si se puede usar."""
    with _candado:
        pausa = _pausas.get(servicio)
        if pausa is None:
            return None
        hasta, motivo = pausa
        if time.monotonic() >= hasta:
            del _pausas[servicio]
            return None
        return motivo


def reanudar(servicio: str) -> None:
    with _candado:
        _pausas.pop(servicio, None)
