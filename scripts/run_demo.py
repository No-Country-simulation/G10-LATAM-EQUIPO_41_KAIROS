#!/usr/bin/env python3
"""Ejecuta los 3 escenarios de demo B2B en Salud y guarda evidencia en docs/demo/resultados/.

Responsable: Juan Pablo Calla (PM), con el documento de demo preparado por el equipo.

Uso:
    python scripts/run_demo.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from nuevamente.agents.graph import generar_contenido_educativo  # noqa: E402
from nuevamente.exports import exportar_anki_csv, exportar_markdown  # noqa: E402
from nuevamente.exports.pdf import generar_pdf  # noqa: E402
from nuevamente.storage.oci_client import get_storage_service  # noqa: E402

DOCUMENTO_PATH = RAIZ / "docs" / "demo" / "protocolo_bioseguridad_salud.md"
RESULTADOS_DIR = RAIZ / "docs" / "demo" / "resultados"

ESCENARIOS = [
    {
        "nombre": "1_onboarding_personal_nuevo",
        "caso_de_uso": "Onboarding de personal clínico nuevo",
        "perfil": "Principiante",
        "formato": "Flashcards",
        "nicho": "Salud",
        "nivel_detalle": "Didáctico",
    },
    {
        "nombre": "2_capacitacion_regulatoria",
        "caso_de_uso": "Capacitación regulatoria interna con certificación",
        "perfil": "Desarrollador Junior/Semi Senior",
        "formato": "Quiz",
        "nicho": "Salud",
        "nivel_detalle": "Didáctico",
    },
    {
        "nombre": "3_actualizacion_ante_auditoria",
        "caso_de_uso": "Actualización de protocolos ante una auditoría",
        "perfil": "Gestor/Ejecutivo",
        "formato": "Resumen Ejecutivo",
        "nicho": "Salud",
        "nivel_detalle": "Conciso",
    },
]


def main() -> int:
    if not DOCUMENTO_PATH.exists():
        print(f"No se encontró el documento de demo: {DOCUMENTO_PATH}", file=sys.stderr)
        return 1

    documento_contenido = DOCUMENTO_PATH.read_text(encoding="utf-8")
    RESULTADOS_DIR.mkdir(parents=True, exist_ok=True)

    resumen_general = []
    storage = get_storage_service()
    print(f"OCI Object Storage: {'conectado' if storage.disponible_oci() else 'NO disponible (se usa el respaldo local)'}")

    for escenario in ESCENARIOS:
        print(f"\n=== Escenario: {escenario['caso_de_uso']} ===")
        print(f"Perfil: {escenario['perfil']} | Formato: {escenario['formato']}")

        t0 = time.perf_counter()
        resultado = generar_contenido_educativo(
            documento_titulo="Protocolo General de Bioseguridad para Personal de Salud",
            documento_contenido=documento_contenido,
            perfil=escenario["perfil"],
            formato=escenario["formato"],
            nicho=escenario["nicho"],
            nivel_detalle=escenario["nivel_detalle"],
        )
        duracion = round(time.perf_counter() - t0, 3)

        print(f"Tiempo de generación: {duracion}s")
        print(f"Score de fidelidad: {resultado.evaluacion.anclaje_fuente_score:.2f} "
              f"(umbral aplicado: {resultado.evaluacion.umbral_aplicado})")
        print(f"Aprobado por el Crítico: {resultado.evaluacion.aprobado_por_critico}")
        print(f"Modelo: {resultado.metadatos.modelo_llm} | Embeddings: {resultado.metadatos.modelo_embeddings}")
        if resultado.metadatos.modelo_llm.startswith("template"):
            print("⚠ Se usó el generador local de respaldo, no el LLM configurado.")
        if resultado.evaluacion.afirmaciones_no_sustentadas:
            print(f"⚠ Afirmaciones no sustentadas: {resultado.evaluacion.afirmaciones_no_sustentadas}")

        # mismo destino que usa la API: el original y el paquete educativo, en OCI (o el respaldo)
        doc_id = resultado.coleccion.doc_id
        original = storage.subir_texto(f"originals/{doc_id}.txt", documento_contenido, content_type="text/plain")
        objeto_id = f"contenidos/{doc_id}/demo-{escenario['nombre']}.json"
        salida = {
            "escenario": escenario,
            "tiempo_generacion_segundos": duracion,
            "metadatos": resultado.metadatos.model_dump(),
            "evaluacion_calidad": resultado.evaluacion.model_dump(),
            "contenido_adaptado": resultado.contenido.model_dump(),
        }
        subida = storage.subir_json(objeto_id, salida)
        salida["almacenamiento_oci"] = {
            "bucket": subida.bucket,
            "objeto_id": subida.objeto_id,
            "objeto_documento_original": original.objeto_id,
            "status_upload": subida.status_upload,
        }
        print(f"Almacenamiento: {subida.status_upload} ({subida.bucket}/{subida.objeto_id})")
        json_path = RESULTADOS_DIR / f"{escenario['nombre']}.json"
        json_path.write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")

        md_path = RESULTADOS_DIR / f"{escenario['nombre']}.md"
        md_path.write_text(exportar_markdown(resultado.contenido, "Protocolo de Bioseguridad"), encoding="utf-8")

        (RESULTADOS_DIR / f"{escenario['nombre']}.pdf").write_bytes(generar_pdf(
            resultado.contenido, "Protocolo de Bioseguridad", escenario["perfil"], resultado.evaluacion.anclaje_fuente_score
        ))

        if resultado.contenido.formato in ("Flashcards", "Quiz"):
            csv_path = RESULTADOS_DIR / f"{escenario['nombre']}_anki.csv"
            csv_path.write_text(exportar_anki_csv(resultado.contenido), encoding="utf-8")

        resumen_general.append(
            {
                "caso_de_uso": escenario["caso_de_uso"],
                "perfil": escenario["perfil"],
                "formato": escenario["formato"],
                "tiempo_generacion_segundos": duracion,
                "anclaje_fuente_score": resultado.evaluacion.anclaje_fuente_score,
                "aprobado_por_critico": resultado.evaluacion.aprobado_por_critico,
                "modelo_llm": resultado.metadatos.modelo_llm,
                "modelo_embeddings": resultado.metadatos.modelo_embeddings,
                "status_upload": subida.status_upload,
            }
        )

    resumen_path = RESULTADOS_DIR / "resumen_3_escenarios.json"
    resumen_path.write_text(json.dumps(resumen_general, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== Resumen de los 3 escenarios ===")
    for r in resumen_general:
        print(
            f"- {r['caso_de_uso']}: score={r['anclaje_fuente_score']:.2f}, "
            f"tiempo={r['tiempo_generacion_segundos']}s, aprobado={r['aprobado_por_critico']}"
        )
    print(f"\nResultados guardados en: {RESULTADOS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
