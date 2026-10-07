"""GeminiLLM: proveedor real usando el SDK oficial google-genai.

Responsable en el equipo Kairos G10: Adrian Gil (ML Engineer).

Implementa la misma interfaz `LLMClient` que TemplateLLM (ver llm/base.py), así
que el resto del pipeline no cambia. Se activa con LLM_PROVIDER=gemini y
GEMINI_API_KEY en el .env.

Diseño:
  - Salida estructurada: se pide JSON con el JSON Schema del modelo Pydantic
    (`response_json_schema`), y la respuesta se valida con ese mismo modelo.
  - Si el JSON no valida, se reenvía el error de validación al modelo para que
    lo corrija, hasta `max_intentos`.
  - Errores transitorios (cuota 429, 5xx) se reintentan con backoff exponencial y,
    si el modelo sigue saturado, se pasa a los de LLM_MODELOS_RESPALDO.
  - Cada llamada tiene un tiempo máximo (LLM_TIMEOUT_S) y todo el intento con Gemini
    un presupuesto total (LLM_PRESUPUESTO_S): si se agota, se abandona y el pipeline
    usa el respaldo local, en vez de dejar al usuario esperando minutos.
"""
from __future__ import annotations

import time

import httpx
from pydantic import ValidationError

from nuevamente.config import settings
from nuevamente.llm.base import LLMError

_CODIGOS_TRANSITORIOS = {429, 500, 502, 503, 504}
# Intentos por modelo ante errores transitorios, antes de pasar al de respaldo.
# Cada intento cuenta para la cuota diaria (20 peticiones/modelo en el plan gratuito).
_REINTENTOS_RED = 2
# Sin tiempo suficiente para una llamada útil, no vale la pena empezarla.
_MINIMO_PARA_LLAMAR_S = 8


def _cuota_diaria_agotada(exc) -> bool:
    """True si el 429 es por el límite diario, no por el de peticiones por minuto."""
    if exc.code != 429:
        return False
    detalles = (exc.details or {}).get("error", {}).get("details", [])
    return any(
        "PerDay" in v.get("quotaId", "") for d in detalles for v in d.get("violations", [])
    )


class GeminiLLM:
    """Implementación de LLMClient sobre la API de Gemini."""

    def __init__(
        self,
        api_key: str | None = None,
        modelo: str | None = None,
        max_intentos: int = 3,
        temperatura: float = 0.2,
    ) -> None:
        try:
            from google import genai
        except ImportError as exc:
            raise LLMError(
                "Falta el SDK de Gemini. Instálalo con: pip install -e \".[gemini]\""
            ) from exc

        api_key = api_key or settings.gemini_api_key
        if not api_key:
            raise LLMError("LLM_PROVIDER=gemini requiere GEMINI_API_KEY en el .env.")

        self.nombre_modelo = modelo or settings.llm_model
        # Modelo principal primero y luego los de respaldo, sin repetidos.
        self._modelos = list(dict.fromkeys([self.nombre_modelo, *settings.llm_modelos_respaldo]))
        from google.genai import types

        # Los reintentos los maneja _llamar (con presupuesto total); los del SDK se
        # desactivan para que no multipliquen la espera.
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=settings.llm_timeout_s * 1000,
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
        self._max_intentos = max_intentos
        self._temperatura = temperatura

    def _llamar(self, contents: list, config, errors, limite: float) -> str:
        """Hace una llamada con reintentos ante errores transitorios (429/5xx).

        Si el modelo actual sigue saturado tras `_REINTENTOS_RED` intentos, pasa al
        siguiente modelo de respaldo. `nombre_modelo` queda con el que respondió, así
        los metadatos reflejan el modelo que generó el contenido de verdad.
        `limite` (reloj monotónico) es el fin del presupuesto de todo el material.
        """
        from google.genai import types

        ultimo: Exception | None = None
        agotado = lambda: limite - time.monotonic() < _MINIMO_PARA_LLAMAR_S  # noqa: E731
        for modelo in self._modelos:
            for intento in range(_REINTENTOS_RED):
                if agotado():
                    break
                try:
                    # cada llamada espera como mucho lo que queda del presupuesto
                    restante_ms = int(min(settings.llm_timeout_s, limite - time.monotonic()) * 1000)
                    config_llamada = config.model_copy(update={"http_options": types.HttpOptions(
                        timeout=restante_ms, retry_options=types.HttpRetryOptions(attempts=1),
                    )})
                    respuesta = self._client.models.generate_content(
                        model=modelo, contents=contents, config=config_llamada
                    )
                    self.nombre_modelo = modelo
                    return respuesta.text or ""
                except errors.APIError as exc:
                    if exc.code not in _CODIGOS_TRANSITORIOS:
                        raise LLMError(f"Error de la API de Gemini ({exc.code}): {exc.message}") from exc
                    ultimo = exc
                    if _cuota_diaria_agotada(exc):
                        break  # reintentar no sirve hasta mañana: siguiente modelo
                    if intento < _REINTENTOS_RED - 1 and not agotado():
                        time.sleep(min(2 ** (intento + 1), 20))
                except httpx.HTTPError as exc:
                    # Sin conexión, DNS, SSL cortado o sin respuesta a tiempo: transitorio, igual que un 503.
                    ultimo = exc
                    if intento < _REINTENTOS_RED - 1 and not agotado():
                        time.sleep(min(2 ** (intento + 1), 20))
            if agotado():
                break
        if agotado():
            raise LLMError(
                f"Gemini no respondió dentro de {settings.llm_presupuesto_s} s "
                f"(modelos probados hasta agotar el tiempo; último error: {ultimo})."
            ) from ultimo
        if isinstance(ultimo, httpx.HTTPError):
            raise LLMError(
                f"No hay conexión con Gemini. Revisa tu conexión a internet ({ultimo})."
            ) from ultimo
        raise LLMError(
            f"Gemini no disponible (modelos probados: {', '.join(self._modelos)}): {ultimo}"
        ) from ultimo

    def generar_estructurado(self, schema: type, system: str, user: str):
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self._temperatura,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
        )
        contents: list = [types.Content(role="user", parts=[types.Part(text=user)])]
        ultimo_error = ""
        limite = time.monotonic() + settings.llm_presupuesto_s

        for _ in range(self._max_intentos):
            texto = self._llamar(contents, config, errors, limite)
            try:
                return schema.model_validate_json(texto)
            except ValidationError as exc:
                # Se le devuelve al modelo su propia respuesta y el error para que la corrija.
                ultimo_error = str(exc)
                contents += [
                    types.Content(role="model", parts=[types.Part(text=texto)]),
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                text="Tu respuesta no cumple el esquema JSON. Corrige estos "
                                f"errores y devuelve el JSON completo:\n{ultimo_error}"
                            )
                        ],
                    ),
                ]

        raise LLMError(
            f"Gemini ({self.nombre_modelo}) no devolvió un JSON válido para {schema.__name__} tras "
            f"{self._max_intentos} intentos: {ultimo_error}"
        )
