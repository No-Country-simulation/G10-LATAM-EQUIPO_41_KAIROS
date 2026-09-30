#!/usr/bin/env python3
"""Diagnóstico rápido: comprueba si la lentitud/bloqueo se debe a las API keys o al programa.

Uso:
    python scripts/diagnostico_gemini.py
"""
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from nuevamente.config import settings
from nuevamente.agents.graph import generar_contenido_educativo
from nuevamente.llm.template_llm import TemplateLLM


def test_programa():
    print("=" * 60)
    print("1. PROBANDO EL PROGRAMA LOCALMENTE (Pipeline completo sin red)")
    print("=" * 60)
    doc_prueba = (
        "El protocolo de bioseguridad exige lavado de manos frecuente durante al menos "
        "20 segundos con agua y jabón, y uso obligatorio de guantes y mascarilla en cada atención."
    )
    t0 = time.perf_counter()
    try:
        resultado = generar_contenido_educativo(
            documento_titulo="Protocolo Bioseguridad",
            documento_contenido=doc_prueba,
            perfil="Principiante",
            formato="Flashcards",
            nicho="Salud",
            nivel_detalle="Resumen conciso",
            llm=TemplateLLM(),
        )
        tiempo = time.perf_counter() - t0
        print(f"  [OK] El programa funciona perfectamente.")
        print(f"       Tiempo de ejecución total: {tiempo:.2f} segundos.")
        print(f"       Formato generado: {resultado.contenido.formato}")
        print(f"       Fidelidad calculada: {resultado.evaluacion.anclaje_fuente_score}")
    except Exception as exc:
        print(f"  [FALLO EN PROGRAMA] {type(exc).__name__}: {exc}")
        return False
    return True


def test_claves_gemini():
    print("\n" + "=" * 60)
    print("2. PROBANDO LAS API KEYS DE GEMINI CONTRA GOOGLE")
    print("=" * 60)
    keys = list(settings.gemini_api_keys)
    if not keys and settings.gemini_api_key:
        keys = [settings.gemini_api_key]

    if not keys:
        print("  [AVISO] No hay ninguna GEMINI_API_KEY en tu .env")
        return

    print(f"  Detectadas {len(keys)} clave(s) de Gemini en .env.\n")

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("  [ERROR] google-genai no está instalado en este entorno.")
        return

    modelos_a_probar = [
        settings.llm_model,
        "gemini-1.5-flash",
        "gemini-2.5-flash",
        "gemini-flash-latest",
    ]
    modelos_a_probar = list(dict.fromkeys(modelos_a_probar))

    for idx, key in enumerate(keys, 1):
        ofuscada = key[:6] + "..." + key[-4:] if len(key) > 10 else key
        print(f"  Clave #{idx} ({ofuscada}):")

        # Probar cliente con timeout de 8 segundos
        http_opts = types.HttpOptions(timeout=8.0)
        try:
            client = genai.Client(api_key=key, http_options=http_opts)
        except Exception as exc:
            print(f"    -> Error al inicializar cliente: {exc}")
            continue

        clave_funciona = False
        for mod in modelos_a_probar:
            t0 = time.perf_counter()
            try:
                resp = client.models.generate_content(
                    model=mod,
                    contents="Responde solo la palabra 'OK'",
                )
                duracion = time.perf_counter() - t0
                texto = (resp.text or "").strip()[:20]
                print(f"    [OK] Modelo '{mod}' respondió en {duracion:.2f}s: \"{texto}\"")
                clave_funciona = True
                break  # Si ya respondió con un modelo, la clave es válida y funcional
            except Exception as exc:
                duracion = time.perf_counter() - t0
                codigo = getattr(exc, "code", None) or getattr(exc, "status_code", None)
                msg = getattr(exc, "message", str(exc))
                if "503" in str(codigo) or "503" in str(msg) or "high demand" in str(msg).lower():
                    print(f"    [503 SATURADO] Modelo '{mod}' ({duracion:.2f}s): Servidor de Google saturado por alta demanda.")
                elif "401" in str(codigo) or "403" in str(codigo) or "not valid" in str(msg).lower():
                    print(f"    [CLAVE INVÁLIDA] HTTP {codigo}: La clave no es válida o fue revocada en Google AI Studio.")
                    break
                elif "429" in str(codigo) or "quota" in str(msg).lower() or "exhausted" in str(msg).lower():
                    print(f"    [CUOTA AGOTADA] HTTP 429 ({duracion:.2f}s): Cuota diaria agotada para esta clave.")
                    break
                elif "404" in str(codigo) or "not found" in str(msg).lower():
                    print(f"    [NO DISPONIBLE] Modelo '{mod}' no existe o fue retirado por Google.")
                else:
                    print(f"    [ERROR {codigo}] ({duracion:.2f}s): {msg[:100]}")

        if not clave_funciona:
            print(f"    => Conclusión: La clave #{idx} NO pudo completar una respuesta exitosa.\n")
        else:
            print(f"    => Conclusión: La clave #{idx} está FUNCIONANDO correctamente.\n")


def main():
    test_programa()
    test_claves_gemini()
    print("=" * 60)
    print("DIAGNÓSTICO FINALIZADO")
    print("=" * 60)


if __name__ == "__main__":
    main()
