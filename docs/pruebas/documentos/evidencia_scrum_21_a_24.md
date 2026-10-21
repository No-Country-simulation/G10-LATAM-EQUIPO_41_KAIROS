# Reporte de Evidencia de Pruebas: Pipeline RAG y Fallback Local (SCRUM 21 a 24)

**Proyecto:** NuevaMente (Hackathon ONE G10 - Kairos G10)
**Área:** Data Engineering / IA
**Responsables:** Gaspar Martinez / Bryan / Adrian

Este documento consolida la evidencia de las pruebas automatizadas ejecutadas exitosamente para los módulos de ingesta, segmentación, vectorización local y generación offline del Sprint 02.

---

## 1. SCRUM-21 y SCRUM-22: Ingesta de Documentos y Chunking

**Módulos probados:** `src/nuevamente/ingest/readers.py` y `src/nuevamente/ingest/chunking.py`
**Archivo de test:** `tests/test_ingest.py`

**Criterios de Aceptación Verificados:**
- [x] (SCRUM-21) Lectura correcta de formatos de entrada (PDF, Markdown, TXT).
- [x] (SCRUM-22) División de texto (chunking) garantizando el tamaño máximo y solapamiento (overlap).
- [x] (SCRUM-22) Detección automática de secciones por encabezados sin cortar oraciones a la mitad.
- [x] (SCRUM-22) Generación de un ID determinista (doc_id) para trazabilidad de cada fragmento.

**Evidencia de Ejecución:**
> pytest tests/test_ingest.py
> 5 passed in 6.12s
> Estado: APROBADO

---

## 2. SCRUM-23: Embeddings Locales (TF-IDF) y Vector Store

**Módulos probados:** `src/nuevamente/rag/embeddings.py` y `src/nuevamente/rag/vectorstore.py`
**Archivo de test:** `tests/test_vectorstore.py`

**Criterios de Aceptación Verificados:**
- [x] Vectorización determinista local utilizando TfidfVectorizer (scikit-learn).
- [x] Almacenamiento aislado en memoria agrupado por documento (doc_id).
- [x] Recuperación precisa mediante Similitud de Coseno.

**Evidencia de Ejecución:**
> pytest tests/test_vectorstore.py
> 3 passed in 3.64s
> Estado: APROBADO

---

## 3. SCRUM-24: TemplateLLM (Generador Determinista Offline)

**Módulos probados:** `src/nuevamente/llm/template_llm.py` y `src/nuevamente/agents/graph.py`
**Archivo de test:** `tests/test_generacion.py`

**Criterios de Aceptación Verificados:**
- [x] Funcionamiento 100% offline (sin llamadas a red) utilizando LLM_PROVIDER=template.
- [x] Inserción de la respuesta dentro de los esquemas Pydantic requeridos (JSON) listos para la interfaz.
- [x] Integridad del fallback automático garantizada frente a caídas de API.

**Evidencia de Ejecución:**
> pytest tests/test_generacion.py
> 9 passed in 8.90s
> Estado: APROBADO
