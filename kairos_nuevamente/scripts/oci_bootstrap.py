#!/usr/bin/env python3
"""Prepara OCI Object Storage (capa Always Free) para NuevaMente.

Qué hace:
  1. Lee tu configuración de OCI (~/.oci/config) y la valida.
  2. Obtiene el namespace de Object Storage de tu tenancy.
  3. Crea el bucket (Standard, PRIVADO) si no existe, o verifica el existente.
  4. Prueba el ciclo completo: subir, leer, listar y borrar un objeto temporal.
  5. Imprime las variables que debes copiar a tu .env.

Uso:
  pip install oci
  python scripts/oci_bootstrap.py
  python scripts/oci_bootstrap.py --bucket mi-bucket --profile DEFAULT

Variables de entorno opcionales (los argumentos tienen prioridad):
  OCI_CONFIG_FILE, OCI_PROFILE, OCI_COMPARTMENT_ID, OCI_BUCKET

Este script NUNCA imprime claves privadas ni huellas completas.
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

try:
    import oci
except ImportError:
    sys.exit("Falta el SDK de OCI. Instálalo con: pip install oci")

BUCKET_POR_DEFECTO = "nuevamente-contenidos-educativos"
PREFIJO_PRUEBA = "_healthcheck/"


def parsear_argumentos() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Bootstrap de OCI Object Storage para NuevaMente")
    p.add_argument("--config", default=os.getenv("OCI_CONFIG_FILE", "~/.oci/config"),
                   help="Ruta del archivo de configuración de OCI")
    p.add_argument("--profile", default=os.getenv("OCI_PROFILE", "DEFAULT"),
                   help="Perfil dentro del archivo de configuración")
    p.add_argument("--compartment", default=os.getenv("OCI_COMPARTMENT_ID"),
                   help="OCID del compartimento (por defecto, el tenancy raíz)")
    p.add_argument("--bucket", default=os.getenv("OCI_BUCKET", BUCKET_POR_DEFECTO),
                   help="Nombre del bucket")
    p.add_argument("--sin-prueba", action="store_true",
                   help="No ejecutar la prueba de subir/leer/borrar")
    return p.parse_args()


def cargar_config(ruta: str, perfil: str) -> dict:
    archivo = Path(ruta).expanduser()
    if not archivo.exists():
        sys.exit(
            f"No encuentro el archivo de configuración: {archivo}\n"
            "Créalo siguiendo docs/SETUP_OCI.md (paso 4) o ejecuta: oci setup config"
        )
    try:
        config = oci.config.from_file(file_location=str(archivo), profile_name=perfil)
        oci.config.validate_config(config)
    except oci.exceptions.InvalidConfig as exc:
        sys.exit(f"La configuración de OCI es inválida: {exc}")
    except oci.exceptions.ProfileNotFound:
        sys.exit(f"El perfil '{perfil}' no existe en {archivo}.")

    clave = Path(config["key_file"]).expanduser()
    if not clave.exists():
        sys.exit(f"No encuentro la clave privada indicada en 'key_file': {clave}")
    return config


def asegurar_bucket(cliente, namespace: str, compartimento: str, nombre: str):
    """Devuelve (bucket, creado). Crea el bucket privado Standard si no existe."""
    try:
        bucket = cliente.get_bucket(namespace, nombre).data
        return bucket, False
    except oci.exceptions.ServiceError as exc:
        if exc.status != 404:
            raise
    detalles = oci.object_storage.models.CreateBucketDetails(
        name=nombre,
        compartment_id=compartimento,
        storage_tier="Standard",
        public_access_type="NoPublicAccess",
    )
    return cliente.create_bucket(namespace, detalles).data, True


def probar_ciclo(cliente, namespace: str, bucket: str) -> None:
    """Sube, lee, lista y borra un objeto temporal para confirmar permisos."""
    nombre = f"{PREFIJO_PRUEBA}{uuid.uuid4().hex}.txt"
    contenido = b"nuevamente-healthcheck"

    cliente.put_object(namespace, bucket, nombre, contenido, content_type="text/plain")
    leido = cliente.get_object(namespace, bucket, nombre).data.content
    if leido != contenido:
        raise RuntimeError("El contenido leído no coincide con el subido.")
    listado = cliente.list_objects(namespace, bucket, prefix=PREFIJO_PRUEBA).data.objects
    if nombre not in [o.name for o in listado]:
        raise RuntimeError("El objeto subido no aparece al listar el bucket.")
    cliente.delete_object(namespace, bucket, nombre)


def explicar_error(exc: oci.exceptions.ServiceError) -> str:
    if exc.status == 401:
        return ("Autenticación fallida (401). Revisa que 'fingerprint', 'user', 'tenancy' y "
                "'key_file' correspondan a la API key que subiste en la consola.")
    if exc.status in (403, 404):
        return (f"Sin permisos o recurso no encontrado ({exc.status}, {exc.code}). Revisa el OCID "
                "del compartimento, la región del config y que tu usuario pueda gestionar buckets.")
    if exc.status == 409:
        return ("Conflicto (409): el nombre del bucket ya existe en el namespace de otra "
                "configuración o está en proceso de eliminación. Prueba con otro nombre.")
    if exc.status == 429:
        return "Demasiadas solicitudes (429). Espera un momento y vuelve a intentar."
    return f"Error de OCI ({exc.status}, {exc.code}): {exc.message}"


def main() -> int:
    args = parsear_argumentos()
    config = cargar_config(args.config, args.profile)
    compartimento = args.compartment or config["tenancy"]

    print(f"Región de la configuración: {config['region']}")
    print(f"Compartimento: {'tenancy raíz' if compartimento == config['tenancy'] else 'personalizado'}")

    try:
        cliente = oci.object_storage.ObjectStorageClient(config)
        namespace = cliente.get_namespace().data
        print(f"Namespace de Object Storage: {namespace}")

        bucket, creado = asegurar_bucket(cliente, namespace, compartimento, args.bucket)
        print(f"Bucket '{args.bucket}': {'CREADO' if creado else 'ya existía'}")

        if bucket.public_access_type != "NoPublicAccess":
            print("⚠ ADVERTENCIA: el bucket NO es privado. Cámbialo a 'Private' en la consola "
                  "antes de subir documentos.")
        if bucket.storage_tier != "Standard":
            print(f"⚠ ADVERTENCIA: el tier es '{bucket.storage_tier}'. Usa Standard para "
                  "mantenerte en la capa Always Free.")

        if args.sin_prueba:
            print("Prueba de subir/leer/borrar omitida (--sin-prueba).")
        else:
            probar_ciclo(cliente, namespace, args.bucket)
            print("Prueba subir → leer → listar → borrar: OK")
    except oci.exceptions.ServiceError as exc:
        print(f"\n✗ {explicar_error(exc)}", file=sys.stderr)
        return 1
    except oci.exceptions.RequestException as exc:
        print(f"\n✗ No se pudo conectar con OCI (red o DNS): {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"\n✗ Falló la prueba de verificación: {exc}", file=sys.stderr)
        return 1

    print("\n✓ Listo. Copia estas variables a tu archivo .env (nunca al repositorio):\n")
    print(f"OCI_CONFIG_FILE={args.config}")
    print(f"OCI_PROFILE={args.profile}")
    print(f"OCI_COMPARTMENT_ID={compartimento}")
    print(f"OCI_BUCKET={args.bucket}")
    print(f"OCI_NAMESPACE={namespace}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
