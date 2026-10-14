"""Persistencia en OCI Object Storage, con fallback local si OCI no está configurado.

Responsables en el equipo Kairos G10: Ethan Espinoza Acosta (Backend Developer,
integración con la API) y Gaspar Martinez Paiva (Data Engineer, cliente OCI).

Decisión de diseño (igual que en el plan de trabajo del PM): si OCI falla o no
está configurado, la app NO se cae. Guarda en `data/fallback/` y marca
`status_upload="fallido_local"` — el fallo queda visible en la respuesta, nunca
oculto.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from nuevamente.config import settings


@dataclass
class ResultadoSubida:
    bucket: str
    objeto_id: str
    status_upload: str  # "completado" | "fallido_local"


class StorageService:
    """Interfaz única que usa el resto de la app (api/, agents/)."""

    def __init__(self) -> None:
        self._namespace_oci: str | None = None
        self._cliente_oci = self._intentar_crear_cliente_oci()
        self._fallback_dir = Path(settings.fallback_dir)
        self._fallback_dir.mkdir(parents=True, exist_ok=True)

    def _intentar_crear_cliente_oci(self):
        try:
            import oci  # type: ignore
        except ImportError:
            return None

        config_path = Path(settings.oci_config_file).expanduser()
        if not config_path.exists():
            return None
        try:
            config = oci.config.from_file(str(config_path), settings.oci_profile)
            oci.config.validate_config(config)
            return oci.object_storage.ObjectStorageClient(config)
        except Exception:
            # Cualquier problema de credenciales o red: caemos a fallback local,
            # sin tumbar la aplicación.
            return None

    def _namespace(self) -> str:
        """El namespace de OCI se consulta una sola vez y se reutiliza: cada consulta es una
        solicitud que cuenta contra el cupo gratuito mensual."""
        if self._namespace_oci is None:
            self._namespace_oci = self._cliente_oci.get_namespace().data
        return self._namespace_oci

    def disponible_oci(self) -> bool:
        return self._cliente_oci is not None

    def subir_bytes(self, objeto_id: str, datos: bytes, content_type: str = "application/octet-stream") -> ResultadoSubida:
        if self._cliente_oci is not None:
            try:
                self._cliente_oci.put_object(
                    self._namespace(), settings.oci_bucket, objeto_id, datos, content_type=content_type
                )
                return ResultadoSubida(bucket=settings.oci_bucket, objeto_id=objeto_id, status_upload="completado")
            except Exception:
                pass  # cae a fallback local abajo

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
        """(objeto_id, fecha de creación) de cada objeto guardado bajo `prefijo`, en OCI y
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
                pass  # sin red o sin permiso de listar: queda el respaldo local

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
