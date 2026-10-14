# Imagen de Kairos (API + interfaz web) para cualquier servidor con Docker:
# Render, Railway, Fly.io, Hugging Face Spaces o una VM propia. Ver docs/DEPLOY_RENDER.md.
FROM python:3.12-slim

# ffmpeg: video y podcast · espeak-ng: voz de respaldo si Gemini TTS no está disponible
# fuentes: diapositivas del video, PDF y PowerPoint
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg espeak-ng fonts-dejavu-core fonts-liberation curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# requirements.txt instala el propio paquete con "-e .": primero lo que define el paquete
COPY pyproject.toml requirements.txt ./
COPY src ./src
RUN pip install -r requirements.txt

COPY scripts ./scripts
COPY docs/demo ./docs/demo

# usuario sin privilegios; los datos (respaldo local, videos, estadísticas) van en /app/data
RUN useradd --create-home --uid 1000 kairos \
    && mkdir -p data/fallback data/vectorstore data/videos data/estadisticas \
    && chown -R kairos:kairos /app
USER kairos

# valores por defecto seguros: el proveedor y las claves se configuran en el servidor
ENV LLM_PROVIDER=gemini \
    LLM_RESPALDO_LOCAL=true \
    EMBEDDINGS_PROVIDER=auto \
    PORT=8000

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# Render, Railway y Fly indican el puerto en $PORT
CMD ["sh", "-c", "uvicorn nuevamente.api.app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
