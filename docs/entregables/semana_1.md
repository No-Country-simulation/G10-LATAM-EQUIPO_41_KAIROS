# Entregable Semanal — Semana 1

**Proyecto:** NuevaMente — Sistema Inteligente de Adaptación y Generación de Contenido Educativo
**Equipo:** Kairos G10 (G10-LATAM-equipo 41)
**Nicho de foco:** Salud
**Semana:** 1 (21–27 de septiembre)

## Avance de la semana

Se construyó y probó un **MVP funcional de punta a punta**:

- **Ingesta de documentos**: lectura de PDF, Markdown y texto plano.
- **RAG**: chunking con solapamiento y detección de secciones, embeddings TF-IDF y recuperación por similitud, aislada por documento.
- **IA generativa con Google Gemini**: conectada y operativa, con modelos de respaldo si el principal está saturado y un generador local de último recurso para que el servicio no se caiga.
- **Orquestación de agentes**: flujo Planificador → Investigador → Redactor → Verificador de fidelidad → Crítico, con ciclo de reintento.
- **Verificación de fidelidad**: score de anclaje a la fuente, con umbral reforzado (0.90) para el nicho Salud.
- **Persistencia**: integración con OCI Object Storage implementada; mientras se configura la cuenta, los resultados se guardan en un respaldo local y la respuesta lo indica (`status_upload: "fallido_local"`).
- **API REST** (FastAPI) con salida JSON estructurada e **interfaz interactiva** (interfaz web servida por la API, y Streamlit), ambas operativas.
- **5 formatos pedagógicos** (Flashcards, Quiz, Tutorial, Resumen Ejecutivo, Guion de Clase), probados en pruebas automatizadas que cubren los **4 perfiles** de destinatario.
- **3 escenarios de demo** ejecutados sobre un documento original de bioseguridad en salud, todos aprobados por el Crítico:

| Caso de uso | Perfil | Formato | Score de fidelidad | Generado con |
|---|---|---|---|---|
| Onboarding de personal clínico nuevo | Principiante | Flashcards | 0.94 | Gemini (gemini-3.5-flash) |
| Capacitación regulatoria interna | Desarrollador Junior/Semi Senior | Quiz | 1.00 | Gemini (gemini-flash-latest) |
| Actualización de protocolos ante auditoría | Gestor/Ejecutivo | Resumen Ejecutivo | 1.00 | Generador local (Gemini no disponible en esa corrida) |

- **69 pruebas automatizadas** en verde, incluida resistencia a inyección de instrucciones.

## Herramientas y tecnologías utilizadas

| Categoría | Herramienta |
|---|---|
| Lenguaje | Python 3.14 |
| Backend / API | FastAPI, Pydantic, Uvicorn |
| IA generativa | Google Gemini (SDK google-genai) |
| RAG / Embeddings | scikit-learn (TF-IDF local) |
| Lectura de documentos | pypdf |
| Pruebas | pytest (69 pruebas) |
| Interfaz | Interfaz web (HTML/CSS/JS) y Streamlit |
| Nube | Oracle Cloud Infrastructure (OCI Object Storage) — en configuración |

## Bloqueos

- **OCI Object Storage** (requisito obligatorio): la integración está en el código, pero falta crear la cuenta Always Free, las claves API y el bucket. Hasta entonces se usa el respaldo local.
- **Disponibilidad de Gemini**: el modelo principal (`gemini-3.7-flash`) responde con error 503 por alta demanda; los modelos de respaldo sí funcionan.

## Próximo paso (Sprint 2)

- Configurar la cuenta OCI y el bucket, y verificar que los resultados se suban con `status_upload: "completado"`.
- Cambiar el modelo principal de Gemini a uno estable y volver a ejecutar los 3 escenarios de demo con Gemini.
- Generar prerrequisitos y conceptos clave con el LLM, y agregar una evaluación de coherencia didáctica.
- Conectar el proyecto a un repositorio en GitHub.
