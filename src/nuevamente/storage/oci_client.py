"""Persistencia en OCI Object Storage, con fallback local si OCI no esta configurado.

Responsables en el equipo Kairos G10: Ethan Espinoza Acosta (Backend Developer,
integracion con la API) y Gaspar Martinez Paiva (Data Engineer, cliente OCI).

Decision de diseno (igual que en el plan de trabajo del PM): si OCI falla o no
esta configurado, la app NO se cae. Guarda en data/fallback/ y marca
status_upload="fallido_local" — el fallo queda visible en la respuesta, nunca
oculto.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nuevamente.config import settings

logger = logging.getLogger(__name__)

_REINTENTO_CONEXION_SEG = 300


@dataclass
class ResultadoSubida:
    bucket: str
    objeto_id: str
    status_upload: str  # "completado" | "fallido_local"


class StorageService:
    """Interfaz unica que usa el resto de la app (api/, agents/)."""

    def __init__(self) -> None:
        self._namespace_oci: str | None = None
        self._motivo_oci = ""
        self._error_hasta = 0.0
        self._cliente_oci = self._intentar_crear_cliente_oci()
        self._fallback_dir = Path(settings.fallback_dir)
        self._fallback_dir.mkdir(parents=True, exist_ok=True)
        self._obtener_namespace_al_iniciar()

    def _intentar_crear_cliente_oci(self):
        try:
            import oci  # type: ignore
        except ImportError:
            self._motivo_oci = "La libreria oci no esta instalada."
            return None

        config_path = Path(settings.oci_config_file).expanduser()
        if not config_path.exists():
            self._motivo_oci = f"No existe el archivo de configuracion de OCI ({settings.oci_config_file})."
            return None
        try:
            config = oci.config.from_file(str(config_path), settings.oci_profile)
            oci.config.validate_config(config)
            cliente = oci.object_storage.ObjectStorageClient(config)
            if not settings.oci_ssl_verify:
                logger.warning("OCI_SSL_VERIFY=false: el cliente de OCI no verifica certificados TLS.")
                cliente.base_client.session.verify = False
            return cliente
        except Exception as exc:
            logger.warning("OCI Object Storage no disponible, se usa el respaldo local: %s", exc)
            self._motivo_oci = f"La configuracion de OCI no es valida: {exc}"
            return None

    def _obtener_namespace_al_iniciar(self) -> None:
        if self._cliente_oci is None:
            return
        try:
            self._namespace_oci = self._cliente_oci.get_namespace().data
            self._motivo_oci = ""
            self._error_hasta = 0.0
        except Exception as exc:
            self._registrar_fallo(exc)

    def _namespace(self) -> str:
        """El namespace de OCI se consulta una sola vez y se reutiliza: cada consulta es una
        solicitud que cuenta contra el cupo gratuito mensual."""
        if self._namespace_oci is None:
            if self._cliente_oci is None:
                raise RuntimeError("Cliente OCI no disponible")
            self._namespace_oci = self._cliente_oci.get_namespace().data
        return self._namespace_oci

    def disponible_oci(self) -> bool:
        """OCI acepta de verdad las credenciales. No basta con que exista el config: una llave
        de API que no esta registrada en la cuenta da 401 en cada subida. La conexion se
        comprueba una vez (pidiendo el namespace) y se vuelve a probar cada pocos minutos si
        fallo; cada subida actualiza el resultado."""
        if self._cliente_oci is None:
            return False
        if self._namespace_oci is not None:
            return True
        if time.monotonic() < self._error_hasta:
            return False
        try:
            self._namespace()
            return True
        except Exception as exc:
            self._registrar_fallo(exc)
            return False

    def motivo_oci(self) -> str:
        """Por que no se esta guardando en OCI, en palabras para el usuario ("" si funciona)."""
        return "" if self.disponible_oci() else self._motivo_oci

    def _registrar_fallo(self, exc: Exception) -> None:
        self._error_hasta = time.monotonic() + _REINTENTO_CONEXION_SEG
        estado = getattr(exc, "status", None)
        if estado == 401:
            self._motivo_oci = (
                "OCI rechazo las credenciales (401): la llave de API del config no esta registrada "
                "en la cuenta. Subela en la consola de OCI (Mi perfil -> Claves de API)."
            )
        elif estado == 404:
            self._motivo_oci = f"No se encontro el bucket {settings.oci_bucket} o el namespace (404)."
        elif estado == 403:
            self._motivo_oci = "El usuario de OCI no tiene permiso sobre el bucket (403)."
        else:
            self._motivo_oci = f"No se pudo conectar con OCI: {str(exc)[:200]}"

    def subir_bytes(self, objeto_id: str, datos: bytes, content_type: str = "application/octet-stream") -> ResultadoSubida:
        if self._cliente_oci is not None:
            try:
                self._cliente_oci.put_object(
                    self._namespace(), settings.oci_bucket, objeto_id, datos, content_type=content_type
                )
                self._motivo_oci, self._error_hasta = "", 0.0
                return ResultadoSubida(bucket=settings.oci_bucket, objeto_id=objeto_id, status_upload="completado")
            except Exception as exc:
                logger.warning("No se pudo subir %s a OCI, se guarda en el respaldo local: %s", objeto_id, exc)
                self._registrar_fallo(exc)

        destino = self._fallback_dir / objeto_id.replace("/", "__")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(datos)
        return ResultadoSubida(bucket=settings.oci_bucket, objeto_id=objeto_id, status_upload="fallido_local")

    def subir_texto(self, objeto_id: str, contenido: str, content_type: str = "application/json") -> ResultadoSubida:
        return self.subir_bytes(objeto_id, contenido.encode("utf-8"), content_type)

    def subir_json(self, objeto_id: str, data: dict) -> ResultadoSubida:
        return self.subir_texto(objeto_id, json.dumps(data, ensure_ascii=False, indent=2))

    def descargar_bytes(self, objeto_id: str) -> bytes | None:
        if self._cliente_oci is not None:
            try:
                resp = self._cliente_oci.get_object(self._namespace(), settings.oci_bucket, objeto_id)
                return resp.data.content
            except Exception:
                pass

        destino = self._fallback_dir / objeto_id.replace("/", "__")
        if destino.is_file():
            return destino.read_bytes()
        return None

    def descargar_texto(self, objeto_id: str) -> str | None:
        datos = self.descargar_bytes(objeto_id)
        return None if datos is None else datos.decode("utf-8")

    def listar(self, prefijo: str) -> Iterator[tuple[str, datetime]]:
        """(objeto_id, fecha de creacion) de cada objeto guardado bajo `prefijo`, en OCI y
        en el respaldo local (un material puede estar en cualquiera de los dos)."""
        vistos: set[str] = set()
        if self._cliente_oci is not None:
            try:
                namespace = self._namespace()
                inicio = None
                while True:
                    resp = self._cliente_oci.list_objects(
                        namespace, settings.oci_bucket, prefix=prefijo, start=inicio, fields="timeCreated"
                    )
                    for obj in resp.data.objects:
                        vistos.add(obj.name)
                        yield obj.name, (obj.time_created or datetime.now()).astimezone()
                    inicio = resp.data.next_start_with
                    if not inicio:
                        break
            except Exception:
                pass

        for archivo in sorted(self._fallback_dir.glob(prefijo.replace("/", "__") + "*")):
            objeto_id = archivo.name.replace("__", "/")
            if archivo.is_file() and objeto_id not in vistos:
                yield objeto_id, datetime.fromtimestamp(archivo.stat().st_mtime).astimezone()


_instancia: StorageService | None = None


def get_storage_service() -> StorageService:
    global _instancia
    if _instancia is None:
        _instancia = StorageService()
    return _instancia
