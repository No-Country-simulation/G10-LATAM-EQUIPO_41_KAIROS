# Guía: cuenta OCI, claves API y bucket privado (Always Free)

**Objetivo:** dejar listo OCI Object Storage para que NuevaMente guarde los documentos originales y los JSON generados, sin generar costos.
**Tiempo estimado:** 30–45 minutos, más la espera de verificación de la cuenta si Oracle la demora.

> Las pantallas de Oracle cambian con frecuencia. Si un menú no coincide con esta guía, busca el nombre de la opción en la barra de búsqueda de la consola.

---

## Paso 1. Crear la cuenta Oracle Cloud Free Tier

1. Entra a `https://www.oracle.com/cloud/free/` y elige **Start for free**.
2. Regístrate con un correo que uses de forma estable (no uno temporal).
3. Elige la **región de origen (home region)** con cuidado: **no se puede cambiar después**, y los recursos Always Free solo se crean en ella. Elige una región cercana que aparezca en el selector (por ejemplo São Paulo, Santiago o Bogotá, si están disponibles).
4. Oracle pide una **tarjeta de crédito o débito solo para verificar identidad**. Según su política, no cobra si te mantienes en recursos gratuitos, pero **verifica las condiciones vigentes** en la página de Free Tier antes de aceptar.
5. Espera el correo de activación y entra a la consola: `https://cloud.oracle.com`.

**Reglas para no pagar nada:**
- Al registrarte suele haber un periodo de prueba con créditos. Pasado ese periodo, la cuenta queda en Always Free **solo si NO la actualizas a "Pay As You Go"**. No aceptes esa actualización.
- Crea únicamente recursos marcados como **Always Free** (Object Storage en tier **Standard**, sin replicación ni tiers de pago).
- Confirma las cuotas vigentes (almacenamiento y solicitudes gratuitas) en la documentación oficial de Oracle. Las cifras pueden cambiar.

---

## Paso 2. Anotar el OCID del tenancy y el namespace

1. Arriba a la derecha, abre el menú de perfil y elige **Tenancy: (tu nombre)**.
2. Copia el **OCID** del tenancy (empieza con `ocid1.tenancy.oc1..`).
3. En la misma pantalla verás el **Object Storage namespace**. Anótalo.

Para simplificar, el bucket se crea en el **compartimento raíz** (que es el tenancy). No necesitas crear más compartimentos.

---

## Paso 3. Crear tu clave API

1. Menú de perfil → **User settings** (o **My profile**).
2. Sección **API keys** → **Add API key**.
3. Elige **Generate API key pair**.
4. Pulsa **Download private key** y guarda el archivo `.pem`.
5. Pulsa **Add**. Te mostrará una **vista previa del archivo de configuración**. Déjala abierta o cópiala.

---

## Paso 4. Crear el archivo de configuración local

1. Crea la carpeta `.oci` en tu carpeta de usuario:
   - Linux/macOS: `~/.oci/`
   - Windows: `C:\Users\TU_USUARIO\.oci\`
2. Mueve la clave privada ahí y renómbrala `oci_api_key.pem`.
3. En Linux/macOS restringe sus permisos: `chmod 600 ~/.oci/oci_api_key.pem`
4. Crea el archivo `config` (sin extensión) con el contenido de la vista previa del paso 3, cambiando `key_file` a la ruta real:

```ini
[DEFAULT]
user=ocid1.user.oc1..xxxxxxxx
fingerprint=xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx
tenancy=ocid1.tenancy.oc1..xxxxxxxx
region=sa-saopaulo-1
key_file=~/.oci/oci_api_key.pem
```

En Windows, escribe la ruta completa en `key_file`, por ejemplo `C:\Users\TU_USUARIO\.oci\oci_api_key.pem`.

> **Seguridad:** la carpeta `.oci` y el `.pem` **nunca** se suben a Git ni se comparten por chat. Si se filtran, elimina esa API key en la consola y genera otra.

---

## Paso 5. Crear el bucket y verificar todo con el script

Desde la raíz del repositorio:

```bash
pip install oci
python scripts/oci_bootstrap.py
```

El script:
1. Valida tu configuración.
2. Crea el bucket **`nuevamente-contenidos-educativos`** (Standard, **privado**) o verifica el existente.
3. Prueba subir, leer, listar y borrar un objeto temporal.
4. Imprime las variables para tu `.env`.

Si el nombre del bucket ya existe en tu namespace, usa otro:
`python scripts/oci_bootstrap.py --bucket nuevamente-tuequipo`

### Alternativa manual (consola)
**Storage → Buckets → Create Bucket**: nombre `nuevamente-contenidos-educativos`, **Default Storage Tier: Standard**, sin acceso público, cifrado por defecto. Luego corre el script solo para verificar.

### Si el script falla

| Mensaje | Causa probable | Solución |
|---|---|---|
| Autenticación fallida (401) | Huella, usuario o clave no coinciden | Revisa que el `config` sea el de la vista previa y que la API key siga activa |
| Sin permisos o no encontrado (403/404) | Compartimento o región equivocados | Usa el OCID del tenancy y la región de tu cuenta |
| Conflicto (409) | Nombre de bucket ya usado | Cambia el nombre con `--bucket` |
| No se pudo conectar | Red o proxy | Revisa tu conexión y la región del `config` |
| No encuentro la clave privada | `key_file` mal escrito | Corrige la ruta en `config` |

---

## Paso 6. Guardar las variables en `.env`

Copia lo que imprime el script a tu `.env` local (que debe estar en `.gitignore`):

```env
OCI_CONFIG_FILE=~/.oci/config
OCI_PROFILE=DEFAULT
OCI_COMPARTMENT_ID=ocid1.tenancy.oc1..xxxxxxxx
OCI_BUCKET=nuevamente-contenidos-educativos
OCI_NAMESPACE=tu_namespace
```

---

## Paso 7. Protégete de costos inesperados

1. En **Billing & Cost Management → Budgets**, crea un presupuesto de **1 USD** con alerta a tu correo. Es una red de seguridad por si algo se crea fuera de Always Free.
2. Revisa **Cost Analysis** una vez por semana.
3. No habilites replicación, versionado innecesario ni otros servicios de pago.

---

## Paso 8. Trabajo en equipo

Elige una de estas opciones:

- **Simple:** cada integrante crea su propia cuenta Free Tier y su bucket para desarrollar. La cuenta principal (la que se usará en la demo) queda a cargo de una sola persona.
- **Compartida:** la persona responsable crea un usuario y una clave API por integrante en **Identity → Users**, los agrega a un grupo y asigna una política limitada al bucket, por ejemplo:

```
Allow group NuevaMenteDev to manage objects in tenancy where target.bucket.name='nuevamente-contenidos-educativos'
Allow group NuevaMenteDev to read buckets in tenancy
```

Nunca compartan una misma clave privada entre varias personas.

---

## Checklist de la tarjeta de Trello

- [ ] Cuenta creada y verificada, en Free Tier
- [ ] Sin actualizar a Pay As You Go
- [ ] OCID del tenancy y namespace anotados (fuera del repo)
- [ ] Clave API generada y `~/.oci/config` creado
- [ ] `python scripts/oci_bootstrap.py` termina con **OK**
- [ ] Bucket **privado**, tier **Standard**
- [ ] Variables guardadas en `.env` (ignorado por Git)
- [ ] Presupuesto de 1 USD con alerta creado
