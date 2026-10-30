# NuevaMente 🎓 — Kairos G10

**Sistema inteligente de adaptación y generación de contenido educativo**

Hackathon ONE G10 (Oracle Next Education y Alura) · Proyecto 1 · Simulación No Country
Equipo **Kairos G10** (G10-LATAM-equipo 41) · Nicho: **Salud** · Versión **1.5**

## Enlaces del proyecto

* 💻 [Repositorio en GitHub](https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS)
* 🌿 [Rama del Sprint 5](https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS/tree/SPRINT05)
* 🌐 [Aplicación en línea (deploy en Render)](https://g10-latam-equipo-41-kairos.onrender.com/)
* 📖 [Documentación interactiva de la API](https://g10-latam-equipo-41-kairos.onrender.com/docs)
* 📋 [Backlog en Jira (proyecto SCRUM)](https://dielidube.atlassian.net/jira/software/projects/SCRUM/boards/1/backlog)
* 📊 [Panel de seguimiento 1](https://dielidube.atlassian.net/jira/dashboards/10001) · [Panel de seguimiento 2](https://dielidube.atlassian.net/jira/dashboards/10002)

> **Nota:** en el plan gratuito de Render, la primera carga tras inactividad tarda cerca de un minuto.

> ⚕️ El contenido generado es material de apoyo educativo basado en el documento del usuario. **No reemplaza el criterio de un profesional de salud.**

## 1. Introducción

Los equipos de salud y tecnología manejan protocolos y manuales extensos que cada persona necesita aprender de forma distinta. **NuevaMente** recibe un documento técnico (PDF, también escaneado mediante OCR; Word, Markdown o texto), lo indexa con RAG y lo transforma en material de estudio personalizado. Cada afirmación generada se **verifica contra la fuente** y recibe un score de anclaje.

## 2. Objetivos

* Adaptar un mismo documento a **4 perfiles**: Principiante, Desarrollador Junior/Semi Senior, Líder Técnico/Arquitecto y Gestor/Ejecutivo.
* Generar **6 formatos pedagógicos**: Tutorial paso a paso, Flashcards, Quiz con justificaciones, Resumen Ejecutivo (TL;DR), Guion de Clase y Podcast.
* Ajustar por **sector** (General, Fintech, Salud, E-commerce, Tecnología), **nivel de detalle** (Conciso, Didáctico, Profundo) e **idioma de salida**.
* Garantizar la **fidelidad** con umbral de 0,90 en Salud y 0,85 en general.
* Persistir original y material en **OCI Object Storage**, con respaldo local.
* Exponer todo por **API REST** y una **interfaz web** propia.

## 3. Funcionalidades

* **Exportación:** Word (.docx), PDF didáctico, PowerPoint (.pptx), Markdown y CSV para Anki, cada uno con diseño propio.
* **Video MP4:** el Guion de Clase se convierte en diapositivas narradas con voces naturales de Gemini TTS (respaldo: OpenAI TTS o voces del sistema).
* **Podcast MP3:** conversación entre Ana y Leo, con voces distintas.
* **Estadísticas:** calificación de 1 a 5 estrellas, comentarios y panel con uso por formato, perfil y sector, descargas y fidelidad media.
* **Historial:** últimos 8 materiales.

## 4. Arquitectura

```
Documento (PDF/DOCX/MD/TXT)
  → Ingesta: chunking con solapamiento + secciones + OCR
  → RAG: embeddings Gemini (768 dim.) / TF-IDF + vector store por doc_id
  → LangGraph: Planificador → Investigador → Caché
               → Redactor (role prompting + few-shot)
               → Crítico (TF-IDF + juez de IA, con reintento)
  → Persistencia: OCI Object Storage o data/fallback/
  → API REST (FastAPI) → Interfaz web
```

**Stack:** Python 3.10+, FastAPI, Pydantic, LangGraph, Google Gemini (LLM, embeddings, OCR, TTS), Claude y otros proveedores de respaldo, scikit-learn, ChromaDB, OCI SDK, Pillow, ffmpeg, Docker y pytest.

## 5. Decisiones de diseño

El pipeline es **real y ejecutable sin servicios en la nube**: cada pieza externa tiene una alternativa local con la misma interfaz.

| Pieza | Respaldo local | Con credenciales |
|---|---|---|
| Embeddings | TF-IDF (scikit-learn) | Gemini `gemini-embedding-001` |
| Vector store | Store propio en numpy | ChromaDB persistente |
| LLM | `TemplateLLM` extractivo | Gemini, Claude u otros |
| Fidelidad | Similitud TF-IDF | TF-IDF + juez de IA con citas verificadas |
| Almacenamiento | `data/fallback/` | OCI Object Storage |
| Caché | Desactivado | Material aprobado sin llamar al LLM |

El juez de IA solo aprueba una afirmación si devuelve citas que **existen textualmente** en el documento, y además evalúa la coherencia didáctica.

## 6. Sprints

Sprints semanales, cada uno con su rama integrada a `main` por pull request.

### Sprint 1 · 21–27 sep · Hecho
**Objetivo:** MVP funcional de punta a punta.
* Ingesta de PDF, Markdown y texto; RAG con TF-IDF por sección.
* Gemini con modelos de respaldo y generador local.
* Agentes con reintento y verificación de fidelidad.
* API REST, interfaz web y Streamlit; 5 formatos para 4 perfiles.
* 3 escenarios de demo en Salud aprobados; **69 pruebas**.

### Sprint 2 · 28 sep–4 oct · Hecho
**Objetivo:** calidad del material y trabajo ordenado en GitHub.
* Material por secciones, sin duplicados y con numeración uniforme.
* Formato **Podcast** y barra de progreso con porcentaje.
* Rama `SPRINT02` con PR a `main`.
* **89 historias de usuario** en 14 épicas.

### Sprint 3 · 5–11 oct · Hecho
**Objetivo:** contrato del enunciado y experiencia de uso.
* JSON con los campos exactos del enunciado, conceptos clave y puntuación del quiz.
* Exportación a **Word** y limpieza del texto extraído.
* Cancelar, historial con buscador, atajos de teclado y aviso legal y ético.
* Caché de material aprobado; sector Tecnología.
* Pruebas de 72 a **175**; seis PR integrados.

### Sprint 4 · 12–18 oct · Parcial
**Objetivo:** cerrar historias, desplegar y preparar la demo.
* Embeddings semánticos, **LangGraph**, few-shot, **OCR**, ChromaDB y **juez de IA**.
* **PDF didáctico**, subida de Word, estadísticas y calificación.
* **Deploy con Docker en Render**; video y podcast en segundo plano (CPU de 78 a 9 s).
* Proveedores OpenRouter, Cohere y OpenAI.
* Pruebas de 175 a **270**; versión 1.4.
* Pendiente: OCI respondía 401 por una llave de API sin registrar.

### Sprint 5 · 19–25 oct · Cierre
**Objetivo:** cerrar el MVP, atender la revisión del mentor y dejar lista la demo.
* Títulos y subtítulos coherentes en Markdown y PDF; video sin saludo de prueba.
* Evidencias gráficas de pruebas y pantallas del aplicativo.
* **Docker Compose** con guía de comandos y checklist.
* Documentación de Jira por sprint: actividades, casos de prueba y estadísticas.
* README reorganizado, pitch y speech; **295 pruebas**; versión **1.5**.

## 7. Setup

**Requisitos:** Python 3.10+ o Docker. Sin claves funciona con respaldos locales.

```bash
git clone https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS.git
cd G10-LATAM-EQUIPO_41_KAIROS
cp .env.example .env
make install
make run-api        # http://localhost:8000/
```

Con Docker Compose: `docker compose up -d --build`

| Comando | Qué hace |
|---|---|
| `make test` | Corre las 295 pruebas |
| `make demo` | Ejecuta los 3 escenarios de Salud |
| `make run-ui` | Interfaz Streamlit opcional |

**Variables principales:** `LLM_PROVIDER` (`template`, `gemini`, `claude`, `auto`…), `GEMINI_API_KEY`, `EMBEDDINGS_PROVIDER`, `VECTOR_STORE`, `JUEZ_IA`, `OCR` y la configuración de OCI.

## 8. Uso de la API

```bash
curl -X POST http://localhost:8000/api/v1/adaptar \
  -H "Content-Type: application/json" \
  -d '{"documento_titulo":"Protocolo de bioseguridad",
       "documento_contenido":"El lavado de manos...",
       "perfil_destinatario":"Principiante",
       "formato_salida":"Flashcards",
       "nicho_sector":"Salud"}'
```

| Endpoint | Función |
|---|---|
| `POST /api/v1/adaptar/archivo` | Adaptar desde un archivo |
| `GET /api/v1/opciones` | Perfiles, formatos y sectores |
| `GET /api/v1/contenidos/{id}` | Recuperar un material |
| `.../exportar?formato=docx\|pdf\|pptx` | Exportar |
| `.../video` · `.../podcast` | Generar MP4 o MP3 |
| `GET /api/v1/estadisticas` · `GET /health` | Uso y estado |

## 9. Demo: casos de uso B2B en Salud

Protocolo de bioseguridad original, con Gemini y juez de IA:

| Caso | Perfil | Formato | Fidelidad |
|---|---|---|---|
| Onboarding clínico | Principiante | Flashcards | 1,00 ✅ |
| Capacitación regulatoria | Dev. Junior/Semi Senior | Quiz | 1,00 ✅ |
| Auditoría de protocolos | Gestor/Ejecutivo | Resumen Ejecutivo | 0,92 ✅ |

## 10. Calidad y seguridad

* **295 pruebas automatizadas**, incluida resistencia a inyección de instrucciones.
* El documento se trata siempre como datos, nunca como instrucciones.
* La interfaz inserta el texto como texto plano, no como HTML.
* Demo sin datos de pacientes ni dosificaciones.

## 11. Despliegue y estado

| Destino | Estado |
|---|---|
| Render (Docker) | ✅ [En línea](https://g10-latam-equipo-41-kairos.onrender.com/) |
| OCI Compute (Always Free) | Script, systemd y nginx listos |
| OCI Object Storage | Cliente listo; respaldo local activo |

**16 de 18** puntos del enunciado completados. Pendientes: verificar OCI Object Storage y crear la instancia de OCI Compute.

**Limitaciones:** la cuota gratuita de Gemini se agota con muchas pruebas seguidas; la app rota modelos y usa el respaldo local.

## 12. Equipo

| Integrante | Rol | Módulos |
|---|---|---|
| Juan Pablo Calla | Project Manager | Arquitectura, configuración, demo |
| Gaspar Martínez Paiva | Data Engineer · ML Engineer | `ingest/`, `rag/` |
| Ethan Espinoza Acosta | Backend · Orquestación | `agents/`, `api/`, `cache/` |
| Darío Higuera Moreno | No Code · Ingeniero de IA | `llm/`, `fidelity/`, `web/`, `exports/` |
| Diana Dure | QA Tester | `tests/` |

## 13. Recursos

* [README completo](https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS#readme)
* [Documentación de Jira por sprint](https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS/tree/main/docs/jira)
* [Entregables e historias de usuario](https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS/tree/main/docs/entregables)
* [Guía de despliegue en Render](https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS/blob/main/docs/DEPLOY_RENDER.md)
