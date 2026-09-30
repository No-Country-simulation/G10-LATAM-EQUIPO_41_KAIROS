"""Política compartida de rotación de modelos y de API keys.

La lógica de reintento con backoff y de paso al siguiente modelo estaba escrita dentro
de `GeminiLLM`, así que cada proveedor nuevo tendría que copiarla. Aquí vive una sola vez
y la usan todos los clientes de `nuevamente.llm`: Gemini y los proveedores compatibles
con la API de OpenAI (Groq, Cerebras, OpenRouter).

La rotación tiene tres niveles según la necesidad:
1. `RotacionKeys`: rota entre varias API keys del mismo proveedor (ej. GEMINI_API_KEYS)
   cuando una clave agota su cuota diaria, multiplicando la capacidad sin cambiar de modelo.
2. `RotacionModelos`: rota entre modelos del mismo proveedor ante errores de cuota o
   saturación temporal de un modelo en particular.
3. `CadenaLLM`: rota entre APIs independientes (Gemini -> Groq -> Cerebras -> OpenRouter)
   cuando un proveedor completo no responde o no tiene credenciales.
"""
from __future__ import annotations

import random
import time
from collections.abc import Callable, Sequence

from nuevamente.llm.base import LLMError

# Códigos que valen la pena reintentar: límite de tasa y errores de servidor/puerta de
# enlace. Cualquier otro (401 sin credenciales, 400 por un prompt inválido) es un fallo
# de configuración y no tiene sentido reintentarlo ni rotar.
CODIGOS_TRANSITORIOS = frozenset({408, 425, 429, 500, 502, 503, 504})

# Intentos por modelo ante errores transitorios (503/429), antes de pasar al de respaldo.
REINTENTOS_RED = 5


# Decisiones que puede devolver un clasificador de errores de proveedor.
TRANSITORIO = "transitorio"
CUOTA_AGOTADA = "cuota_agotada"
# La clave o credencial en sí está mal (401/403). No es un problema del modelo ni del
# prompt, así que no tiene sentido reintentar con ella, pero sí tiene sentido probar con
# la siguiente: una key caducada no invalida las demás.
CREDENCIAL_INVALIDA = "credencial_invalida"


class RotacionModelos:
    """Recorre una lista de modelos reintentando cada uno antes de pasar al siguiente.

    Uso típico dentro de un cliente de proveedor::

        self._rotacion = RotacionModelos([modelo_principal, *respaldo])
        texto = self._rotacion.ejecutar(self._llamar, self._clasificar, "Gemini")

    El `clasificar` recibe la excepción del SDK del proveedor y devuelve `TRANSITORIO` o
    `CUOTA_AGOTADA`. Si el error no es reintentable debe lanzar `LLMError` él mismo: la
    rotación solo se ocupa de los casos en los que tiene sentido seguir intentando.
    """

    def __init__(
        self,
        modelos: Sequence[str],
        reintentos: int = REINTENTOS_RED,
        espera_inicial: int = 2,
        espera_maxima: int = 20,
    ) -> None:
        # Sin repetidos y respetando el orden: el primero es el modelo principal.
        self.modelos = list(dict.fromkeys(m for m in modelos if m))
        if not self.modelos:
            raise LLMError("La rotación necesita al menos un modelo configurado.")
        self.reintentos = max(1, reintentos)
        self.espera_inicial = max(1, espera_inicial)
        self.espera_maxima = max(self.espera_inicial, espera_maxima)
        self.modelo_actual = self.modelos[0]

    def ejecutar(
        self,
        llamar: Callable[[str], str],
        clasificar: Callable[[Exception], str],
        etiqueta: str,
    ) -> str:
        """Llama a `llamar(modelo)` hasta que un modelo responda.

        Ante un error transitorio reintenta el mismo modelo con backoff exponencial.
        Si la cuota diaria de ese modelo está agotada, abandona el modelo de inmediato
        (esperar no sirve hasta el reset) y pasa al siguiente. Si se agotan todos los
        modelos, lanza `LLMError` con la lista de los probados.
        """
        ultimo_error: Exception | None = None
        for modelo in self.modelos:
            for intento in range(self.reintentos):
                try:
                    texto = llamar(modelo)
                except Exception as exc:  # noqa: BLE001 - `clasificar` decide qué hacer
                    decision = clasificar(exc)  # puede lanzar LLMError si es fatal
                    ultimo_error = exc
                    if decision == CUOTA_AGOTADA:
                        break  # reintentar no sirve hasta el reset: siguiente modelo
                    if intento < self.reintentos - 1:
                        # Backoff exponencial con jitter: base * 2^intento + jitter aleatorio
                        jitter = random.uniform(0.1, 1.0) * min(1.0, float(self.espera_inicial))
                        espera = min(float(self.espera_inicial) * (2 ** intento) + jitter, float(self.espera_maxima))
                        time.sleep(espera)
                else:
                    # Se actualiza también el nombre del modelo en el cliente para que los
                    # metadatos reflejen el que generó el contenido de verdad.
                    self.modelo_actual = modelo
                    return texto

        raise LLMError(
            f"{etiqueta} no disponible (modelos probados: {', '.join(self.modelos)}): {ultimo_error}"
        ) from ultimo_error


class RateLimiter:
    """Control de flujo prudente entre llamadas a la API para respetar cuotas de RPM/TPM.

    Asegura una pausa mínima entre peticiones sucesivas para evitar ráfagas descontroladas
    que saturan la cuota por minuto.
    """

    def __init__(self, retraso_minimo_segundos: float = 1.5) -> None:
        self.retraso_minimo = max(0.0, float(retraso_minimo_segundos))
        self._ultimo_acceso: float = 0.0

    def esperar(self) -> float:
        """Pausa la ejecución si no ha transcurrido el intervalo mínimo desde la última llamada."""
        if self.retraso_minimo <= 0:
            return 0.0
        ahora = time.time()
        transcurrido = ahora - self._ultimo_acceso
        tiempo_espera = 0.0
        if self._ultimo_acceso > 0 and transcurrido < self.retraso_minimo:
            tiempo_espera = self.retraso_minimo - transcurrido
            time.sleep(tiempo_espera)
        self._ultimo_acceso = time.time()
        return tiempo_espera



class RotacionKeys:
    """Administra una lista de API keys con rotación ante agotamiento de cuota.

    Mantiene la clave activa actual para que las peticiones subsiguientes no repitan
    claves que ya agotaron su cuota diaria.
    """

    def __init__(self, keys: Sequence[str]) -> None:
        self.keys = list(dict.fromkeys(k.strip() for k in keys if k and k.strip()))
        if not self.keys:
            raise LLMError("La rotación de API keys necesita al menos una clave configurada.")
        self._indice = 0
        self._agotadas: set[str] = set()
        # Claves descartadas por credencial inválida. A diferencia de la cuota, esto no se
        # reinicia: una key caducada no vuelve a ser buena dentro del mismo proceso.
        self._descartadas: set[str] = set()

    @property
    def key_actual(self) -> str:
        """Devuelve la clave activa actual."""
        return self.keys[self._indice]

    @property
    def total_keys(self) -> int:
        """Cantidad total de claves configuradas."""
        return len(self.keys)

    @property
    def agotadas(self) -> set[str]:
        """Conjunto de claves marcadas como agotadas."""
        return set(self._agotadas)

    @property
    def descartadas(self) -> set[str]:
        """Claves descartadas por credencial inválida (no vuelven tras un reinicio)."""
        return set(self._descartadas)

    def marcar_agotada(self, key: str) -> None:
        """Registra una clave como agotada de cuota y avanza a la siguiente disponible."""
        self._agotadas.add(key)
        self._avanzar_a_disponible()

    def descartar(self, key: str) -> None:
        """Marca una clave como inutilizable (401/403) y avanza a la siguiente.

        Es la diferencia con `marcar_agotada`: una cuota se repone mañana, una credencial
        inválida no. Por eso `reiniciar` no limpia las descartadas.
        """
        self._descartadas.add(key)
        self._avanzar_a_disponible()

    def todas_agotadas(self) -> bool:
        """Indica si no queda ninguna clave usable (agotada o descartada)."""
        return len(self._agotadas | self._descartadas) >= len(self.keys)

    def hay_clave_usable(self) -> bool:
        """Indica si queda alguna clave que no esté agotada ni descartada."""
        return not self.todas_agotadas()

    def rotar(self) -> str:
        """Fuerza la rotación de la clave actual (marcándola como agotada) a la siguiente."""
        self.marcar_agotada(self.key_actual)
        return self.key_actual

    def reiniciar(self) -> None:
        """Reinicia las claves agotadas de cuota y regresa el índice a 0.

        Las descartadas por credencial inválida se conservan: reiniciar es para cuando
        vence el día y vuelve la cuota, no para arreglar una key que ya no sirve.
        """
        self._agotadas.clear()
        self._indice = 0
        self._avanzar_a_disponible()

    def _avanzar_a_disponible(self) -> None:
        if self.todas_agotadas():
            return
        for i in range(len(self.keys)):
            idx = (self._indice + i) % len(self.keys)
            if self.keys[idx] not in self._agotadas and self.keys[idx] not in self._descartadas:
                self._indice = idx
                return

    def claves_disponibles(self) -> list[str]:
        """Devuelve la lista de claves aún utilizables en orden a partir de la activa."""
        if self.todas_agotadas():
            return []
        disponibles: list[str] = []
        for i in range(len(self.keys)):
            idx = (self._indice + i) % len(self.keys)
            k = self.keys[idx]
            if k not in self._agotadas and k not in self._descartadas:
                disponibles.append(k)
        return disponibles

