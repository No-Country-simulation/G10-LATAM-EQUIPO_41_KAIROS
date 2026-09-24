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
from dataclasses import dataclass
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

    def disponible_oci(self) -> bool:
        return self._cliente_oci is not None

    def subir_texto(self, objeto_id: str, contenido: str, content_type: str = "application/json") -> ResultadoSubida:
        if self._cliente_oci is not None:
            try:
                namespace = self._cliente_oci.get_namespace().data
                self._cliente_oci.put_object(
                    namespace, settings.oci_bucket, objeto_id, contenido.encode("utf-8"), content_type=content_type
                )
                return ResultadoSubida(bucket=settings.oci_bucket, objeto_id=objeto_id, status_upload="completado")
            except Exception:
                pass  # cae a fallback local abajo

        destino = self._fallback_dir / objeto_id.replace("/", "__")
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido, encoding="utf-8")
        return ResultadoSubida(bucket=settings.oci_bucket, objeto_id=objeto_id, status_upload="fallido_local")

    def subir_json(self, objeto_id: str, data: dict) -> ResultadoSubida:
        return self.subir_texto(objeto_id, json.dumps(data, ensure_ascii=False, indent=2))

    def descargar_texto(self, objeto_id: str) -> str | None:
        if self._cliente_oci is not None:
            try:
                namespace = self._cliente_oci.get_namespace().data
                resp = self._cliente_oci.get_object(namespace, settings.oci_bucket, objeto_id)
                return resp.data.content.decode("utf-8")
            except Exception:
                pass

        destino = self._fallback_dir / objeto_id.replace("/", "__")
        if destino.is_file():
            return destino.read_text(encoding="utf-8")
        return None


_instancia: StorageService | None = None


def get_storage_service() -> StorageService:
    global _instancia
    if _instancia is None:
        _instancia = StorageService()
    return _instancia
