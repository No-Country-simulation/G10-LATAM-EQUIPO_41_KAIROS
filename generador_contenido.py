import os
import json
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

# Tu API Key personal de Google Gemini obtenida en Google AI Studio
os.environ["GOOGLE_API_KEY"] = "AQ.Ab8RN6KLOdc0Nt_b089-9rv_VKcrF8AZmcVMzydId2-RoGBTfw"

def generar_contenido_educativo(tema, perfil_audiencia, formato_salida):
    print("1. Cargando base de datos vectorial local...")
    embeddings = HuggingFaceEmbeddings(
        model_name="./modelo_local",
        model_kwargs={'device': 'cpu'}
    )
    
    vectorstore = Chroma(
        persist_directory="./vector_store", 
        embedding_function=embeddings
    )
    
    print(f"2. Buscando fragmentos del PDF sobre: '{tema}'...")
    # Recuperamos los 4 segmentos de texto con mayor similitud
    docs = vectorstore.similarity_search(tema, k=4)
    contexto = "\n\n".join([doc.page_content for doc in docs])
    
    print(f"3. Generando contenido con Gemini ({perfil_audiencia} - {formato_salida})...")
    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", temperature=0.3)
    
    plantilla_prompt = """
Eres un diseñador instruccional experto. Tu tarea es adaptar la información técnica provista a una audiencia específica y entregar la respuesta ÚNICAMENTE en formato JSON válido.

CONTEXTO TÉCNICO RECUPERADO DEL MANUAL:
{contexto}

PARÁMETROS DE ADAPTACIÓN:
- Tema buscado: {tema}
- Perfil de la audiencia: {perfil}
- Formato pedagógico: {formato}

INSTRUCCIONES:
1. Ajusta el vocabulario, nivel de detalle y tono al perfil '{perfil}'.
2. Diseña la respuesta para cumplir la estructura típica del formato '{formato}' (ej. Flashcards = pregunta/respuesta; Quiz = pregunta/opciones; Resumen = secciones).
3. Devuelve la respuesta como un objeto JSON strictly válido, sin incluir bloques Markdown como ```json.

ESTRUCTURA JSON REQUERIDA:
{{
    "tema": "{tema}",
    "perfil_audiencia": "{perfil}",
    "formato": "{formato}",
    "contenido": [
        {{
            "titulo": "Título de la sección, tarjeta o pregunta",
            "concepto": "Explicación adaptada al perfil",
            "detalle_adicional": "Ejemplo práctico o alternativas de respuesta"
        }}
    ]
}}
"""

    prompt = PromptTemplate(
        template=plantilla_prompt,
        input_variables=["contexto", "tema", "perfil", "formato"]
    )
    
    chain = prompt | llm
    
    respuesta = chain.invoke({
        "contexto": contexto,
        "tema": tema,
        "perfil": perfil_audiencia,
        "formato": formato_salida
    })
    
    # Extraemos el texto sin importar si viene como string o como lista de bloques
    if isinstance(respuesta.content, list):
        texto_bruto = "".join(
            part if isinstance(part, str) else part.get("text", "") 
            for part in respuesta.content
        )
    else:
        texto_bruto = str(respuesta.content)

    # Limpiamos los marcadores de Markdown en caso de que el modelo los haya incluido
    texto_limpio = texto_bruto.replace("```json", "").replace("```", "").strip()
    return texto_limpio

if __name__ == "__main__":
    # Parámetros editables para probar diferentes casos de uso
    TEMA_BUSQUEDA = "procedimientos de seguridad"
    PERFIL_TARGET = "Principiante"  # Opciones: Principiante, Técnico, Ejecutivo
    FORMATO_TARGET = "Flashcards"   # Opciones: Flashcards, Quiz, Resumen

    json_salida = generar_contenido_educativo(TEMA_BUSQUEDA, PERFIL_TARGET, FORMATO_TARGET)
    
    print("\n--- RESPUESTA JSON GENERADA ---")
    print(json_salida)
    
    # Guardamos el JSON estructurado
    with open("resultado_adaptado.json", "w", encoding="utf-8") as f:
        f.write(json_salida)
        
    print("\n¡Proceso finalizado! Archivo 'resultado_adaptado.json' generado con éxito.")