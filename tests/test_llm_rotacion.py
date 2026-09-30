"""Pruebas de la rotación de modelos y la cadena de proveedores.

Responsable: Diana Dure (QA Tester).

Nada aquí toca la red: los clientes de prueba son dobles que cuentan llamadas, y el
cliente OpenAI-compatible se ejerce contra un `httpx.MockTransport` en memoria.
"""
from __future__ import annotations

import json
import time

import pytest
from pydantic import BaseModel

from nuevamente.llm.base import LLMError
from nuevamente.llm.cadena_llm import CadenaLLM, crear_cadena
from nuevamente.llm.rotacion import CUOTA_AGOTADA, TRANSITORIO, RotacionKeys, RotacionModelos


class Salida(BaseModel):
    titulo: str
    puntos: list[str]


class Falso:
    """Cliente de la interfaz LLMClient que falla o responde según se le pida."""

    def __init__(self, etiqueta: str, *, falla: bool = False, json_invalido: bool = False) -> None:
        self.etiqueta = etiqueta
        self.nombre_modelo = f"{etiqueta}-modelo"
        self._falla = falla
        self._json_invalido = json_invalido
        self.llamadas = 0

    def generar_estructurado(self, schema, system, user):
        self.llamadas += 1
        if self._falla:
            raise LLMError(f"{self.etiqueta}: cuota diaria agotada")
        if self._json_invalido:
            return schema.model_validate_json('{"titulo": 1}') if False else _romper(schema)
        return schema.model_validate({"titulo": self.etiqueta, "puntos": ["a"]})


def _romper(schema):
    raise LLMError("respuesta no irreparable")


# --- RotacionModelos --------------------------------------------------------


def test_rota_al_siguiente_modelo_tras_un_error_transitorio():
    """Un 429 de cuota diaria no se reintenta: se pasa al modelo de respaldo."""
    intentos: dict[str, int] = {}

    def llamar(modelo: str) -> str:
        intentos[modelo] = intentos.get(modelo, 0) + 1
        if modelo == "principal":
            raise RuntimeError("429 quota")
        return f"respuesta de {modelo}"

    rotacion = RotacionModelos(["principal", "respaldo"])
    texto = rotacion.ejecutar(llamar, lambda exc: CUOTA_AGOTADA, "Prueba")

    assert texto == "respuesta de respaldo"
    assert intentos["principal"] == 1, "no debe reintentar un modelo sin cuota"
    assert rotacion.modelo_actual == "respaldo"


def test_reintenta_el_mismo_modelo_antes_de_rotar():
    """Un 5xx sí admite reintento, y solo después se pasa al siguiente modelo."""
    intentos: dict[str, int] = {}

    def llamar(modelo: str) -> str:
        intentos[modelo] = intentos.get(modelo, 0) + 1
        if modelo == "principal" and intentos[modelo] < 2:
            raise RuntimeError("503")
        return "ok"

    rotacion = RotacionModelos(["principal"], reintentos=3, espera_inicial=1)
    assert rotacion.ejecutar(llamar, lambda exc: TRANSITORIO, "Prueba") == "ok"
    assert intentos["principal"] == 2, "debe reintentar antes de rendirse"


def test_error_fatal_no_rota():
    """Un 401 es un problema de credenciales: falla de inmediato, sin gastar cuota."""

    def llamar(modelo: str) -> str:
        raise RuntimeError("401")

    def clasificar(exc):
        raise LLMError("credenciales invalidas")

    with pytest.raises(LLMError, match="credenciales invalidas"):
        RotacionModelos(["a", "b"], espera_inicial=1).ejecutar(llamar, clasificar, "Prueba")


def test_agota_todos_los_modelos_y_lista_cuales():
    with pytest.raises(LLMError) as exc:
        RotacionModelos(
            ["a", "b"], espera_inicial=1
        ).ejecutar(lambda m: (_ for _ in ()).throw(RuntimeError("500")), lambda e: CUOTA_AGOTADA, "Prueba")
    assert "a, b" in str(exc.value)


def test_rotacion_exige_al_menos_un_modelo():
    with pytest.raises(LLMError, match="al menos un modelo"):
        RotacionModelos([])


# --- RotacionKeys ------------------------------------------------------------


def test_rotacion_keys_avanza_al_marcar_agotada():
    rot = RotacionKeys(["k1", "k2", "k3"])
    assert rot.key_actual == "k1"
    assert rot.total_keys == 3
    assert not rot.todas_agotadas()

    rot.marcar_agotada("k1")
    assert rot.key_actual == "k2"
    assert rot.agotadas == {"k1"}
    assert rot.claves_disponibles() == ["k2", "k3"]

    rot.marcar_agotada("k2")
    assert rot.key_actual == "k3"
    assert not rot.todas_agotadas()

    rot.marcar_agotada("k3")
    assert rot.todas_agotadas()
    assert rot.claves_disponibles() == []


def test_rotacion_keys_reiniciar():
    rot = RotacionKeys(["k1", "k2"])
    rot.marcar_agotada("k1")
    rot.marcar_agotada("k2")
    assert rot.todas_agotadas()

    rot.reiniciar()
    assert not rot.todas_agotadas()
    assert rot.key_actual == "k1"
    assert rot.claves_disponibles() == ["k1", "k2"]


def test_rotacion_keys_sin_claves_lanza_error():
    with pytest.raises(LLMError, match="al menos una clave"):
        RotacionKeys([])


def test_rotacion_keys_ignora_duplicados_y_espacios():
    rot = RotacionKeys(["  k1 ", "k2", "k1", ""])
    assert rot.keys == ["k1", "k2"]
    assert rot.total_keys == 2


def test_rotacion_keys_rotar_fuerza_avance():
    rot = RotacionKeys(["k1", "k2"])
    siguiente = rot.rotar()
    assert siguiente == "k2"
    assert rot.key_actual == "k2"
    assert rot.agotadas == {"k1"}


def test_rotacion_keys_descartar_una_credencial_invalida():
    """Una key inválida se aparta y no cuenta como disponible."""
    rot = RotacionKeys(["k1", "k2", "k3"])
    rot.descartar("k1")

    assert rot.descartadas == {"k1"}
    assert rot.key_actual == "k2"
    assert rot.claves_disponibles() == ["k2", "k3"]
    assert rot.hay_clave_usable()


def test_rotacion_keys_reiniciar_no_recupera_una_key_invalida():
    """La cuota se repone al día siguiente; una credencial inválida no."""
    rot = RotacionKeys(["k1", "k2"])
    rot.descartar("k1")
    rot.marcar_agotada("k2")
    assert not rot.hay_clave_usable()

    rot.reiniciar()

    # k2 vuelve (era cuota, no credencial) pero k1 sigue fuera para siempre.
    assert rot.descartadas == {"k1"}, "un 401 no se arregla reiniciando la cuota"
    assert rot.claves_disponibles() == ["k2"]



# --- CadenaLLM: rotación entre APIs -----------------------------------------


def test_cadena_cae_a_la_siguiente_api_cuando_una_agota_cuota():
    cadena = CadenaLLM([Falso("gemini", falla=True), Falso("groq")])
    resultado = cadena.generar_estructurado(Salida, "sys", "user")

    assert resultado.titulo == "groq"
    # Los metadatos deben decir qué API generó el contenido de verdad.
    assert cadena.nombre_modelo == "groq:groq-modelo"


def test_cadena_no_gasta_intentos_si_el_primero_responde():
    segundo = Falso("groq")
    cadena = CadenaLLM([Falso("gemini"), segundo])

    cadena.generar_estructurado(Salida, "sys", "user")

    assert segundo.llamadas == 0, "no debe tocar la segunda API si la primera respondió"


def test_cadena_reporta_todos_los_intentos_si_ninguna_responde():
    with pytest.raises(LLMError) as exc:
        CadenaLLM([Falso("gemini", falla=True), Falso("groq", falla=True)]).generar_estructurado(
            Salida, "sys", "user"
        )
    mensaje = str(exc.value)
    assert "gemini" in mensaje and "groq" in mensaje


def test_cadena_omite_proveedores_sin_api_key():
    """Sin clave de un proveedor, la cadena debe seguir funcionando con los demás."""

    def sin_credencial():
        raise LLMError("requiere su API key")

    factories = {
        "gemini": sin_credencial,
        "groq": lambda: Falso("groq"),
        "cerebras": sin_credencial,
    }
    cadena = crear_cadena(["gemini", "groq", "cerebras"], factories=factories)

    assert len(cadena._clientes) == 1
    assert cadena.generar_estructurado(Salida, "sys", "user").titulo == "groq"


def test_cadena_sin_ninguna_credenencial_explica_que_revisar():
    def sin_credencial():
        raise LLMError("requiere su API key")

    with pytest.raises(LLMError, match="credenciales"):
        crear_cadena(["gemini"], factories={"gemini": sin_credencial})


def test_cadena_rechaza_proveedor_desconocido():
    with pytest.raises(LLMError, match="no está en la cadena"):
        crear_cadena(["no-existe"], factories={})


def test_cadena_vacia_es_error_explicito():
    with pytest.raises(LLMError, match="ningún cliente utilizable"):
        CadenaLLM([])


# --- Cliente OpenAI-compatible ----------------------------------------------


def _cliente_falso(respuestas, **kwargs):
    """Construye un OpenAICompatLLM con un transporte HTTP simulado.

    `respuestas` es una lista de tuplas (status, json) o funciones que reciben el cuerpo
    de la petición y devuelven esa tupla, para poder simular 400 en el primer intento.
    """
    import httpx

    from nuevamente.llm.openai_compat_llm import OpenAICompatLLM

    enviados: list[dict] = []
    cola = list(respuestas)

    def manejador(peticion: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(peticion.content)
        enviados.append(cuerpo)
        paso = cola.pop(0) if len(cola) > 1 else cola[0]
        codigo, datos = paso(cuerpo) if callable(paso) else paso
        return httpx.Response(codigo, json=datos)

    cliente = OpenAICompatLLM(
        base_url="https://ejemplo.test/v1",
        api_key="clave-de-prueba",
        modelo="modelo-a",
        modelos_respaldo=("modelo-b",),
        etiqueta="Prueba",
        **kwargs,
    )
    cliente._client = None
    cliente._httpx = httpx.Client(
        base_url="https://ejemplo.test/v1", transport=httpx.MockTransport(manejador)
    )
    return cliente, enviados


def _ok():
    return (200, {"choices": [{"message": {"content": '{"titulo": "hola", "puntos": ["a"]}'}}]})


def test_cliente_pide_json_schema_y_valida_la_salida():
    cliente, enviados = _cliente_falso([_ok()])
    salida = cliente.generar_estructurado(Salida, "instruccion", "contenido")

    assert salida.titulo == "hola"
    assert enviados[0]["response_format"]["type"] == "json_schema"
    assert enviados[0]["messages"][0] == {"role": "system", "content": "instruccion"}


def test_cliente_degrada_a_json_object_si_el_proveedor_rechaza_el_esquema():
    """Groq y OpenRouter no aceptan json_schema en todos sus modelos: hay que caer a json_object."""

    def rechaza_esquema(cuerpo):
        if cuerpo["response_format"]["type"] == "json_schema":
            return (400, {"error": {"message": "response_format json_schema not supported"}})
        return _ok()

    cliente, enviados = _cliente_falso([rechaza_esquema])
    salida = cliente.generar_estructurado(Salida, "sys", "user")

    assert salida.titulo == "hola"
    assert enviados[0]["response_format"]["type"] == "json_schema"
    assert enviados[1]["response_format"]["type"] == "json_object"


def test_cliente_repara_el_json_invalido_reenviando_el_error():
    respuestas = [
        (200, {"choices": [{"message": {"content": '{"titulo": "hola"}'}}]}),  # falta "puntos"
        _ok(),
    ]
    cliente, enviados = _cliente_falso(respuestas)
    salida = cliente.generar_estructurado(Salida, "sys", "user")

    assert salida.puntos == ["a"]
    # Al modelo hay que devolverle su respuesta mala y el motivo del rechazo.
    roles = [m["role"] for m in enviados[1]["messages"]]
    assert roles == ["system", "user", "assistant", "user"]


def test_cliente_rota_de_modelo_ante_un_429():
    respuestas = [
        lambda cuerpo: (
            (429, {"error": {"message": "Rate limit reached for tokens per day"}})
            if cuerpo["model"] == "modelo-a"
            else _ok()
        )
    ]
    cliente, enviados = _cliente_falso(respuestas)
    salida = cliente.generar_estructurado(Salida, "sys", "user")

    assert salida.titulo == "hola"
    assert [c["model"] for c in enviados] == ["modelo-a", "modelo-b"]
    assert cliente.nombre_modelo == "modelo-b"


def test_cliente_ignora_rotacion_ante_un_400_de_prompt():
    """Un 400 no es saturación: es un error del prompt, repetirlo no lo arregla."""
    cliente, enviados = _cliente_falso([(400, {"error": {"message": "invalid request"}})])

    with pytest.raises(LLMError, match="400"):
        cliente.generar_estructurado(Salida, "sys", "user")
    assert len(enviados) == 1, "no debe reintentar ni rotar ante un 400"


def test_cliente_rechaza_el_esquema_solo_si_el_error_lo_dice():
    """Solo se degrada a json_object si el 400 menciona el esquema o response_format."""
    respuestas = [
        lambda cuerpo: (
            (400, {"error": {"message": "response_format is not supported for this model"}})
            if cuerpo["response_format"]["type"] == "json_schema"
            else _ok()
        )
    ]
    cliente, enviados = _cliente_falso(respuestas)

    assert cliente.generar_estructurado(Salida, "sys", "user").titulo == "hola"
    assert enviados[1]["response_format"]["type"] == "json_object"


# --- GeminiLLM: rotación de API keys ----------------------------------------
from typing import Any


class _FalsoAPIError(Exception):
    def __init__(self, code: int, message: str, details: dict | None = None) -> None:
        super().__init__(f"APIError {code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}


class _FalsoClienteGemini:
    """Doble de prueba que emula el SDK genai.Client sin conexión a red."""

    def __init__(self, key: str, simulador) -> None:
        self.key = key
        self.simulador = simulador
        self.models = self

    def generate_content(self, model: str, contents: list, config: Any = None) -> Any:
        return self.simulador(self.key, model, contents, config)


class _FalsaRespuesta:
    def __init__(self, text: str) -> None:
        self.text = text


def _simular_gemini(simulador, **kwargs):
    from nuevamente.llm.gemini_llm import GeminiLLM

    def factory(key: str):
        return _FalsoClienteGemini(key, simulador)

    opciones = {"espera_inicial": 0.001, "reintentos_red": 2, "retraso_rpm": 0.0}
    opciones.update(kwargs)
    return GeminiLLM(client_factory=factory, **opciones)



def test_gemini_rota_a_siguiente_api_key_cuando_se_agota_cuota():
    """Un 429 de cuota diaria rota a la siguiente API key manteniendo el modelo."""
    llamadas: list[tuple[str, str]] = []

    def simulador(key: str, model: str, contents: list, config: Any):
        llamadas.append((key, model))
        if key == "k1":
            raise _FalsoAPIError(
                429,
                "Resource has been exhausted. Quota exceeded for quota metric 'requests per day'",
                details={"error": {"details": [{"violations": [{"quotaId": "GenerateContentRequestsPerDayPerProject"}]}]}},
            )
        return _FalsaRespuesta('{"titulo": "resultado k2", "puntos": ["p1"]}')

    gemini = _simular_gemini(simulador, api_keys=["k1", "k2"], modelo="gemini-3.8-flash")
    salida = gemini.generar_estructurado(Salida, "sys", "user")

    assert salida.titulo == "resultado k2"
    assert gemini.api_key_actual == "k2"
    assert llamadas == [("k1", "gemini-3.8-flash"), ("k2", "gemini-3.8-flash")]


def test_gemini_recuerda_la_key_activa_en_subsecuentes_llamadas():
    """Tras rotar a k2, las siguientes peticiones van directo a k2 sin tocar k1."""
    llamadas: list[str] = []

    def simulador(key: str, model: str, contents: list, config: Any):
        llamadas.append(key)
        if key == "k1":
            raise _FalsoAPIError(429, "PerDay limit reached")
        return _FalsaRespuesta('{"titulo": "exito", "puntos": ["a"]}')

    gemini = _simular_gemini(simulador, api_keys=["k1", "k2"], modelo="gemini-3.8-flash")

    # Primera llamada: k1 falla (cuota) -> rota a k2 -> ok
    gemini.generar_estructurado(Salida, "sys", "user")
    assert llamadas == ["k1", "k2"]

    # Segunda llamada: va directamente a k2
    llamadas.clear()
    gemini.generar_estructurado(Salida, "sys", "user")
    assert llamadas == ["k2"], "no debe volver a intentar k1 si ya agotó su cuota diaria"


def test_gemini_reintenta_error_transitorio_en_la_misma_key():
    """Un 503 o 429 RPM se reintenta en la misma key con backoff y no rota la key."""
    intentos: dict[str, int] = {}

    def simulador(key: str, model: str, contents: list, config: Any):
        intentos[key] = intentos.get(key, 0) + 1
        if intentos[key] == 1:
            raise _FalsoAPIError(503, "Service Unavailable")
        return _FalsaRespuesta('{"titulo": "ok", "puntos": ["a"]}')

    gemini = _simular_gemini(simulador, api_keys=["k1", "k2"], modelo="gemini-3.8-flash")
    salida = gemini.generar_estructurado(Salida, "sys", "user")

    assert salida.titulo == "ok"
    assert gemini.api_key_actual == "k1"
    assert intentos == {"k1": 2}


def test_gemini_rota_a_siguiente_key_ante_401_sin_reintentar_la_mala():
    """Una key inválida (401) se salta, pero no se reintenta ni tumba al proveedor.

    Es el caso real de una lista de keys donde una está caducada o mal pegada: con el
    comportamiento anterior, esa única key mala tumbaba a Gemini entero y se desperdiciaban
    las demás claves buenas.
    """
    llamadas: list[tuple[str, str]] = []

    def simulador(key: str, model: str, contents: list, config: Any):
        llamadas.append((key, model))
        if key == "k1":
            raise _FalsoAPIError(401, "API key not valid. Please pass a valid API key.")
        if key == "k2":
            raise _FalsoAPIError(401, "API key not valid. Please pass a valid API key.")
        return _FalsaRespuesta('{"titulo": "ok con k3", "puntos": ["a"]}')

    gemini = _simular_gemini(simulador, api_keys=["k1", "k2", "k3"], modelo="gemini-3.8-flash")
    salida = gemini.generar_estructurado(Salida, "sys", "user")

    assert salida.titulo == "ok con k3"
    assert gemini.api_key_actual == "k3"
    # Cada key mala se intenta UNA vez, sin reintentos, y con el mismo modelo.
    assert llamadas == [
        ("k1", "gemini-3.8-flash"),
        ("k2", "gemini-3.8-flash"),
        ("k3", "gemini-3.8-flash"),
    ]


def test_gemini_no_reintenta_una_key_invalida_en_llamadas_siguientes():
    """La key con 401 queda descartada para el resto del proceso, incluso tras reiniciar."""
    llamadas: list[str] = []

    def simulador(key: str, model: str, contents: list, config: Any):
        llamadas.append(key)
        if key in ("k1", "k2"):
            raise _FalsoAPIError(401, "API key not valid.")
        return _FalsaRespuesta('{"titulo": "ok", "puntos": ["a"]}')

    gemini = _simular_gemini(
        simulador, api_keys=["k1", "k2", "k3"], modelo="gemini-3.8-flash", modelos_respaldo=["gemini-3.5-flash"]
    )
    gemini.generar_estructurado(Salida, "sys", "user")
    assert llamadas == ["k1", "k2", "k3"]

    # Segunda petición: la cuota se repone, pero una credencial inválida no se arregla.
    llamadas.clear()
    gemini.generar_estructurado(Salida, "sys", "user")
    assert llamadas == ["k3"]


def test_gemini_todas_las_keys_invalidas_reporta_cuantas_se_descartaron():
    def simulador(key: str, model: str, contents: list, config: Any):
        raise _FalsoAPIError(401, "API key not valid.")

    gemini = _simular_gemini(simulador, api_keys=["k1", "k2"], modelo="gemini-3.8-flash")

    with pytest.raises(LLMError) as exc:
        gemini.generar_estructurado(Salida, "sys", "user")

    assert "descartadas por credencial inválida: 2" in str(exc.value)


def test_gemini_403_tambien_rota_de_key():
    """Un 403 (permisos) tiene el mismo tratamiento que un 401: se prueba otra key."""
    llamadas: list[str] = []

    def simulador(key: str, model: str, contents: list, config: Any):
        llamadas.append(key)
        if key == "k1":
            raise _FalsoAPIError(403, "Permission denied for this API key.")
        return _FalsaRespuesta('{"titulo": "ok", "puntos": ["a"]}')

    gemini = _simular_gemini(simulador, api_keys=["k1", "k2"], modelo="gemini-3.8-flash")

    assert gemini.generar_estructurado(Salida, "sys", "user").titulo == "ok"
    assert llamadas == ["k1", "k2"]


def test_gemini_401_no_tumba_al_siguiente_modelo_de_la_cadena():
    """Si todas las keys de Gemini son inválidas, el error sube y la cadena prueba otra API."""
    from nuevamente.llm.cadena_llm import CadenaLLM

    def simulador(key: str, model: str, contents: list, config: Any):
        raise _FalsoAPIError(401, "API key not valid.")

    gemini = _simular_gemini(simulador, api_keys=["k1", "k2"], modelo="gemini-3.8-flash")
    respaldo = Falso("openrouter")
    cadena = CadenaLLM([gemini, respaldo])

    assert cadena.generar_estructurado(Salida, "sys", "user").titulo == "openrouter"
    assert cadena.nombre_modelo == "openrouter:openrouter-modelo"


def test_gemini_agota_todas_las_keys_y_modelos_lanza_error():
    """Si todas las API keys agotan cuota en todos los modelos, falla explicando qué probó."""
    def simulador(key: str, model: str, contents: list, config: Any):
        raise _FalsoAPIError(429, "PerDay limit reached")

    gemini = _simular_gemini(
        simulador,
        api_keys=["k1", "k2"],
        modelo="gemini-3.8-flash",
        modelos_respaldo=["gemini-3.5-flash"],
    )

    with pytest.raises(LLMError) as exc:
        gemini.generar_estructurado(Salida, "sys", "user")

    mensaje = str(exc.value)
    assert "Gemini no disponible" in mensaje
    assert "keys probadas: 2" in mensaje
    assert "gemini-3.8-flash" in mensaje
    assert "gemini-3.5-flash" in mensaje


def test_gemini_parsea_varias_claves_desde_string_o_tupla():
    from nuevamente.llm.gemini_llm import GeminiLLM

    g1 = GeminiLLM(api_key="k1, k2, k3", client_factory=lambda k: None)
    assert g1.api_keys == ("k1", "k2", "k3")
    assert g1.api_key_actual == "k1"

    g2 = GeminiLLM(api_keys=["k_a", "k_b"], client_factory=lambda k: None)
    assert g2.api_keys == ("k_a", "k_b")


def test_gemini_sin_claves_lanza_error_explicito(monkeypatch):
    from nuevamente.config import Settings
    from nuevamente.llm.gemini_llm import GeminiLLM

    monkeypatch.setattr("nuevamente.llm.gemini_llm.settings", Settings(gemini_api_key="", gemini_api_keys=()))
    with pytest.raises(LLMError, match="requiere GEMINI_API_KEY o GEMINI_API_KEYS"):
        GeminiLLM(client_factory=lambda k: None)


# --- Tests de las 4 soluciones para servidor saturado / rate limits ----------


class ResourceExhausted(Exception):
    """Emula google.api_core.exceptions.ResourceExhausted (HTTP 429)."""
    def __init__(self, message: str, headers: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.headers = headers or {"retry-after": "5"}


class ServiceUnavailable(Exception):
    """Emula google.api_core.exceptions.ServiceUnavailable (HTTP 503)."""
    def __init__(self, message: str, headers: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.headers = headers or {"x-goog-ratelimit-reset": "2026-09-29T12:00:00Z"}


def test_gemini_captura_resource_exhausted_y_service_unavailable():
    """Captura ResourceExhausted (429) y ServiceUnavailable (503) de google.api_core.exceptions."""
    intentos: list[str] = []

    def simulador(key: str, model: str, contents: list, config: Any):
        intentos.append(key)
        if len(intentos) == 1:
            # Primero lanza 503 (servidor saturado): se debe reintentar con backoff
            raise ServiceUnavailable("This model is currently experiencing high demand.")
        if len(intentos) == 2:
            # Segundo lanza 429 cuota agotada: rota a la siguiente key
            raise ResourceExhausted("Resource has been exhausted (e.g. check quota per day).")
        return _FalsaRespuesta('{"titulo": "recuperado", "puntos": ["p1"]}')

    gemini = _simular_gemini(
        simulador,
        api_keys=["k1", "k2"],
        modelo="gemini-1.5-flash",
        reintentos_red=3,
        espera_inicial=0.001,
        retraso_rpm=0.0,
    )
    resultado = gemini.generar_estructurado(Salida, "sys", "user")

    assert resultado.titulo == "recuperado"
    assert gemini.api_key_actual == "k2"
    # k1 intentó el 503 (reintentó), luego dio 429 de cuota (rotó a k2), y k2 tuvo éxito
    assert "k1" in intentos and "k2" in intentos


def test_gemini_reintentos_hasta_5_con_backoff_y_jitter():
    """Implementa reintentos automáticos (hasta 5) con backoff exponencial ante 503."""
    intentos_cuenta = 0

    def simulador(key: str, model: str, contents: list, config: Any):
        nonlocal intentos_cuenta
        intentos_cuenta += 1
        if intentos_cuenta < 5:
            raise ServiceUnavailable("Servidor temporalmente saturado 503")
        return _FalsaRespuesta('{"titulo": "exito al 5to intento", "puntos": ["ok"]}')

    gemini = _simular_gemini(
        simulador,
        api_keys=["k1"],
        modelo="gemini-1.5-flash",
        reintentos_red=5,
        espera_inicial=0.001,
        retraso_rpm=0.0,
    )
    salida = gemini.generar_estructurado(Salida, "sys", "user")

    assert salida.titulo == "exito al 5to intento"
    assert intentos_cuenta == 5


def test_gemini_rate_limiter_control_de_flujo():
    """El RateLimiter previene saturar RPM/TPM pausando entre llamadas sucesivas."""
    from nuevamente.llm.rotacion import RateLimiter

    limiter = RateLimiter(retraso_minimo_segundos=0.05)
    t0 = time.time()
    limiter.esperar()
    limiter.esperar()  # Inmediata: debe esperar al menos ~0.05s
    t1 = time.time()

    assert (t1 - t0) >= 0.045, "RateLimiter debe forzar pausa entre llamadas consecutivas"


def test_gemini_optimizacion_modelo_pro_a_flash():
    """Si se configura una variante 'Pro', se optimiza por defecto a 'Flash' para mayor throughput."""
    from nuevamente.llm.gemini_llm import GeminiLLM

    # Con preferir_flash=True (por defecto), 'gemini-1.5-pro' cambia a 'gemini-1.5-flash'
    g_flash = GeminiLLM(
        api_key="k1",
        modelo="gemini-1.5-pro",
        preferir_flash=True,
        client_factory=lambda k: None,
    )
    assert g_flash.modelos[0] == "gemini-1.5-flash"
    assert g_flash.nombre_modelo == "gemini-1.5-flash"

    # Con preferir_flash=False, se respeta explícitamente el modelo Pro
    g_pro = GeminiLLM(
        api_key="k1",
        modelo="gemini-1.5-pro",
        preferir_flash=False,
        client_factory=lambda k: None,
    )
    assert g_pro.modelos[0] == "gemini-1.5-pro"


def test_gemini_diagnostico_incluye_codigo_mensaje_y_headers():
    """Registra y reporta en el LLMError el código HTTP, mensaje y headers exactos."""
    def simulador(key: str, model: str, contents: list, config: Any):
        raise ServiceUnavailable(
            "Service Unavailable: High demand spike",
            headers={"x-goog-ratelimit-reset": "30s", "retry-after": "30"},
        )

    gemini = _simular_gemini(
        simulador,
        api_keys=["k1"],
        modelo="gemini-1.5-flash",
        modelos_respaldo=(),
        reintentos_red=2,
        espera_inicial=0.001,
        retraso_rpm=0.0,
    )

    with pytest.raises(LLMError) as exc:
        gemini.generar_estructurado(Salida, "sys", "user")

    mensaje = str(exc.value)
    assert "Diagnóstico:" in mensaje
    assert "HTTP 503" in mensaje
    assert "High demand spike" in mensaje
    assert "retry-after" in mensaje or "x-goog-ratelimit-reset" in mensaje


