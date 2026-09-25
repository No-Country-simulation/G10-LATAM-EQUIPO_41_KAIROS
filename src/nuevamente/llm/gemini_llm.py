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
"""
from __future__ import annotations

import time

from pydantic import ValidationError

from nuevamente.config import settings
from nuevamente.llm.base import LLMError

_CODIGOS_TRANSITORIOS = {429, 500, 502, 503, 504}
# Intentos por modelo ante errores transitorios, antes de pasar al de respaldo.
# Cada intento cuenta para la cuota diaria (20 peticiones/modelo en el plan gratuito).
_REINTENTOS_RED = 3


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
        self._client = genai.Client(api_key=api_key)
        self._max_intentos = max_intentos
        self._temperatura = temperatura

    def _llamar(self, contents: list, config, errors) -> str:
        """Hace una llamada con reintentos ante errores transitorios (429/5xx).

        Si el modelo actual sigue saturado tras `_REINTENTOS_RED` intentos, pasa al
        siguiente modelo de respaldo. `nombre_modelo` queda con el que respondió, así
        los metadatos reflejan el modelo que generó el contenido de verdad.
        """
        ultimo: Exception | None = None
        for modelo in self._modelos:
            for intento in range(_REINTENTOS_RED):
                try:
                    respuesta = self._client.models.generate_content(
                        model=modelo, contents=contents, config=config
                    )
                    self.nombre_modelo = modelo
                    return respuesta.text or ""
                except errors.APIError as exc:
                    if exc.code not in _CODIGOS_TRANSITORIOS:
                        raise LLMError(f"Error de la API de Gemini ({exc.code}): {exc.message}") from exc
                    ultimo = exc
                    if _cuota_diaria_agotada(exc):
                        break  # reintentar no sirve hasta mañana: siguiente modelo
                    if intento < _REINTENTOS_RED - 1:
                        time.sleep(min(2 ** (intento + 1), 20))
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

        for _ in range(self._max_intentos):
            texto = self._llamar(contents, config, errors)
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
