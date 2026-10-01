#!/usr/bin/env python3
"""Benchmark de velocidad y latencia para APIs de LLM en NuevaMente.

Prueba y compara en vivo los tiempos reales de respuesta de cada proveedor y modelo:
- Modo Local (TemplateLLM)
- Modelos de Gemini (Flash-Lite vs Flash vs Latest)
- Groq / Cerebras / OpenRouter (si tienen API key configurada en .env)

Uso:
    python scripts/benchmark_velocidad.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from pydantic import BaseModel, Field

from nuevamente.config import settings
from nuevamente.llm.base import LLMError
from nuevamente.llm.factory import crear_llm
from nuevamente.llm.gemini_llm import GeminiLLM
from nuevamente.llm.template_llm import TemplateLLM
from nuevamente.schemas.formatos import FlashcardsContenido


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


def _medir_generacion(etiqueta: str, cliente) -> dict:
    """Ejecuta una generación real estructurada y mide el tiempo exacto."""
    print(f"  Probando {etiqueta:<35} ... ", end="", flush=True)
    t0 = time.perf_counter()
    try:
        resultado = cliente.generar_estructurado(
            schema=FlashcardsContenido,
            system=SYSTEM_PROMPT,
            user=USER_PAYLOAD,
        )
        tiempo = time.perf_counter() - t0
        items_count = len(getattr(resultado, "items", []))
        print(f"OK ({tiempo:6.2f}s | {items_count} tarjetas)")
        return {
            "nombre": etiqueta,
            "tiempo": tiempo,
            "estado": "OK",
            "detalle": f"{items_count} flashcards",
            "error": None,
        }
    except Exception as exc:
        tiempo = time.perf_counter() - t0
        msg = str(exc).replace("\n", " ")
        if "503" in msg:
            detalle_err = "HTTP 503 (Servidor saturado)"
        elif "429" in msg:
            detalle_err = "HTTP 429 (Cuota agotada)"
        elif "404" in msg:
            detalle_err = "HTTP 404 (Modelo no disponible)"
        else:
            detalle_err = msg[:40] + "..."
        print(f"FALLO ({tiempo:6.2f}s | {detalle_err})")
        return {
            "nombre": etiqueta,
            "tiempo": tiempo,
            "estado": "FALLO",
            "detalle": detalle_err,
            "error": msg,
        }


def main():
    print("=" * 72)
    print("      BENCHMARK DE VELOCIDAD DE MODELOS Y APIS — NUEVAMENTE")
    print("=" * 72)
    print(f"Documento de prueba: {len(DOC_PRUEBA)} caracteres (~45 palabras)")
    print("Tarea evaluada: Generación estructurada de Flashcards (Esquema Pydantic)\n")

    pruebas = []

    # 1. Línea Base Local (TemplateLLM)
    pruebas.append(("Local (TemplateLLM sin red)", TemplateLLM()))

    # 2. Modelos de Google Gemini (si hay API key)
    keys_gemini = list(settings.gemini_api_keys)
    if not keys_gemini and settings.gemini_api_key:
        keys_gemini = [settings.gemini_api_key]

    if keys_gemini:
        modelos_gemini = [
            ("Gemini Flash-Lite (gemini-3.1-flash-lite)", "gemini-3.1-flash-lite"),
            ("Gemini Flash (gemini-3.5-flash)", "gemini-3.5-flash"),
            ("Gemini Flash Latest (gemini-flash-latest)", "gemini-flash-latest"),
            ("Gemini 3.8 Flash (gemini-3.8-flash)", "gemini-3.8-flash"),
        ]
        for etiqueta, mod in modelos_gemini:
            try:
                cl = GeminiLLM(
                    api_keys=keys_gemini,
                    modelo=mod,
                    modelos_respaldo=(),
                    max_intentos=1,
                    reintentos_red=1,
                    retraso_rpm=0.0,
                )
                pruebas.append((etiqueta, cl))
            except Exception as e:
                print(f"  [AVISO] No se pudo inicializar {etiqueta}: {e}")
    else:
        print("  [!] No se detectaron GEMINI_API_KEY o GEMINI_API_KEYS en .env")

    # 3. Groq (si hay key)
    if settings.groq_api_key:
        try:
            cl_groq = crear_llm("groq")
            pruebas.append((f"Groq ({cl_groq.nombre_modelo})", cl_groq))
        except Exception as e:
            print(f"  [AVISO] No se pudo inicializar Groq: {e}")
    else:
        print("  [INFO] GROQ_API_KEY no configurada (Groq ofrece inferencia en <1s).")

    # 4. Cerebras (si hay key)
    if settings.cerebras_api_key:
        try:
            cl_cerebras = crear_llm("cerebras")
            pruebas.append((f"Cerebras ({cl_cerebras.nombre_modelo})", cl_cerebras))
        except Exception as e:
            print(f"  [AVISO] No se pudo inicializar Cerebras: {e}")

    # 5. OpenRouter (si hay key)
    if settings.openrouter_api_key:
        try:
            cl_or = crear_llm("openrouter")
            pruebas.append((f"OpenRouter ({cl_or.nombre_modelo})", cl_or))
        except Exception as e:
            print(f"  [AVISO] No se pudo inicializar OpenRouter: {e}")

    print("\n--- INICIANDO MEDICIÓN EN VIVO ---")
    resultados = []
    for etiqueta, cliente in pruebas:
        res = _medir_generacion(etiqueta, cliente)
        resultados.append(res)

    print("\n" + "=" * 72)
    print("                    TABLA COMPARATIVA DE VELOCIDAD")
    print("=" * 72)
    print(f"{'Proveedor / Modelo':<36} | {'Tiempo':<9} | {'Estado':<7} | {'Velocidad / Nota'}")
    print("-" * 72)

    for r in resultados:
        tiempo_str = f"{r['tiempo']:.2f}s" if r["tiempo"] is not None else "--"
        if r["estado"] == "OK":
            if r["tiempo"] < 0.1:
                veredicto = "[INSTANTANEO - Local]"
            elif r["tiempo"] < 3.5:
                veredicto = "[ULTRA RAPIDO]"
            elif r["tiempo"] < 10.0:
                veredicto = "[ACEPTABLE]"
            else:
                veredicto = "[LENTO]"
            nota = f"{veredicto} ({r['detalle']})"
        else:
            nota = f"[FALLO] {r['detalle']}"

        print(f"{r['nombre']:<36} | {tiempo_str:<9} | {r['estado']:<7} | {nota}")

    print("=" * 72)

    # Conclusión pedagógica
    exitosos = [r for r in resultados if r["estado"] == "OK" and r["tiempo"] > 0.1]
    if exitosos:
        mas_rapido = min(exitosos, key=lambda x: x["tiempo"])
        print(f"\nRECOMENDACION:")
        print(f"   El modelo en la nube mas rapido disponible en tu configuracion es:")
        print(f"   -> {mas_rapido['nombre']} ({mas_rapido['tiempo']:.2f} segundos).")
        print(f"   Configuralo en tu .env como:")
        if "gemini" in mas_rapido["nombre"].lower():
            mod_id = mas_rapido["nombre"].split("(")[-1].rstrip(")")
            print(f"   LLM_PROVIDER=gemini\n   LLM_MODEL={mod_id}")
        elif "groq" in mas_rapido["nombre"].lower():
            print(f"   LLM_PROVIDER=groq")
        elif "openrouter" in mas_rapido["nombre"].lower():
            print(f"   LLM_PROVIDER=openrouter")
    print("\nListo.\n")


if __name__ == "__main__":
    main()
