import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

def procesar_documento(ruta_pdf):
    print(f"1. Cargando el documento: {ruta_pdf}")
    loader = PyPDFLoader(ruta_pdf)
    documentos = loader.load()

    print("2. Segmentando el texto (Chunking)...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    chunks = text_splitter.split_documents(documentos)
    print(f"   Se generaron {len(chunks)} segmentos.")

    print("3. Generando embeddings en modo offline desde 'modelo_local'...")
    # Carga el modelo directamente desde los archivos locales descargados
    embeddings = HuggingFaceEmbeddings(
        model_name="./modelo_local",
        model_kwargs={'device': 'cpu'}
    )
    
    # Genera la base de datos de una sola vez sin depender de red
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory="./vector_store"
    )
    
    print("¡Indexación completada con éxito!")
    return vectorstore

if __name__ == "__main__":
    ruta_archivo = "manual_prueba.pdf" 
    
    if os.path.exists(ruta_archivo):
        db = procesar_documento(ruta_archivo)
    else:
        print(f"Error: No se encontró el archivo '{ruta_archivo}'.")