"""Exportación del contenido adaptado a Markdown y a CSV compatible con Anki.

Responsable en el equipo Kairos G10: Dario Higuera Moreno (No Code Developer).
Este es uno de los diferenciales del checklist ("Exportación Multiformato").
"""
from __future__ import annotations

import csv
import io

from nuevamente.schemas.formatos import (
    ContenidoAdaptado,
    FlashcardsContenido,
    GuionDeClaseContenido,
    QuizContenido,
    ResumenEjecutivoContenido,
    TutorialContenido,
)


def exportar_markdown(contenido: ContenidoAdaptado, titulo_documento: str = "") -> str:
    lineas: list[str] = []
    if titulo_documento:
        lineas.append(f"> Generado por NuevaMente a partir de: {titulo_documento}")
        lineas.append("")

    if isinstance(contenido, FlashcardsContenido):
        lineas.append(f"# {contenido.titulo}")
        lineas.append("")
        lineas.append(contenido.introduccion_contextualizada)
        lineas.append("")
        for i, item in enumerate(contenido.items, 1):
            lineas.append(f"## {i}. {item.frente}")
            lineas.append(item.dorso)
            if item.pista_didactica:
                lineas.append(f"*Pista: {item.pista_didactica}*")
            lineas.append("")

    elif isinstance(contenido, QuizContenido):
        lineas.append(f"# {contenido.titulo}")
        lineas.append("")
        for i, p in enumerate(contenido.preguntas, 1):
            lineas.append(f"## Pregunta {i}")
            lineas.append(p.enunciado)
            lineas.append("")
            for j, opcion in enumerate(p.opciones):
                marca = "✅" if j == p.indice_correcto else "◻️"
                lineas.append(f"{marca} {chr(65+j)}. {opcion}")
            lineas.append("")
            lineas.append(f"**Justificación:** {p.justificacion}")
            lineas.append("")

    elif isinstance(contenido, TutorialContenido):
        lineas.append(f"# Tutorial")
        lineas.append(f"**Objetivo:** {contenido.objetivo}")
        lineas.append("")
        if contenido.prerrequisitos:
            lineas.append("**Prerrequisitos:**")
            for p in contenido.prerrequisitos:
                lineas.append(f"- {p}")
            lineas.append("")
        for paso in contenido.pasos:
            lineas.append(f"## Paso {paso.orden}: {paso.titulo}")
            lineas.append(paso.instruccion)
            if paso.resultado_esperado:
                lineas.append(f"*Resultado esperado: {paso.resultado_esperado}*")
            lineas.append("")
        if contenido.errores_comunes:
            lineas.append("## Errores comunes")
            for e in contenido.errores_comunes:
                lineas.append(f"- {e}")
            lineas.append("")
        if contenido.checklist_final:
            lineas.append("## Checklist final")
            for c in contenido.checklist_final:
                lineas.append(f"- [ ] {c}")

    elif isinstance(contenido, ResumenEjecutivoContenido):
        lineas.append("# Resumen Ejecutivo")
        lineas.append("")
        lineas.append(contenido.resumen)
        lineas.append("")
        lineas.append("**Puntos clave:**")
        for pk in contenido.puntos_clave:
            lineas.append(f"- {pk}")
        if contenido.decisiones_o_riesgos:
            lineas.append("")
            lineas.append("**Riesgos/decisiones:**")
            for r in contenido.decisiones_o_riesgos:
                lineas.append(f"- {r}")
        if contenido.impacto_de_negocio:
            lineas.append("")
            lineas.append(f"**Impacto de negocio:** {contenido.impacto_de_negocio}")

    elif isinstance(contenido, GuionDeClaseContenido):
        lineas.append(f"# Guion de Clase ({contenido.duracion_total_min} min)")
        lineas.append("")
        for escena in contenido.escenas:
            lineas.append(f"## Escena {escena.orden} — {escena.duracion_seg}s")
            lineas.append(f"**Narración:** {escena.narracion}")
            if escena.apoyo_visual:
                lineas.append(f"**Apoyo visual:** {escena.apoyo_visual}")
            lineas.append("")

    return "\n".join(lineas)


def exportar_anki_csv(contenido: ContenidoAdaptado) -> str:
    """Genera un CSV con columnas frente,dorso — formato de importación directa de Anki.

    Solo tiene sentido para Flashcards y Quiz (los formatos con pares
    pregunta/respuesta); para el resto se exporta el contenido igualmente,
    en pares título/detalle, por si el usuario quiere usarlo como repaso.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    if isinstance(contenido, FlashcardsContenido):
        for item in contenido.items:
            writer.writerow([item.frente, item.dorso])
    elif isinstance(contenido, QuizContenido):
        for p in contenido.preguntas:
            correcta = p.opciones[p.indice_correcto]
            writer.writerow([p.enunciado, f"{correcta} — {p.justificacion}"])
    elif isinstance(contenido, TutorialContenido):
        for paso in contenido.pasos:
            writer.writerow([f"Paso {paso.orden}: {paso.titulo}", paso.instruccion])
    elif isinstance(contenido, ResumenEjecutivoContenido):
        for pk in contenido.puntos_clave:
            writer.writerow([pk, contenido.resumen[:200]])
    elif isinstance(contenido, GuionDeClaseContenido):
        for escena in contenido.escenas:
            writer.writerow([f"Escena {escena.orden}", escena.narracion])

    return buffer.getvalue()
