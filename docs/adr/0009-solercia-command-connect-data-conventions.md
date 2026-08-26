# ADR 0009 — Solercia Command, Solercia Connect y convenciones de datos

- **Estado:** Parcialmente aceptado — decisiones vigentes con propuestas y validaciones pendientes
- **Fecha:** 2026-08-22
- **Última actualización:** 2026-08-23
- **Decisores:** Equipo Solercia — Producto y Arquitectura
- **Relacionado:** ADR 0004 (`docs/adr/0004-stack-and-conventions.md`),
  `docs/ARCHITECTURE.md`, `docs/API.md`

---

## Contexto

**DECIDED** Este ADR fija las fronteras entre productos, la dirección para conectores y
las reglas que deben compartir los datos cuando crucen servicios. Esta actualización
también aprueba **Solercia Command** como nombre del producto y `solercia-command` como
nombre de la carpeta local.

**DECIDED** El cambio de identidad es acotado: no ordena una migración masiva ni autoriza
renombrar objetos de base de datos, contratos de API, paquetes, módulos, identificadores de
despliegue, remotos Git, repositorios GitHub, dominios o razones sociales.

**CURRENT** La evidencia parte de una auditoría de solo lectura ya realizada sobre las
45 tablas ORM y las migraciones 0001–0024 de Command, y sobre las 24 tablas y 5
migraciones de Security. No se encontró diferencia entre los conjuntos de tablas del ORM y
las cadenas de migración auditadas.

**PROPOSED** Los contratos de Solercia Connect, el skill transversal y las fases futuras
descritas aquí son diseños por validar; este ADR no afirma que estén implementados.

### Leyenda de estados

| Etiqueta | Significado |
| --- | --- |
| **CURRENT** | Hecho verificado en el estado actual o en una fuente oficial. |
| **DECIDED** | Decisión aceptada que orienta el trabajo posterior. |
| **PROPOSED** | Diseño candidato; no está aprobado ni implementado por este ADR. |
| **PENDING** | Validación o decisión que todavía debe cerrarse. |

## Decisión

### Resumen ejecutivo

| Tema | Estado | Resultado |
| --- | --- | --- |
| Nombre de producto | **DECIDED** | `Solercia Command`. |
| Descriptor comercial | **PROPOSED** | «Centro operativo de trabajo». |
| Carpeta local | **DECIDED** | `gestion_proyectos` se renombra a `solercia-command`. |
| Fronteras de suite | **DECIDED** | Command ejecuta trabajo; Connect normaliza hechos externos; Security gobierna SGSI, cumplimiento y evidencia. |
| Persistencia | **DECIDED** | No fusionar bases de datos, repositorios ni estados internos. |
| Conectores | **DECIDED** | Runtime reutilizable Python-first; OAuth y API oficiales como ruta primaria. |
| Datos comunes | **DECIDED** / **PROPOSED** | Conservar PK locales y normalizar solo los contratos que crucen servicios. |
| Adopción | **DECIDED** | Evolución incremental, sin migración masiva. |

### Nombre del producto

**DECIDED** El nombre técnico y de producto es **Solercia Command**. El nombre representa
trabajo, ejecución y agenda unificada sin reducir el producto a gestión de proyectos.

**PROPOSED** El descriptor comercial es **«Centro operativo de trabajo»**.

**DECIDED** La carpeta local cambia de `gestion_proyectos` a `solercia-command`. Esta
decisión no cambia la identidad de ningún objeto Git ni implica renombrar un remoto.

**DECIDED** Permanecen sin cambios las bases de datos y tablas, los contratos de API, los
identificadores de paquetes y módulos, los nombres de despliegue y entorno, las variables,
los remotos Git y cualquier identificador de GitHub. Tampoco se reescriben referencias
históricas o símbolos de dominio que describen la gestión de proyectos.

**PENDING** La disponibilidad de dominios, el nombre jurídico y el uso público de la marca
deben validarse antes de un lanzamiento; esas validaciones no condicionan el nombre técnico
ni la carpeta local aprobados aquí.

### Fronteras de la suite

| Producto | Estado | Responsabilidad propia | Fuera de su propiedad |
| --- | --- | --- | --- |
| Solercia Command | **DECIDED** | Trabajo operativo, ejecución, tareas y agenda unificada. | Conectividad externa canónica y decisiones SGSI. |
| Solercia Connect | **DECIDED** | Conectividad con proveedores y hechos externos normalizados. | Prioridad, proyecto, estado interno de tareas y decisiones SGSI. |
| Solercia Security | **DECIDED** | SGSI, cumplimiento, validación y cierre de evidencia. | Planificación y estado operativo del trabajo. |

**DECIDED** Las bases de datos, los repositorios y los estados internos permanecen
separados. La integración se realiza mediante identificadores públicos, referencias y
eventos; nunca mediante acceso directo a tablas de otro producto ni mediante agregados
compartidos.

## Arquitectura de conectores

### Runtime y superficies

**DECIDED** La arquitectura objetivo es un runtime reutilizable **Python-first** con un
núcleo único y estas superficies:

| Superficie | Propósito |
| --- | --- |
| CLI | Operación manual, automatización y diagnóstico controlado. |
| SDK / biblioteca | Consumo directo desde servicios Python. |
| API local | Integración desacoplada con aplicaciones locales. |
| Adaptador MCP opcional | Exposición a agentes sin convertir MCP en el núcleo. |

**DECIDED** OAuth y las API oficiales son la ruta primaria. Para Microsoft 365, la
aplicación debe registrarse, obtener tokens y solicitar únicamente los permisos necesarios;
los escenarios delegados y de aplicación tienen autorizaciones distintas según
[Microsoft Graph: autenticación y autorización](https://learn.microsoft.com/en-us/graph/auth/auth-concepts).
Los scopes y el consentimiento, incluido el consentimiento administrativo para permisos
restringidos, se validan por capacidad y tenant según
[Microsoft Entra: scopes y permisos](https://learn.microsoft.com/en-us/entra/identity-platform/scopes-oidc).

**DECIDED** Playwright puede usarse solo como fallback temporal cuando la API oficial no
esté disponible o la autorización del tenant esté bloqueada. Debe utilizar un perfil de
navegador persistente y dedicado a automatización, nunca el perfil personal predeterminado;
`launch_persistent_context` conserva cookies y almacenamiento en `user_data_dir`, y la
propia documentación exige un directorio separado en
[Playwright BrowserType](https://playwright.dev/python/docs/api/class-browsertype).

**CURRENT** Outlook REST v2 está deprecado y su endpoint fue decommissionado; no es una
ruta soportada. Las integraciones nuevas deben usar Microsoft Graph, como indica la
[referencia oficial de Outlook Mail REST API v2](https://learn.microsoft.com/en-us/previous-versions/office/office-365-api/api/version-2.0/mail-rest-operations).

### Alcance de una prueba por reenvío de correo

**DECIDED** Reenviar correo de Outlook a una cuenta personal solo permite validar:

- ingestión de mensajes;
- clasificación del contenido;
- presentación en la interfaz.

**DECIDED** Esa prueba no valida autorización del tenant, calendario de Outlook,
Teams, SharePoint, Planner ni trazabilidad nativa de Microsoft 365. Tampoco sustituye la
prueba OAuth con scopes y consentimiento reales.

## Estructuras de datos actuales verificadas

**CURRENT** La comparación siguiente describe el estado auditado, no un estándar futuro.

| Aspecto | Command (`solercia-command` local; identificadores heredados sin cambio) | Security (`solercia_security`) |
| --- | --- | --- |
| Alcance auditado | ≈45 tablas ORM; migraciones 0001–0024. | ≈24 tablas; 5 migraciones. |
| Clave primaria | UUID generado por la aplicación. | `BIGINT GENERATED BY IDENTITY`. |
| Esquema PostgreSQL | `public`. | Esquema explícito `sgsi`. |
| Tenancy | `organization_id`, directo o denormalizado. | `entity_id`. |
| Tiempos | `created_at` / `updated_at` con `timestamptz`; `updated_at` es impulsado por el ORM. | Marcas temporales definidas según el dominio. |
| Ciclo de vida | `is_active` extendido y `deleted_at` frecuente. | Sin soft delete genérico; ciclo de vida específico por dominio. |
| Actores de auditoría | `created_by` / `updated_by` genéricos. | Actores y eventos específicos del dominio; patrones de eventos append-only. |
| Restricciones | Menor cobertura de `CHECK` en base de datos. | Mayor uso de `CHECK` para reglas de dominio. |
| Integración y procedencia | Cobertura sólida de conectores, intake y procedencia. | Evidencia, cumplimiento y trazabilidad SGSI. |
| Mixin genérico | Timestamp, soft delete, auditoría y tenant. | Sin mezcla genérica de auditoría, soft delete y versión. |
| Optimistic locking | No existe versionado optimista generalizado real. | No existe versionado optimista generalizado real. |
| ORM frente a migraciones | Sin diferencias de conjuntos de tablas en la cadena auditada. | Sin diferencias de conjuntos de tablas en la cadena auditada. |

**CURRENT** La base compartida de Command puede revisarse en
[`backend/app/shared/base_model.py`](/Users/camilocalderont/Proyectos/SOLERCIA/solercia-command/backend/app/shared/base_model.py).
La cobertura de integración está distribuida entre
[`backend/app/integrations/`](/Users/camilocalderont/Proyectos/SOLERCIA/solercia-command/backend/app/integrations/),
[`backend/app/modules/connectors/`](/Users/camilocalderont/Proyectos/SOLERCIA/solercia-command/backend/app/modules/connectors/)
y
[`backend/app/modules/intake/`](/Users/camilocalderont/Proyectos/SOLERCIA/solercia-command/backend/app/modules/intake/).
La base de modelos de Security está en
[`apps/api/app/shared/models.py`](/Users/camilocalderont/Proyectos/SOLERCIA/solercia_security/apps/api/app/shared/models.py).

## Convención común futura de base de datos

**DECIDED** La convergencia será contractual y selectiva. No se reemplazarán las
convenciones internas sanas de cada producto ni se reescribirán claves primarias existentes.

| Tema | Estado | Convención |
| --- | --- | --- |
| PK local | **DECIDED** | Cada producto conserva su estrategia local de PK. |
| Identidad externa | **PROPOSED** | Añadir `public_id UUID` solo a objetos que crucen servicios. |
| Tenant | **PROPOSED** | El envelope usa `tenant_id` semántico y cada producto lo mapea a `organization_id`, `entity_id` o `company_id`. |
| Tiempo | **PROPOSED** | UTC con `timestamptz`; distinguir tiempo del hecho, ingestión y actualización. |
| Ciclo de vida | **PROPOSED** | Semántica explícita por entidad; no combinar `is_active` y `deleted_at` sin invariantes. |
| Auditoría | **PROPOSED** | Actores explícitos y diferenciados para creación, cambio y eventos de dominio. |
| Enumeraciones estables | **PROPOSED** | `VARCHAR` más `CHECK`; evitar enums nativos cuando dificulten evolución. |
| Integridad multi-tenant | **PROPOSED** | FKs compuestas tenant-safe cuando una referencia deba permanecer dentro del tenant. |
| Datos extensibles | **PROPOSED** | Solo `JSONB`; no JSON serializado dentro de texto. |
| Idempotencia | **PROPOSED** | `UNIQUE` en la clave natural completa más escritura atómica con `ON CONFLICT`. |
| Procedencia | **PROPOSED** | Conservar proveedor, cuenta, identificador externo, hash, tiempos y versión de esquema. |
| Concurrencia | **PROPOSED** | Campo `version` únicamente en agregados con edición concurrente real. |
| Secretos | **PROPOSED** | Secretos aislados y cifrados; nunca mezclados con payloads o metadatos de negocio. |

**DECIDED** Los prefijos físicos de Boki `vc_`, `i_`, `d_`, `b_`, `dt_`,
`tx_` y `json_` son heredados y específicos de ese producto. **MUST NOT** convertirse
en la convención global de Solercia.

## Solercia Connect

### DTOs canónicos

**PROPOSED** Solercia Connect comienza como una capacidad de solo lectura y expone los
siguientes DTOs normalizados:

| DTO | Responsabilidad |
| --- | --- |
| `Account` | Cuenta externa autorizada y su identidad pública. |
| `Tenant` | Organización externa y mapeo al tenant semántico. |
| `Capability` | Capacidad disponible y scopes efectivos por proveedor/cuenta. |
| `Cursor` | Continuación incremental y checkpoint de sincronización. |
| `MailMessage` | Hecho normalizado de correo. |
| `CalendarEvent` | Hecho normalizado de calendario. |
| `ExternalTask` | Tarea reportada por un proveedor, sin convertirla en `Task` de Command. |
| `MeetingNote` | Nota o transcripción normalizada con procedencia. |
| `FileItem` | Archivo externo y sus metadatos de origen. |
| `IntegrationEnvelope` | Envelope común para transportar hechos externos. |

**PROPOSED** `IntegrationEnvelope` contiene como mínimo:

| Campo | Semántica |
| --- | --- |
| `provider` | Proveedor de origen. |
| `account_public_id` | Cuenta pública de Connect que obtuvo el dato. |
| `external_id` | Identificador estable en el proveedor. |
| `occurred_at` | Momento en que ocurrió el hecho externo. |
| `ingested_at` | Momento de ingestión en Connect. |
| `payload_hash` | Hash para integridad y deduplicación. |
| `schema_version` | Versión del contrato normalizado. |
| `metadata` | Extensión JSONB sin secretos y con retención controlada. |

**DECIDED** Connect no será propietario de `Task`, prioridad, proyecto ni decisiones
SGSI. `ExternalTask` es un hecho externo; Command decide si lo convierte en trabajo
operativo y Security decide si tiene significado de cumplimiento.

## Integración entre Command y Security

**PROPOSED** `ExternalWorkReference` enlaza objetos mediante `public_id`, tipo de
origen, correlación y versión del contrato. Cada producto conserva una proyección local de
la referencia; no existe FK entre bases ni tabla compartida.

**PROPOSED** La sincronización usa estos eventos:

| Evento | Emisor propietario | Hecho sincronizado |
| --- | --- | --- |
| `WorkRequested` | Security | Existe una solicitud de trabajo operativo asociada a un objeto SGSI. |
| `WorkCompleted` | Command | El trabajo operativo terminó según el estado de Command. |
| `EvidenceValidationRequired` | Command | La evidencia asociada al trabajo requiere decisión de Security. |
| `ComplianceClosed` | Security | El ciclo de cumplimiento o evidencia fue cerrado por Security. |

**DECIDED** Command es la única autoridad sobre el estado operativo del trabajo y de las
tareas. Security es la única autoridad sobre cumplimiento, validación y cierre de
evidencia. Las referencias y los eventos sincronizan hechos observables; no replican ni
permiten modificar agregados internos del otro producto.

## Skill general de convenciones Solercia

**CURRENT** Existe el skill global
`~/.agents/skills/solercia-persistence/SKILL.md`, que exige límites
de persistencia independientes por producto, repositorios locales, transacciones fuera de
los repositorios y pruebas en la frontera correcta. Command lo activa mediante
[`agents/rules/solercia-persistence.md`](../../agents/rules/solercia-persistence.md), y el
registro local debe resolver la ruta global sin depender del nombre anterior de la carpeta.

**PROPOSED** Ampliar esa fuente solo si se aprueba un contrato común de datos y perfiles
por dialecto. La estructura de referencia candidata es:

```text
~/.agents/skills/solercia-persistence/
├── SKILL.md
└── references/
    ├── repository-contract.md
    ├── python-sqlalchemy.md
    └── typescript-typeorm-nestjs.md
```

**DECIDED** La fuente global no se convierte en paquete de runtime ni crea persistencia
compartida. Cada producto conserva su regla adaptadora y su implementación local.

## Riesgos y hallazgos

| Estado | Riesgo o hallazgo | Consecuencia |
| --- | --- | --- |
| **CURRENT** | Algunos modelos de Command declaran FKs con `SET NULL` hacia columnas `NOT NULL`. | La acción referencial puede fallar al eliminar el registro padre. |
| **CURRENT** | Hay ventanas check-then-insert en idempotencia. | Dos procesos pueden superar la comprobación y competir al insertar. |
| **CURRENT** | Parte del tenant scoping está denormalizado sin FKs compuestas tenant-safe. | Una referencia puede quedar asociada al tenant incorrecto si la aplicación falla. |
| **CURRENT** | Ningún producto tiene optimistic locking generalizado. | La última escritura puede sobrescribir cambios concurrentes. |
| **CURRENT** | PII, secretos o payloads crudos pueden superar la retención necesaria. | Aumenta la exposición y el costo de cumplimiento. |
| **CURRENT** | El onboarding OAuth delegado depende de UI, políticas y consentimiento del proveedor. | Cambios de interfaz o tenant pueden romper onboarding y renovación. |
| **CURRENT** | El launcher de CodeGraph resuelve Node v26.0.0 y rechaza ejecutarse. | El índice local está vigente y fue consultado con el intérprete Node 22 instalado; no se anuló el safety check ni se reindexó. |

**PROPOSED** Las mitigaciones son selectivas: corregir incompatibilidades de FK,
reemplazar check-then-insert con constraints y upserts, reforzar referencias multi-tenant,
aplicar versionado solo donde exista edición concurrente, y definir políticas de cifrado,
redacción y retención antes de persistir payloads nuevos.

## Adopción por fases

**DECIDED** La adopción no incluye una migración masiva ni una base de datos compartida.

| Fase | Estado | Alcance |
| --- | --- | --- |
| 0. Preservar | **DECIDED** | Mantener PK, esquemas, repositorios y estados internos actuales. |
| 1. Contrato | **PROPOSED** | Formalizar el contrato común y el skill de usuario; validar contra SQLAlchemy y TypeORM. |
| 2. Connect read-only | **PROPOSED** | Extraer el runtime reutilizable y publicar DTOs/envelopes sin escrituras hacia proveedores. |
| 3. Referencias y eventos | **PROPOSED** | Introducir `ExternalWorkReference` y los cuatro eventos con idempotencia y observabilidad. |
| 4. Endurecimiento | **PROPOSED** | Corregir solo agregados afectados: FKs, upserts, tenant safety, retención y versionado selectivo. |

## Decisiones pendientes

- **PENDING** Validación jurídica, de marca pública y de dominios para `Solercia Command`;
  no condiciona el nombre técnico ni la carpeta local.
- **PENDING** Propietario, paquete y política de versionado de los DTOs de Connect.
- **PENDING** Mapeo y autoridad de `tenant_id` frente a `organization_id`,
  `entity_id` y `company_id`.
- **PENDING** Transporte de eventos, outbox/inbox y garantías de entrega.
- **PENDING** Matriz de scopes, consentimiento delegado o de aplicación y tenants
  admitidos por capacidad.
- **PENDING** Política de minimización, cifrado, redacción y retención para PII, secretos
  y payloads crudos.
- **PENDING** Criterio de retiro para cada fallback de Playwright.

## Consecuencias

### Positivas

- **DECIDED** Las fronteras evitan que conectores, trabajo y SGSI compitan por el mismo
  agregado.
- **DECIDED** Conservar las PK locales reduce riesgo y permite adopción incremental.
- **DECIDED** Identificadores públicos, procedencia y eventos hacen auditable cada cruce
  sin acoplar bases de datos.
- **DECIDED** La API oficial como ruta primaria mantiene autorización y trazabilidad
  nativas.
- **DECIDED** El nombre y la carpeta local quedan alineados sin mezclar el cambio de marca
  con una migración de contratos o de persistencia.

### Negativas / costos

- **DECIDED** Cada producto debe mantener mapeos, proyecciones e idempotencia en sus
  propios límites.
- **DECIDED** La separación introduce consistencia eventual y exige observabilidad de
  eventos.
- **DECIDED** Los fallbacks de navegador requieren operación segura, perfil dedicado y
  mantenimiento ante cambios de UI.
- **CURRENT** Las propuestas no entregan valor operativo hasta que se validen e
  implementen por fases.

## Próximo paso recomendado

1. **PENDING** Realizar una revisión conjunta de Producto, Arquitectura y Seguridad para
   cerrar el contrato mínimo de `IntegrationEnvelope`, el mapeo de `tenant_id` y la
   política de retención antes de crear el skill transversal o implementar Solercia
   Connect.
