"""Interfaz Streamlit de NuevaMente.

Responsable en el equipo Kairos G10: Dario Higuera Moreno (No Code Developer).

Corre el pipeline directamente en proceso (sin pasar por la API HTTP) para que
la demo funcione con `streamlit run ui/app.py` sin depender de un servidor
FastAPI corriendo aparte. En producción también podría hablar con la API.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import streamlit as st

from nuevamente.agents.graph import generar_contenido_educativo
from nuevamente.exports import exportar_anki_csv, exportar_markdown
from nuevamente.ingest.readers import DocumentoInvalidoError, leer_texto_plano
from nuevamente.llm.base import LLMError
from nuevamente.schemas.enums import FormatoSalida, NichoSector, NivelDetalle, PerfilDestinatario
from nuevamente.storage.oci_client import get_storage_service

st.set_page_config(page_title="NuevaMente · Kairos G10", page_icon="🎓", layout="wide")

if "historial" not in st.session_state:
    st.session_state.historial = []

with st.sidebar:
    st.title("🎓 NuevaMente")
    st.caption("Kairos G10 · Hackathon ONE G10 · Nicho de foco: Salud")

    modo_entrada = st.radio("Fuente del documento", ["Pegar texto", "Subir archivo (.txt/.md)"])

    if modo_entrada == "Pegar texto":
        titulo_doc = st.text_input("Título del documento", value="Protocolo de Bioseguridad")
        contenido_doc = st.text_area("Contenido del documento", height=220)
    else:
        archivo = st.file_uploader("Documento (.txt o .md)", type=["txt", "md"])
        titulo_doc, contenido_doc = "", ""
        if archivo is not None:
            titulo_doc = Path(archivo.name).stem
            contenido_doc = archivo.read().decode("utf-8", errors="replace")

    perfil = st.selectbox("Perfil del destinatario", [p.value for p in PerfilDestinatario])
    formato = st.selectbox("Formato de salida", [f.value for f in FormatoSalida])
    nicho = st.selectbox("Nicho / sector", [n.value for n in NichoSector], index=[n.value for n in NichoSector].index("Salud"))
    nivel = st.selectbox("Nivel de detalle", [n.value for n in NivelDetalle])

    generar = st.button("Generar contenido educativo", type="primary", use_container_width=True)

    storage = get_storage_service()
    st.divider()
    st.caption(f"OCI Object Storage: {'✅ conectado' if storage.disponible_oci() else '⚠️ modo local (sin credenciales OCI)'}")

st.title("Adaptación de contenido educativo")

if nicho == "Salud":
    st.info(
        "⚕️ **Aviso:** este contenido es material de apoyo educativo generado a partir del "
        "documento proporcionado. No reemplaza el criterio de un profesional de salud ni las "
        "indicaciones oficiales vigentes.",
        icon="⚕️",
    )

if generar:
    if not contenido_doc or not contenido_doc.strip():
        st.error("Ingresa o sube un documento antes de generar contenido.")
    else:
        pasos = st.empty()
        try:
            with st.spinner("Indexando documento (chunking + embeddings)…"):
                pasos.write("**Etapa:** Ingesta y RAG")
                time.sleep(0.2)

            t0 = time.perf_counter()
            with st.spinner("Planificando → investigando → redactando → verificando fidelidad…"):
                resultado = generar_contenido_educativo(
                    documento_titulo=titulo_doc or "Documento sin título",
                    documento_contenido=contenido_doc,
                    perfil=perfil,
                    formato=formato,
                    nicho=nicho,
                    nivel_detalle=nivel,
                )
            duracion = round(time.perf_counter() - t0, 2)

            slug_formato = formato.lower().replace(" ", "-")
            slug_perfil = perfil.lower().replace("/", "-").replace(" ", "-")
            objeto_id = f"contenidos/{resultado.coleccion.doc_id}/{slug_formato}-{slug_perfil}.json"
            objeto_original = f"originals/{resultado.coleccion.doc_id}.txt"
            storage.subir_texto(objeto_original, contenido_doc, content_type="text/plain")

            import json as _json

            from nuevamente.schemas.response import AlmacenamientoOCI, Metadatos, RespuestaAdaptacion
            import uuid as _uuid

            respuesta = RespuestaAdaptacion(
                request_id=str(_uuid.uuid4()),
                metadatos=resultado.metadatos,
                contenido_adaptado=resultado.contenido,
                evaluacion_calidad=resultado.evaluacion,
                almacenamiento_oci=AlmacenamientoOCI(bucket="", objeto_id="", status_upload="pendiente"),
            )
            subida = storage.subir_json(objeto_id, respuesta.model_dump(mode="json"))
            respuesta.almacenamiento_oci = AlmacenamientoOCI(
                bucket=subida.bucket,
                objeto_id=subida.objeto_id,
                objeto_documento_original=objeto_original,
                status_upload=subida.status_upload,
            )

            st.session_state.historial.insert(
                0, {"titulo": titulo_doc, "perfil": perfil, "formato": formato, "nicho": nicho, "respuesta": respuesta}
            )
            st.success(f"Contenido generado en {duracion} s")
        except (LLMError, DocumentoInvalidoError, ValueError) as exc:
            st.error(f"No se pudo generar el contenido: {exc}")

if st.session_state.historial:
    ultimo = st.session_state.historial[0]
    respuesta = ultimo["respuesta"]

    tab_contenido, tab_json, tab_calidad, tab_almacenamiento, tab_historial = st.tabs(
        ["📖 Contenido", "🧾 JSON", "🔍 Calidad", "☁️ Almacenamiento", "🕘 Historial"]
    )

    with tab_contenido:
        col1, col2 = st.columns([3, 1])
        with col1:
            contenido = respuesta.contenido_adaptado
            if contenido.formato == "Flashcards":
                st.subheader(contenido.titulo)
                st.write(contenido.introduccion_contextualizada)
                for i, item in enumerate(contenido.items, 1):
                    with st.expander(f"{i}. {item.frente}"):
                        st.write(item.dorso)
                        if item.pista_didactica:
                            st.caption(f"💡 {item.pista_didactica}")
            elif contenido.formato == "Quiz":
                st.subheader(contenido.titulo)
                for i, p in enumerate(contenido.preguntas, 1):
                    st.markdown(f"**{i}. {p.enunciado}**")
                    seleccion = st.radio(
                        "Elige una opción", p.opciones, key=f"quiz_{i}_{p.enunciado[:20]}", label_visibility="collapsed"
                    )
                    if st.button("Verificar", key=f"verificar_{i}"):
                        if p.opciones.index(seleccion) == p.indice_correcto:
                            st.success(f"¡Correcto! {p.justificacion}")
                        else:
                            st.warning(f"No es la respuesta esperada. {p.justificacion}")
            elif contenido.formato == "Tutorial":
                st.subheader("Tutorial")
                st.write(f"**Objetivo:** {contenido.objetivo}")
                for paso in contenido.pasos:
                    st.markdown(f"**Paso {paso.orden}: {paso.titulo}**")
                    st.write(paso.instruccion)
                if contenido.checklist_final:
                    st.write("**Checklist final:**")
                    for i, c in enumerate(contenido.checklist_final):
                        st.checkbox(c, key=f"chk_{i}_{c}")
            elif contenido.formato == "Resumen Ejecutivo":
                st.subheader("Resumen Ejecutivo")
                st.write(contenido.resumen)
                st.write("**Puntos clave:**")
                for pk in contenido.puntos_clave:
                    st.markdown(f"- {pk}")
                if contenido.impacto_de_negocio:
                    st.info(contenido.impacto_de_negocio)
            elif contenido.formato == "Guion de Clase":
                st.subheader(f"Guion de Clase ({contenido.duracion_total_min} min)")
                for escena in contenido.escenas:
                    st.markdown(f"**Escena {escena.orden}** ({escena.duracion_seg}s)")
                    st.write(escena.narracion)
                    st.caption(escena.apoyo_visual)

        with col2:
            st.metric("Tiempo de generación", f"{respuesta.metadatos.tiempo_generacion_segundos:.2f} s")
            st.metric("Tiempo estimado de estudio", f"{respuesta.metadatos.tiempo_estimado_estudio_minutos} min")
            st.metric("Score de fidelidad", f"{respuesta.evaluacion_calidad.anclaje_fuente_score:.2f}")
            md = exportar_markdown(respuesta.contenido_adaptado, ultimo["titulo"])
            st.download_button("⬇️ Descargar Markdown", md, file_name="contenido.md")
            csv_data = exportar_anki_csv(respuesta.contenido_adaptado)
            st.download_button("⬇️ Descargar CSV (Anki)", csv_data, file_name="contenido_anki.csv")

    with tab_json:
        st.json(respuesta.model_dump(mode="json"))

    with tab_calidad:
        ev = respuesta.evaluacion_calidad
        c1, c2, c3 = st.columns(3)
        c1.metric("Score de anclaje a la fuente", f"{ev.anclaje_fuente_score:.2f}")
        c2.metric("Umbral aplicado", f"{ev.umbral_aplicado:.2f}")
        c3.metric("Claridad pedagógica", ev.claridad_pedagogica)
        st.write(f"Afirmaciones evaluadas: {ev.afirmaciones_total} · sustentadas: {ev.afirmaciones_sustentadas}")
        if ev.afirmaciones_no_sustentadas:
            st.warning("Afirmaciones marcadas como no sustentadas por la fuente:")
            for a in ev.afirmaciones_no_sustentadas:
                st.write(f"- {a}")
        else:
            st.success("Todas las afirmaciones quedaron sustentadas por el documento fuente.")
        st.caption(ev.observaciones)

    with tab_almacenamiento:
        al = respuesta.almacenamiento_oci
        st.write(f"**Bucket:** {al.bucket}")
        st.write(f"**Objeto generado:** {al.objeto_id}")
        st.write(f"**Documento original:** {al.objeto_documento_original}")
        if al.status_upload == "completado":
            st.success("Guardado en OCI Object Storage")
        else:
            st.warning("Guardado en almacenamiento local de respaldo (OCI no disponible en este entorno)")

    with tab_historial:
        for h in st.session_state.historial:
            st.write(f"**{h['titulo']}** — {h['perfil']} · {h['formato']} · {h['nicho']}")
else:
    st.caption("Genera tu primer contenido desde el panel de la izquierda.")
