import os
import json
import streamlit as st
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

os.environ["GOOGLE_API_KEY"] = "TU_CLAVE_API_AQUI"

st.set_page_config(
    page_title="Generador Educativo RAG",
    page_icon="🎓",
    layout="wide"
)

st.title("🎓 Adaptador de Contenido Técnico con IA (RAG)")
st.markdown("Transforma cualquier manual técnico en material didáctico adaptado automáticamente.")

def procesar_pdf_subido(archivo):
    ruta_temporal = os.path.join(".", "temp_manual.pdf")
    with open(ruta_temporal, "wb") as f:
        f.write(archivo.getbuffer())
        
    loader = PyPDFLoader(ruta_temporal)
    documentos = loader.load()
    
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_documents(documentos)
    
    embeddings = HuggingFaceEmbeddings(model_name="./modelo_local", model_kwargs={'device': 'cpu'})
    
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory="./vector_store_app"
    )
    
    if os.path.exists(ruta_temporal):
        os.remove(ruta_temporal)
        
    return vectorstore

def generar_respuesta(vectorstore, tema, perfil, formato):
    docs = vectorstore.similarity_search(tema, k=4)
    contexto = "\n\n".join([doc.page_content for doc in docs])
    
    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", temperature=0.3)
    
    plantilla = """
Eres un diseñador instruccional experto. Tu tarea es adaptar la información técnica provista a una audiencia específica y entregar la respuesta ÚNICAMENTE en formato JSON válido.

CONTEXTO TÉCNICO RECUPERADO DEL MANUAL:
{contexto}

PARÁMETROS DE ADAPTACIÓN:
- Tema buscado: {tema}
- Perfil de la audiencia: {perfil}
- Formato pedagógico: {formato}

DIRECTRICES ESTRICTAS DE PERFIL:
- Principiante: Usa un lenguaje muy sencillo, explicaciones conceptuales y analogías cotidianas. Evita jerga técnica compleja sin explicarla.
- Técnico: Incluye nombres exactos de variables, tablas, códigos, prefijos, sintaxis y reglas de desarrollo sin simplificar.
- Ejecutivo: Enfócate exclusivamente en el impacto operativo, buenas prácticas corporativas, gestión de riesgos y cumplimiento de estándares a alto nivel.

DIRECTRICES ESTRICTAS DE FORMATO:
- Flashcards: 
  * "titulo": Pregunta corta o concepto clave.
  * "concepto": Explicación concisa.
  * "detalle_adicional": Ejemplo práctico o caso de uso.
- Quiz: 
  * "titulo": Pregunta de evaluación.
  * "concepto": Las 4 opciones de respuesta (A, B, C, D).
  * "detalle_adicional": Indicar cuál es la respuesta correcta y la explicación de por qué es esa.
- Resumen: 
  * "titulo": Nombre del subtema o sección.
  * "concepto": Síntesis ejecutiva del tema.
  * "detalle_adicional": Puntos clave / Conclusiones esenciales.

Devuelve la respuesta como un objeto JSON strictly válido, sin incluir bloques Markdown como ```json.

ESTRUCTURA JSON REQUERIDA:
{{
    "tema": "{tema}",
    "perfil_audiencia": "{perfil}",
    "formato": "{formato}",
    "contenido": [
        {{
            "titulo": "Título adaptado al formato",
            "concepto": "Contenido adaptado al perfil y formato",
            "detalle_adicional": "Detalle, respuesta o ejemplo según formato"
        }}
    ]
}}
"""
    prompt = PromptTemplate(template=plantilla, input_variables=["contexto", "tema", "perfil", "formato"])
    chain = prompt | llm
    
    respuesta = chain.invoke({"contexto": contexto, "tema": tema, "perfil": perfil, "formato": formato})
    
    if isinstance(respuesta.content, list):
        texto_bruto = "".join(part if isinstance(part, str) else part.get("text", "") for part in respuesta.content)
    else:
        texto_bruto = str(respuesta.content)

    return texto_bruto.replace("```json", "").replace("```", "").strip()

# Panel lateral
with st.sidebar:
    st.header("📄 1. Cargar Manual")
    pdf_subido = st.file_uploader("Sube un archivo PDF técnico", type=["pdf"])
    
    st.header("⚙️ 2. Parámetros")
    tema_input = st.text_input("Tema a buscar:", value="Nomenclatura")
    perfil_input = st.selectbox("Perfil de audiencia:", ["Principiante", "Técnico", "Ejecutivo"])
    formato_input = st.selectbox("Formato pedagógico:", ["Flashcards", "Quiz", "Resumen"])
    
    boton_procesar = st.button("🚀 Generar Contenido", type="primary", use_container_width=True)

# Área principal
if boton_procesar:
    if not tema_input.strip():
        st.warning("Por favor ingresa un tema válido.")
    else:
        try:
            with st.spinner("Procesando documento y generando respuesta..."):
                if pdf_subido is not None:
                    v_store = procesar_pdf_subido(pdf_subido)
                else:
                    embeddings = HuggingFaceEmbeddings(model_name="./modelo_local", model_kwargs={'device': 'cpu'})
                    v_store = Chroma(persist_directory="./vector_store", embedding_function=embeddings)
                
                json_str = generar_respuesta(v_store, tema_input, perfil_input, formato_input)
                datos = json.loads(json_str)
                
            st.success("¡Contenido generado exitosamente!")
            
            st.subheader(f"📌 {datos.get('tema', tema_input).title()}")
            st.caption(f"Perfil: **{datos.get('perfil_audiencia')}** | Formato: **{datos.get('formato')}**")
            st.divider()
            
            # Renderizado visual adaptable al formato seleccionado
            contenido = datos.get("contenido", [])
            fmt = datos.get("formato", formato_input)

            for i, item in enumerate(contenido, 1):
                if fmt == "Quiz":
                    etiqueta_bloque = f"❓ Pregunta {i}: {item.get('titulo', '')}"
                elif fmt == "Resumen":
                    etiqueta_bloque = f"📖 Sección {i}: {item.get('titulo', '')}"
                else:
                    etiqueta_bloque = f"📇 Tarjeta {i}: {item.get('titulo', '')}"

                with st.expander(etiqueta_bloque, expanded=True):
                    st.markdown(f"**{item.get('concepto')}**")
                    if item.get("detalle_adicional"):
                        if fmt == "Quiz":
                            st.success(f"✅ **Respuesta & Explicación:** {item.get('detalle_adicional')}")
                        else:
                            st.info(f"💡 **Detalle / Ejemplo:** {item.get('detalle_adicional')}")

            # Vista raw del JSON y descarga
            st.divider()
            with st.expander("📄 Ver estructura JSON (Entregable Raw)"):
                st.json(datos)
                st.download_button(
                    label="📥 Descargar resultado_adaptado.json",
                    data=json.dumps(datos, indent=4, ensure_ascii=False),
                    file_name="resultado_adaptado.json",
                    mime="application/json"
                )

        except Exception as e:
            st.error(f"Error durante el procesamiento: {e}")
else:
    st.info("👈 Puedes subir un PDF nuevo o usar el manual por defecto. Ajusta los parámetros y presiona **Generar Contenido**.")