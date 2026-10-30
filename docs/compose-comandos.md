#!/usr/bin/env bash
# =============================================================================
# COMANDOS.md — Referencia rápida para Kairos (Docker Compose)
# -----------------------------------------------------------------------------
# Proyecto: G10-LATAM-EQUIPO_41_KAIROS
# Stack:    Python 3.12 + FastAPI + Uvicorn · Docker Compose
# Requisitos: .env en la raíz · oci_config y clave_oci.pem un nivel arriba
# =============================================================================

# -----------------------------------------------------------------------------
# 1. VALIDAR EL COMPOSE (sin levantar nada)
# -----------------------------------------------------------------------------

# Sintaxis YAML correcta (no imprime nada si todo está bien)
docker compose config --quiet && echo "sintaxis OK"

# Ver el compose resuelto (rutas absolutas, variables expandidas)
docker compose config

# Listar servicios y volúmenes declarados
docker compose config --services
docker compose config --volumes

# ¿El compose actual coincide con el contenedor en ejecución?
docker compose config --hash="*"
docker inspect kairos_app --format '{{index .Config.Labels "com.docker.compose.config-hash"}}'


# -----------------------------------------------------------------------------
# 2. LEVANTAR / ACTUALIZAR (según qué cambió)
# -----------------------------------------------------------------------------

# Primera vez, o cambió el código / Dockerfile / requirements
docker compose up -d --build

# Cambió compose.yaml (volúmenes, puertos, env_file) → recrear contenedor
docker compose up -d --force-recreate

# Cambiaron código Y compose a la vez
docker compose up -d --build --force-recreate

# No cambió nada (solo confirmar que sigue arriba)
docker compose up -d

# Reiniciar solo Nginx (si añadiste HTTPS y regeneraste certs)
docker compose restart nginx


# -----------------------------------------------------------------------------
# 3. ESTADO Y LOGS
# -----------------------------------------------------------------------------

# Estado y salud del contenedor (debe decir "healthy")
docker compose ps

# Logs en vivo (Ctrl+C para salir)
docker compose logs -f

# Logs solo de un servicio
docker compose logs -f kairos
docker compose logs -f nginx

# Últimas 100 líneas
docker compose logs --tail=100 kairos


# -----------------------------------------------------------------------------
# 4. VERIFICAR MONTAJES Y VARIABLES
# -----------------------------------------------------------------------------

# Ver los montajes del contenedor (deben salir kairos_data + oci_config + clave_oci.pem)
docker inspect kairos_app --format '{{json .Mounts}}'

# ¿El archivo OCI se ve desde dentro?
docker exec kairos_app test -f /etc/secrets/oci_config && echo "oci_config OK"

# ¿La clave privada se ve desde dentro?
docker exec kairos_app test -f /etc/secrets/clave_oci.pem && echo "clave OK"

# ¿Las variables OCI llegaron al contenedor?
docker exec kairos_app printenv | grep OCI


# -----------------------------------------------------------------------------
# 5. ENTRAR AL CONTENEDOR
# -----------------------------------------------------------------------------

# Entrar como usuario kairos (UID 1000, el normal)
docker exec -it kairos_app bash

# Entrar como root (solo para depuración puntual)
docker exec -it -u root kairos_app bash

# Si bash no existe en la imagen
docker exec -it kairos_app sh


# -----------------------------------------------------------------------------
# 6. INSPECCIONAR EL VOLUMEN DE DATOS
# -----------------------------------------------------------------------------

# Ver el contenido de /app/data desde dentro
docker exec -it kairos_app ls -la /app/data
docker exec -it kairos_app ls -la /app/data/videos

# Saber dónde está el volumen en el host
docker volume inspect g10-latam-equipo_41_kairos_kairos_data

# Copiar datos del volumen a tu máquina (backup)
docker cp kairos_app:/app/data ./data_backup

# Copiar un archivo de tu máquina al volumen
docker cp ./archivo_local kairos_app:/app/data/


# -----------------------------------------------------------------------------
# 7. DETENER Y LIMPIAR
# -----------------------------------------------------------------------------

# Detener sin borrar el contenedor
docker compose stop

# Volver a arrancar lo detenido
docker compose start

# Detener y borrar contenedor (el volumen kairos_data SE CONSERVA)
docker compose down

# ⚠️ PELIGRO: borra también el volumen → pierdes videos, respaldos, estadísticas
docker compose down -v

# Ver espacio que ocupan imágenes, contenedores y volúmenes
docker system df


# -----------------------------------------------------------------------------
# 8. ACTUALIZAR CÓDIGO DESDE GITHUB
# -----------------------------------------------------------------------------

# Traer cambios del repo
git pull

# Reconstruir y levantar con el código nuevo
docker compose up -d --build


# -----------------------------------------------------------------------------
# 9. HTTPS LOCAL CON MKCERT (si lo configuraste)
# -----------------------------------------------------------------------------

# Generar certificados locales (solo una vez, o si cambias de dominio)
mkcert -key-file nginx/certs/key.pem -cert-file nginx/certs/cert.pem localhost 127.0.0.1 ::1

# Aplicar cambios de Nginx (si cambió nginx.conf o los certs)
docker compose restart nginx

# Verificar HTTPS local
curl -k https://localhost/health


# -----------------------------------------------------------------------------
# 10. PRODUCCIÓN CON CERTBOT (si lo configuraste)
# -----------------------------------------------------------------------------

# Obtener certificado Let's Encrypt (solo la primera vez)
docker compose run --rm certbot certonly --webroot --webroot-path=/var/www/certbot \
  --email tu-email@ejemplo.com --agree-tos --no-eff-email \
  -d tu-dominio.com

# Reiniciar Nginx para cargar el certificado
docker compose restart nginx


# =============================================================================
# RESUMEN: ¿QUÉ COMANDO USO?
# -----------------------------------------------------------------------------
# Cambié código Python / Dockerfile / requirements  → up -d --build
# Cambié compose.yaml (volúmenes, puertos, env)     → up -d --force-recreate
# Cambié código Y compose                           → up -d --build --force-recreate
# No cambié nada, solo verificar                    → up -d
# Quiero ver si está sano                           → ps + logs -f
# Quiero verificar montajes                         → inspect .Mounts + test -f
# Quiero entrar al contenedor                       → exec -it kairos_app bash
# Quiero backup de datos                            → docker cp kairos_app:/app/data
# Quiero detener sin perder datos                   → down (NUNCA down -v)
# =============================================================================