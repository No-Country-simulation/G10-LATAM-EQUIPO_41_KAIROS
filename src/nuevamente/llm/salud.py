"""Enrutado por salud: qué proveedor usar en este momento, según cómo se ha portado.

Responsable en el equipo Kairos G10: Adrian Gil (ML Engineer).

`CadenaLLM` (ver cadena_llm.py) recorre `LLM_CADENA` siempre desde el principio, así que
un proveedor lento o saturado se paga entero en cada petición: si Gemini entra en su racha
de "503 high demand", cada request se come sus reintentos y sus timeouts antes de llegar a
Groq. Reordenar la cadena a mano en el `.env` no sirve, porque el proveedor rápido cambia
de un momento a otro: hoy Gemini responde en 2 s y en diez minutos en 50 s.

Este módulo aprende de lo observado y contesta una pregunta distinta a la de la rotación de
modelos (rotacion.py): no *qué modelo* usar dentro de una API que ya sabemos que está sana,
sino *a qué API* llamar ahora mismo.

Separa Deliberadamente dos señales, porque merecen tratos distintos:

  - **Caídas** (el proveedor devuelve error: 429, 503, cuota, red): abren un circuito y
    apartan el proveedor durante un cooldown que crece con cada reincidencia. Es el
    circuit breaker clásico: dejar de gastar cuota y tiempo en quien está caído.
  - **Lentitud** (responde bien, pero tarde): no abre circuito. Solo baja su puesto en el
    orden, porque un proveedor lento sigue siendo un proveedor bueno y puede volver a ser
    el más rápido en la siguiente llamada. Confundir "lento" con "caído" sería tirar
    capacidad sana por un mal momento.

El orden resultante es: primero los circuitos a medio abrir (para comprobar que se
recuperaron), después los sanos ordenados por latencia media observada, y al final los
caídos, que nunca se descartan del todo: si todos están abiertos, el sistema los prueba
igual, porque quedarse sin generar contenido es peor que esperar.

Todo el estado se guarda con `time.monotonic()` (immune al cambio de hora del reloj) y se
protege con un lock, porque los endpoints de FastAPI son `def` y se ejecutan en un thread
pool: dos peticiones simultáneas escriben aquí a la vez.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from nuevamente.config import settings

# Estados del circuito de un proveedor.
CERRADO = "cerrado"  # sano: se usa con normalidad
SEMIABIERTO = "semiabierto"  # pasó el cooldown: se prueba para ver si se recuperó
ABIERTO = "abierto"  # caído: se aparta hasta que venza su cooldown

#: Un proveedor sin datos de latencia va al final dentro de su estado, para no inventar una
#: ventaja que no se ha medido. Entre los que sí tienen datos, gana el más rápido.
SIN_MEDIR = float("inf")


@dataclass
class SaludProveedor:
    """Lo que se sabe de un proveedor en este proceso."""

    clave: str
    posicion: int  # su lugar en LLM_CADENA, para desempatar y conservar el orden configurado
    circuito: str = CERRADO
    latencia: float | None = None  # media móvil exponencial, en segundos
    exitos: int = 0
    fallos: int = 0
    fallos_consecutivos: int = 0
    veces_abierto: int = 0
    abierto_hasta: float = 0.0  # monotonic; 0 = no está en cooldown
    ultima_latencia: float | None = None
    ultimo_error: str = ""

    @property
    def disponible(self) -> bool:
        """False solo mientras dura el cooldown; en semiabierto ya se puede volver a probar."""
        return self.circuito != ABIERTO or time.monotonic() >= self.abierto_hasta

    def cooldown_actual(self, base: float, tope: float) -> float:
        """Pausa antes de reintentar: crece con cada apertura para no martillear al caído."""
        if self.veces_abierto <= 1:
            return base
        return min(tope, base * (2 ** (self.veces_abierto - 1)))


class RouterSalud:
    """Decide el orden de los proveedores a partir de lo que se ha observado.

    `claves` es la cadena configurada, en orden de preferencia del operador. Sirve para dos
    cosas: conocer al proveedor cuando aparece en los resultados (el cliente y su clave se
    emparejan por posición) y conservarlo como criterio de desempate.
    """

    def __init__(
        self,
        claves: Sequence[str],
        *,
        umbral_fallos: int = 2,
        cooldown: float = 45.0,
        cooldown_max: float = 300.0,
        alfa: float = 0.3,
        latencia_inicial: Mapping[str, float] | None = None,
        reloj=time.monotonic,
    ) -> None:
        self._lock = threading.Lock()
        self._umbral_fallos = max(1, umbral_fallos)
        self._cooldown = max(0.0, cooldown)
        self._cooldown_max = max(self._cooldown, cooldown_max)
        self._alfa = min(1.0, max(0.01, alfa))
        self._reloj = reloj
        # Priors: lo que se midió a mano en esta máquina. Sirven para que la primera
        # petición no pague un proveedor saturado antes de tener historial propio.
        self._priors = dict(latencia_inicial or {})
        self._salud: dict[str, SaludProveedor] = {
            clave: SaludProveedor(clave=clave, posicion=i) for i, clave in enumerate(claves)
        }

    # --- consulta -----------------------------------------------------------

    @property
    def claves(self) -> list[str]:
        """Los proveedores que este router sigue, en el orden en que se configuraron."""
        with self._lock:
            return [s.clave for s in sorted(self._salud.values(), key=lambda s: s.posicion)]

    def estado_de(self, clave: str) -> SaludProveedor | None:
        with self._lock:
            return self._salud.get(clave)

    def ordenar(self, claves: Sequence[str]) -> list[str]:
        """Devuelve `claves` reordenadas por salud. Nunca elimina ni repite ninguna.

        Los circuitos abiertos cuyo cooldown ya venció pasan a semiabierto aquí mismo, para
        que el próximo request sea el que los vuelva a probar.

        El criterio es la latencia efectiva de cada uno: la medida si la hay, y si no, el
        prior que se configuró a mano. Lo que no tiene ni una cosa ni la otra se va al final,
        porque no hay nada que lo respalde.

        En particular, lo que no se ha probado **no** va primero. Se probó: ponerlo delante
        hace que el proveedor más rápido y de peor calidad (el TemplateLLM local, que responde
        en 1 ms) se quede ganando para siempre, y el sistema nunca mejora. Explorar sin coste
        es trabajo de la carrera (LLM_CARRERA), que pregunta a varios a la vez; en modo
        secuencial, explorar es pagar la latencia del desconocido.
        """
        ahora = self._reloj()
        with self._lock:
            estados = [self._estado_de(c) for c in claves]
            for s in estados:
                if s.circuito == ABIERTO and ahora >= s.abierto_hasta:
                    s.circuito = SEMIABIERTO
            rango = {SEMIABIERTO: 0, CERRADO: 1, ABIERTO: 2}
            return [
                s.clave
                for s in sorted(
                    estados,
                    key=lambda s: (
                        rango[s.circuito],
                        self._latencia_para_ordenar(s),
                        s.posicion,
                    ),
                )
            ]

    def candidatos(self, claves: Sequence[str], cuantos: int) -> list[str]:
        """Los `cuantos` primeros del orden, para la carrera en paralelo."""
        return self.ordenar(claves)[:cuantos]

    def estado(self) -> list[dict]:
        """Fotografía del router, para el endpoint de opciones y los logs."""
        ahora = self._reloj()
        with self._lock:
            filas = []
            for s in sorted(self._salud.values(), key=lambda s: s.posicion):
                if s.circuito == ABIERTO and ahora >= s.abierto_hasta:
                    s.circuito = SEMIABIERTO
                restante = max(0.0, s.abierto_hasta - ahora) if s.circuito == ABIERTO else 0.0
                filas.append(
                    {
                        "proveedor": s.clave,
                        "estado": s.circuito,
                        "latencia_s": round(s.latencia, 2) if s.latencia is not None else None,
                        "ultima_latencia_s": (
                            round(s.ultima_latencia, 2) if s.ultima_latencia is not None else None
                        ),
                        "exitos": s.exitos,
                        "fallos": s.fallos,
                        "reintento_en_s": round(restante, 1) if restante else None,
                        "ultimo_error": s.ultimo_error[:160],
                    }
                )
            return filas

    # --- registro de resultados --------------------------------------------

    def registrar_exito(self, clave: str, segundos: float) -> None:
        """Cierra el circuito (si estaba en recuperación) y actualiza la latencia media.

        La media es exponencial y no acumulada a propósito: una sola llamada lenta de 50 s
        tiene que mover el aguja lo suficiente para que el proveedor pierda el primer puesto,
        pero no tanto como para borrarle el historial de cientos de llamadas buenas.
        """
        with self._lock:
            s = self._estado_de(clave)
            s.exitos += 1
            s.fallos_consecutivos = 0
            s.ultima_latencia = segundos
            s.ultimo_error = ""
            if s.circuito != CERRADO:
                s.circuito = CERRADO
                s.veces_abierto = 0  # se recuperó: el próximo fallo empieza de cero
            s.latencia = segundos if s.latencia is None else (1 - self._alfa) * s.latencia + self._alfa * segundos

    def registrar_fallo(self, clave: str, error: str = "") -> None:
        """Suma un fallo y abre el circuito si se acumularan los suficientes seguidos."""
        with self._lock:
            s = self._estado_de(clave)
            s.fallos += 1
            s.fallos_consecutivos += 1
            s.ultimo_error = error
            # Un éxito desde entonces ya lo había puesto a cero; si no, este es el primero
            # de una racha. Se cuenta la racha, no el total, para que un fallo aislado tras
            # mil llamadas buenas no apague a un proveedor sano.
            if s.circuito == SEMIABIERTO or s.fallos_consecutivos >= self._umbral_fallos:
                self._abrir(s)

    def registrar_latencia(self, clave: str, segundos: float) -> None:
        """Registra el tiempo de una llamada que se perdió en la carrera.

        No cuenta como fallo ni abre circuito: perder una carrera no significa estar caído,
        solo estar lento, y la lentitud ya se refleja en el orden. Actualizar la media aquí sí
        importa, porque es la señal que decide quién va primero en la siguiente petición.
        """
        with self._lock:
            s = self._estado_de(clave)
            s.ultima_latencia = segundos
            if s.circuito == CERRADO:
                s.latencia = (
                    segundos if s.latencia is None else (1 - self._alfa) * s.latencia + self._alfa * segundos
                )

    # --- interno ------------------------------------------------------------

    def _abrir(self, s: SaludProveedor) -> None:
        s.circuito = ABIERTO
        s.veces_abierto += 1
        s.abierto_hasta = self._reloj() + s.cooldown_actual(self._cooldown, self._cooldown_max)

    def _estado_de(self, clave: str) -> SaludProveedor:
        """Cliente del mapa interno, creando la entrada si el proveedor es nuevo.

        La creación no se bloquea porque ya estamos dentro de `self._lock` en todos los
        caminos que la usan.
        """
        estado = self._salud.get(clave)
        if estado is None:
            estado = SaludProveedor(clave=clave, posicion=len(self._salud))
            self._salud[clave] = estado
        return estado

    def _latencia_para_ordenar(self, s: SaludProveedor) -> float:
        if s.latencia is not None:
            return s.latencia
        return self._priors.get(s.clave, SIN_MEDIR)


# --- Registro del proceso ---------------------------------------------------
# La cadena se construye por petición pero `crear_llm` la cachea (llm/factory.py), de modo
# que hay una sola cadena viva y su router acumula el historial entre peticiones. Este
# registro es la puerta de entrada para poder mostrar ese historial desde fuera.

_routers: "dict[tuple[str, ...], RouterSalud]" = {}
_registro_lock = threading.Lock()


def registrar(router: RouterSalud) -> None:
    """Deja el router a mano para poder consultarlo desde la API."""
    with _registro_lock:
        _routers[tuple(sorted(router.claves))] = router


def registrar_y_ver() -> dict:
    """Registra la cadena que se acaba de construir y devuelve el estado de salud.

    Se invoca desde el endpoint: al pasar por `crear_llm`, garantiza que exista una cadena
    (y con ella un router) aunque aún no se haya generado nada, y de paso devuelve lo que se
    sabe hasta ahora de cada proveedor.
    """
    # Import local y no arriba del archivo: factory -> cadena_llm -> salud. Si factory
    # importara a salud al cargarse, sería un ciclo.
    from nuevamente.llm.factory import crear_llm

    cliente = crear_llm()
    router = getattr(cliente, "router", None)
    if router is not None:
        registrar(router)

    return {
        "activo": router is not None,
        "carrera": settings.carrera_activada,
        "proveedores": router.estado() if router is not None else [],
    }


def ver() -> dict:
    """Estado de los proveedores conocidos, sin crear nada nuevo."""
    with _registro_lock:
        filas = [s for r in _routers.values() for s in r.estado()]
    return {
        "activo": bool(filas),
        "carrera": settings.carrera_activada,
        "proveedores": filas,
    }