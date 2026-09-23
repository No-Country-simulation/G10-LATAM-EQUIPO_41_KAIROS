# 🎓 Generador Educativo RAG - Hackathon 2026

![Python](https://img.shields.io/badge/Python-3.13-blue)
![LangChain](https://img.shields.io/badge/LangChain-RAG-green)
![Streamlit](https://img.shields.io/badge/Streamlit-UI-red)
![Gemini](https://img.shields.io/badge/Gemini-3.5_Flash_Lite-orange)

Aplicación web interactiva que utiliza Inteligencia Artificial y la arquitectura **RAG (Generación Aumentada por Recuperación)** para transformar manuales técnicos complejos en material didáctico estructurado (Flashcards, Quizzes y Resúmenes).

## 🚀 Arquitectura y Solución de Desafíos
Este proyecto fue diseñado con una **arquitectura híbrida (Local/Cloud)** para superar estrictas restricciones de red corporativas (firewalls) y límites de cuota (Rate Limits 429) en APIs gratuitas:

1. **Ingestión e Indexación (Offline):** El procesamiento de PDFs y la generación de embeddings se ejecutan 100% en local utilizando el modelo de HuggingFace `all-MiniLM-L6-v2` y **ChromaDB**. Esto garantiza privacidad, elimina latencia y evita bloqueos de red.
2. **Orquestación y Generación (Cloud):** Solo el contexto recuperado (los fragmentos más relevantes) se envía al modelo `gemini-3.5-flash-lite` mediante un prompt estructurado para adaptar el tono pedagógico y generar una respuesta estricta en formato `JSON`.

## ⚙️ Requisitos previos
- Python 3.10 o superior.
- Una API Key de Google Gemini (Google AI Studio).
- Carpeta `modelo_local` (modelo de embeddings `all-MiniLM-L6-v2` descargado localmente).

## 🛠️ Instalación y Uso

1. **Clonar el repositorio y preparar el entorno:**
   ```bash
   git clone <URL_DE_TU_REPO>
   cd Hackathon_2026
   python -m venv venv
   venv\Scripts\activate
