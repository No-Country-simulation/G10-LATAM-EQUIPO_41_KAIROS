# Checklist de Docker Compose

Comprobaciones para levantar Kairos y verificar que quedó sano.
Docker es **opcional** en local: también puedes correrlo solo con Python
(`make install` y `make run-api`). Docker es obligatorio solo si despliegas en Render.

## 1. Primera vez (levantar)

1. Requisitos: archivo `.env` en la raíz del repo.
2. Construir y levantar:

   ```bash
   docker compose up -d --build
   ```

   → La app queda en http://localhost:8000/

3. El contenedor debe quedar `healthy`:

   ```bash
   docker compose ps
   ```

## 2. Verificar que está sano

4. La app responde:

   ```bash
   curl -s http://localhost:8000/health
   ```

5. (Solo si usas OCI) las credenciales se montaron:

   ```bash
   docker exec kairos_app test -f /etc/secrets/oci_config && echo "existe" || echo "no existe"
   ```

## 3. Detener

```bash
docker compose down    # los datos se conservan
```

Para logs, volúmenes, actualizar código, HTTPS y demás, ver [`compose-comandos.md`](compose-comandos.md).
