# Despliegue en OCI Compute (Always Free)

Guía para publicar Kairos en una máquina virtual **Always Free** de Oracle Cloud (HU-82).
Todo lo que se instala está en [`deploy/`](../deploy/):

| Archivo | Qué hace |
|---|---|
| `deploy/instalar.sh` | Instala paquetes, crea el entorno, el servicio y nginx. Se vuelve a ejecutar para actualizar. |
| `deploy/kairos.service` | Servicio systemd: mantiene la app encendida y la reinicia si se cae. |
| `deploy/nginx-kairos.conf` | Publica el puerto 80 y pasa las solicitudes a uvicorn (127.0.0.1:8000). |

> **Costo cero:** usa solo formas marcadas *Always Free* y no actualices la cuenta a
> "Pay As You Go". Crea el presupuesto de 1 USD con alerta (ver [SETUP_OCI.md](SETUP_OCI.md)).

## 1. Crear la instancia

1. Consola de OCI → **Compute → Instances → Create instance**.
2. **Image:** Canonical **Ubuntu 24.04** (trae Python 3.12; las dependencias están verificadas
   para Python 3.12 en x86 y en ARM).
3. **Shape:** *Ampere* **VM.Standard.A1.Flex** con 1 OCPU y 6 GB de memoria (dentro de la
   capa Always Free), o **VM.Standard.E2.1.Micro** si Ampere no tiene capacidad en tu región.
4. **Networking:** la VCN por defecto con **subred pública** y **IP pública** asignada.
5. **SSH keys:** sube tu clave pública (o descarga la que genera OCI).
6. Crea la instancia y copia su **IP pública**.

## 2. Abrir el puerto 80

**Networking → Virtual Cloud Networks →** tu VCN **→ Security Lists → Default Security List →
Add Ingress Rules**:

- Source CIDR: `0.0.0.0/0`
- IP Protocol: TCP
- Destination Port Range: `80`

(El firewall interno de la instancia lo abre el script de instalación.)

## 3. Instalar Kairos

```bash
ssh ubuntu@<IP_PUBLICA>
git clone https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS.git kairos
cd kairos
sudo bash deploy/instalar.sh
```

La primera vez crea `/opt/kairos/.env` desde `.env.example`. Complétalo:

```bash
sudo nano /opt/kairos/.env
```

Como mínimo: `LLM_PROVIDER=gemini` y `GEMINI_API_KEY=...`. Para guardar en Object Storage,
copia la configuración de OCI a la instancia (desde tu computadora):

```bash
scp ~/.oci/config ~/.oci/oci_api_key.pem ubuntu@<IP_PUBLICA>:/tmp/
# en la instancia:
sudo mkdir -p /home/kairos/.oci && sudo mv /tmp/config /tmp/oci_api_key.pem /home/kairos/.oci/
sudo sed -i 's#key_file=.*#key_file=/home/kairos/.oci/oci_api_key.pem#' /home/kairos/.oci/config
sudo chown -R kairos:kairos /home/kairos/.oci && sudo chmod 600 /home/kairos/.oci/*
```

y en `/opt/kairos/.env`: `OCI_CONFIG_FILE=/home/kairos/.oci/config`. Luego vuelve a ejecutar
`sudo bash deploy/instalar.sh`.

## 4. Comprobar

- `http://<IP_PUBLICA>/` abre la interfaz.
- `http://<IP_PUBLICA>/health` responde `"status": "ok"` y `"oci_disponible": true` si OCI quedó bien.
- Estado y registros del servicio:

  ```bash
  systemctl status kairos
  journalctl -u kairos -f
  ```

## 5. Actualizar

```bash
cd ~/kairos && git pull && sudo bash deploy/instalar.sh
```

## Notas

- **Voces:** el video y el podcast usan Gemini TTS; si no está disponible, `espeak-ng`
  (instalado por el script), que suena más robótico.
- **ChromaDB** (`VECTOR_STORE=chroma`) es opcional: `sudo -u kairos /opt/kairos/.venv/bin/pip install chromadb`.
- La app escucha solo en `127.0.0.1:8000`; lo único expuesto es nginx en el puerto 80.
