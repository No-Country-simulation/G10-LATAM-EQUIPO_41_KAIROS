import oci
import urllib3 # 1. Importar librería de conexiones

# 2. Desactivar las advertencias de seguridad en la consola para que no molesten
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Carga la configuración de autenticación desde el archivo predeterminado ~/.oci/config
config = oci.config.from_file()

# Inicializa el cliente de Object Storage
object_storage = oci.object_storage.ObjectStorageClient(config)

# 3. Forzar al cliente a ignorar el proxy corporativo
object_storage.base_client.session.verify = False

# Variables de entorno
namespace = object_storage.get_namespace().data
bucket_name = "nuevamente-contenidos-educativos" # Reemplaza con el nombre exacto de tu bucket
file_path = "documento_prueba.txt"
object_name = "documento_prueba.txt"

# Creamos un archivo local de prueba
with open(file_path, "w") as f:
    f.write("Prueba de conectividad para el Hackathon ONE G10")

# Subimos el archivo al bucket para persistir la información
with open(file_path, "rb") as f:
    object_storage.put_object(
        namespace,
        bucket_name,
        object_name,
        f
    )

print(f"Archivo '{object_name}' subido exitosamente a OCI Object Storage.")