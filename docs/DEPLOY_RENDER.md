# Despliegue alternativo: Render (gratis, con Docker)

Además de OCI Compute ([DEPLOY_OCI.md](DEPLOY_OCI.md)), Kairos se publica en **Render** con el
`Dockerfile` del repositorio. No hace falta instalar nada: Render construye la imagen desde GitHub.

| Archivo | Qué hace |
|---|---|
| `Dockerfile` | Imagen con Python 3.12, ffmpeg, espeak-ng y fuentes; corre uvicorn en el puerto `$PORT`. |
| `.dockerignore` | Deja fuera `.env`, llaves, datos locales y tests: ningún secreto entra en la imagen. |
| `render.yaml` | Blueprint de Render: servicio web Docker en el plan gratuito, rama `SPRINT04`. |

## Pasos (unos 10 minutos, la mayoría esperando la construcción)

1. Entra a <https://dashboard.render.com> e inicia sesión **con tu cuenta de GitHub**.
2. **New → Blueprint** y elige el repositorio
   `No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS`, rama **SPRINT04**.
   Render lee `render.yaml` y propone el servicio `kairos-nuevamente`.
3. Te pedirá **`GEMINI_API_KEY`**: pega tu clave de Google AI Studio (queda guardada solo en Render).
4. **Apply**. La primera construcción tarda unos minutos. Al terminar, la app queda en
   `https://kairos-nuevamente.onrender.com` (o el nombre que Render asigne).
5. Comprueba `https://<tu-servicio>.onrender.com/health` → `{"status": "ok", ...}`.

> Sin Blueprint: **New → Web Service**, repositorio y rama `SPRINT04`, *Runtime*: **Docker**,
> plan **Free**, *Health Check Path*: `/health`, y la variable `GEMINI_API_KEY`.

## Guardar en OCI Object Storage desde Render (opcional)

En el servicio → **Environment → Secret Files**, crea:

- `oci_api_key.pem` con el contenido de `~/.oci/oci_api_key.pem`.
- `oci_config` con el contenido de `~/.oci/config`, cambiando la línea
  `key_file=/etc/secrets/oci_api_key.pem`.

y agrega la variable `OCI_CONFIG_FILE=/etc/secrets/oci_config`. `/health` mostrará
`"oci_disponible": true`.

## Lo que conviene saber del plan gratuito

- **Se duerme** tras 15 minutos sin visitas; la primera visita después tarda ~1 minuto en despertar.
- **512 MB de memoria**: alcanza para la app. Con `VECTOR_STORE=local` (por defecto).
- **Disco efímero**: el respaldo local (`data/`), los videos y las estadísticas se borran al
  reiniciar. Para persistir los materiales, configura OCI Object Storage (arriba).
- Cada `git push` a `SPRINT04` vuelve a desplegar (`autoDeploy: true`).

## Otros servidores con el mismo Dockerfile

- **Railway** (<https://railway.app>): *New Project → Deploy from GitHub repo*, rama `SPRINT04`;
  detecta el `Dockerfile`. Agrega `GEMINI_API_KEY` en *Variables* y genera un dominio en *Settings*.
- **Fly.io**: `fly launch` (detecta el `Dockerfile`, puerto interno 8000) y
  `fly secrets set GEMINI_API_KEY=...`.
- **Cualquier VM con Docker**:

  ```bash
  docker build -t kairos .
  docker run -d -p 80:8000 -e GEMINI_API_KEY=... --name kairos kairos
  ```
