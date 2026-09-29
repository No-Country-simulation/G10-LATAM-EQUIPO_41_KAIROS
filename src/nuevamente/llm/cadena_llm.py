"""Cadena de proveedores: rota entre APIs distintas cuando una se queda sin cuota.

Responsable en el equipo Kairos G10: Adrian Gil (ML Engineer).

`RotacionModelos` (ver rotacion.py) rota entre modelos de la *misma* API, que comparten
cuota: si Gemini marca la cuota diaria agotada, sus tres modelos de respaldo caen también.
Este módulo añade un nivel por encima: una lista de clientes con cuotas independientes, de
forma que agotar una API no corta la generación.

Se configura con `LLM_CADENA`, una lista de proveedores en orden de preferencia:

    LLM_CADENA=gemini,groq,cerebras,openrouter

El pipeline no cambia: `CadenaLLM` implementa la misma interfaz `LLMClient`, así que
`agentes/graph.py` sigue hablando con un único cliente. `nombre_modelo` refleja el
proveedor:modelo que de verdad generó el contenido, para que los metadatos lo digan.
"""
from __future__ import annotations

from collections.abc import Sequence

from nuevamente.config import settings
from nuevamente.llm.base import LLMClient, LLMError

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
        self._indice = 0
        # `nombre_modelo` se resuelve contra el cliente activo; los metadatos deben decir
        # qué proveedor/modelo generó el contenido, no el primero de la lista.
        self.nombre_modelo = _nombre_de(self._clientes[0])

    @property
    def cliente_activo(self) -> LLMClient:
        return self._clientes[self._indice]

    def generar_estructurado(self, schema: type, system: str, user: str):
        errores: list[str] = []
        for indice, cliente in enumerate(self._clientes):
            nombre = _nombre_de(cliente)
            try:
                resultado = cliente.generar_estructurado(schema, system, user)
            except LLMError as exc:
                # Cuota, red o JSON irreparable en este proveedor: al siguiente.
                errores.append(f"{nombre}: {exc}")
                continue
            self._indice = indice
            self.nombre_modelo = _nombre_de(cliente)
            return resultado

        raise LLMError(
            "Ninguna API de la cadena pudo generar el contenido. "
            f"Proveedores probados: {', '.join(errores)}"
        )


def _nombre_de(cliente: LLMClient) -> str:
    """Identifica al cliente como `proveedor:modelo` para logs y metadatos."""
    etiqueta = getattr(cliente, "etiqueta", None)
    modelo = getattr(cliente, "nombre_modelo", "?")
    return f"{etiqueta}:{modelo}" if etiqueta else str(modelo)


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
