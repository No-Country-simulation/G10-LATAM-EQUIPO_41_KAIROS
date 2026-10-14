"""Estadísticas de uso y experiencia de usuario.

Cada acción del usuario final se guarda como un evento en una línea de
`<ESTADISTICAS_DIR>/eventos.jsonl`:

- "generacion": material creado (formato, perfil, sector, nivel, origen, fidelidad, tiempos).
- "descarga": exportación a Word, PowerPoint, Markdown o Anki, video o audio del podcast.
- "calificacion": estrellas (1 a 5) y comentario opcional sobre un material.

Los materiales creados antes de que existieran las estadísticas (el historial guardado en
OCI o en el respaldo local) se suman con `importar_historial()`, marcados "historico".
De ellos no se sabe el nivel de detalle ni el origen, ni si se descargaron o calificaron.

Nunca se guarda el texto del documento: solo las elecciones y los resultados. Registrar
un evento jamás debe tumbar la petición del usuario, así que los errores de escritura se
ignoran (la estadística se pierde, el material no).
"""
from __future__ import annotations

import json
import threading
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from nuevamente.config import settings

_candado = threading.Lock()
DIAS_DE_ACTIVIDAD = 14
COMENTARIOS_RECIENTES = 10


def _archivo() -> Path:
    return Path(settings.estadisticas_dir) / "eventos.jsonl"


def registrar(tipo: str, **datos) -> None:
    # hora local del servidor con su desfase: el día de un evento es el día en que lo vivió el usuario
    _escribir({"tipo": tipo, "fecha": datetime.now().astimezone().isoformat(timespec="seconds"), **datos})


def _escribir(evento: dict) -> None:
    try:
        with _candado:
            archivo = _archivo()
            archivo.parent.mkdir(parents=True, exist_ok=True)
            with archivo.open("a", encoding="utf-8") as f:
                f.write(json.dumps(evento, ensure_ascii=False) + "\n")
    except OSError:
        pass


def leer_eventos() -> list[dict]:
    archivo = _archivo()
    if not archivo.is_file():
        return []
    eventos = []
    with _candado, archivo.open(encoding="utf-8") as f:
        for linea in f:
            try:
                eventos.append(json.loads(linea))
            except json.JSONDecodeError:
                continue  # una línea cortada por un corte de luz no invalida el resto
    return eventos


def importar_historial() -> int:
    """Agrega un evento "generacion" por cada material guardado que aún no esté contado.
    Se puede llamar las veces que sea: lo ya contado no se repite. Devuelve cuántos sumó."""
    from nuevamente.schemas.response import RegistroAdaptacion
    from nuevamente.storage.oci_client import get_storage_service

    contados = {e.get("objeto_id") for e in leer_eventos() if e["tipo"] in ("generacion", "historial_ilegible")}
    storage = get_storage_service()
    nuevos = 0
    for objeto_id, fecha in storage.listar("contenidos/"):
        if objeto_id in contados or not objeto_id.endswith(".json"):
            continue
        crudo = storage.descargar_texto(objeto_id)
        try:
            registro = RegistroAdaptacion.model_validate_json(crudo or "")
        except ValueError:
            # se anota para no volver a descargarlo cada vez que se abran las estadísticas
            registrar("historial_ilegible", objeto_id=objeto_id)
            continue
        ev, meta = registro.evaluacion_calidad, registro.metadatos
        # el sector no se guardaba; solo Salud se distingue, por su umbral más estricto
        es_salud = settings.fidelity_min_salud != settings.fidelity_min_general and (
            abs(ev.umbral_aplicado - settings.fidelity_min_salud) < 1e-9
        )
        _escribir({
            "tipo": "generacion",
            "fecha": fecha.isoformat(timespec="seconds"),
            "objeto_id": objeto_id,
            "formato": registro.contenido_adaptado.formato,
            "perfil": meta.perfil_aplicado,
            "nicho": "Salud" if es_salud else None,
            "fidelidad": ev.anclaje_fuente_score,
            "aprobado": ev.aprobado_por_critico,
            "tiempo_generacion_s": round(meta.tiempo_generacion_segundos, 2),
            "tiempo_estudio_min": meta.tiempo_estimado_estudio_minutos,
            "modo_local": "respaldo" in meta.modelo_llm,
            "historico": True,
        })
        nuevos += 1
    return nuevos


def _promedio(valores: list[float], decimales: int = 2) -> float | None:
    return round(sum(valores) / len(valores), decimales) if valores else None


def _conteo(eventos: list[dict], campo: str) -> list[dict]:
    """[{"nombre": ..., "total": ...}] de mayor a menor."""
    return [{"nombre": k, "total": n} for k, n in Counter(e.get(campo) or "Sin registrar" for e in eventos).most_common()]


def resumen(hoy: datetime | None = None) -> dict:
    eventos = leer_eventos()
    generaciones = [e for e in eventos if e["tipo"] == "generacion"]
    descargas = [e for e in eventos if e["tipo"] == "descarga"]
    # si alguien vuelve a calificar el mismo material, vale su última calificación
    ultima: dict[str, dict] = {}
    for e in eventos:
        if e["tipo"] == "calificacion":
            ultima[e.get("objeto_id", "")] = e
    calificaciones = list(ultima.values())

    por_formato = []
    for fila in _conteo(generaciones, "formato"):
        del_formato = [e for e in generaciones if (e.get("formato") or "Sin registrar") == fila["nombre"]]
        estrellas = [c["estrellas"] for c in calificaciones if c.get("formato") == fila["nombre"]]
        por_formato.append({
            **fila,
            "fidelidad_promedio": _promedio([e["fidelidad"] for e in del_formato if "fidelidad" in e]),
            "calificacion_promedio": _promedio(estrellas, 1),
            "calificaciones": len(estrellas),
        })

    hoy = (hoy or datetime.now().astimezone()).date()
    por_dia = Counter(e["fecha"][:10] for e in generaciones)
    actividad = []
    for i in range(DIAS_DE_ACTIVIDAD - 1, -1, -1):
        dia = (hoy - timedelta(days=i)).isoformat()
        actividad.append({"fecha": dia, "total": por_dia.get(dia, 0)})

    estrellas = [c["estrellas"] for c in calificaciones]
    comentarios = sorted((c for c in calificaciones if c.get("comentario")), key=lambda c: c["fecha"], reverse=True)

    return {
        "totales": {
            "materiales": len(generaciones),
            "descargas": len(descargas),
            "calificaciones": len(calificaciones),
            "calificacion_promedio": _promedio(estrellas, 1),
            "fidelidad_promedio": _promedio([e["fidelidad"] for e in generaciones if "fidelidad" in e]),
            "tasa_aprobacion": _promedio([1.0 if e.get("aprobado") else 0.0 for e in generaciones]),
            "tiempo_generacion_promedio_s": _promedio(
                [e["tiempo_generacion_s"] for e in generaciones if "tiempo_generacion_s" in e], 1
            ),
            "modo_local": sum(1 for e in generaciones if e.get("modo_local")),
            "historicos": sum(1 for e in generaciones if e.get("historico")),
        },
        "por_formato": por_formato,
        "por_perfil": _conteo(generaciones, "perfil"),
        "por_sector": _conteo(generaciones, "nicho"),
        "por_nivel": _conteo(generaciones, "nivel_detalle"),
        "por_origen": _conteo(generaciones, "origen"),
        "descargas_por_tipo": _conteo(descargas, "formato"),
        "distribucion_estrellas": [
            {"estrellas": n, "total": sum(1 for s in estrellas if s == n)} for n in range(5, 0, -1)
        ],
        "actividad_diaria": actividad,
        "comentarios_recientes": [
            {k: c.get(k) for k in ("fecha", "estrellas", "comentario", "formato", "perfil")}
            for c in comentarios[:COMENTARIOS_RECIENTES]
        ],
    }
