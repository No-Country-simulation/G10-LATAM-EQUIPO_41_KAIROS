#!/usr/bin/env python3
"""Benchmark de velocidad y latencia para APIs de LLM en NuevaMente.

Mide EN VIVO el tiempo real de respuesta de cada modelo, uno por uno, con el esquema
Pydantic real del pipeline (FlashcardsContenido) y un documento de prueba corto.

Qué mide y por qué así:
  * Lee los modelos del .env (LLM_MODEL, LLM_MODELOS_RESPALDO, LLM_MODELOS_GROQ, ...),
    no una lista fija escrita a mano: si mañana cambias un modelo en el .env, este
    script mide lo que de verdad se va a usar en producción. Una lista hardcodeada
    envejece y termina midiendo modelos que ya no interesan.
  * Cada modelo se prueba SOLO (sin modelos de respaldo y con max_intentos=1). Si no,
    una medición de "gemini-3.5-flash" se convierte en una medición de la rotación
    entera y no sabes cuál falló.
  * Tope de tiempo por llamada: con la cuota agotada Gemini puede reintentar 45+ s
    por modelo; para un benchmark eso es demora inútil, no información.
  * Guarda el resultado en docs/benchmark_api_ultima.json y lo compara con la corrida
    anterior, para ver en segundos si algo se degradó desde la última vez.

Uso:
    .venv\\Scripts\\python scripts/benchmark_velocidad.py
    .venv\\Scripts\\python scripts/benchmark_velocidad.py --solo gemini,groq -n 3
    .venv\\Scripts\\python scripts/benchmark_velocidad.py --timeout 45
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as TimeoutExpirado
from datetime import datetime
from pathlib import Path

# Los scripts de este proyecto se corren en la consola de Windows: sin este envoltorio,
# los acentos rompen el stream con charmap y el script muere a mitad de corrida
# (CONTEXTO_PROYECTO.txt sección 4.3).
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from pydantic import BaseModel  # noqa: E402

from nuevamente.config import settings  # noqa: E402
from nuevamente.llm.gemini_llm import GeminiLLM  # noqa: E402
from nuevamente.llm.openai_compat_llm import OpenAICompatLLM  # noqa: E402
from nuevamente.llm.template_llm import TemplateLLM  # noqa: E402
from nuevamente.schemas.formatos import FlashcardsContenido  # noqa: E402

RUTA_HISTORIAL = RAIZ / "docs" / "benchmark_api_ultima.json"

DOC_PRUEBA = (
    "El protocolo hospitalario de bioseguridad exige el lavado clínico de manos "
    "durante al menos 20 segundos con agua y jabón antiséptico antes y después del contacto "
    "con cada paciente. El uso de guantes estériles y mascarilla quirúrgica N95 es de carácter "
    "estricto y obligatorio en el área de cuidados intensivos para prevenir infecciones intrahospitalarias."
)

USER_PAYLOAD = json.dumps(
    {
        "documento_titulo": "Protocolo de Bioseguridad Hospitalaria",
        "perfil": "Principiante",
        "nicho": "Salud",
        "nivel_detalle": "Conciso",
        "chunks": [
            {
                "chunk_id": "chunk_001",
                "texto": DOC_PRUEBA,
                "seccion": "Normas de Bioseguridad",
            }
        ],
        "retroalimentacion_critico": "",
    },
    ensure_ascii=False,
)

SYSTEM_PROMPT = (
    "Eres el agente Redactor de NuevaMente. Genera entre 3 y 5 flashcards concisas "
    "usando EXCLUSIVAMENTE la evidencia proporcionada. Cita 'chunk_001' en cada fuente. Escribe en español."
)

# Proveedores compatibles con la API de OpenRouter/Groq: base_url + variable de modelos.
PROVEEDORES_OPENAI = {
    "groq": (
        "https://api.groq.com/openai/v1",
        settings.groq_api_key,
        "LLM_MODELOS_GROQ",
        ("openai/gpt-oss-120b", "openai/gpt-oss-20b"),
        "Groq",
    ),
    "cerebras": (
        "https://api.cerebras.ai/v1",
        settings.cerebras_api_key,
        "LLM_MODELOS_CEREBRAS",
        ("gpt-oss-120b", "qwen-3.8-27b"),
        "Cerebras",
    ),
    "openrouter": (
        "https://openrouter.ai/api/v1",
        settings.openrouter_api_key,
        "LLM_MODELOS_OPENROUTER",
        ("openrouter/free", "google/gemma-4-31b-it:free"),
        "OpenRouter",
    ),
}


def _modelos_de(nombre_var: str, por_defecto: tuple[str, ...]) -> tuple[str, ...]:
    crudo = os.getenv(nombre_var, "")
    return tuple(m.strip() for m in crudo.split(",") if m.strip()) or por_defecto


def _clasificar(tiempo: float) -> str:
    if tiempo < 0.1:
        return "[INSTANTANEO - Local]"
    if tiempo < 3.5:
        return "[ULTRA RAPIDO]"
    if tiempo < 10.0:
        return "[ACEPTABLE]"
    return "[LENTO]"


def _traducir_error(msg: str) -> str:
    if "503" in msg:
        return "HTTP 503 (servicio con alta demanda)"
    if "429" in msg:
        return "HTTP 429 (cuota agotada)"
    if "404" in msg:
        return "HTTP 404 (modelo inexistente / nombre inventado)"
    if "401" in msg or "403" in msg:
        return "HTTP 401/403 (API key invalida)"
    return msg.replace("\n", " ")[:90]


def _medir(cliente, timeout: float) -> tuple[float | None, str, str]:
    """Una generación real con tope de tiempo. Devuelve (segundos|None, estado, detalle)."""
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=1) as pool:
        tarea = pool.submit(
            cliente.generar_estructurado,
            schema=FlashcardsContenido,
            system=SYSTEM_PROMPT,
            user=USER_PAYLOAD,
        )
        try:
            resultado = tarea.result(timeout=timeout)
        except TimeoutExpirado:
            pool.shutdown(wait=False)
            return None, "FALLO", f"sin respuesta en {timeout:.0f}s (tope del benchmark)"
        except Exception as exc:  # LLMError y errores del SDK
            return time.perf_counter() - t0, "FALLO", _traducir_error(str(exc))
    tiempo = time.perf_counter() - t0
    return tiempo, "OK", f"{len(getattr(resultado, 'items', []))} flashcards"


def _medir_repetido(cliente, timeout: float, repeticiones: int) -> dict:
    """Repite la medición y devuelve el mejor tiempo (lo que el usuario percibe)."""
    tiempos: list[float] = []
    errores: list[str] = []
    ultimo_estado = "FALLO"
    ultimo_detalle = ""

    for _ in range(repeticiones):
        tiempo, estado, detalle = _medir(cliente, timeout)
        ultimo_estado, ultimo_detalle = estado, detalle
        if estado == "OK" and tiempo is not None:
            tiempos.append(tiempo)
        else:
            errores.append(detalle)

    if tiempos:
        mejor = min(tiempos)
        promedio = sum(tiempos) / len(tiempos)
        return {
            "tiempo": round(mejor, 3),
            "promedio": round(promedio, 3),
            "estado": "OK",
            "detalle": ultimo_detalle,
            "corridas_ok": len(tiempos),
            "corridas": len(tiempos) + len(errores),
            "error": None,
        }
    return {
        "tiempo": None,
        "promedio": None,
        "estado": "FALLO",
        "detalle": ultimo_detalle,
        "corridas_ok": 0,
        "corridas": len(errores),
        "error": "; ".join(dict.fromkeys(errores))[:300],
    }


def _recolectar_pruebas(solo: set[str]) -> list[tuple[str, str, object]]:
    """Lista de (etiqueta, proveedor, cliente) a medir, leída de la configuración real."""
    pruebas: list[tuple[str, str, object]] = []

    if not solo or "template" in solo:
        pruebas.append(("Local (TemplateLLM sin red)", "template", TemplateLLM()))

    if not solo or "gemini" in solo:
        claves = list(settings.gemini_api_keys) or (
            [settings.gemini_api_key] if settings.gemini_api_key else []
        )
        if claves:
            modelos = list(
                dict.fromkeys([settings.llm_model, *settings.llm_modelos_respaldo])
            )
            for mod in modelos:
                try:
                    cliente = GeminiLLM(
                        api_keys=claves,
                        modelo=mod,
                        modelos_respaldo=(),
                        max_intentos=1,
                        reintentos_red=1,
                        retraso_rpm=0.0,
                    )
                    pruebas.append((f"Gemini ({mod})", "gemini", cliente))
                except Exception as exc:
                    print(f"  [AVISO] No se pudo inicializar Gemini {mod}: {exc}")
        else:
            print("  [!] Sin GEMINI_API_KEY ni GEMINI_API_KEYS en el .env")

    for proveedor, (base_url, api_key, var_modelos, por_defecto, etiqueta) in PROVEEDORES_OPENAI.items():
        if solo and proveedor not in solo:
            continue
        if not api_key:
            print(f"  [INFO] Sin {proveedor.upper()}_API_KEY en el .env (se omite).")
            continue
        for mod in _modelos_de(var_modelos, por_defecto):
            pruebas.append(
                (
                    f"{etiqueta} ({mod})",
                    proveedor,
                    OpenAICompatLLM(
                        base_url=base_url,
                        api_key=api_key,
                        modelo=mod,
                        modelos_respaldo=(),
                        etiqueta=etiqueta,
                    ),
                )
            )

    return pruebas


def _cargar_historial() -> dict:
    if not RUTA_HISTORIAL.exists():
        return {}
    try:
        return json.loads(RUTA_HISTORIAL.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Mide la latencia real de cada API/LLM del .env")
    parser.add_argument(
        "--solo",
        default="",
        help="proveedores a medir, separados por coma (template,gemini,groq,cerebras,openrouter)",
    )
    parser.add_argument(
        "-n", "--repetir", type=int, default=1, help="mediciones por modelo (default 1)"
    )
    parser.add_argument(
        "--timeout", type=float, default=30.0, help="tope de segundos por llamada (default 30)"
    )
    args = parser.parse_args()

    solo = {p.strip().lower() for p in args.solo.split(",") if p.strip()}
    historial = _cargar_historial()
    anteriores: dict[str, float] = historial.get("mejores_tiempos", {})

    print("=" * 78)
    print("   BENCHMARK DE VELOCIDAD DE MODELOS Y APIS — NUEVAMENTE (lee el .env)")
    print("=" * 78)
    print(f"Documento de prueba: {len(DOC_PRUEBA)} caracteres (~45 palabras)")
    print("Tarea: generación estructurada de Flashcards (esquema Pydantic real del pipeline)")
    print(f"Tope por llamada: {args.timeout:.0f}s | Mediciones por modelo: {args.repetir}\n")

    pruebas = _recolectar_pruebas(solo)
    if not pruebas:
        print("No hay ningún proveedor configurado en el .env para medir.")
        return 1

    print("--- MEDICIÓN EN VIVO ---")
    resultados = []
    for etiqueta, proveedor, cliente in pruebas:
        print(f"  {etiqueta:<45} ... ", end="", flush=True)
        med = _medir_repetido(cliente, args.timeout, args.repetir)
        if med["estado"] == "OK":
            extra = ""
            if med["corridas"] > 1:
                extra = f" | mejor de {med['corridas_ok']}/{med['corridas']} ({med['promedio']:.2f}s prom)"
            print(f"OK ({med['tiempo']:6.2f}s{extra} | {med['detalle']})")
        else:
            print(f"FALLO ({med['detalle']})")
        resultados.append(
            {"nombre": etiqueta, "proveedor": proveedor, **med}
        )

    print("\n" + "=" * 78)
    print("                       TABLA COMPARATIVA DE VELOCIDAD")
    print("=" * 78)
    cabecera = f"{'Proveedor / Modelo':<46} | {'Tiempo':<8} | {'Vs. ultima':<11} | Nota"
    print(cabecera)
    print("-" * 78)

    for r in resultados:
        if r["estado"] == "OK":
            tiempo_str = f"{r['tiempo']:.2f}s"
            nota = f"{_clasificar(r['tiempo'])} ({r['detalle']})"
        else:
            tiempo_str = "--"
            nota = f"[FALLO] {r['detalle']}"

        previo = anteriores.get(r["nombre"])
        if previo is None or r["tiempo"] is None:
            delta = "nuevo"
        else:
            dif = r["tiempo"] - previo
            delta = f"{dif:+.2f}s"
            if abs(dif) >= 2.0:
                delta += " !!"
        print(f"{r['nombre']:<46} | {tiempo_str:<8} | {delta:<11} | {nota}")

    print("=" * 78)

    # Guardar para comparar en la próxima corrida.
    mejores = {r["nombre"]: r["tiempo"] for r in resultados if r["estado"] == "OK"}
    RUTA_HISTORIAL.parent.mkdir(parents=True, exist_ok=True)
    RUTA_HISTORIAL.write_text(
        json.dumps(
            {
                "fecha": datetime.now().isoformat(timespec="seconds"),
                "mejores_tiempos": mejores,
                "resultados": resultados,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nHistorial guardado en {RUTA_HISTORIAL.relative_to(RAIZ)}")

    exitosos = [r for r in resultados if r["estado"] == "OK" and r["proveedor"] != "template"]
    if exitosos:
        rapido = min(exitosos, key=lambda x: x["tiempo"])
        lentos = [r for r in exitosos if r["tiempo"] and r["tiempo"] >= 10.0]
        print("\nRECOMENDACIÓN:")
        print(f"   El más rápido ahora: {rapido['nombre']} ({rapido['tiempo']:.2f}s).")
        if "gemini" in rapido["proveedor"]:
            print(f"   LLM_PROVIDER=gemini\n   LLM_MODEL={rapido['nombre'].split('(')[-1].rstrip(')')}")
        else:
            print(f"   LLM_PROVIDER={rapido['proveedor']}")
        if lentos:
            print(
                "   Lentos (>10s): "
                + ", ".join(f"{r['nombre']} ({r['tiempo']:.1f}s)" for r in lentos)
                + " — no los pongas como LLM_MODEL."
            )
        print(
            "\n   Ojo: esto mide SOLO el Redactor. El orden final lo decide el router de"
            "\n   salud (/api/v1/salud-llm), no el .env: este script solo te dice quién está"
            "\n   rápido y quién saturado en este momento."
        )
    else:
        print("\nNingún proveedor en la nube respondió. Revisa claves/cuota o usa LLM_PROVIDER=template.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
