"""Cadena de proveedores: rota entre APIs distintas cuando una se queda sin cuota.

Responsable en el equipo Kairos G10: Adrian Gil (ML Engineer).

`RotacionModelos` (ver rotacion.py) rota entre modelos de la *misma* API, que comparten
cuota: si Gemini marca la cuota diaria agotada, sus tres modelos de respaldo caen también.
Este módulo añade un nivel por encima: una lista de clientes con cuotas independientes, de
forma que agotar una API no corta la generación.

Se configura con `LLM_CADENA`, una lista de proveedores en orden de preferencia:

    LLM_CADENA=gemini,groq,cerebras,openrouter

Ese es el orden *deseado*, no el orden real de uso. Recorrerlo a ciegas hacia muy caro:
cuando Gemini entra en su racha de "503 high demand", cada request se come sus reintentos y
sus timeouts antes de llegar a Groq, y una generación que costaba 1,3 s pasa a 48 s. Como el
proveedor rápido cambia de un momento a otro (hoy Gemini contesta en 2 s y en diez minutos en
50 s), tampoco sirve con reordenar el `.env` a mano.

Por eso la cadena consulta a `RouterSalud` (llm/salud.py) en cada llamada: pasa primero el
que esté sano y más rápido según lo medido, deja atrás al que está caído y, si aun así
todos fallan, los prueba a todos antes que rendirse. Con `LLM_CARRERA=true` además se pide
el prompt a los dos mejores a la vez y se gana el primero que conteste.

El pipeline no cambia: `CadenaLLM` implementa la misma interfaz `LLMClient`, así que
`agentes/graph.py` sigue hablando con un único cliente. `nombre_modelo` refleja el
proveedor:modelo que de verdad generó el contenido, para que los metadatos lo digan.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait

from nuevamente.config import settings
from nuevamente.llm.base import LLMClient, LLMError
from nuevamente.llm.salud import RouterSalud, registrar

logger = logging.getLogger(__name__)

# Proveedores que se pueden encadenar, en el orden de factories de llm/factory.py.
PROVEEDORES_CADENA = ("gemini", "groq", "cerebras", "openrouter", "template")


class CadenaLLM:
    """Intenta cada cliente de la cadena hasta que uno devuelva contenido válido.

    Se salta un cliente cuando este no tiene credenciales configuradas, para que la cadena
    funcione con solo algunas de las claves puestas. Si todos los que tienen clave fallan,
    lanza `LLMError` con el detalle de cada intento.
    """

    def __init__(self, clientes: Sequence[LLMClient]) -> None:
        if not clientes:
            raise LLMError(
                "LLM_CADENA no dejó ningún cliente utilizable. Revisa las API keys en el .env "
                "(ver .env.example) o deja LLM_PROVIDER=template para trabajar sin red."
            )
        self._clientes = list(clientes)
        self._por_clave = {_clave_de(c): c for c in self._clientes}
        self._indice = 0
        # `nombre_modelo` se resuelve contra el cliente activo; los metadatos deben decir
        # qué proveedor/modelo generó el contenido, no el primero de la lista. Se guarda por
        # hilo: con la carrera activada, dos peticiones pueden ganar a la vez y cada una
        # tiene que leer el nombre de *su* ganador, no el del último que escribió.
        self._nombre_inicial = _nombre_de(self._clientes[0])
        self._nombres = threading.local()

        # El router se crea en el cliente, no por proceso: la cadena se construye en cada
        # petición, así que el historial de salud vive aquí y sobrevive entre peticiones.
        # Cadenas distintas (distintos tests, otro consumidor) no se pisan.
        self._router = (
            RouterSalud(
                list(self._por_clave),
                umbral_fallos=settings.salud_umbral_fallos,
                cooldown=settings.salud_cooldown,
                cooldown_max=settings.salud_cooldown_max,
                alfa=settings.salud_alfa,
                latencia_inicial=settings.salud_latencia_inicial,
            )
            if settings.salud_activada
            else None
        )
        if self._router is not None:
            # A mano en cuanto existe, para que /api/v1/salud-llm pueda mostrar el historial
            # aunque aún no se haya generado nada, sin depender de que se pegue a ese endpoint.
            registrar(self._router)

    @property
    def nombre_modelo(self) -> str:
        return getattr(self._nombres, "valor", self._nombre_inicial)

    @nombre_modelo.setter
    def nombre_modelo(self, valor: str) -> None:
        self._nombre_inicial = valor
        self._nombres.valor = valor

    @property
    def cliente_activo(self) -> LLMClient:
        return self._clientes[self._indice]

    @property
    def router(self) -> RouterSalud | None:
        """El router de salud, o None si el enrutado por salud está desactivado."""
        return self._router

    def generar_estructurado(self, schema: type, system: str, user: str):
        orden = self._orden_de_intento()
        if settings.carrera_activada and len(orden) > 1:
            return self._carrera(orden[: max(2, settings.carrera_cuantos)], schema, system, user)
        return self._secuencial(orden, schema, system, user)

    # --- recorrido -----------------------------------------------------------

    def _orden_de_intento(self) -> list[LLMClient]:
        """Clientes en el orden en que conviene probarlos ahora mismo."""
        if self._router is None:
            return list(self._clientes)
        claves = self._router.ordenar(list(self._por_clave))
        return [self._por_clave[c] for c in claves if c in self._por_clave]

    def _secuencial(self, orden: Sequence[LLMClient], schema: type, system: str, user: str):
        errores: list[str] = []
        for cliente in orden:
            nombre = _nombre_de(cliente)
            saltado = self._motivo_de_salto(cliente)
            if saltado:
                # No es un error: es el circuito abierto. Se anota aparte para no ensuciar el
                # mensaje final, pero se avisa, porque explica un salto de latencia de golpe.
                logger.info("Cadena LLM: se salta %s (%s)", nombre, saltado)
                continue
            try:
                resultado = self._intentar(cliente, schema, system, user)
            except LLMError as exc:
                # Cuota, red o JSON irreparable en este proveedor: al siguiente.
                errores.append(f"{nombre}: {exc}")
                continue
            self._activar(cliente)
            self._avisar_si_cayo(errores)
            return resultado

        raise LLMError(
            "Ninguna API de la cadena pudo generar el contenido. "
            f"Proveedores probados: {', '.join(errores)}"
        )

    def _motivo_de_salto(self, cliente: LLMClient) -> str:
        """Por qué no se prueba este proveedor ahora mismo, o "" si sí se puede."""
        if self._router is None:
            return ""
        estado = self._router.estado_de(_clave_de(cliente))
        if estado is None or estado.disponible:
            return ""
        restante = estado.cooldown_actual(settings.salud_cooldown, settings.salud_cooldown_max)
        return f"circuito abierto, ~{restante:.0f}s de espera tras {estado.fallos} fallos"

    def _avisar_si_cayo(self, errores: list[str]) -> None:
        """Avisa cuando el contenido lo generó un proveedor que no era el primero.

        Sin esto la degradación es silenciosa: la cadena cae al respaldo, el material sale
        extractivo y de peor calidad, y no queda rastro de por qué en la respuesta.
        """
        if errores:
            logger.warning(
                "Cadena LLM: se degradó al respaldo tras %d proveedor(es) con error: %s",
                len(errores),
                "; ".join(errores),
            )

    def _carrera(self, candidatos: Sequence[LLMClient], schema: type, system: str, user: str):
        """Pide el mismo prompt a varios proveedores a la vez y gana el primero que conteste.

        Es la respuesta directa a "a veces los de Gemini sí responden rápido": en lugar de
        decidir por cuál empezar, se le pregunta a los dos y se entrega lo primero que llegue.
        Cuando Gemini está sano devuelve su respuesta y Groq se desperdicia; cuando está
        saturado, Groq responde en ~1 s y el usuario no llega a notar la diferencia.

        `LLM_CARRERA_ESPERA_S` escalona la salida: con 0 salen todos juntos (lo más rápido y lo
        que más cuota gasta), con 1.5 el segundo solo se lanza si el primero no contestó a
        tiempo, que es el punto donde el gasto compensa de sobra.

        La llamada perdedora no se cancela (una petición ya lanzada no se detiene), pero su
        hilo termina solo y su desenlace real se registra igual en el router: si el perdedor
        falla de verdad, cuenta como fallo, porque lo fue.
        """
        pool = ThreadPoolExecutor(max_workers=len(candidatos), thread_name_prefix="llm-carrera")
        futuros: dict[Future, LLMClient] = {}
        errores: list[str] = []
        pendientes: set[Future] = set()
        try:
            for i, cliente in enumerate(candidatos):
                if i == 1 and settings.carrera_espera > 0 and pendientes:
                    # Antes de gastar la llamada del segundo, se mira si el primero ya
                    # contestó dentro de la espera configurada.
                    hechos, pendientes = wait(
                        pendientes, timeout=settings.carrera_espera, return_when=FIRST_COMPLETED
                    )
                    ganador = self._ganador(hechos, futuros, errores)
                    if ganador is not None:
                        self._avisar_si_cayo(errores)
                        return ganador
                futuro = pool.submit(self._intentar, cliente, schema, system, user)
                futuros[futuro] = cliente
                pendientes.add(futuro)

            while pendientes:
                hechos, pendientes = wait(pendientes, return_when=FIRST_COMPLETED)
                ganador = self._ganador(hechos, futuros, errores)
                if ganador is not None:
                    self._avisar_si_cayo(errores)
                    return ganador
        finally:
            # wait=False: si ya hay ganador, el perdedor sigue su curso en segundo plano y no
            # debe retrasar la respuesta. El pool se cierra solo cuando todos sus hilos acaban.
            pool.shutdown(wait=False)

        raise LLMError(
            "Ninguna API de la cadena pudo generar el contenido. "
            f"Proveedores probados: {', '.join(errores)}"
        )

    def _ganador(self, hechos, futuros: dict, errores: list[str]):
        """Primer resultado válido de un lote de futuros terminados; None si todos fallaron."""
        for futuro in hechos:
            cliente = futuros[futuro]
            try:
                resultado = futuro.result()
            except LLMError as exc:
                errores.append(f"{_nombre_de(cliente)}: {exc}")
                continue
            self._activar(cliente)
            return resultado
        return None

    def _intentar(self, cliente: LLMClient, schema: type, system: str, user: str):
        """Una llamada a un proveedor, midiendo lo que tarda y anotándolo en el router."""
        clave = _clave_de(cliente)
        t0 = time.perf_counter()
        try:
            resultado = cliente.generar_estructurado(schema, system, user)
        except LLMError as exc:
            if self._router is not None:
                self._router.registrar_fallo(clave, str(exc))
            raise
        segundos = time.perf_counter() - t0
        if self._router is not None:
            self._router.registrar_exito(clave, segundos)
        return resultado

    def _activar(self, cliente: LLMClient) -> None:
        """Deja constancia de qué proveedor ganó, para los metadatos y `cliente_activo`."""
        self._indice = self._clientes.index(cliente)
        self.nombre_modelo = _nombre_de(cliente)


def _clave_de(cliente: LLMClient) -> str:
    """Identificador estable del proveedor, para agrupar su historial de salud.

    No se puede usar `nombre_modelo`: cambia en cuanto el proveedor rota a su modelo de
    respaldo, y el historial quedaría partido en dos sin que nada lo explique.
    """
    clave = getattr(cliente, "clave_proveedor", None)
    if clave:
        return str(clave).lower()
    etiqueta = getattr(cliente, "etiqueta", None)
    return str(etiqueta or type(cliente).__name__).lower()


def _nombre_de(cliente: LLMClient) -> str:
    """Identifica al cliente como `proveedor:modelo` para logs y metadatos."""
    return f"{_clave_de(cliente)}:{getattr(cliente, 'nombre_modelo', '?')}"


def crear_cadena(
    proveedores: Sequence[str] | None = None,
    factories: dict | None = None,
) -> CadenaLLM:
    """Construye la cadena desde `LLM_CADENA` (o la lista indicada).

    `factories` permite inyectar las fábricas de llm/factory.py sin importarlas aquí, lo
    que mantiene esta función testeable sin tocar la red ni el SDK de cada proveedor.
    """
    from nuevamente.llm.factory import _FACTORIES

    factories = factories or _FACTORIES
    if proveedores is None:
        proveedores = settings.llm_cadena
    proveedores = [p.strip().lower() for p in proveedores if p.strip()]

    clientes: list[LLMClient] = []
    sin_credenciales: list[str] = []
    for nombre in proveedores:
        if nombre not in factories:
            raise LLMError(
                f"Proveedor '{nombre}' no está en la cadena. Disponibles: "
                f"{', '.join(PROVEEDORES_CADENA)}"
            )
        try:
            clientes.append(factories[nombre]())
        except LLMError as exc:
            # Sin API key: se omite en lugar de romper la generación entera. Si al final
            # no queda ningún cliente, el error de arriba ya explica qué revisar.
            sin_credenciales.append(f"{nombre} ({exc})")

    if not clientes and sin_credenciales:
        raise LLMError(
            "Ninguna API de LLM_CADENA tiene credenciales configuradas. Revisa: "
            + "; ".join(sin_credenciales)
        )
    return CadenaLLM(clientes)
