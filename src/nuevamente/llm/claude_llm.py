"""ClaudeLLM: proveedor real usando el SDK oficial de Anthropic.

Implementa la misma interfaz `LLMClient` que TemplateLLM y GeminiLLM (ver
llm/base.py), así que el resto del pipeline no cambia. Se activa con
LLM_PROVIDER=claude y ANTHROPIC_API_KEY en el .env.

Diseño:
  - Salida estructurada: `messages.parse(output_format=<modelo Pydantic>)` restringe
    la respuesta al esquema del formato y la devuelve ya validada.
  - Si aun así no valida (p. ej. una restricción que el esquema no puede expresar),
    se reenvía el error al modelo para que lo corrija, hasta `max_intentos`.
  - Los reintentos ante 429/5xx y errores de red los hace el propio SDK.
"""
from __future__ import annotations

from pydantic import ValidationError

from nuevamente.config import settings
from nuevamente.llm.base import LLMError


class ClaudeLLM:
    """Implementación de LLMClient sobre la API de Claude."""

    def __init__(self, api_key: str | None = None, modelo: str | None = None, max_intentos: int = 2) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise LLMError("Falta el SDK de Anthropic. Instálalo con: pip install -e \".[claude]\"") from exc

        api_key = api_key or settings.anthropic_api_key
        if not api_key:
            raise LLMError("LLM_PROVIDER=claude requiere ANTHROPIC_API_KEY en el .env.")

        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        self.nombre_modelo = modelo or settings.claude_model
        self._max_intentos = max_intentos

    def _llamar(self, schema: type, system: str, messages: list):
        a = self._anthropic
        try:
            return self._client.messages.parse(
                model=self.nombre_modelo,
                max_tokens=16000,
                system=system,
                messages=messages,
                output_format=schema,
            )
        except a.AuthenticationError as exc:
            raise LLMError("La ANTHROPIC_API_KEY no es válida o fue revocada.") from exc
        except a.PermissionDeniedError as exc:
            raise LLMError(f"La API key de Claude no tiene permiso para {self.nombre_modelo}.") from exc
        except a.NotFoundError as exc:
            raise LLMError(f"Modelo de Claude no encontrado: {self.nombre_modelo}.") from exc
        except a.RateLimitError as exc:
            raise LLMError(f"Claude alcanzó el límite de uso o de crédito: {exc.message}") from exc
        except a.BadRequestError as exc:
            if "credit balance" in str(exc.message):
                raise LLMError(
                    "La cuenta de Anthropic no tiene crédito. Cárgalo en platform.claude.com → Plans & Billing."
                ) from exc
            raise LLMError(f"Claude rechazó la petición: {exc.message}") from exc
        except a.APIStatusError as exc:
            raise LLMError(f"Error de la API de Claude ({exc.status_code}): {exc.message}") from exc
        except a.APIConnectionError as exc:
            raise LLMError("No hay conexión con Claude. Revisa tu conexión a internet.") from exc

    def generar_estructurado(self, schema: type, system: str, user: str):
        messages: list = [{"role": "user", "content": user}]
        ultimo_error = ""

        for _ in range(self._max_intentos):
            try:
                respuesta = self._llamar(schema, system, messages)
            except ValidationError as exc:
                # el JSON cumplió el esquema pero no una validación de Pydantic: se pide corregir
                ultimo_error = str(exc)
                messages += [
                    {"role": "assistant", "content": "(respuesta con errores de validación)"},
                    {"role": "user", "content": f"Tu respuesta no cumple el esquema. Corrige estos errores y devuelve el JSON completo:\n{ultimo_error}"},
                ]
                continue

            if respuesta.stop_reason == "refusal":
                raise LLMError("Claude declinó generar este contenido.")
            if respuesta.stop_reason == "max_tokens":
                raise LLMError("La respuesta de Claude se cortó por longitud (max_tokens).")
            if respuesta.parsed_output is None:
                raise LLMError("Claude no devolvió un JSON con el formato pedido.")
            return respuesta.parsed_output

        raise LLMError(
            f"Claude ({self.nombre_modelo}) no devolvió un JSON válido para {schema.__name__} tras "
            f"{self._max_intentos} intentos: {ultimo_error}"
        )
