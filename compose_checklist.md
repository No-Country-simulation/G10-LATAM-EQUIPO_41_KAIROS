# 1. El contenedor está healthy
docker compose ps

# 2. El montaje aparece en inspect (deben salir 2: kairos_data y oci_config)
docker inspect kairos_app --format '{{json .Mounts}}'

# 3. El archivo se ve desde dentro
docker exec kairos_app test -f /etc/secrets/oci_config && echo "existe" || echo "no existe"

# 4. La app responde
curl -s http://localhost:8000/health