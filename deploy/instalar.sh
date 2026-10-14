#!/usr/bin/env bash
# Instala Kairos en una instancia Always Free de OCI Compute con Ubuntu 22.04/24.04 (HU-82).
#
# Uso, en la instancia (ver docs/DEPLOY_OCI.md):
#   git clone https://github.com/No-Country-simulation/G10-LATAM-EQUIPO_41_KAIROS.git kairos
#   cd kairos && sudo bash deploy/instalar.sh
#
# Se puede volver a ejecutar para actualizar: trae el código, reinstala dependencias y reinicia.
set -euo pipefail

DESTINO=/opt/kairos
ORIGEN="$(cd "$(dirname "$0")/.." && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "Ejecuta con sudo: sudo bash deploy/instalar.sh" >&2
  exit 1
fi

echo "==> Paquetes del sistema (Python, ffmpeg, voz de respaldo, fuentes, nginx)"
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-venv python3-pip git rsync curl ffmpeg espeak-ng fonts-dejavu fonts-liberation nginx

echo "==> Usuario de servicio y código en $DESTINO"
id -u kairos >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin kairos
mkdir -p "$DESTINO"
rsync -a --delete --exclude .venv --exclude .env --exclude data "$ORIGEN"/ "$DESTINO"/
mkdir -p "$DESTINO/data/fallback" "$DESTINO/data/vectorstore" "$DESTINO/data/videos" "$DESTINO/data/estadisticas"

if [[ ! -f "$DESTINO/.env" ]]; then
  cp "$DESTINO/.env.example" "$DESTINO/.env"
  echo "    Se creó $DESTINO/.env desde .env.example: complétalo (GEMINI_API_KEY, OCI_*) y vuelve a ejecutar."
fi

echo "==> Entorno virtual y dependencias"
python3 -m venv "$DESTINO/.venv"
"$DESTINO/.venv/bin/pip" install --upgrade pip
# desde la carpeta del proyecto: requirements.txt instala el paquete con "-e ."
(cd "$DESTINO" && "$DESTINO/.venv/bin/pip" install -r requirements.txt)
chown -R kairos:kairos "$DESTINO"
chmod 600 "$DESTINO/.env"

echo "==> Servicio systemd"
cp "$DESTINO/deploy/kairos.service" /etc/systemd/system/kairos.service
systemctl daemon-reload
systemctl enable --now kairos
systemctl restart kairos

echo "==> nginx en el puerto 80"
cp "$DESTINO/deploy/nginx-kairos.conf" /etc/nginx/sites-available/kairos
ln -sf /etc/nginx/sites-available/kairos /etc/nginx/sites-enabled/kairos
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> Firewall de la instancia (las imágenes de OCI bloquean todo salvo SSH)"
if ! iptables -C INPUT -p tcp --dport 80 -m state --state NEW -j ACCEPT 2>/dev/null; then
  iptables -I INPUT 6 -p tcp --dport 80 -m state --state NEW -j ACCEPT
  if command -v netfilter-persistent >/dev/null; then netfilter-persistent save; fi
fi

echo "==> Comprobación"
for i in $(seq 1 20); do
  if curl -fsS http://127.0.0.1/health; then echo; break; fi
  sleep 2
done
echo "Listo. Abre http://<IP pública de la instancia>/ (y revisa la Security List: TCP 80 abierto)."
