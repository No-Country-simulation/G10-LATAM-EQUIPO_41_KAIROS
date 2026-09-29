#!/usr/bin/env python3
"""Comprueba qué APIs de LLM responden de verdad, gastando UNA llamada mínima cada una.

Los tests de pytest NO sirven para esto: corren contra dobles en memoria y pasan
incluso con la red desconectada, para que la suite sea rápida y no consuma cuota. Este
script es el complemento: hace una petición real y muy corta a cada proveedor con clave
en el .env, y dice qué modelos funcionan.

Uso:
    python scripts/check_apis.py
    python scripts/check_apis.py --groq --openrouter     # solo esos

Cada línea cuesta una fracción de la cuota diaria. La rotación de modelos de respaldo
NO se prueba aquí a propósito: si el modelo principal responde, el script para ahí, y no
gastamos cuota de los 3 modelos para demostrar que rotan (eso lo cubren los tests).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from pydantic import BaseModel  # noqa: E402

from nuevamente.config import settings  # noqa: E402
from nuevamente.llm.base import LLMError  # noqa: E402

# Esquema mínimo: obliga a la API a devolver JSON estructurado, que es lo que el pipeline
# necesita de verdad. Si un proveedor no puede con esto, no sirve para este proyecto.
class _Sonda(BaseModel):
    ok: bool
    mensaje: str


# Un prompt corto y genérico: no se envía documento del cliente ni nada sensible.
PREGUNTA = '{"responde": {"ok": true, "mensaje": "conexion verificada"}}'
SISTEMA = "Responde solo con el JSON pedido."


def _probar(nombre: str, cliente, segundos: int) -> tuple[bool, str]:
    """Una llamada mínima, con tope de tiempo. Devuelve (si funciona, detalle legible).

    El tope importa: con la cuota agotada, el cliente de Gemini puede quedarse esperando
    varios minutos reintentando, y para un chequeo de humo eso es una demora inútil.
    """
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as TimeoutExpirado

    with ThreadPoolExecutor(max_workers=1) as pool:
        tarea = pool.submit(cliente.generar_estructurado, _Sonda, SISTEMA, PREGUNTA)
        try:
            respuesta = tarea.result(timeout=segundos)
        except TimeoutExpirado:
            pool.shutdown(wait=False)
            return False, f"sin respuesta en {segundos}s (cuota agotada o API lenta)"
        except LLMError as exc:
            return False, str(exc).replace("\n", " ")[:220]
        except Exception as exc:  # SDK que lanza algo distinto a LLMError
            return False, f"{type(exc).__name__}: {exc}".replace("\n", " ")[:220]

    modelo = getattr(cliente, "nombre_modelo", "?")
    if respuesta.ok and respuesta.mensaje:
        return True, f"respondio {modelo}"
    return True, f"respondio {modelo} pero con contenido inesperado: {respuesta}"


def _construir(nombre: str):
    """Devuelve el cliente del proveedor, o None si no hay clave configurada."""
    if nombre == "gemini":
        if not settings.gemini_api_keys:
            return None, "sin GEMINI_API_KEY en el .env"
        from nuevamente.llm.gemini_llm import GeminiLLM

        return GeminiLLM(), f"{len(settings.gemini_api_keys)} key(s) detectada(s)"

    claves = {
        "groq": settings.groq_api_key,
        "cerebras": settings.cerebras_api_key,
        "openrouter": settings.openrouter_api_key,
    }
    if not claves[nombre]:
        return None, f"sin {nombre.upper()}_API_KEY en el .env"

    import importlib

    modulo = importlib.import_module("nuevamente.llm.openai_compat_llm")
    return getattr(modulo, f"crear_{nombre}")(), "clave detectada"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--todos", action="store_true", help="probar todos los proveedores de LLM_CADENA"
    )
    parser.add_argument(
        "--timeout", type=int, default=45, help="segundos maximos por API (default 45)"
    )
    for nombre in ("gemini", "groq", "cerebras", "openrouter"):
        parser.add_argument(f"--{nombre}", action="store_true", help=f"probar solo {nombre}")
    args = parser.parse_args()

    pedidos = [n for n in ("gemini", "groq", "cerebras", "openrouter") if getattr(args, n)]
    if args.todos or not pedidos:
        pedidos = list(settings.llm_cadena) or ["gemini"]
    pedidos = [p for p in dict.fromkeys(pedidos) if p != "template"]

    print(f"Probando {len(pedidos)} API(s). Cada una gasta una llamada mínima.\n")
    resultados: list[tuple[str, bool, str]] = []

    for nombre in pedidos:
        try:
            cliente, aviso = _construir(nombre)
        except Exception as exc:
            resultados.append((nombre, False, f"no se pudo construir: {exc}"[:220]))
            continue
        if cliente is None:
            resultados.append((nombre, False, aviso))
            continue
        resultados.append((nombre, *_probar(nombre, cliente, args.timeout)))

    for nombre, ok, detalle in resultados:
        print(f"  {'OK  ' if ok else 'FALLA'}  {nombre:<11} {detalle}")

    funcionales = [n for n, ok, _ in resultados if ok]
    print()
    if not funcionales:
        print("Ninguna API responde. Revisa las claves en el .env o usa LLM_PROVIDER=template.")
        return 1
    print(f"Listas para generar: {', '.join(funcionales)}")
    if len(funcionales) == 1:
        print("Solo hay una API con clave: si su cuota se agota, la generacion se corta.")
        print("Agrega GROQ_API_KEY, CEREBRAS_API_KEY o OPENROUTER_API_KEY al .env para rotar.")
    else:
        print(f"Hay {len(funcionales)} APIs con cuota propia: la rotacion esta activa.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
