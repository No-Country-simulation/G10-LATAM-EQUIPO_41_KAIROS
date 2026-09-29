# scripts/test_oci_conexion.py
from nuevamente.storage.oci_client import get_storage_service
from nuevamente.config import settings

def probar_oci_real():
    print(f"=== Diagnóstico OCI Storage ===")
    print(f"Bucket objetivo: {settings.oci_bucket}")
    print(f"Perfil OCI: {settings.oci_profile}")
    print(f"Archivo de config: {settings.oci_config_file}")
    
    storage = get_storage_service()
    
    if not storage.disponible_oci():
        print("\n❌ ALERTA: OCI Client no se inicializó correctamente.")
        print("  Causas posibles:")
        print("  1. No está instalado el paquete 'oci' (ejecuta: pip install oci).")
        print("  2. El archivo ~/.oci/config no existe o no tiene el formato correcto.")
        print("  3. El perfil especificado no coincide.")
        return

    print("\n✓ OCI Client inicializado. Probando subida de objeto real...")
    
    payload_prueba = {
        "origen": "Prueba Hackathon ONE G10",
        "modulo": "storage/oci_client.py",
        "status": "conexion_exitosa"
    }
    
    resultado = storage.subir_json("pruebas/diagnostico_oci.json", payload_prueba)
    
    print(f"\nResultado de Subida:")
    print(f" - Bucket: {resultado.bucket}")
    print(f" - ID Objeto: {resultado.objeto_id}")
    print(f" - Status Upload: {resultado.status_upload}")

    if resultado.status_upload == "completado":
        print("\n✓ ¡Éxito! El archivo se guardó en el Bucket de Oracle Cloud.")
        
        # Probar lectura
        contenido_descargado = storage.descargar_texto("pruebas/diagnostico_oci.json")
        print(f"✓ Descarga verificada desde OCI: {contenido_descargado}")
    else:
        print("\n❌ Falló la subida a OCI. La aplicación redirigió el archivo a data/fallback/.")

if __name__ == "__main__":
    probar_oci_real()