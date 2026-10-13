from __future__ import annotations

import json
import os

from pydantic import ValidationError

from nuevamente.config import settings
from nuevamente.llm.base import LLMError, PROMPT_CORRECCION_JSON
from nuevamente.llm.rotacion import CUOTA_AGOTADA, TRANSITORIO, RotacionModelos


class _ErrorHTTP(Exception):
    """Error de la API de OpenAI-compatible, normalizado a la forma que espera la rotación."""

    def __init__(self, codigo: int, mensaje: str) -> None:
        super().__init__(f"HTTP {codigo}: {mensaje}")
        self.codigo = codigo
        self.mensaje = mensaje


class OpenAICompatLLM:
    """Implementación de `LLMClient` sobre cualquier endpoint chat/completions de OpenAI.

    Un mismo objeto sirve a Groq, Cerebras y OpenRouter: cambia `base_url`, la clave y los
    identificadores de modelo. Solo se usa el cliente `openai` si está instalado; si no, se
    habla HTTP directamente con `httpx`, que ya es dependencia del proyecto. Así el
    proveedor Groq funciona con `pip install -e .` sin instalar nada extra.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        modelo: str,
        modelos_respaldo: tuple[str, ...] = (),
        *,
        etiqueta: str = "Proveedor",
        max_intentos: int = 3,
        temperatura: float = 0.2,
        timeout: float = 60.0,
        max_tokens: int = 4096,
    ) -> None:
        if not api_key:
            raise LLMError(f"{etiqueta} requiere su API key configurada (ver .env.example).")

        self.nombre_modelo = modelo
        self._etiqueta = etiqueta
        self._temperatura = temperatura
        self._max_intentos = max_intentos
        self._max_tokens = max_tokens
        self._rotacion = RotacionModelos([modelo, *modelos_respaldo])
        self.nombre_modelo = self._rotacion.modelo_actual

        # Modelos que aceptan json_schema. El resto cae a json_object con reparación.
        self._soporta_json_schema = True
        self._timeout = timeout

        try:
            from openai import OpenAI
        except ImportError:
            OpenAI = None  # type: ignore[assignment]

        if OpenAI is not None:
            self._client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                max_retries=0,  # los reintentos los gestiona RotacionModelos
                timeout=timeout,
            )
            self._httpx = None
        else:
            import httpx

            self._client = None
            self._httpx = httpx.Client(
                base_url=base_url.rstrip("/"),
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=timeout,
            )

    # --- llamada a la API -------------------------------------------
    
    def _llamar(self, modelo: str, mensajes: list[dict], esquema: dict) -> str:
        cuerpo: dict = {
            "model": modelo,
            "messages": mensajes,
            "temperature": self._temperatura,
        }
        # Los modelos gpt-oss de Groq son de razonamiento y, sin acotarlo, se llevan
        # el 85-90% del presupuesto de tokens pensando (medido: 885 de 999 tokens) antes
        # de escribir el JSON. Con el prompt de 12 chunks eso agota el TPM de la org y
        # dispara 429. 'low' deja ~20 tokens de razonamiento y el JSON completo.
        if modelo.startswith("openai/gpt-oss"):
            cuerpo["reasoning_effort"] = "low"
            # Tope alto a propósito: razonamiento + JSON + 8-12 flashcards. Sin esto el
            # proveedor decide el corte y puede devolver el JSON a medio escribir.
            cuerpo["max_completion_tokens"] = self._max_tokens
        if self._soporta_json_schema:
            cuerpo["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": esquema.get("title", "salida"), "schema": esquema},
            }
        else:
            # Groq rechaza json_object si los mensajes no mencionan "json" en algún
            # punto: 400 "messages must contain the word 'json'". Los prompts de
            # prompts.py no lo dicen, así que hay que asegurarlo al degradar.
            cuerpo["messages"] = [
                {**m, "content": m["content"] + "\n\nResponde únicamente en formato JSON."}
                if i == 0
                else m
                for i, m in enumerate(mensajes)
            ]
            cuerpo["response_format"] = {"type": "json_object"}

        if self._client is not None:
            respuesta = self._client.chat.completions.create(**cuerpo)
            return respuesta.choices[0].message.content or ""

        respuesta = self._httpx.post("/chat/completions", json=cuerpo)
        if respuesta.status_code >= 400:
            raise _ErrorHTTP(respuesta.status_code, _mensaje_de_error(respuesta.text))
        datos = respuesta.json()
        return datos["choices"][0]["message"].get("content") or ""

    def _clasificar(self, exc: Exception) -> str:
        codigo = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        if codigo is None:
            codigo = getattr(exc, "codigo", None)
        if codigo is None:
            raise LLMError(f"Error no clasificado de {self._etiqueta}: {exc}") from exc

        codigo = int(codigo)
        # 400 blaming json_schema: el modelo no soporta salidas estructuradas estrictas.
        # Se degrada a json_object y se reintenta. Un 400 por cualquier otra causa
        # (prompt demasiado largo, campo inválido) no se reintenta ni se degrada.
        if codigo == 400 and self._soporta_json_schema and _rechaza_el_esquema(exc):
            self._soporta_json_schema = False
            raise _ReintentarSinEsquema() from exc
        # 400 "Failed to generate/validate JSON": el modelo sí aceptó el esquema pero
        # su salida no lo valida. No es culpa del prompt ni del esquema, así que no
        # degrada ni rota: se reintenta la misma llamada, que con otro sorteo del
        # modelo suele salir bien. Es transitorio aunque llegue como 400.
        if codigo == 400 and _fallo_de_generar_json(exc):
            return TRANSITORIO
        if codigo == 400:
            raise LLMError(f"Error de la API de {self._etiqueta} (400): {exc}") from exc

        from nuevamente.llm.rotacion import CODIGOS_TRANSITORIOS

        if codigo not in CODIGOS_TRANSITORIOS:
            raise LLMError(f"Error de la API de {self._etiqueta} ({codigo}): {exc}") from exc
        if _cuota_diaria_agotada(codigo, str(exc)):
            return CUOTA_AGOTADA
        return TRANSITORIO

    # --- interfaz LLMClient ------------------------------------------------

    @property
    def clave_proveedor(self) -> str:
        return self._etiqueta.lower()

    def generar_estructurado(self, schema: type, system: str, user: str):
        mensajes = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        esquema = schema.model_json_schema()
        ultimo_error = ""

        for _ in range(self._max_intentos):
            try:
                texto = self._rotacion.ejecutar(
                    lambda m: self._llamar(m, mensajes, esquema), self._clasificar, self._etiqueta
                )
            except _ReintentarSinEsquema:
                continue  # el siguiente intento ya usará response_format=json_object
            # Tras rotar, `nombre_modelo` debe decir qué modelo respondió de verdad, que es
            # lo que queda en los metadatos de la generación.
            self.nombre_modelo = self._rotacion.modelo_actual

            try:
                return schema.model_validate_json(texto)
            except ValidationError as exc:
                # Se le devuelve al modelo su propia respuesta y el error para que la corrija.
                ultimo_error = str(exc)
                mensajes += [
                    {"role": "assistant", "content": texto},
                    {
                        "role": "user",
                        "content": PROMPT_CORRECCION_JSON.format(error=ultimo_error),
                    },
                ]

        raise LLMError(
            f"{self._etiqueta} ({self.nombre_modelo}) no devolvió un JSON válido para "
            f"{schema.__name__} tras {self._max_intentos} intentos: {ultimo_error}"
        )


class _ReintentarSinEsquema(Exception):
    """Señal interna: el proveedor rechazó json_schema, reintentar en modo json_object."""


def _mensaje_de_error(cuerpo: str) -> str:
    """Extrae el mensaje de error de la respuesta, sea JSON o texto plano."""
    try:
        datos = json.loads(cuerpo)
    except (ValueError, TypeError):
        return cuerpo[:400]
    error = datos.get("error", datos) if isinstance(datos, dict) else datos
    if isinstance(error, dict):
        return str(error.get("message", error))[:400]
    return str(error)[:400]


def _cuota_diaria_agotada(codigo: int, cuerpo: str) -> bool:
    """Distingue límite diario de límite por minuto en los proveedores OpenAI-compatible.

    Groq y Cerebras distinguen `requests` (por minuto) de `tokens` por día; OpenRouter
    responde 429 sin más detalle. Ante la duda se asume transitorio: un reintento con
    backoff es barato frente a saltarse un modelo que sí habría respondido.
    """
    if codigo != 429:
        return False
    # Groq/Cerebras: 429 con límite de tokens por día agotado.
    marcadores = (
        "requests per day",
        "tokens per day",
        "daily",
        "day_limit",
        "per day",
    )
    return any(m in cuerpo.lower() for m in marcadores)


# Frases con las que Groq, Cerebras y OpenRouter señalan que el modelo no acepta
# `response_format` con esquema. Si un 400 no menciona nada de esto, el problema es otro
# (un prompt demasiado largo, un campo mal nombrado) y no se arregla degradando el modo:
# degradar solo gastaría un intento de cuota y ocultaría el error real.
_PISTAS_ESQUEMA = ("json_schema", "response_format", "structured output", "structured_output")

# Groq responde 400 con estos mensajes cuando el modelo acepta el esquema pero su
# salida no lo valida. Verificado contra api.groq.com con gpt-oss-20b: es intermitente
# para el mismo prompt (4 llamadas idénticas: 3 HTTP 200, 1 HTTP 400), o sea que la
# respuesta correcta es reintentar, no degradar el modo de salida.
_FALLO_JSON = ("failed to generate json", "failed to validate json", "failed_generation")


def _rechaza_el_esquema(exc: Exception) -> bool:
    return any(pista in str(exc).lower() for pista in _PISTAS_ESQUEMA)


def _fallo_de_generar_json(exc: Exception) -> bool:
    return any(pista in str(exc).lower() for pista in _FALLO_JSON)


# --- Fábricas por proveedor concreto ---------------------------------------
# Los modelos por defecto son los que cada proveedor sirve hoy en su plan gratuito.
# Se pueden sobreescribir con LLM_MODELOS_<PROVEEDOR> sin tocar código.


def _modelos_de(nombre_var: str, por_defecto: tuple[str, ...]) -> tuple[str, ...]:
    crudo = os.getenv(nombre_var, "")
    return tuple(m.strip() for m in crudo.split(",") if m.strip()) or por_defecto


def crear_groq(api_key: str | None = None, modelo: str | None = None) -> OpenAICompatLLM:
    return _crear(
        base_url="https://api.groq.com/openai/v1",
        api_key=api_key or settings.groq_api_key,
        modelo=modelo,
        modelos_defecto=_modelos_de(
            "LLM_MODELOS_GROQ", ("openai/gpt-oss-120b", "openai/gpt-oss-20b")
        ),
        etiqueta="Groq",
    )


def crear_cerebras(api_key: str | None = None, modelo: str | None = None) -> OpenAICompatLLM:
    return _crear(
        base_url="https://api.cerebras.ai/v1",
        api_key=api_key or settings.cerebras_api_key,
        modelo=modelo,
        modelos_defecto=_modelos_de("LLM_MODELOS_CEREBRAS", ("gpt-oss-120b", "qwen-3.8-27b")),
        etiqueta="Cerebras",
    )


def crear_openrouter(api_key: str | None = None, modelo: str | None = None) -> OpenAICompatLLM:
    return _crear(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key or settings.openrouter_api_key,
        modelo=modelo,
        # El router `openrouter/free` elige entre los modelos gratuitos que admiten la
        # característica que pide la petición; útil cuando los IDs :free concretos rotan.
        modelos_defecto=_modelos_de(
            "LLM_MODELOS_OPENROUTER",
            (
                "openrouter/free",
                "google/gemma-4-31b-it:free",
                "nvidia/nemotron-3-super-120b-a12b:free",
            ),
        ),
        etiqueta="OpenRouter",
    )


def _crear(
    base_url: str,
    api_key: str,
    modelo: str | None,
    modelos_defecto: tuple[str, ...],
    etiqueta: str,
) -> OpenAICompatLLM:
    modelos = list(dict.fromkeys([modelo, *modelos_defecto])) if modelo else list(modelos_defecto)
    return OpenAICompatLLM(
        base_url=base_url,
        api_key=api_key,
        modelo=modelos[0],
        modelos_respaldo=tuple(modelos[1:]),
        etiqueta=etiqueta,
    )
