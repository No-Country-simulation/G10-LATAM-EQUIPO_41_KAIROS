import json
import os
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

os.environ["OCI_CONFIG_FILE"] = str(Path(tempfile.gettempdir()) / "sin-oci-evidencia")
os.environ["FALLBACK_DIR"] = str(Path(tempfile.gettempdir()) / "kairos-fallback-evidencia")

from nuevamente.storage.oci_client import StorageService


class Error401(Exception):
    status = 401


class Cliente401:
    def get_namespace(self):
        raise Error401("NotAuthenticated")

    def put_object(self, *args, **kwargs):
        raise Error401("NotAuthenticated")


storage = StorageService()
storage._cliente_oci = Cliente401()
storage._namespace_oci = None
storage._error_hasta = 0.0
storage._motivo_oci = ""

resultado = {
    "escenario": "Simulacion local: OCI responde 401 NotAuthenticated",
    "comprobacion_real_de_conexion": {
        "oci_disponible": storage.disponible_oci(),
        "oci_motivo": storage.motivo_oci(),
    },
}

subida = storage.subir_texto("pruebas/diagnostico_401.txt", "prueba de respaldo")
resultado["subida_con_401"] = {
    "status_upload": subida.status_upload,
    "bucket": subida.bucket,
    "objeto_id": subida.objeto_id,
}

texto = json.dumps(resultado, ensure_ascii=False, indent=2) + "\n"
destino = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("diagnostico_401_simulado.json")
destino.write_text(texto, encoding="utf-8")
print(texto)
