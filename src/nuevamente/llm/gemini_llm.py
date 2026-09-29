"""GeminiLLM: proveedor real usando el SDK oficial google-genai.

Responsable en el equipo Kairos G10: Adrian Gil (ML Engineer).

Implementa la misma interfaz `LLMClient` que TemplateLLM (ver llm/base.py), así
que el resto del pipeline no cambia. Se activa con LLM_PROVIDER=gemini y
GEMINI_API_KEY o GEMINI_API_KEYS en el .env.

Diseño:
  - Salida estructurada: se pide JSON con el JSON Schema del modelo Pydantic
    (`response_json_schema`), y la respuesta se valida con ese mismo modelo.
  - Si el JSON no valida, se reenvía el error de validación al modelo para que
    lo corrija, hasta `max_intentos`.
  - Rotación de API keys (`RotacionKeys`): si una clave agota su cuota diaria
    (429 / quota exceeded), pasa inmediatamente a la siguiente clave disponible
    manteniendo el modelo principal, multiplicando la capacidad de peticiones.
  - Errores transitorios (503 ServiceUnavailable, 429 RPM/TPM ResourceExhausted):
    se reintentan automáticamente con backoff exponencial y jitter (delay base 2s,
    duplicando hasta 5 reintentos).
  - Control de flujo (RPM / TPM): un RateLimiter previene saturación entre llamadas.
  - Optimización de modelo: detección de variantes 'Pro' para cambiar por defecto a 'Flash'.
  - Diagnóstico detallado: registro en logs del código HTTP exacto, mensaje y headers.
"""
from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import ValidationError

from nuevamente.config import settings
from nuevamente.llm.base import LLMError
from nuevamente.llm.rotacion import (
    CODIGOS_TRANSITORIOS,
    CREDENCIAL_INVALIDA,
    CUOTA_AGOTADA,
    REINTENTOS_RED,
    TRANSITORIO,
    RateLimiter,
    RotacionKeys,
)

logger = logging.getLogger("nuevamente.llm.gemini")

# Soporte para excepciones estándar de Google si están disponibles
try:
    from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
    _GOOGLE_CORE_EXCEPTIONS = (ResourceExhausted, ServiceUnavailable)
except ImportError:
    _GOOGLE_CORE_EXCEPTIONS = ()


def _cuota_diaria_agotada(exc: Exception) -> bool:
    """True si el 429 es por el límite diario/cuota, no por el de peticiones por minuto."""
    code = getattr(exc, "code", None)
    if code is None:
        code = getattr(exc, "status_code", None)
    if code is None and ("ResourceExhausted" in exc.__class__.__name__):
        code = 429
    if code != 429:
        return False

    msg = (getattr(exc, "message", "") or str(exc)).lower()
    marcadores = (
        "perday",
        "per_day",
        "per day",
        "daily",
        "quota exceeded",
        "quota_exhausted",
        "quota exhausted",
        "resource_exhausted",
        "resource has been exhausted",
        "resourceexhausted",
        "requests per day",
        "tokens per day",
    )
    if any(m in msg for m in marcadores):
        return True

    detalles = getattr(exc, "details", None)
    detalles_lista = []
    if isinstance(detalles, dict):
        detalles_lista = detalles.get("error", {}).get("details", [])
    elif isinstance(detalles, list):
        detalles_lista = detalles

    if isinstance(detalles_lista, list):
        for d in detalles_lista:
            if isinstance(d, dict):
                for v in d.get("violations", []):
                    if isinstance(v, dict) and "perday" in v.get("quotaId", "").lower():
                        return True
    return False


# 401/403: la credencial no vale. Con varias keys configuradas esto no tumba al
# proveedor, solo descarta esa key y se sigue con la siguiente.
_CODIGOS_CREDENCIAL = frozenset({401, 403})


def _extraer_diagnostico(exc: Exception) -> dict[str, Any]:
    """Extrae código HTTP exacto, mensaje, encabezados de respuesta y detalles para diagnóstico."""
    codigo = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if codigo is None:
        nombre_exc = exc.__class__.__name__
        if "ResourceExhausted" in nombre_exc:
            codigo = 429
        elif "ServiceUnavailable" in nombre_exc:
            codigo = 503

    mensaje = getattr(exc, "message", None) or str(exc)

    headers = None
    resp = getattr(exc, "response", None)
    if resp is not None:
        headers = getattr(resp, "headers", None)
    if headers is None:
        headers = getattr(exc, "headers", None)

    detalles = getattr(exc, "details", None)
    return {
        "codigo_http": codigo,

        "mensaje": mensaje,
        "headers": dict(headers) if headers is not None else None,
        "detalles": detalles,
    }


def _clasificar(exc: Exception) -> str:
    """Traduce cualquier excepción de Gemini (incluidas ResourceExhausted y ServiceUnavailable)
    a la decisión de rotación y reintento.
    """
    codigo = getattr(exc, "code", None)
    if codigo is None:
        codigo = getattr(exc, "status_code", None)

    if _GOOGLE_CORE_EXCEPTIONS and isinstance(exc, _GOOGLE_CORE_EXCEPTIONS):
        if "ResourceExhausted" in exc.__class__.__name__:
            codigo = 429
        elif "ServiceUnavailable" in exc.__class__.__name__:
            codigo = 503

    if codigo is None:
        nombre_exc = exc.__class__.__name__
        if "ResourceExhausted" in nombre_exc:
            codigo = 429
        elif "ServiceUnavailable" in nombre_exc:
            codigo = 503

    if codigo in _CODIGOS_CREDENCIAL:
        return CREDENCIAL_INVALIDA
    if codigo not in CODIGOS_TRANSITORIOS:
        diag = _extraer_diagnostico(exc)
        raise LLMError(
            f"Error no reintentable de la API de Gemini ({codigo}): {diag['mensaje']} "
            f"| Headers: {diag['headers']}"
        ) from exc
    if _cuota_diaria_agotada(exc):
        return CUOTA_AGOTADA
    return TRANSITORIO



class GeminiLLM:
    """Implementación de LLMClient sobre la API de Gemini con rotación de claves y modelos."""

    def __init__(
        self,
        api_key: str | None = None,
        api_keys: Sequence[str] | None = None,
        modelo: str | None = None,
        modelos_respaldo: Sequence[str] | None = None,
        max_intentos: int = 3,
        temperatura: float = 0.2,
        reintentos_red: int | None = None,
        espera_inicial: float | None = None,
        espera_maxima: float = 30.0,
        retraso_rpm: float | None = None,
        preferir_flash: bool | None = None,
        client_factory: Callable[[str], Any] | None = None,
    ) -> None:
        claves: list[str] = []
        if api_keys:
            claves.extend(k.strip() for k in api_keys if k and k.strip())
        elif api_key:
            claves.extend(k.strip() for k in api_key.split(",") if k and k.strip())
        else:
            claves.extend(settings.gemini_api_keys)
            if not claves and settings.gemini_api_key:
                claves.append(settings.gemini_api_key)

        claves = list(dict.fromkeys(claves))
        if not claves:
            raise LLMError(
                "LLM_PROVIDER=gemini requiere GEMINI_API_KEY o GEMINI_API_KEYS en el .env."
            )

        if client_factory is None:
            try:
                from google import genai
            except ImportError as exc:
                raise LLMError(
                    "Falta el SDK de Gemini. Instálalo con: pip install -e \".[gemini]\""
                ) from exc

        self.etiqueta = "gemini"

        # 3. Optimización de modelo: si se solicita un modelo 'Pro' y está habilitada
        # la preferencia por Flash, se optimiza por defecto a 'gemini-1.5-flash'
        # que ofrece throughput y límites de cuota gratuita (RPM/RPD) mucho más amplios.
        modelo_base = modelo or settings.llm_model
        usar_flash = preferir_flash if preferir_flash is not None else settings.gemini_preferir_flash
        if usar_flash and "pro" in modelo_base.lower():
            logger.warning(
                "Detectada variante Pro ('%s') con cuotas estrictas de RPM/TPM en el plan gratuito. "
                "Optimizando automáticamente a 'gemini-1.5-flash' para mayor throughput.",
                modelo_base,
            )
            modelo_base = "gemini-1.5-flash"

        respaldo = (
            modelos_respaldo
            if modelos_respaldo is not None
            else settings.llm_modelos_respaldo
        )
        self.modelos = list(dict.fromkeys([modelo_base, *respaldo]))
        self.nombre_modelo = self.modelos[0]
        self._rotacion_keys = RotacionKeys(claves)
        self._max_intentos = max_intentos
        self._temperatura = temperatura

        # 1. Backoff exponencial y reintentos (hasta 5 reintentos con delay base 2s)
        self._reintentos_red = (
            reintentos_red if reintentos_red is not None else settings.gemini_max_reintentos
        )
        self._espera_inicial = (
            espera_inicial if espera_inicial is not None else settings.gemini_delay_base
        )
        self._espera_maxima = espera_maxima
        self._client_factory = client_factory
        self._clients: dict[str, Any] = {}

        # 2. Control de flujo y rate limits (RPM / TPM):
        retraso_segundos = retraso_rpm if retraso_rpm is not None else settings.gemini_rpm_delay
        self._rate_limiter = RateLimiter(retraso_minimo_segundos=retraso_segundos)

    @property
    def api_key_actual(self) -> str:
        """Devuelve la clave API actualmente activa."""
        return self._rotacion_keys.key_actual

    @property
    def api_keys(self) -> tuple[str, ...]:
        """Devuelve todas las claves API configuradas."""
        return tuple(self._rotacion_keys.keys)

    def _obtener_cliente(self, key: str):
        if key not in self._clients:
            if self._client_factory is not None:
                self._clients[key] = self._client_factory(key)
            else:
                from google import genai

                self._clients[key] = genai.Client(api_key=key)
        return self._clients[key]

    def _llamar(self, key: str, modelo: str, contents: list, config) -> str:
        """Una llamada a la API para una clave y modelo dados con control de tasa (RPM)."""
        # Control de flujo: pausa prudente para no saturar RPM ni TPM
        self._rate_limiter.esperar()
        cliente = self._obtener_cliente(key)
        respuesta = cliente.models.generate_content(
            model=modelo, contents=contents, config=config
        )
        return respuesta.text or ""

    def _ejecutar(self, contents: list, config) -> str:
        """Ejecuta la llamada recorriendo modelos y rotando API keys ante cuota agotada,
        con backoff exponencial, jitter y diagnóstico detallado de errores.
        """
        ultimo_error: Exception | None = None
        claves_probadas: set[str] = set()

        for modelo in self.modelos:
            # Si todas estaban agotadas para el modelo anterior, se reinician
            # para intentar con el siguiente modelo de respaldo
            if not self._rotacion_keys.hay_clave_usable():
                self._rotacion_keys.reiniciar()

            while self._rotacion_keys.hay_clave_usable():
                clave = self._rotacion_keys.key_actual
                claves_probadas.add(clave)

                decision_final = None
                for intento in range(self._reintentos_red):
                    try:
                        texto = self._llamar(clave, modelo, contents, config)
                        self.nombre_modelo = modelo
                        return texto
                    except Exception as exc:
                        decision = _clasificar(exc)
                        ultimo_error = exc
                        if decision in (CUOTA_AGOTADA, CREDENCIAL_INVALIDA):
                            decision_final = decision
                            break
                        if intento < self._reintentos_red - 1:
                            # 1. Backoff exponencial con jitter aleatorio
                            jitter = random.uniform(0.1, 1.0) * min(1.0, float(self._espera_inicial))
                            espera = min(
                                float(self._espera_inicial) * (2 ** intento) + jitter,
                                float(self._espera_maxima),
                            )
                            # 4. Diagnóstico de errores durante los reintentos
                            diag = _extraer_diagnostico(exc)
                            logger.warning(
                                "[Gemini Reintento %d/%d] Modelo: '%s' | HTTP %s: %s | Headers: %s | Espera: %.2fs",
                                intento + 1,
                                self._reintentos_red,
                                modelo,
                                diag["codigo_http"],
                                diag["mensaje"],
                                diag["headers"],
                                espera,
                            )
                            time.sleep(espera)

                if decision_final == CREDENCIAL_INVALIDA:
                    self._rotacion_keys.descartar(clave)
                    continue
                if decision_final == CUOTA_AGOTADA:
                    self._rotacion_keys.marcar_agotada(clave)
                    continue
                # Error transitorio continuo en este modelo tras reintentos (ej. 503 saturado):
                # probar el siguiente modelo de respaldo
                break

        # 4. Diagnóstico detallado al agotar todos los intentos
        diag = _extraer_diagnostico(ultimo_error) if ultimo_error else {}
        logger.error(
            "[Gemini Error Agotado] No se pudo completar la llamada tras reintentos. "
            "Modelos probados: %s | HTTP: %s | Mensaje: %s | Headers: %s | Detalles: %s",
            ", ".join(self.modelos),
            diag.get("codigo_http"),
            diag.get("mensaje"),
            diag.get("headers"),
            diag.get("detalles"),
        )
        raise LLMError(
            f"Gemini no disponible tras agotar reintentos (modelos probados: {', '.join(self.modelos)}; "
            f"keys probadas: {len(claves_probadas)}, "
            f"descartadas por credencial inválida: {len(self._rotacion_keys.descartadas)}). "
            f"Diagnóstico: HTTP {diag.get('codigo_http')} - {diag.get('mensaje')} "
            f"| Headers: {diag.get('headers')}"
        ) from ultimo_error


    def generar_estructurado(self, schema: type, system: str, user: str):
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self._temperatura,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
        )
        contents: list = [types.Content(role="user", parts=[types.Part(text=user)])]
        ultimo_error = ""

        for _ in range(self._max_intentos):
            try:
                texto = self._ejecutar(contents, config)
            except LLMError:
                # Tras agotar todas las keys y modelos de Gemini, la cadena (si la hay) prueba
                # con otra API. Sin cadena, el error sube y la API responde 502.
                raise
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

