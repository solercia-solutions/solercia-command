# Integración con Jira: importar un proyecto

Solercia Command puede traer un proyecto completo de Jira Cloud (épicas, historias, tareas,
subtareas, errores y sprints) a un proyecto de Command. La integración es **de solo lectura hacia
Jira**: nunca crea, edita, mueve ni comenta nada en Jira.

## 1. Crear el token de API de Atlassian

Usa un **token de API clásico** (sin alcances) de la cuenta que hará la lectura. Lo ideal es una
cuenta de servicio dedicada, con acceso solo a los proyectos que se van a importar.

1. Inicia sesión en Atlassian con esa cuenta y abre
   <https://id.atlassian.com/manage-profile/security/api-tokens>.
2. Elige **Crear token de API** (no la opción «con alcances»).
3. Escribe un nombre que identifique su uso, por ejemplo `solercia-command-importacion`, y elige
   la fecha de vencimiento más corta que sirva para tu operación.
4. Copia el token en ese momento: Atlassian no lo vuelve a mostrar.

El token hereda los permisos de la cuenta; por eso los permisos se controlan en Jira, no en el
token.

## 2. Permisos que necesita la cuenta en Jira

La cuenta debe tener, en cada proyecto que quieras importar:

| Permiso de Jira | Para qué se usa |
|---|---|
| **Examinar proyectos** (*Browse projects*) | Listar los proyectos y leer sus incidencias, incluidas épicas, subtareas y el campo de sprint |
| Acceso al producto **Jira Software** | Que el campo de sprint y los puntos de historia lleguen en la búsqueda |

No se necesita ningún permiso de creación, edición, transición ni administración. Si la
configuración de privacidad del sitio oculta los correos de los usuarios, la importación funciona
igual, pero las tareas quedan sin asignar (ver la sección 4).

## 3. Registrar el conector en Command

1. En **Conexiones**, sobre la tarjeta del conector Jira, elige **Registrar credenciales**.
2. Ingresa la URL del sitio (`https://<sitio>.atlassian.net`), el correo de la cuenta y el token.
   Command valida el par contra Jira (`/rest/api/3/myself`) antes de guardarlo.
3. El token se guarda cifrado y nunca vuelve a mostrarse ni se escribe en los registros. Solo se
   aceptan sitios `https` del dominio `atlassian.net`.

## 4. Importar un proyecto

Con el rol de administrador o gerente y una cuenta activa en el conector, elige **Importar
proyecto** en la tarjeta de Jira. El asistente tiene tres pasos:

1. **Elegir proyecto**: lista los proyectos que la cuenta puede ver e indica los que ya se
   importaron.
2. **Revisar**: muestra cuántas épicas, historias, subtareas y errores hay, los sprints, la
   equivalencia de estados y la estimación total. Este paso no guarda nada. Puedes ajustar el
   nombre y el código del proyecto que se creará en Command (por defecto, el nombre de Jira y su
   clave).
3. **Importar**: crea o actualiza todo en una sola operación y muestra el resumen.

### Cómo se trasladan los datos

| En Jira | En Command |
|---|---|
| Proyecto | Proyecto nuevo con metodología **Scrum** y su tablero por defecto |
| Épica, historia, tarea, subtarea, error | Tarea del tipo equivalente; la jerarquía épica → historia → subtarea se conserva |
| Clave de la incidencia (`PROJ-12`) | Se conserva como referencia externa; la tarea recibe además su clave propia de Command |
| Estado | Por su categoría en Jira: «Por hacer» → primer estado del tablero, «En curso» → «In Progress», «Listo» → último estado |
| Estimación original (segundos) | Horas estimadas (`segundos / 3600`) |
| Puntos de historia | Puntos de estimación (los decimales se redondean hacia arriba) |
| Sprint futuro / activo / cerrado | Sprint en borrador / activo / cerrado, con sus fechas |
| Responsable | Se asigna al miembro de la organización con el mismo correo; si no hay coincidencia, la tarea queda sin asignar y su descripción indica el responsable original |

Casos que el resumen informa:

- **Subtareas sin padre**: si el padre no pertenece al proyecto importado, la subtarea se crea sin
  padre.
- **Tareas sin asignar**: el correo de Jira no corresponde a ningún miembro de la organización, o
  Jira no lo comparte.
- **Estados sin equivalencia exacta**: se ubican por su categoría de Jira.

En los proyectos de Jira administrados por la empresa (*company-managed*), la relación entre una
épica y sus historias se toma del campo `parent` cuando Jira lo entrega.

## 5. Volver a importar el mismo proyecto

Puedes repetir la importación cuantas veces necesites; **nunca duplica**:

- El proyecto, cada sprint (por su nombre) y cada tarea (por su clave de Jira) quedan anclados a su
  origen. Al reimportar se actualizan título, estado, estimación, prioridad y sprint de lo que ya
  existe, y solo se crea lo nuevo.
- Las tareas existentes conservan su clave de Command; solo las nuevas consumen números.
- El nombre y el código del proyecto en Command no cambian al reimportar.
- Si una tarea cambió de nivel en Jira (por ejemplo, una épica que ahora es subtarea), la
  importación se detiene sin aplicar ningún cambio y el mensaje indica la clave afectada.
- Si Jira falla a mitad de la lectura, no se guarda nada y puedes reintentar con seguridad.

## 6. Mensajes de error frecuentes

| Mensaje | Qué hacer |
|---|---|
| Jira rechazó el correo o el API token | Genera un token nuevo y vuelve a registrar las credenciales |
| El proyecto ya no está disponible | Revisa que la cuenta conserve el permiso «Examinar proyectos» |
| Jira está limitando las solicitudes | Espera unos minutos y reintenta |
| El código ya está en uso | Cambia el código del proyecto en el paso «Revisar» |
| El proyecto de Jira tiene más issues de los que admite la importación | Sube `JIRA_IMPORT_MAX_ISSUES` (por defecto 20000) en la configuración del backend y reintenta; no se guarda nada mientras tanto |
