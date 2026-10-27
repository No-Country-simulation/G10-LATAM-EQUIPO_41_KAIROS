<div align="center">

<img src="src/nuevamente/web/logo-kairos.png" alt="Logo de Kairos" width="420">

# NuevaMente 🎓 — Kairos G10

**Sistema inteligente de adaptación y generación de contenido educativo**

Convierte un documento técnico en material de estudio personalizado (tutoriales, flashcards,
quizzes, resúmenes, videos y podcasts) y verifica cada afirmación contra la fuente.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](src/nuevamente/api/app.py)
[![LangGraph](https://img.shields.io/badge/Orquestación-LangGraph-FF6F00)](src/nuevamente/agents/graph.py)
[![Oracle Cloud](https://img.shields.io/badge/Cloud-Oracle_OCI-F80000?logo=oracle&logoColor=white)](docs/SETUP_OCI.md)
[![Docker](https://img.shields.io/badge/Docker-listo-2496ED?logo=docker&logoColor=white)](Dockerfile)
[![Tests](https://img.shields.io/badge/Tests-317%20passed-success?logo=pytest&logoColor=white)](#7-pruebas)
[![Deploy](https://img.shields.io/badge/Deploy-Render-46E3B7?logo=render&logoColor=white)](https://g10-latam-equipo-41-kairos.onrender.com/)
[![Versión](https://img.shields.io/badge/Versión-1.5-blueviolet)](src/nuevamente/__init__.py)

**[🌐 App en línea](https://g10-latam-equipo-41-kairos.onrender.com/)** ·
**[📖 Documentación de la API](https://g10-latam-equipo-41-kairos.onrender.com/docs)** ·
**[📋 Backlog en Jira](https://dielidube.atlassian.net/jira/software/projects/SCRUM/boards/1/backlog)** ·
**[📊 Paneles de seguimiento](#2-demo-y-enlaces-del-proyecto)** ·
**[💻 Repositorio](https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS)**

**Hackathon ONE G10** (Oracle Next Education & Alura) — Proyecto 1<br>
Equipo **Kairos G10** (G10-LATAM-equipo 41) · Nicho de foco: **Salud**

<img src="docs/pruebas/evidencias/pantallas/p01_inicio.jpg" alt="Interfaz web de NuevaMente" width="85%">

</div>

> [!IMPORTANT]
> ⚕️ El contenido que genera esta aplicación es material de apoyo educativo
> basado en la documentación que el usuario proporciona. **No reemplaza el
> criterio de un profesional de salud ni las indicaciones oficiales vigentes.**

---

## Índice

1. [Descripción general](#1-descripción-general)
2. [Demo y enlaces del proyecto](#2-demo-y-enlaces-del-proyecto)
3. [Arquitectura](#3-arquitectura)
4. [Decisiones de diseño](#4-decisiones-de-diseño)
5. [Instalación y puesta en marcha](#5-instalación-y-puesta-en-marcha)
6. [Uso](#6-uso)
7. [Pruebas](#7-pruebas)
8. [Seguridad y manejo responsable del nicho Salud](#8-seguridad-y-manejo-responsable-del-nicho-salud)
9. [Limitaciones conocidas](#9-limitaciones-conocidas)
10. [Estado del proyecto](#10-estado-del-proyecto)
11. [Estructura del repositorio](#11-estructura-del-repositorio)
12. [Evidencias y material de presentación](#12-evidencias-y-material-de-presentación)
13. [Equipo](#13-equipo)
14. [Créditos](#créditos)

---

## 1. Descripción general

Recibe un documento técnico (PDF, también escaneado mediante OCR con Gemini; Word .docx,
Markdown o texto), lo indexa con RAG, y lo
transforma en contenido educativo personalizado según:

- **Perfil del destinatario:** Principiante, Desarrollador Junior/Semi Senior,
  Líder Técnico/Arquitecto, Gestor/Ejecutivo.
- **Formato pedagógico:** Guía Práctica Paso a Paso (Tutorial), Flashcards de Memorización,
  Quiz Interactivo con Justificaciones, Resumen Ejecutivo (TL;DR), Guion de Clase / Video y
  Podcast (solo en audio). La API acepta tanto el nombre corto ("Tutorial") como el del enunciado.
- **Nicho/sector:** General, Fintech, Salud, E-commerce, Tecnología.
- **Nivel de detalle:** Conciso, Didáctico o Profundo.
- **Idioma de salida** (`idioma_salida`, por API): el material se redacta en el idioma pedido.

Cualquier resultado se puede descargar como **documento Word (.docx)**, **PDF didáctico**
o **presentación PowerPoint (.pptx)**, además de Markdown y CSV para Anki (botones
"📝 Word", "📄 PDF" y "📊 PowerPoint" en la interfaz, o
`GET /api/v1/contenidos/{objeto_id}/exportar?formato=docx|pdf|pptx&titulo=...`). Cada formato
tiene su propio diseño: tarjetas pregunta/respuesta, cada pregunta del quiz seguida
de su respuesta, un paso por diapositiva, puntos clave, y las escenas del guion con
la narración en las **notas del orador**.

El **Guion de Clase** además se puede convertir en un **video MP4 narrado**: una
diapositiva por escena con la narración en voz en off (botón "Generar video" en
la interfaz, o `GET /api/v1/contenidos/{objeto_id}/video`). El video y el podcast se generan en
segundo plano (ver [sección 6.3](#63-video-del-guion-de-clase-y-podcast)).

El **Podcast** es una conversación entre dos locutores: Ana conduce y pregunta,
y Leo explica lo que dice el documento. Se entrega **solo como audio MP3**, con
una voz distinta para cada uno: la interfaz lo graba al terminar y muestra el
reproductor (o `GET /api/v1/contenidos/{objeto_id}/podcast`). No se exporta a
Markdown, Anki ni PowerPoint. Las voces son **naturales, de Gemini TTS** (Ana: *Sulafat*,
cálida; Leo: *Charon*, clara), con tono pausado y claro; se configuran con
`PODCAST_VOCES`, `PODCAST_VOZ_ANA` y `PODCAST_VOZ_LEO`. Si Gemini TTS no está
disponible (sin cuota o sin red), el episodio se narra con las voces del sistema
y la interfaz lo indica. Solo se verifican contra la fuente
las intervenciones de Leo, que son las que llevan contenido del documento.

**Estadísticas de uso y experiencia de usuario:** debajo de cada material el usuario lo
califica de 1 a 5 estrellas y puede dejar un comentario. El panel
**http://localhost:8000/estadisticas** (botón "📊 Estadísticas" del menú, o
`GET /api/v1/estadisticas`) muestra los materiales creados por día, los formatos, perfiles,
sectores y tipos de archivo más usados, las descargas, la fidelidad media, la calificación
media y los últimos comentarios. Los eventos se guardan en `data/estadisticas/eventos.jsonl`
(`ESTADISTICAS_DIR`), sin el texto de ningún documento.

**Historial:** el menú "🕘 Historial" guarda en el navegador los últimos 8 materiales, con el
**documento de origen y su extensión** (📕 PDF · informe.pdf, 📘 Word · …, ✍️ Texto pegado) y un
buscador. La pestaña **Guardado** de cada material permite descargar el documento original.

Cada afirmación generada se **verifica contra el documento fuente** y se le
asigna un score de anclaje. Esto vale para los 6 formatos: en Resumen Ejecutivo
se verifica cada oración del resumen, en Guion de Clase cada escena y en Podcast cada intervención de Leo. Si un
resultado no trae afirmaciones con fuente, no se aprueba y su score es 0. Todo se guarda en OCI Object Storage (o en un
respaldo local si OCI no está configurado) y se expone por API REST y por una
interfaz web (HTML/CSS/JS, servida por la misma API en `http://localhost:8000/`).

## 2. Demo y enlaces del proyecto

| Recurso | Enlace |
|---|---|
| 🌐 Aplicación en línea (deploy en Render) | https://g10-latam-equipo-41-kairos.onrender.com/ |
| 📖 Documentación interactiva de la API | https://g10-latam-equipo-41-kairos.onrender.com/docs |
| 💻 Repositorio del proyecto (GitHub) | https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS |
| 🌿 Rama del sprint actual | https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS/tree/SPRINT05 |
| 📋 Backlog del proyecto (Jira) | https://dielidube.atlassian.net/jira/software/projects/SCRUM/boards/1/backlog |
| 📊 Panel de seguimiento 1 (Jira) | https://dielidube.atlassian.net/jira/dashboards/10001 |
| 📊 Panel de seguimiento 2 (Jira) | https://dielidube.atlassian.net/jira/dashboards/10002 |
| 📁 Documentación de Jira (actividades, casos de prueba, estadísticas y pruebas por sprint) | [`docs/jira/`](docs/jira/README.md) |

El seguimiento de las actividades se lleva en Jira, en el proyecto con clave `SCRUM`
(por ejemplo, SCRUM-21 a SCRUM-24).

> [!NOTE]
> La aplicación en línea usa el plan gratuito de Render: si estuvo inactiva, la primera
> carga puede tardar alrededor de un minuto mientras el servidor se reactiva.

## 3. Arquitectura

![Arquitectura de Kairos](docs/entregables/Arquitectura_Kairos.jpg)

En texto:

```
Documento (PDF/DOCX/MD/TXT)
        │
        ▼
   [Ingesta]  chunking con solapamiento + detección de secciones
        │
        ▼
[RAG]  embeddings semánticos de Gemini (gemini-embedding-001, 768 dim.)
       con TF-IDF local de respaldo + vector store propio, aislado por doc_id
        │
        ▼
[Orquestación]  grafo de LangGraph (StateGraph): Planificador → Investigador
                (por sección) → caché de material aprobado → Redactor (role
                prompting + few-shot) → Crítico (TF-IDF + juez de IA, con reintento)
        │
        ▼
[Persistencia]  OCI Object Storage (o fallback local en data/fallback/)
        │
        ▼
  API REST (FastAPI)  ──►  Interfaz web (src/nuevamente/web/)
```

### 3.1 Flujo de agentes

Es un `StateGraph` de LangGraph ([agents/graph.py](src/nuevamente/agents/graph.py)), un nodo por agente:

![Flujo de agentes de Kairos](docs/entregables/Flujo_Agentes_Kairos.jpg)

```mermaid
flowchart LR
    I[indexar<br/>chunking + embeddings] --> A[planificar]
    A --> B[investigar<br/>RAG por sección]
    B --> K{consultar_cache}
    K -- ya aprobado antes --> Z[respuesta desde caché]
    K -- no está --> C[redactar<br/>LLM + few-shot]
    C --> E{criticar<br/>TF-IDF + juez de IA}
    E -- score < umbral y quedan reintentos --> C
    E -- aprobado / sin mejora --> F[finalizar<br/>metadatos + OCI]
```

## 4. Decisiones de diseño

> Recomendado leerlo antes de evaluar el código.

El pipeline es **100% real y ejecutable** también sin servicios en la nube: cada
pieza externa tiene una alternativa local con la misma interfaz, y la app usa la
local cuando la externa no está configurada o falla.

| Pieza | Sin credenciales / respaldo | Con credenciales |
|---|---|---|
| Embeddings | `LocalTfidfEmbeddings` (scikit-learn, sin red), también respaldo si Gemini falla | `GeminiEmbeddings` (`gemini-embedding-001`, semánticos, `EMBEDDINGS_PROVIDER=auto`) |
| Vector store | Store propio en numpy, aislado por `doc_id` (`VECTOR_STORE=local`) | ChromaDB persistente (`VECTOR_STORE=chroma`), misma interfaz `buscar`/`buscar_por_seccion` |
| LLM generador | `TemplateLLM` (extractivo, determinista), también respaldo si el LLM falla (`LLM_RESPALDO_LOCAL`) | `GeminiLLM` (`LLM_PROVIDER=gemini`, con modelos de respaldo) o `ClaudeLLM` (`LLM_PROVIDER=claude`) — misma interfaz `LLMClient` |
| Juez de fidelidad | Similitud TF-IDF contra el chunk citado | TF-IDF + juez de IA con citas textuales verificadas y coherencia didáctica (`JUEZ_IA=auto`) |
| Orquestación | `StateGraph` de LangGraph con reintento (igual en ambos casos) | — |
| OCI Object Storage | Fallback a `data/fallback/` si no hay credenciales o OCI rechaza la subida | Cliente real vía `oci` SDK (requiere `~/.oci/config` y la llave de API registrada en la consola) |
| Caché de contenido | Desactivado por defecto (`CACHE_CONTENIDO_ACTIVADO=false`) | Material ya aprobado se devuelve sin llamar al LLM (`cache/contenido.py`) |

**Importante:** esto no es una simulación con datos falsos. El pipeline corre
de principio a fin sobre el documento real que se le da, indexa contenido
real, recupera evidencia real y verifica fidelidad real contra esa evidencia.
Lo que cambia entre este entorno y producción es *qué tan sofisticado* es el
componente de generación/embeddings, no si el flujo funciona.

## 5. Instalación y puesta en marcha

### 5.1 Inicio rápido

Con `make` (requiere Python 3.10 o superior):

```bash
cp .env.example .env     # y completa las claves que vayas a usar
make install
make run-api             # → http://localhost:8000/
```

O con Docker Compose, en un solo paso (ver [5.5](#55-docker-compose)):

```bash
docker compose up -d --build   # → http://localhost:8000/
```

Sin ninguna clave, la aplicación funciona igual con las alternativas locales
(ver [Decisiones de diseño](#4-decisiones-de-diseño)).

### 5.2 Instalación paso a paso

Requiere Python 3.10 o superior. Se recomienda un entorno virtual:

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
cp .env.example .env
```

Los comandos habituales están en el `Makefile` (ejecutar desde la raíz del repo):

| Comando        | Qué hace                                                                 |
|----------------|--------------------------------------------------------------------------|
| `make install` | Instala el paquete en modo editable con extras `dev`, `ui` y `gemini`     |
| `make test`    | Corre los tests (317 pruebas, deben pasar todas; ver [sección 7](#7-pruebas))           |
| `make run-api` | Levanta la API y la interfaz web en http://localhost:8000/                |
| `make run-ui`  | (Opcional) Levanta la interfaz Streamlit anterior                         |
| `make demo`    | Ejecuta los 3 escenarios de demo (Salud, B2B) y guarda evidencia          |
| `make requirements` | Regenera `requirements.txt` con las versiones instaladas en el `.venv` |

Antes del primer commit, instala la revisión de secretos: `python scripts/revisar_secretos.py --instalar`. Bloquea el commit si encuentra llaves o archivos `.pem`/`.env`; GitHub Actions corre la misma revisión y las pruebas en cada push y pull request.

Equivalentes sin `make`:

```bash
# 1. Instalar el paquete y dependencias
pip install -e ".[dev,ui,gemini]"
# (o versiones fijadas: pip install -r requirements.txt)
# Tras cambiar dependencias en pyproject.toml, regenerar las versiones fijadas:
#   pip install -e ".[dev,oci,gemini,claude,ui,openai]" && python scripts/generar_requirements.py

# 2. Correr los tests
pytest tests/ -v

# 3. Levantar la API y la interfaz web (un solo proceso)
uvicorn nuevamente.api.app:app --reload
# Interfaz:                  http://localhost:8000/
# Documentación de la API:   http://localhost:8000/docs

# 4. (Opcional) la interfaz Streamlit anterior sigue disponible
streamlit run ui/app.py

# 5. Ejecutar los 3 escenarios de demo y guardar evidencia en docs/demo/resultados/
python scripts/run_demo.py
```

Extras opcionales de `pyproject.toml`: `claude` (Anthropic), `oci` (OCI Object Storage) y
`chroma` (ChromaDB), por ejemplo `pip install -e ".[claude,oci]"`.

> Las rutas de datos (`data/vectorstore`, `data/fallback`, `data/videos`, `data/estadisticas`) son relativas al
> directorio desde donde se ejecuta el comando: correr todo desde la raíz del repo.

### 5.3 Variables de entorno

Copia `.env.example` a `.env`. Se carga al importar `nuevamente.config`: primero el
`.env` del directorio actual y luego el de la raíz del repo. Las variables ya
exportadas en la terminal tienen prioridad sobre las del archivo.

Las más usadas (la lista completa y comentada está en `.env.example`):

```env
# "template" (sin red) | "gemini" | "claude" | "groq" | "cerebras" | "openrouter" | "cohere" | "openai" | "auto" (cadena)
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.7-flash
LLM_MODELOS_RESPALDO=gemini-3.5-flash,gemini-3.6-flash,gemini-3-flash-preview,gemini-flash-latest
GEMINI_API_KEY=                  # https://aistudio.google.com/apikey
GROQ_API_KEY=                    # https://console.groq.com/keys
CEREBRAS_API_KEY=                # https://cloud.cerebras.ai
OPENROUTER_API_KEY=              # https://openrouter.ai/keys
COHERE_API_KEY=                  # https://dashboard.cohere.com/api-keys
OPENAI_API_KEY=                  # https://platform.openai.com/api-keys (de pago)
ANTHROPIC_API_KEY=               # https://platform.claude.com/settings/keys (con LLM_PROVIDER=claude)
CLAUDE_MODEL=claude-opus-5
EMBEDDINGS_PROVIDER=auto        # Gemini si hay API key, con TF-IDF local de respaldo | local
VECTOR_STORE=local               # local | chroma
JUEZ_IA=auto                     # juez de fidelidad con IA | off (solo TF-IDF)
OCR=auto                         # OCR de PDF escaneados con Gemini | off
FIDELITY_MIN_GENERAL=0.85
FIDELITY_MIN_SALUD=0.90          # umbral reforzado para el nicho Salud
OCI_CONFIG_FILE=~/.oci/config
OCI_BUCKET=nuevamente-contenidos-educativos
OCI_SSL_VERIFY=true              # false solo tras un proxy/antivirus que intercepte HTTPS (solo afecta a OCI)
VIDEO_VOCES=gemini               # gemini (voz natural) | sistema
VIDEO_HILOS=1                    # hilos de ffmpeg: 1 = menos memoria
CACHE_CONTENIDO_ACTIVADO=false   # caché de material aprobado (ahorra cuota del LLM)
```

<details>
<summary><b>Rotación de modelos y de APIs</b> (qué pasa cuando un proveedor se queda sin cuota)</summary>

Hay dos niveles, porque los dos problemas son distintos:

| Nivel | Dónde | Qué resuelve |
|---|---|---|
| Modelos de la misma API | `llm/rotacion.py` | Un 429 o un 5xx en un modelo concreto. Reintenta con backoff y, si ese modelo no tiene cuota, pasa al siguiente de `LLM_MODELOS_RESPALDO`. |
| APIs distintas | `llm/cadena_llm.py` | La cuota diaria de una cuenta se agotó. `LLM_PROVIDER=auto` cae a la siguiente API de `LLM_CADENA`. |

Lo segundo es lo que evita que la generación se corte: todos los modelos de Gemini
comparten la cuota de tu cuenta, así que cuando se agota no ayuda a añadir más modelos
de Gemini, hace falta otra clave. Groq, Cerebras y OpenRouter tienen plan gratuito y
cuotas independientes entre sí y de Google AI Studio.

```env
LLM_PROVIDER=auto
LLM_CADENA=gemini,groq,cerebras,openrouter
```

Solo hay que poner las claves de las APIs que quieras usar: un proveedor sin `*_API_KEY`
en el `.env` se salta solo, sin romper la cadena. Los proveedores con plan gratuito:

| Proveedor | Modelos gratuitos por defecto | Dónde sacar la key |
|---|---|---|
| Gemini | `gemini-3.7-flash` + los de `LLM_MODELOS_RESPALDO` (cada uno con su cuota diaria) | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| Groq | `openai/gpt-oss-120b`, `openai/gpt-oss-20b` | [console.groq.com/keys](https://console.groq.com/keys) |
| Cerebras | `gpt-oss-120b`, `qwen-3.8-27b` | [cloud.cerebras.ai](https://cloud.cerebras.ai) |
| OpenRouter | `openrouter/free` (elige entre los `:free` que soportan salidas estructuradas) | [openrouter.ai/keys](https://openrouter.ai/keys) |
| Cohere | `command-a-plus-05-2026`, `command-a-03-2025`, `command-r-plus-08-2024` (clave de prueba gratuita) | [dashboard.cohere.com/api-keys](https://dashboard.cohere.com/api-keys) |

OpenAI también está disponible (`OPENAI_API_KEY`, modelos `gpt-4.1-mini` y `gpt-4o-mini`), pero
es **de pago**: conviene ponerlo al final de `LLM_CADENA`, como último respaldo.

Los proveedores de la tabla se hablan con un único cliente (`llm/openai_compat_llm.py`),
porque todos exponen la misma API `chat/completions` (Cohere, a través de su endpoint de compatibilidad). No hace falta instalar nada
extra: usa el SDK `openai` si está presente y, si no, habla HTTP con `httpx`, que ya es
dependencia del proyecto. Solo Gemini necesita su SDK (`pip install -e ".[gemini]"`).

Los límites de los planes gratuitos cambian con frecuencia; se pueden cambiar los modelos
por proveedor sin tocar código con `LLM_MODELOS_GROQ`, `LLM_MODELOS_CEREBRAS`,
`LLM_MODELOS_OPENROUTER`, `LLM_MODELOS_COHERE` y `LLM_MODELOS_OPENAI`.

</details>

### 5.4 Docker

Con Docker (la misma imagen que se usa para desplegar, ver [docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md)):

```bash
docker build -t kairos .
docker run -p 8000:8000 -e GEMINI_API_KEY=... kairos   # http://localhost:8000/
```

### 5.5 Docker Compose

El repositorio incluye lo necesario para levantar la aplicación con Docker Compose, a partir
del código del repo y de sus actualizaciones. Se probó en local y responde a las consultas.

| Archivo | Para qué sirve |
|---|---|
| [`compose.yaml`](https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS/blob/main/compose.yaml) | Define el servicio (API + interfaz web), el volumen de datos y la configuración de OCI |
| [`compose_comandos_kairos.md`](https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS/blob/main/compose_comandos_kairos.md) | Lista de comandos para manejar Docker Compose (levantar, ver logs, actualizar, detener) |
| [`compose_checklist.md`](https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS/blob/main/compose_checklist.md) | Comprobaciones para verificar que el contenedor quedó bien montado y sano |

```bash
docker compose up -d --build   # construir y levantar → http://localhost:8000/
docker compose logs -f         # ver los logs en vivo
docker compose ps              # ver el estado y la salud
docker compose down            # detener (los datos se conservan)
```

> Requisitos: el `.env` en la raíz del repo y `oci_config` (con su llave `.pem`) en la carpeta
> padre del repo, como indica `compose.yaml`.

### 5.6 Despliegue

| Destino | Estado | Guía |
|---|---|---|
| Render (Docker, plan gratuito) | ✅ En línea: https://g10-latam-equipo-41-kairos.onrender.com/ | [docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md) · [`render.yaml`](render.yaml) |
| Railway / Fly.io / cualquier VM | Misma imagen de Docker | [docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md) |
| OCI Compute (VM Always Free) | Script, systemd y nginx listos; falta crear la instancia | [docs/DEPLOY_OCI.md](docs/DEPLOY_OCI.md) · [`deploy/`](deploy/) |

Ver también `docs/SETUP_OCI.md` para crear la cuenta OCI Always Free, el
bucket privado y las claves API paso a paso, y `python scripts/test_oci_conexion.py` para
comprobar una subida real al bucket.

## 6. Uso

### 6.1 API REST

```bash
curl -X POST http://localhost:8000/api/v1/adaptar \
  -H "Content-Type: application/json" \
  -d '{
    "documento_titulo": "Protocolo de bioseguridad",
    "documento_contenido": "El lavado de manos con agua y jabón durante al menos 20 segundos elimina la mayoría de los microorganismos de las manos.",
    "perfil_destinatario": "Principiante",
    "formato_salida": "Flashcards",
    "nicho_sector": "Salud"
  }'
```

Otros endpoints útiles: `POST /api/v1/adaptar/archivo` (multipart, con el archivo),
`GET /api/v1/opciones` (perfiles, formatos, sectores, niveles, voces, extensiones y versión),
`GET /api/v1/contenidos/{objeto_id}` (recuperar un material), `.../exportar?formato=docx|pdf|pptx|markdown|anki_csv`,
`.../original` (documento original), `GET /health` y `GET /api/v1/estadisticas`.
La documentación interactiva completa está en `/docs`.

### 6.2 Escenarios de demo (Salud, casos de uso B2B)

Ejecutados por `scripts/run_demo.py` sobre `docs/demo/protocolo_bioseguridad_salud.md`
(documento original del equipo, de dominio general, sin datos de pacientes):

| # | Caso de uso empresarial | Perfil | Formato |
|---|---|---|---|
| 1 | Onboarding de personal clínico nuevo | Principiante | Flashcards |
| 2 | Capacitación regulatoria interna | Desarrollador Junior/Semi Senior | Quiz |
| 3 | Actualización de protocolos ante auditoría | Gestor/Ejecutivo | Resumen Ejecutivo |

Resultados (JSON, Markdown, PDF y CSV de Anki) en `docs/demo/resultados/`; se regeneran con
`make demo`, que además guarda cada paquete y el documento original con el mismo servicio de
almacenamiento que la API y anota su `status_upload`.

Última ejecución, con **Gemini** como LLM y como embeddings (`gemini-3-flash-preview`, `gemini-embedding-001`)
y el **juez de IA** activo:

| # | Fidelidad | Crítico |
|---|---:|---|
| 1 · Flashcards | 1,00 | ✅ Aprobado (umbral Salud 0,90) |
| 2 · Quiz | 1,00 | ✅ Aprobado |
| 3 · Resumen Ejecutivo | 0,92 | ✅ Aprobado: las oraciones de síntesis se validan con citas textuales verificadas |

Si algún escenario sale del generador local (Gemini sin cuota), `make demo` no sobrescribe la
evidencia; con `python scripts/run_demo.py --permitir-respaldo` se acepta igual.

### 6.3 Video del Guion de Clase y podcast

- Las diapositivas se dibujan con Pillow y ffmpeg arma el MP4 (H.264 + AAC, 1280×720).
  Se usa el ffmpeg del sistema y, si no hay, el que trae el paquete `imageio-ffmpeg`.
- **Voz femenina o masculina**, a elección en la interfaz (con botón para escuchar una
  muestra) o con `?voz=femenina|masculina` en la API. Por defecto son **voces naturales de
  Gemini TTS** (`VIDEO_VOZ_FEMENINA=Sulafat`, `VIDEO_VOZ_MASCULINA=Charon`; otras voces
  masculinas: *Orus*, *Iapetus*, *Algieba*). Cada escena es **una solicitud con solo su
  texto**, sin indicaciones de estilo, y del audio se toma solo el sonido (sin cabecera ni
  metadatos), para que no haya ruido al cambiar de diapositiva. Si Gemini no está
  disponible y hay `OPENAI_API_KEY`, se narra con las **voces naturales de OpenAI TTS**
  (`gpt-4o-mini-tts`; `VIDEO_VOZ_OPENAI_MASCULINA=ash`, `VIDEO_VOZ_OPENAI_FEMENINA=coral`);
  es de pago (unos 0,015 USD por minuto de audio). Con `VIDEO_VOCES=openai` se usa OpenAI
  sin esperar a Gemini. Si tampoco está disponible, se usa el respaldo **"sistema"**: `say`
  en macOS; si no está, las **voces neuronales gratuitas de Microsoft Edge** (`edge-tts`,
  sin API key ni cuota diaria: `VIDEO_VOZ_EDGE_FEMENINA=es-MX-DaliaNeural`,
  `VIDEO_VOZ_EDGE_MASCULINA=es-MX-JorgeNeural`; `EDGE_TTS=off` lo apaga), que es lo que da
  voz al video y al podcast en Render; y si Edge no responde, `espeak-ng` en Linux. Siempre
  el video completo con la misma voz. Si ninguna voz puede narrar, la API responde con un
  error claro en lugar de entregar un video mudo; con `VIDEO_TTS=off` cada escena se muestra
  en silencio.
  `X-Video-Voces` indica con qué se narró ("gemini", "openai" o "sistema").
- **Cuota de Gemini TTS:** el plan gratuito da **10 solicitudes por día y por modelo**. Si
  un modelo se queda sin cuota se pasa al siguiente (`PODCAST_TTS_MODEL` y luego
  `TTS_MODELOS_RESPALDO`, por defecto `gemini-3.8-flash-tts,gemini-2.5-flash-preview-tts,
  gemini-3.8-flash-lite-tts`), tanto para el video como para el podcast.
- **Solo datos del documento:** el video tiene una portada en silencio con el título del
  documento y, en cada diapositiva, la sección de la que sale la escena y su narración. No se
  agregan saludos, transiciones ni despedidas, y las indicaciones de apoyo visual del guion
  no se muestran ni se leen.
- **Lectura natural** (`exports/narracion.py`): antes de leer, el texto se adapta
  para la voz (fechas en palabras, abreviaturas expandidas, siglas deletreadas, sin
  restos de tablas ni Markdown); el ritmo es algo más pausado, con silencios entre
  oraciones; el volumen se normaliza y las diapositivas entran y salen con
  un fundido.
- Para una voz todavía más natural en macOS, descarga una versión **mejorada** o
  **premium** (por ejemplo "Paulina (mejorada)" o "Juan (mejorada)") en *Ajustes del
  Sistema → Accesibilidad → Contenido leído → Voz del sistema → Gestionar voces*.
  Kairos la prefiere automáticamente sobre la versión básica.
- El video se genera la primera vez que se pide y queda en caché en `data/videos/`.
  Un guion de 12 escenas tarda entre 1,5 y 3 minutos (según la voz).
- **En segundo plano y con poca memoria**, para servidores pequeños: con `?asincrono=1`
  (lo usa la interfaz) el video y el podcast responden `202` mientras se generan y la interfaz
  vuelve a pedirlos cada 3 s, sin dejar una conexión abierta minutos. Se genera un archivo
  pesado a la vez y ffmpeg usa un hilo (`VIDEO_HILOS=1`), dentro de los 512 MB del plan
  gratuito de Render.
- **Poca CPU** (Render free da 0,1 CPU): el video sale a 10 cuadros por segundo, cada
  diapositiva se decodifica una sola vez, x264 usa `ultrafast` y el audio va en mono a 96 kbps
  con `dynaudnorm`. En un guion de 12 escenas, ffmpeg pasó de 78 s de CPU a 16 s y su pico
  de memoria de 219 MB a 41 MB, sin cambiar cómo se ve ni cómo suena.

## 7. Pruebas

El proyecto tiene **317 pruebas automatizadas** (pytest). Corren sin red ni credenciales:
usan el generador local (`LLM_PROVIDER=template`), el respaldo local de almacenamiento y
voces simuladas, así que dan el mismo resultado en cualquier máquina.

### 7.1 Cómo ejecutarlas

```bash
pip install -e ".[dev]"
pytest -q                          # todas (≈20 s)
pytest tests/test_api.py -q        # un archivo
pytest -q -k enunciado             # solo las que contienen "enunciado" en el nombre
```

Resultado esperado: `317 passed`.

![Pruebas automatizadas por archivo: 295 de 295 aprobadas](docs/pruebas/evidencias/graficos/grafico_pruebas_por_archivo.svg)

### 7.2 Qué cubre cada archivo

<details>
<summary>Ver las 317 pruebas por archivo</summary>

| Archivo | Pruebas | Qué verifica |
|---|---:|---|
| `tests/test_api.py` | 82 | Endpoints REST: los 6 formatos con distintos perfiles, la **solicitud exacta del enunciado** (con `"Didactico"` sin tilde), que la respuesta tenga **exactamente** las claves del ejemplo, guardar y recuperar un material, validación de entrada (422), subida de archivo .docx, formato no compatible, archivo demasiado grande (413), exportación a Markdown, Anki, Word, PDF y PowerPoint, video MP4 del Guion (también en segundo plano), podcast MP3, **cancelar un video en generación**, nombres de formato del enunciado, archivo original (también su descarga), respaldo local si OCI falla a mitad de la subida, `/docs` con sus esquemas, versión, namespace de OCI y tipo de documento de origen |
| `tests/test_llm_rotacion.py` | 45 | Rotación de modelos y de claves de Gemini, y la cadena de proveedores (Gemini → Groq → Cerebras → OpenRouter) cuando uno se queda sin cuota |
| `tests/test_llm_salud.py` | 28 | Enrutado por salud de los proveedores: circuit breaker, orden por latencia y carrera entre proveedores |
| `tests/test_generacion.py` | 15 | Flujo completo de agentes: fidelidad de los formatos de síntesis, reintento del Crítico, nivel de detalle, agrupación por sección, la portada no llega al Redactor y la evidencia cubre todo el documento |
| `tests/test_estadisticas.py` | 9 | Estadísticas de uso: generar, descargar y calificar se reflejan en el resumen, recalificar reemplaza la calificación anterior, tipo de archivo subido, validación de estrellas (422), material inexistente (404), la página `/estadisticas`, tolerancia a una línea dañada e importación del historial |
| `tests/test_ingest.py` | 26 | Lectura y chunking: secciones por títulos, PDF con títulos fuera de orden, Word (.docx) con títulos y tablas, texto pegado sin saltos de línea, limpieza de índices, avisos legales, contactos y encabezados/pies de PDF, títulos en dos líneas, siglas y nombres propios, OCR de PDF escaneados y extracción de **conceptos clave** de un texto sin títulos |
| `tests/test_schemas.py` | 7 | Esquemas Pydantic de cada formato y limpieza de referencias internas (los `chunk_id` no aparecen en el texto que ve el estudiante) |
| `tests/test_prompts.py` | 21 | Role prompting y ejemplos few-shot: cada ejemplo cumple el esquema de su formato y enseña a citar la fuente |
| `tests/test_embeddings.py` | 5 | Embeddings: si Gemini falla al indexar o en una consulta, la colección entera pasa a TF-IDF (sin mezclar vectores) |
| `tests/test_grafo.py` | 4 | Grafo de LangGraph: un nodo por agente y el ciclo Crítico → Redactor con retroalimentación |
| `tests/test_cache_contenido.py` | 7 | Caché de contenido aprobado (Ethan): acierto en la segunda generación, alcance Resumen Ejecutivo + Salud, la clave cambia con la evidencia y las opciones, y el endpoint de estadísticas |
| `tests/test_juez.py` | 5 | Juez de IA: solo aprueba con citas que existen en el documento, una síntesis necesita que todas sus citas existan, y la coherencia didáctica |
| `tests/test_fidelity.py` | 5 | Verificador de fidelidad: afirmaciones sustentadas, parciales e inventadas |
| `tests/test_narracion.py` | 19 | Narración: lectura natural, voz de Gemini con respaldo del sistema sin mezclar voces, audio de Gemini sin cabecera ni metadatos (sin ruido entre diapositivas), reintento de la voz natural en pausa, aviso si ninguna voz narra, respaldo con Edge TTS (y su pausa si falla), rotación de modelos TTS y **video sin introducción hablada** (la voz solo lee las escenas) |
| `tests/test_titulos.py` | 18 | **Títulos, subtítulos y texto en Markdown y PDF**: niveles `#` a `######`, títulos numerados con guion (`1 - Objetivos`), títulos subrayados, comentarios dentro de bloques de código; en PDF, títulos por tamaño de letra, negrita, marcadores y títulos en dos renglones; y los documentos reales de `docs/pruebas/documentos/` |
| `tests/test_depuracion.py` | 4 | Eliminación de partes duplicadas en el material generado |
| `tests/test_disponibilidad.py` | 4 | Pausa de un servicio que acaba de fallar, para no esperarlo en cada solicitud |
| `tests/test_vectorstore.py` | 5 | Indexación y búsqueda por similitud en el vector store, y ChromaDB con los mismos resultados |
| `tests/test_resumen.py` | 2 | Partes del Resumen Ejecutivo (idea central, puntos clave, riesgos y recomendaciones) para exportarlo |
| `tests/test_env_example.py` | 2 | Toda variable de entorno que lee el código está documentada en `.env.example`, y las llaves van vacías |
| `tests/test_revisar_secretos.py` | 1 | El revisor de secretos detecta llaves y archivos de credenciales sin imprimirlas |
| `tests/test_security.py` | 3 | Resistencia a instrucciones inyectadas en el documento y que todo lo generado cite un chunk real, y que el módulo de OCI no desactive la verificación TLS del proceso |

</details>

### 7.3 Prueba manual con la solicitud del enunciado

Con la API en marcha (`make run-api`), la solicitud de ejemplo del enunciado, tal cual:

```bash
curl -X POST http://localhost:8000/api/v1/adaptar \
  -H "Content-Type: application/json" \
  -d '{
    "documento_titulo": "Introduccion a la Arquitectura de Redes VCN en OCI",
    "documento_contenido": "La Virtual Cloud Network (VCN) es una red privada y personalizable configurada en Oracle Cloud Infrastructure. Similar a una red de centro de datos tradicional, la VCN ofrece control total sobre su entorno de red, incluyendo subredes publicas y privadas, tablas de enrutamiento, Internet Gateways, NAT Gateways y Security Lists para control de trafico mediante reglas de entrada (ingress) y salida (egress).",
    "perfil_destinatario": "Principiante",
    "formato_salida": "Flashcards",
    "nicho_sector": "General",
    "nivel_detalle": "Didactico"
  }'
```

Responde `200` con la misma forma que el ejemplo del enunciado (el texto de las tarjetas
varía según el modelo que las genere):

```json
{
  "status": "exito",
  "metadatos": {
    "perfil_aplicado": "Principiante",
    "formato_generado": "Flashcards",
    "tiempo_estimado_estudio_minutos": 1,
    "conceptos_clave": ["VCN", "Oracle Cloud Infrastructure", "Internet Gateways", "NAT Gateways", "Security Lists"]
  },
  "contenido_adaptado": {
    "titulo": "…",
    "introduccion_contextualizada": "…",
    "items": [
      { "frente": "…", "dorso": "…", "pista_didactica": "…" }
    ]
  },
  "evaluacion_calidad": {
    "anclaje_fuente_score": 1.0,
    "claridad_pedagogica": "Alta",
    "observaciones": "Lenguaje ajustado con explicaciones simples y analogías para público principiante, sin tecnicismos excesivos. Aprobado por el Crítico dentro del umbral de fidelidad."
  },
  "almacenamiento_oci": {
    "bucket": "nuevamente-contenidos-educativos",
    "objeto_id": "contenidos/<doc_id>/flashcards-principiante-<id>.json",
    "status_upload": "completado"
  }
}
```

`status_upload` es `"completado"` cuando OCI Object Storage está configurado y
`"fallido_local"` cuando el material se guardó en el respaldo local (`data/fallback/`).
Esta misma solicitud está automatizada en `test_solicitud_exacta_del_enunciado`.

## 8. Seguridad y manejo responsable del nicho Salud

- El documento de demo es contenido original del equipo, de carácter general,
  **sin datos de pacientes** y sin indicaciones de dosificación de medicamentos.
- El umbral de fidelidad para Salud es más estricto (0.90) que el general (0.85).
- La interfaz muestra un aviso visible cuando el nicho seleccionado es Salud.
- La interfaz web inserta todo el texto del documento como texto, nunca como HTML,
  así que un documento con etiquetas o scripts no puede ejecutar código en el navegador.
- El contenido del documento se trata siempre como **datos**, nunca como
  instrucciones (ver `tests/test_security.py`).

## 9. Limitaciones conocidas

### 9.1 Juez de fidelidad

- El primer filtro es la similitud TF-IDF contra el fragmento citado. Con un LLM real, un **juez
  de IA** (`JUEZ_IA=auto`) revisa solo las afirmaciones dudosas, viendo el fragmento citado y los
  más cercanos por significado, y en la misma solicitud evalúa la **coherencia didáctica**. Solo
  puede dar por sustentada una afirmación si devuelve citas que **existen textualmente** en esos
  fragmentos (se comprueba en código). Con el generador local queda solo el TF-IDF.

### 9.2 Cuotas gratuitas de Gemini

- El plan gratuito limita las solicitudes por día y por modelo (texto, embeddings y TTS por
  separado). La app rota entre modelos y, si se agotan todos, usa el respaldo local (TF-IDF,
  generador local o voces del sistema) y lo indica; muchas pruebas seguidas agotan la cuota.

### 9.3 Generador local (`TemplateLLM`)

- Es extractivo: no traduce. `idioma_salida` funciona con un LLM real (Gemini); con el
  generador local el material sale en el idioma del documento.
- Es determinista: ignora la retroalimentación del Crítico, por eso el flujo corta
  los reintentos cuando el resultado sale idéntico al intento anterior.
- En el Quiz, los distractores son oraciones reales de *otras* secciones del
  documento; la correcta es la que corresponde a la sección que nombra la pregunta.

## 10. Estado del proyecto

**16 de 18** puntos del enunciado completados. Pendientes: verificar OCI Object Storage
(falta registrar la llave de API en la consola) y crear la instancia de OCI Compute.

<details>
<summary>Ver el checklist completo del enunciado</summary>

- [x] Ingesta funcional de PDF, Word (.docx), Markdown y texto
- [x] RAG con chunking, embeddings semánticos (Gemini, con TF-IDF de respaldo) y búsqueda vectorial
- [x] Orquestación con LangGraph (Planificador → Investigador → Redactor → Crítico, con reintento)
- [x] Prompts con role prompting y ejemplos few-shot por formato (validados contra su esquema)
- [x] Juez de fidelidad con IA (citas verificadas) y evaluación de coherencia didáctica
- [x] ChromaDB como vector store opcional (`VECTOR_STORE=chroma`)
- [x] OCR de PDF escaneados con Gemini (`OCR=auto`)
- [x] Adapta el mismo contenido a los 4 perfiles y los 6 formatos (probado en `tests/test_api.py`)
- [x] Salida JSON estructurada, interfaz web propia + API REST operativa
- [x] Orquestación con LLM real: Google Gemini (`GeminiLLM`), con Claude como alternativa
- [ ] Integración con OCI Object Storage **verificada**: cliente, SDK, `~/.oci/config` y la llave
      de API (`~/.oci/oci_api_key.pem`) están listos, pero OCI responde `401 NotAuthenticated`
      hasta registrar la llave pública en la consola (*My profile → API keys*); mientras tanto
      todo cae al respaldo local (`status_upload: "fallido_local"`). Ver `docs/SETUP_OCI.md`
- [x] Verificación de fidelidad con score y afirmaciones no sustentadas
- [x] 3 ejemplos de ejecución reales con Gemini, documentados como casos de uso B2B en Salud
- [x] Exportación multiformato: Markdown, Anki (CSV), Word, **PDF didáctico** y PowerPoint
- [x] Caché de material aprobado (opcional) para ahorrar cuota del LLM
- [x] Tests automatizados (295), incluida seguridad ante inyección de instrucciones
- [ ] Despliegue en OCI Compute: script, servicio systemd, nginx y guía listos en `deploy/` y
      [docs/DEPLOY_OCI.md](docs/DEPLOY_OCI.md); falta crear la instancia en la cuenta de OCI
- [x] Despliegue alternativo con Docker en Render (plan gratuito), Railway o Fly.io:
      `Dockerfile`, `render.yaml` y guía en [docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md).
      En línea: https://g10-latam-equipo-41-kairos.onrender.com/

</details>

## 11. Estructura del repositorio

```
nuevamente/
├── src/nuevamente/
│   ├── __init__.py        # versión de la app (1.N = Sprint N)
│   ├── config.py
│   ├── estadisticas.py    # estadísticas de uso y calificaciones
│   ├── schemas/        # enums, request, response, formatos (Ethan)
│   ├── ingest/          # lectores + chunking (Gaspar)
│   ├── rag/             # embeddings + vector store (Gaspar)
│   ├── llm/              # LLMClient, TemplateLLM, rotación, cadena y fábrica (Darío)
│   ├── agents/           # orquestación de agentes (Ethan)
│   ├── fidelity/         # verificación de fidelidad y juez de IA (Darío)
│   ├── cache/            # caché de material aprobado (Ethan)
│   ├── storage/          # cliente OCI + fallback (Ethan/Gaspar)
│   ├── exports/          # Markdown, Anki, Word, PDF, PowerPoint, video MP4, podcast y narración (Dario)
│   ├── api/              # FastAPI (Ethan)
│   └── web/              # Interfaz web y panel de estadísticas (Dario)
├── ui/app.py              # Interfaz Streamlit anterior (opcional)
├── scripts/
│   ├── oci_bootstrap.py   # crea/verifica el bucket OCI
│   ├── test_oci_conexion.py  # prueba una subida real al bucket (Gaspar)
│   ├── generar_requirements.py
│   └── run_demo.py        # corre los 3 escenarios de Salud
├── tests/                  # 317 pruebas (Diana)
├── deploy/                 # instalación en OCI Compute: script, systemd y nginx
├── docs/
│   ├── SETUP_OCI.md       # cuenta, bucket y claves de OCI
│   ├── DEPLOY_OCI.md      # despliegue en una VM Always Free de OCI
│   ├── DEPLOY_RENDER.md   # despliegue con Docker en Render (u otro servidor)
│   ├── entregables/       # informes e historias de usuario (v2.0)
│   ├── jira/              # documentación de Jira por sprint: actividades, casos de prueba, estadísticas y pruebas
│   ├── pruebas/
│   │   ├── documentos/    # documentos de prueba (PDF, Markdown, Word) del sprint
│   │   └── evidencias/    # capturas y gráficos de las pruebas realizadas (sección 12)
│   └── demo/
│       ├── protocolo_bioseguridad_salud.md
│       └── resultados/
├── pyproject.toml         # paquete instalable (pip install -e .)
├── requirements.txt       # dependencias fijadas
├── Makefile               # install / test / run-api / run-ui / demo
├── Dockerfile             # imagen para Render, Railway, Fly.io o cualquier VM
├── compose.yaml           # Docker Compose para levantar la app en local
├── compose_comandos_kairos.md  # comandos para manejar Docker Compose
├── compose_checklist.md   # comprobaciones del contenedor
├── render.yaml            # blueprint de Render (plan gratuito)
├── .env.example
└── README.md
```

**Versionado:** la versión sigue el sprint (1.N = Sprint N; hoy **1.5**). Se define en
`src/nuevamente/__init__.py` y se muestra en el pie de la interfaz y en `/health`.

## 12. Evidencias y material de presentación

Cada entrega del sprint se presenta con la misma estructura: **qué cambió**, **cómo se
comprueba** y **dónde está la evidencia**. Las entregas de esta sección se presentaron en el Sprint 4.

### 12.1 Video sin introducción de prueba de voz

**Qué cambió.** El video del Guion de Clase ya no abre con el saludo hablado («Hola, te doy
la bienvenida…»), que sonaba como una prueba de voz, ni agrega transiciones («Sigamos.») o
despedida. Ahora contiene solo datos del documento:

| Parte del video | Imagen | Voz |
|---|---|---|
| Portada (3 s) | Título del documento | En silencio |
| Una diapositiva por escena | Sección del documento de la que sale la escena + su texto | Solo la narración de la escena |

La muestra del botón **🔊 Escuchar** sigue disponible en la interfaz para elegir la voz,
pero no forma parte del video. Los videos guardados con la versión anterior se regeneran
solos (`VERSION = 8` en `exports/video.py`).

**Cómo se comprueba.** `pytest tests/test_narracion.py -k introduccion` verifica que la voz
recibe únicamente el texto de las escenas. Evidencia: capturas 04 y 05 ([sección 12.3](#123-evidencias-de-pruebas)).

### 12.2 Viñetas y guiones: títulos, subtítulos y texto en Markdown y PDF

**Qué cambió.** El material (pasos del tutorial, viñetas, flashcards, escenas del guion y
diapositivas) se arma por secciones del documento, así que reconocer bien sus títulos es lo
que hace que cada viñeta quede bajo el título correcto.

| Formato | Cómo se reconoce un título | Cómo se reconoce el texto |
|---|---|---|
| **Markdown (.md)** | `#` a `######`, títulos subrayados con `===` (nivel 1) o `---` (nivel 2); se quitan `**negrita**`, `` `código` `` y enlaces del título | Todo lo demás. Un `#` dentro de un bloque de código (```` ``` ````) es un comentario, no un título; un ```` ``` ```` sin cerrar no anula los títulos siguientes |
| **PDF** | 1) **Marcadores** del PDF (el índice lateral que crea Word), aunque el título no esté como texto; 2) **letra más grande** que el texto corrido (el nivel sale del tamaño: el más grande es 1); 3) renglón entero en **negrita** del tamaño del texto (si no es un rótulo como «Ejemplos:»); 4) si no hay nada de lo anterior, títulos **numerados** («2.3 Modos») o en **MAYÚSCULAS** | Lo demás. No pasan por título: encabezados y pies que se repiten, entradas del índice («… Pag 21.»), líneas que siguen en minúscula, cabeceras de tabla ni comentarios de código (`# …`) |
| PDF escaneado o sin espacios entre palabras | Se lee con OCR de Gemini, que marca títulos (`##`) y subtítulos (`###`) | Se omiten encabezados, pies y números de página |
| Word (.docx) | Estilos «Título 1…3» / «Heading 1…3» (sin cambios) | Párrafos y tablas |

El código está en `src/nuevamente/ingest/readers.py` (PDF) y `src/nuevamente/ingest/chunking.py`
(Markdown y reglas de texto).

**Documentos de prueba** (`docs/pruebas/documentos/`) y secciones reconocidas antes y
después del cambio:

| Documento | Tipo de estructura | Antes | Después |
|---|---|---:|---:|
| `evidencia_scrum_21_a_24.md` | Markdown con `#`, `##`, negritas y separadores `---` | 4 | 4 |
| `DD_IA_01.pdf` | Glosario: cada término en negrita | 0 | 31 |
| `evidencia_scrum_21_a_24.pdf` | Es el mismo archivo que `DD_IA_01.pdf` (no es el PDF del .md) | 0 | 31 |
| `guia-prompting-alcaraz-cricc.pdf` | Títulos solo en los marcadores del PDF | 4 | 33 |
| `IoT-Guia-Basica.pdf` | Títulos en letra grande, diagramas con texto en mayúsculas | 5 | 21 |
| `E-Commers.pdf` | Títulos y subtítulos en dos tamaños | 12 | 13 |
| `Manual Forms 6i.pdf` / `Libro guía del usuario.pdf` | Numerados («5.2-BLOQUES DE DATOS:»), índice y código | 44 (con ~15 líneas de código tomadas por título) | 36 / 35 |
| `Memoria en generador de video_v6 - DeepSeek.pdf` | Conversación con código (`# comentario`) | 92 | 95 |
| `Normas de Conducta y Convivencia.pdf` | Títulos en letra algo mayor | 9 | 9 |
| `Manual como hacer clic.pdf` | Texto corto | 3 | 3 |
| `original6.pdf` | Artículo con el texto guardado sin espacios | 0 | 0 sin OCR; con `GEMINI_API_KEY` se lee por OCR |
| `.docx` de Fintech, Políticas y Resumen E-commerce | Estilos de título de Word | 30 / 12 / 7 | 30 / 12 / 7 |

**Cómo se comprueba.** `pytest tests/test_titulos.py -v` (15 pruebas, incluidas las de los
documentos reales; se omiten si la carpeta no está en el equipo). Evidencia: capturas 01, 02 y 03.

### 12.3 Evidencias de pruebas

#### Resumen gráfico de las pruebas realizadas

```mermaid
flowchart LR
    A["Pruebas realizadas<br/>Sprint 4"] --> B["Automatizadas (pytest)<br/>295 de 295 ✅"]
    A --> C["Documentos de prueba<br/>15 archivos: 11 PDF, 1 MD, 3 DOCX ✅"]
    A --> D["De punta a punta por la API ✅"]
    A --> E["Video del guion ✅"]
    A --> F["Interfaz web ✅"]
    A --> G["Fidelidad ✅"]
    G --> G1["Generador local<br/>86 de 90"]
    G --> G2["IA real (Gemini)<br/>9 de 10"]
    F --> F2["24 materiales:<br/>4 perfiles × 6 formatos"]
    F --> F3["18 pantallas"]
    B --> B1["Títulos en Markdown y PDF<br/>15 nuevas"]
    B --> B2["Video sin introducción hablada<br/>1 nueva"]
    B --> B3["Resto de la suite<br/>279"]
    C --> C1["Secciones reconocidas<br/>antes y después"]
    D --> D1["Tutorial desde el .md<br/>4 pasos = 4 títulos"]
    D --> D2["Guion desde E-Commers.pdf<br/>8 escenas"]
    D --> D3["Flashcards desde<br/>Normas de Conducta.pdf"]
    E --> E1["Portada en silencio,<br/>sin saludo"]
    E --> E2["Cada diapositiva lleva<br/>la sección del documento"]
    F --> F1["App en marcha<br/>(make run-api)"]
```

| Prueba | Cómo se hizo | Resultado |
|---|---|---|
| Suite automatizada completa | `pytest -q` | ✅ 295 de 295 |
| Títulos, subtítulos y texto en Markdown y PDF | `pytest tests/test_titulos.py -v` (15 pruebas) | ✅ 15 de 15 |
| Video sin introducción hablada | `pytest tests/test_narracion.py -k introduccion` | ✅ 1 de 1 |
| Secciones en los 15 documentos de prueba | Lectura y chunking de cada archivo, antes y después del cambio | ✅ 12 mejoran o se mantienen; 2 pierden títulos falsos; `original6.pdf` necesita OCR |
| Material desde Markdown | API: Tutorial desde `evidencia_scrum_21_a_24.md` | ✅ un paso por cada título |
| Material desde PDF | API: Guion de Clase desde `E-Commers.pdf` y Flashcards desde `Normas…pdf` | ✅ conceptos y tarjetas con los títulos del PDF |
| Video MP4 | API: video del guion de `E-Commers.pdf` | ✅ portada sin saludo y escenas con su sección |
| Interfaz web | Recorrido automático con Chrome: 4 perfiles × 6 formatos y 18 pantallas (secciones [12.5](#125-proceso-de-generación-de-contenido-por-perfil) y [12.6](#126-pantallas-del-aplicativo)) | ✅ 24 materiales generados |
| Fidelidad, generador local | 15 documentos × 6 formatos | ✅ 86 de 90 (los 4 restantes: frases cortas, ver hallazgos) |
| Fidelidad, IA real | Gemini: 5 documentos × Resumen Ejecutivo y Quiz | ✅ 9 de 10 (1 bajo el umbral de Salud) |

![Pruebas automatizadas por archivo: 295 de 295 aprobadas](docs/pruebas/evidencias/graficos/grafico_pruebas_por_archivo.svg)

![Títulos y subtítulos reconocidos por documento, antes y después](docs/pruebas/evidencias/graficos/grafico_titulos_antes_despues.svg)

#### Prueba de fidelidad

Cada material se verifica contra el documento: cada afirmación se compara con el fragmento
que dice citar, y el puntaje es `(sustentadas + 0,5 × parciales) / total`. Se aprueba con
**0,85** o más (**0,90** en el sector Salud). Se hicieron dos rondas con los documentos de
`docs/pruebas/documentos/`:

| Ronda | Materiales | Aprobados | Qué mide |
|---|---:|---:|---|
| Generador local (sin red) | 90 = 15 documentos × 6 formatos | **86** (96 %) | Que toda la cadena (lectura, secciones, verificación) funcione con cada documento y formato |
| IA real (Gemini, juez TF-IDF + juez de IA) | 10 = 5 documentos × Resumen Ejecutivo y Quiz | **9** (90 %) | La fidelidad de un modelo que redacta con sus palabras, en los dos formatos más exigentes |

![Prueba de fidelidad por documento y formato, generador local](docs/pruebas/evidencias/graficos/grafico_fidelidad_matriz.svg)

![Prueba de fidelidad con IA real](docs/pruebas/evidencias/graficos/grafico_fidelidad_ia.svg)

**Hallazgos.**
- Los 4 materiales sin aprobar de la ronda local (E-Commers: Flashcards 0,83 y Quiz 0,80;
  Manual como hacer clic: Quiz 0,83; Memoria: Flashcards 0,79) no tienen texto inventado:
  las afirmaciones marcadas son frases copiadas tal cual del documento pero muy cortas
  («Transacciones entre empresas.», «No hay paralelismo.»). El verificador TF-IDF compara
  palabras en común con un fragmento largo y subestima las frases cortas. Mejora posible:
  dar por sustentada una afirmación que aparece literal en su fragmento.
- Con IA real, el único que no aprueba es el Resumen Ejecutivo de *Normas de Conducta*
  (0,88), por el umbral más estricto de Salud (0,90): 3 de 4 afirmaciones sustentadas. La
  interfaz lo muestra como «⚠️ Revisar».
- Con la cuota gratuita de Gemini, cada material tardó entre 30 s y 8 min, por las esperas
  y la rotación de modelos cuando uno se queda sin cuota.

#### Capturas

Capturas en [`docs/pruebas/evidencias/`](docs/pruebas/evidencias/), tomadas el 20/10/2026 en la
rama `SPRINT04.4` con el generador local (`LLM_PROVIDER=template`, sin red):

| # | Captura | Qué documenta |
|---|---|---|
| 01 | [Pruebas automatizadas](docs/pruebas/evidencias/01_pruebas_automatizadas.png) | `pytest -v` de las pruebas nuevas (16 PASSED) y la suite completa (295 passed) |
| 02 | [Títulos antes y después](docs/pruebas/evidencias/02_titulos_reconocidos_antes_despues.png) | Secciones reconocidas en cada documento de prueba, antes (commit `715d90a`) y después |
| 03 | [Material generado](docs/pruebas/evidencias/03_material_generado_desde_md_y_pdf.png) | Tutorial desde el `.md` (un paso por título), guion desde `E-Commers.pdf` y flashcards desde `Normas…pdf` |
| 04 | [Portada del video](docs/pruebas/evidencias/04_video_portada_sin_saludo.png) | Portada con el título del documento, en silencio y sin saludo |
| 05 | [Primera escena del video](docs/pruebas/evidencias/05_video_primera_escena.png) | La diapositiva lleva la sección del documento («Introducción») y solo su narración |
| 06 | [Interfaz web](docs/pruebas/evidencias/06_interfaz_web.png) | La aplicación en marcha (`make run-api`) |

| 01 · Pruebas automatizadas | 02 · Títulos antes y después |
|---|---|
| ![Pruebas automatizadas](docs/pruebas/evidencias/01_pruebas_automatizadas.png) | ![Títulos reconocidos antes y después](docs/pruebas/evidencias/02_titulos_reconocidos_antes_despues.png) |
| **03 · Material generado desde .md y PDF** | **06 · Interfaz web** |
| ![Material generado desde Markdown y PDF](docs/pruebas/evidencias/03_material_generado_desde_md_y_pdf.png) | ![Interfaz web](docs/pruebas/evidencias/06_interfaz_web.png) |
| **04 · Portada del video, sin saludo** | **05 · Primera escena del video** |
| ![Portada del video sin saludo](docs/pruebas/evidencias/04_video_portada_sin_saludo.png) | ![Primera escena del video](docs/pruebas/evidencias/05_video_primera_escena.png) |

### 12.4 Recursos de pruebas

Enlaces del proyecto (deploy, repositorio y Jira) en la [sección 2](#2-demo-y-enlaces-del-proyecto).

| Recurso | Enlace |
|---|---|
| Pruebas automatizadas | [`tests/`](tests/) (ver [sección 7](#7-pruebas)) |
| Pruebas de títulos en Markdown y PDF | [`tests/test_titulos.py`](tests/test_titulos.py) |
| Documentos de prueba | [`docs/pruebas/documentos/`](docs/pruebas/documentos/) |
| Evidencias (capturas) | [`docs/pruebas/evidencias/`](docs/pruebas/evidencias/) |
| Gráficos de las pruebas | [`docs/pruebas/evidencias/graficos/`](docs/pruebas/evidencias/graficos/) |
| Capturas por perfil (24 materiales) | [`docs/pruebas/evidencias/perfiles/`](docs/pruebas/evidencias/perfiles/) |
| Capturas de las pantallas | [`docs/pruebas/evidencias/pantallas/`](docs/pruebas/evidencias/pantallas/) |
| Docker Compose (archivo y guías) | [`compose.yaml`](https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS/blob/main/compose.yaml) · [`compose_comandos_kairos.md`](https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS/blob/main/compose_comandos_kairos.md) · [`compose_checklist.md`](https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS/blob/main/compose_checklist.md) |
| Resultados de los escenarios de demo | [`docs/demo/resultados/`](docs/demo/resultados/) |

### 12.5 Proceso de generación de contenido por perfil

Capturas de la interfaz tomadas el 20/10/2026 con el documento de prueba `E-Commers.pdf`,
sector **General** y nivel de detalle **Didáctico**, para los 4 perfiles y los 6 formatos
(24 materiales). Se generaron con el generador local (`LLM_PROVIDER=template`, sin red), así
que el texto es extractivo y cambia poco entre perfiles; con Gemini u otro modelo, el
lenguaje se adapta a cada perfil. Clic en una imagen para verla en tamaño completo.

```mermaid
flowchart LR
    A["1 · Documento<br/>(subir o pegar)"] --> B["2 · Perfil<br/>🌱 💻 🏗️ 📈"] --> C["3 · Formato<br/>🧭 🃏 ❓ 📊 🎬 🎙️"] --> D["4 · Sector y nivel<br/>General · Didáctico"] --> E["5 · Aceptar aviso<br/>y crear"] --> F["6 · Agentes<br/>lee, busca, redacta, verifica"] --> G["7 · Material<br/>+ fidelidad + descargas"]
```

<details open>
<summary><b>🌱 Inicial/Básico (Principiante-Junior)</b></summary>

<table>
<tr>
<td align="center" width="50%"><b>1 · Elegir documento, perfil y formato</b><br><a href="docs/pruebas/evidencias/perfiles/inicial_1_opciones.jpg"><img src="docs/pruebas/evidencias/perfiles/inicial_1_opciones.jpg" width="260" alt="Opciones · 🌱 Inicial/Básico (Principiante-Junior)"></a></td>
<td align="center" width="50%"><b>2 · Creación en curso (agentes trabajando)</b><br><a href="docs/pruebas/evidencias/perfiles/inicial_2_progreso.jpg"><img src="docs/pruebas/evidencias/perfiles/inicial_2_progreso.jpg" width="420" alt="Progreso · 🌱 Inicial/Básico (Principiante-Junior)"></a></td>
</tr>
</table>

**3 · Material generado, un formato por captura:**

<table>
<tr><td align="center" width="33%"><b>🧭 Tutorial</b><br><a href="docs/pruebas/evidencias/perfiles/inicial_3_tutorial.jpg"><img src="docs/pruebas/evidencias/perfiles/inicial_3_tutorial.jpg" width="300" alt="🧭 Tutorial · 🌱 Inicial/Básico (Principiante-Junior)"></a></td><td align="center" width="33%"><b>🃏 Flashcards</b><br><a href="docs/pruebas/evidencias/perfiles/inicial_3_flashcards.jpg"><img src="docs/pruebas/evidencias/perfiles/inicial_3_flashcards.jpg" width="300" alt="🃏 Flashcards · 🌱 Inicial/Básico (Principiante-Junior)"></a></td><td align="center" width="33%"><b>❓ Quiz</b><br><a href="docs/pruebas/evidencias/perfiles/inicial_3_quiz.jpg"><img src="docs/pruebas/evidencias/perfiles/inicial_3_quiz.jpg" width="300" alt="❓ Quiz · 🌱 Inicial/Básico (Principiante-Junior)"></a></td></tr><tr><td align="center" width="33%"><b>📊 Resumen Ejecutivo</b><br><a href="docs/pruebas/evidencias/perfiles/inicial_3_resumen.jpg"><img src="docs/pruebas/evidencias/perfiles/inicial_3_resumen.jpg" width="300" alt="📊 Resumen Ejecutivo · 🌱 Inicial/Básico (Principiante-Junior)"></a></td><td align="center" width="33%"><b>🎬 Guion de Clase</b><br><a href="docs/pruebas/evidencias/perfiles/inicial_3_guion.jpg"><img src="docs/pruebas/evidencias/perfiles/inicial_3_guion.jpg" width="300" alt="🎬 Guion de Clase · 🌱 Inicial/Básico (Principiante-Junior)"></a></td><td align="center" width="33%"><b>🎙️ Podcast</b><br><a href="docs/pruebas/evidencias/perfiles/inicial_3_podcast.jpg"><img src="docs/pruebas/evidencias/perfiles/inicial_3_podcast.jpg" width="300" alt="🎙️ Podcast · 🌱 Inicial/Básico (Principiante-Junior)"></a></td></tr>
</table>

</details>
<details>
<summary><b>💻 Intermedio (semisénior)</b></summary>

<table>
<tr>
<td align="center" width="50%"><b>1 · Elegir documento, perfil y formato</b><br><a href="docs/pruebas/evidencias/perfiles/intermedio_1_opciones.jpg"><img src="docs/pruebas/evidencias/perfiles/intermedio_1_opciones.jpg" width="260" alt="Opciones · 💻 Intermedio (semisénior)"></a></td>
<td align="center" width="50%"><b>2 · Creación en curso (agentes trabajando)</b><br><a href="docs/pruebas/evidencias/perfiles/intermedio_2_progreso.jpg"><img src="docs/pruebas/evidencias/perfiles/intermedio_2_progreso.jpg" width="420" alt="Progreso · 💻 Intermedio (semisénior)"></a></td>
</tr>
</table>

**3 · Material generado, un formato por captura:**

<table>
<tr><td align="center" width="33%"><b>🧭 Tutorial</b><br><a href="docs/pruebas/evidencias/perfiles/intermedio_3_tutorial.jpg"><img src="docs/pruebas/evidencias/perfiles/intermedio_3_tutorial.jpg" width="300" alt="🧭 Tutorial · 💻 Intermedio (semisénior)"></a></td><td align="center" width="33%"><b>🃏 Flashcards</b><br><a href="docs/pruebas/evidencias/perfiles/intermedio_3_flashcards.jpg"><img src="docs/pruebas/evidencias/perfiles/intermedio_3_flashcards.jpg" width="300" alt="🃏 Flashcards · 💻 Intermedio (semisénior)"></a></td><td align="center" width="33%"><b>❓ Quiz</b><br><a href="docs/pruebas/evidencias/perfiles/intermedio_3_quiz.jpg"><img src="docs/pruebas/evidencias/perfiles/intermedio_3_quiz.jpg" width="300" alt="❓ Quiz · 💻 Intermedio (semisénior)"></a></td></tr><tr><td align="center" width="33%"><b>📊 Resumen Ejecutivo</b><br><a href="docs/pruebas/evidencias/perfiles/intermedio_3_resumen.jpg"><img src="docs/pruebas/evidencias/perfiles/intermedio_3_resumen.jpg" width="300" alt="📊 Resumen Ejecutivo · 💻 Intermedio (semisénior)"></a></td><td align="center" width="33%"><b>🎬 Guion de Clase</b><br><a href="docs/pruebas/evidencias/perfiles/intermedio_3_guion.jpg"><img src="docs/pruebas/evidencias/perfiles/intermedio_3_guion.jpg" width="300" alt="🎬 Guion de Clase · 💻 Intermedio (semisénior)"></a></td><td align="center" width="33%"><b>🎙️ Podcast</b><br><a href="docs/pruebas/evidencias/perfiles/intermedio_3_podcast.jpg"><img src="docs/pruebas/evidencias/perfiles/intermedio_3_podcast.jpg" width="300" alt="🎙️ Podcast · 💻 Intermedio (semisénior)"></a></td></tr>
</table>

</details>
<details>
<summary><b>🏗️ Avanzado (Senior-Arquitecto-Técnico)</b></summary>

<table>
<tr>
<td align="center" width="50%"><b>1 · Elegir documento, perfil y formato</b><br><a href="docs/pruebas/evidencias/perfiles/avanzado_1_opciones.jpg"><img src="docs/pruebas/evidencias/perfiles/avanzado_1_opciones.jpg" width="260" alt="Opciones · 🏗️ Avanzado (Senior-Arquitecto-Técnico)"></a></td>
<td align="center" width="50%"><b>2 · Creación en curso (agentes trabajando)</b><br><a href="docs/pruebas/evidencias/perfiles/avanzado_2_progreso.jpg"><img src="docs/pruebas/evidencias/perfiles/avanzado_2_progreso.jpg" width="420" alt="Progreso · 🏗️ Avanzado (Senior-Arquitecto-Técnico)"></a></td>
</tr>
</table>

**3 · Material generado, un formato por captura:**

<table>
<tr><td align="center" width="33%"><b>🧭 Tutorial</b><br><a href="docs/pruebas/evidencias/perfiles/avanzado_3_tutorial.jpg"><img src="docs/pruebas/evidencias/perfiles/avanzado_3_tutorial.jpg" width="300" alt="🧭 Tutorial · 🏗️ Avanzado (Senior-Arquitecto-Técnico)"></a></td><td align="center" width="33%"><b>🃏 Flashcards</b><br><a href="docs/pruebas/evidencias/perfiles/avanzado_3_flashcards.jpg"><img src="docs/pruebas/evidencias/perfiles/avanzado_3_flashcards.jpg" width="300" alt="🃏 Flashcards · 🏗️ Avanzado (Senior-Arquitecto-Técnico)"></a></td><td align="center" width="33%"><b>❓ Quiz</b><br><a href="docs/pruebas/evidencias/perfiles/avanzado_3_quiz.jpg"><img src="docs/pruebas/evidencias/perfiles/avanzado_3_quiz.jpg" width="300" alt="❓ Quiz · 🏗️ Avanzado (Senior-Arquitecto-Técnico)"></a></td></tr><tr><td align="center" width="33%"><b>📊 Resumen Ejecutivo</b><br><a href="docs/pruebas/evidencias/perfiles/avanzado_3_resumen.jpg"><img src="docs/pruebas/evidencias/perfiles/avanzado_3_resumen.jpg" width="300" alt="📊 Resumen Ejecutivo · 🏗️ Avanzado (Senior-Arquitecto-Técnico)"></a></td><td align="center" width="33%"><b>🎬 Guion de Clase</b><br><a href="docs/pruebas/evidencias/perfiles/avanzado_3_guion.jpg"><img src="docs/pruebas/evidencias/perfiles/avanzado_3_guion.jpg" width="300" alt="🎬 Guion de Clase · 🏗️ Avanzado (Senior-Arquitecto-Técnico)"></a></td><td align="center" width="33%"><b>🎙️ Podcast</b><br><a href="docs/pruebas/evidencias/perfiles/avanzado_3_podcast.jpg"><img src="docs/pruebas/evidencias/perfiles/avanzado_3_podcast.jpg" width="300" alt="🎙️ Podcast · 🏗️ Avanzado (Senior-Arquitecto-Técnico)"></a></td></tr>
</table>

</details>
<details>
<summary><b>📈 Experto / Directivo (Lead, Ejecutivo, Gestor)</b></summary>

<table>
<tr>
<td align="center" width="50%"><b>1 · Elegir documento, perfil y formato</b><br><a href="docs/pruebas/evidencias/perfiles/experto_1_opciones.jpg"><img src="docs/pruebas/evidencias/perfiles/experto_1_opciones.jpg" width="260" alt="Opciones · 📈 Experto / Directivo (Lead, Ejecutivo, Gestor)"></a></td>
<td align="center" width="50%"><b>2 · Creación en curso (agentes trabajando)</b><br><a href="docs/pruebas/evidencias/perfiles/experto_2_progreso.jpg"><img src="docs/pruebas/evidencias/perfiles/experto_2_progreso.jpg" width="420" alt="Progreso · 📈 Experto / Directivo (Lead, Ejecutivo, Gestor)"></a></td>
</tr>
</table>

**3 · Material generado, un formato por captura:**

<table>
<tr><td align="center" width="33%"><b>🧭 Tutorial</b><br><a href="docs/pruebas/evidencias/perfiles/experto_3_tutorial.jpg"><img src="docs/pruebas/evidencias/perfiles/experto_3_tutorial.jpg" width="300" alt="🧭 Tutorial · 📈 Experto / Directivo (Lead, Ejecutivo, Gestor)"></a></td><td align="center" width="33%"><b>🃏 Flashcards</b><br><a href="docs/pruebas/evidencias/perfiles/experto_3_flashcards.jpg"><img src="docs/pruebas/evidencias/perfiles/experto_3_flashcards.jpg" width="300" alt="🃏 Flashcards · 📈 Experto / Directivo (Lead, Ejecutivo, Gestor)"></a></td><td align="center" width="33%"><b>❓ Quiz</b><br><a href="docs/pruebas/evidencias/perfiles/experto_3_quiz.jpg"><img src="docs/pruebas/evidencias/perfiles/experto_3_quiz.jpg" width="300" alt="❓ Quiz · 📈 Experto / Directivo (Lead, Ejecutivo, Gestor)"></a></td></tr><tr><td align="center" width="33%"><b>📊 Resumen Ejecutivo</b><br><a href="docs/pruebas/evidencias/perfiles/experto_3_resumen.jpg"><img src="docs/pruebas/evidencias/perfiles/experto_3_resumen.jpg" width="300" alt="📊 Resumen Ejecutivo · 📈 Experto / Directivo (Lead, Ejecutivo, Gestor)"></a></td><td align="center" width="33%"><b>🎬 Guion de Clase</b><br><a href="docs/pruebas/evidencias/perfiles/experto_3_guion.jpg"><img src="docs/pruebas/evidencias/perfiles/experto_3_guion.jpg" width="300" alt="🎬 Guion de Clase · 📈 Experto / Directivo (Lead, Ejecutivo, Gestor)"></a></td><td align="center" width="33%"><b>🎙️ Podcast</b><br><a href="docs/pruebas/evidencias/perfiles/experto_3_podcast.jpg"><img src="docs/pruebas/evidencias/perfiles/experto_3_podcast.jpg" width="300" alt="🎙️ Podcast · 📈 Experto / Directivo (Lead, Ejecutivo, Gestor)"></a></td></tr>
</table>

</details>

### 12.6 Pantallas del aplicativo

Todas las pantallas y estados de la interfaz web (`make run-api` → http://localhost:8000/).
Clic en una imagen para verla en tamaño completo.

<details open>
<summary>Ver las 18 pantallas</summary>

<table>
<tr><td align="center" width="50%"><b>01 · Inicio: formulario y espacio para el material</b><br><a href="docs/pruebas/evidencias/pantallas/p01_inicio.jpg"><img src="docs/pruebas/evidencias/pantallas/p01_inicio.jpg" width="420" alt="Inicio: formulario y espacio para el material"></a></td><td align="center" width="50%"><b>02 · 💡 Cómo funciona (ayuda)</b><br><a href="docs/pruebas/evidencias/pantallas/p02_como_funciona.jpg"><img src="docs/pruebas/evidencias/pantallas/p02_como_funciona.jpg" width="420" alt="💡 Cómo funciona (ayuda)"></a></td></tr>
<tr><td align="center" width="50%"><b>03 · ⚖️ Aviso legal y ético (debe leerse completo para aceptarlo)</b><br><a href="docs/pruebas/evidencias/pantallas/p03_aviso_legal.jpg"><img src="docs/pruebas/evidencias/pantallas/p03_aviso_legal.jpg" width="420" alt="⚖️ Aviso legal y ético (debe leerse completo para aceptarlo)"></a></td><td align="center" width="50%"><b>04 · 📎 Subir archivo: perfiles, formatos, sector y nivel</b><br><a href="docs/pruebas/evidencias/pantallas/p04_subir_archivo.jpg"><img src="docs/pruebas/evidencias/pantallas/p04_subir_archivo.jpg" width="420" alt="📎 Subir archivo: perfiles, formatos, sector y nivel"></a></td></tr>
<tr><td align="center" width="50%"><b>05 · Archivo no compatible (.xlsx): aviso y opción de cargar otro</b><br><a href="docs/pruebas/evidencias/pantallas/p05_archivo_no_compatible.jpg"><img src="docs/pruebas/evidencias/pantallas/p05_archivo_no_compatible.jpg" width="420" alt="Archivo no compatible (.xlsx): aviso y opción de cargar otro"></a></td><td align="center" width="50%"><b>06 · Archivo cargado (E-Commers.pdf)</b><br><a href="docs/pruebas/evidencias/pantallas/p06_archivo_cargado.jpg"><img src="docs/pruebas/evidencias/pantallas/p06_archivo_cargado.jpg" width="420" alt="Archivo cargado (E-Commers.pdf)"></a></td></tr>
<tr><td align="center" width="50%"><b>07 · Sector Salud: aviso de material de apoyo educativo</b><br><a href="docs/pruebas/evidencias/pantallas/p07_opciones_y_aviso_salud.jpg"><img src="docs/pruebas/evidencias/pantallas/p07_opciones_y_aviso_salud.jpg" width="420" alt="Sector Salud: aviso de material de apoyo educativo"></a></td><td align="center" width="50%"><b>08 · Pestaña 🔍 Fidelidad: afirmaciones verificadas contra el documento</b><br><a href="docs/pruebas/evidencias/pantallas/p10_pestana_calidad.jpg"><img src="docs/pruebas/evidencias/pantallas/p10_pestana_calidad.jpg" width="420" alt="Pestaña 🔍 Fidelidad: afirmaciones verificadas contra el documento"></a></td></tr>
<tr><td align="center" width="50%"><b>09 · Pestaña ☁️ Guardado: bucket, objeto y documento original</b><br><a href="docs/pruebas/evidencias/pantallas/p11_pestana_almacenamiento.jpg"><img src="docs/pruebas/evidencias/pantallas/p11_pestana_almacenamiento.jpg" width="420" alt="Pestaña ☁️ Guardado: bucket, objeto y documento original"></a></td><td align="center" width="50%"><b>10 · Pestaña 🧾 JSON: respuesta completa de la API</b><br><a href="docs/pruebas/evidencias/pantallas/p12_pestana_json.jpg"><img src="docs/pruebas/evidencias/pantallas/p12_pestana_json.jpg" width="420" alt="Pestaña 🧾 JSON: respuesta completa de la API"></a></td></tr>
<tr><td align="center" width="50%"><b>11 · Calificación de 1 a 5 estrellas y comentario</b><br><a href="docs/pruebas/evidencias/pantallas/p13_calificacion.jpg"><img src="docs/pruebas/evidencias/pantallas/p13_calificacion.jpg" width="420" alt="Calificación de 1 a 5 estrellas y comentario"></a></td><td align="center" width="50%"><b>12 · 🎬 Video del Guion de Clase con elección de voz</b><br><a href="docs/pruebas/evidencias/pantallas/p14_video_guion.jpg"><img src="docs/pruebas/evidencias/pantallas/p14_video_guion.jpg" width="420" alt="🎬 Video del Guion de Clase con elección de voz"></a></td></tr>
<tr><td align="center" width="50%"><b>13 · 🎙️ Podcast: episodio en audio con Ana y Leo</b><br><a href="docs/pruebas/evidencias/pantallas/p15_podcast.jpg"><img src="docs/pruebas/evidencias/pantallas/p15_podcast.jpg" width="420" alt="🎙️ Podcast: episodio en audio con Ana y Leo"></a></td><td align="center" width="50%"><b>14 · 🕘 Historial con buscador</b><br><a href="docs/pruebas/evidencias/pantallas/p16_historial.jpg"><img src="docs/pruebas/evidencias/pantallas/p16_historial.jpg" width="420" alt="🕘 Historial con buscador"></a></td></tr>
<tr><td align="center" width="50%"><b>15 · Estado de guardado (OCI o respaldo local) y su motivo</b><br><a href="docs/pruebas/evidencias/pantallas/p17_guardado_oci.jpg"><img src="docs/pruebas/evidencias/pantallas/p17_guardado_oci.jpg" width="420" alt="Estado de guardado (OCI o respaldo local) y su motivo"></a></td><td align="center" width="50%"><b>16 · 🌙 Modo oscuro</b><br><a href="docs/pruebas/evidencias/pantallas/p18_modo_oscuro.jpg"><img src="docs/pruebas/evidencias/pantallas/p18_modo_oscuro.jpg" width="420" alt="🌙 Modo oscuro"></a></td></tr>
<tr><td align="center" width="50%"><b>17 · 📊 Panel de estadísticas de uso</b><br><a href="docs/pruebas/evidencias/pantallas/p19_estadisticas.jpg"><img src="docs/pruebas/evidencias/pantallas/p19_estadisticas.jpg" width="420" alt="📊 Panel de estadísticas de uso"></a></td><td align="center" width="50%"><b>18 · Documentación de la API (/docs)</b><br><a href="docs/pruebas/evidencias/pantallas/p20_api_docs.jpg"><img src="docs/pruebas/evidencias/pantallas/p20_api_docs.jpg" width="420" alt="Documentación de la API (/docs)"></a></td></tr>
</table>

</details>

## 13. Equipo

| Persona | Rol |
|---|---|
| Juan Pablo Calla | Project Manager |
| Gaspar Martínez Paiva | Data Engineer · Machine Learning Engineer |
| Ethan Espinoza Acosta | Backend Developer · Orquestación de agentes |
| Darío Higuera Moreno | No Code Developer · Ingeniero de IA |
| Diana Dure | QA Tester |

### 13.1 Quién construyó qué

| Módulo | Responsable | Rol |
|---|---|---|
| `config.py`, arquitectura general, `docs/demo/` | Juan Pablo Calla | Project Manager |
| `ingest/`, `rag/` | Gaspar Martínez Paiva | Data Engineer |
| `agents/graph.py` (orquestación de agentes) | Ethan Espinoza Acosta | Orquestación de agentes |
| `llm/`, `fidelity/` | Darío Higuera Moreno | Ingeniero de IA |
| `schemas/`, `api/`, `cache/` | Ethan Espinoza Acosta | Backend Developer |
| `web/`, `ui/`, `exports/` | Darío Higuera Moreno | No Code Developer |
| `tests/` | Diana Dure | QA Tester |

## Créditos

Proyecto desarrollado por el equipo **Kairos G10** (G10-LATAM-equipo 41) para el
**Hackathon ONE G10** de **Oracle Next Education** y **Alura**, en la simulación de
**No Country**.
