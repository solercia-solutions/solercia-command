# ADR 0008 — RBAC, nombre desglosado con `full_name` calculado y refresco de JWT por cookie

- **Estado:** Aceptado
- **Fecha:** 2026-06-27
- **Decisores:** Equipo Solercia PM
- **Relacionado:** `docs/DATA-MODEL.md`, `docs/AUTH.md`, `docs/API.md` (Autenticación y
  Administración), `docs/adr/0001-multitenancy-row-level.md`,
  `docs/adr/0003-mvp-schema-bootstrap.md`, `docs/adr/0004-stack-and-conventions.md`

---

## Contexto

Esta fase incorpora la **gestión de usuarios**, el **control de acceso por roles (RBAC)** y
un **refresco de sesión seguro**. Tres decisiones de diseño concentran el riesgo y merecen
quedar registradas:

1. **Nombre de la persona.** El modelo actual guarda un único campo `full_name`. El negocio
   necesita el nombre **desglosado** (primer/segundo nombre, primer/segundo apellido) para
   formularios, reportes y futuras integraciones. Pero buena parte del sistema ya consume
   `user.full_name`: el esquema `UserRead`, el `assignee_name` de las tareas, la vista
   ejecutiva y el rendimiento por colaborador. Cambiar la columna no puede romper eso.
2. **Autorización.** Hasta ahora la autorización se apoya en `organization_members.role`
   (`admin|manager|member|viewer`) vía `require_role`. Es suficiente para los endpoints de
   proyectos/tareas, pero el área de administración necesita un modelo más rico: roles
   configurables, permisos sobre **actividades** (menús) y una navegación que se derive de
   esos permisos. Codificar todo eso en un enum fijo no escala.
3. **Sesión.** El login emite hoy un único token de acceso que el frontend guarda y reenvía.
   Si ese token es de vida larga y se guarda en `localStorage`, queda expuesto a robo por
   XSS. Hace falta un esquema de **access corto + refresco** que minimice esa superficie sin
   romper el login actual (que entrega `access_token` en el cuerpo).

Además, agregar tablas y columnas implica una pregunta de esquema: ¿se necesita una
migración Alembic? (ver decisión 4).

## Decisión

### 1. Nombre desglosado con `full_name` como propiedad calculada

`users` reemplaza la columna `full_name` por cuatro columnas —`primer_nombre`,
`segundo_nombre` (nullable), `primer_apellido`, `segundo_apellido` (nullable)— y agrega
`dependency_id` (FK opcional a `dependencies`). Para **no romper** el código que lee
`user.full_name`, este pasa a ser una **propiedad calculada** del modelo, no un dato
almacenado:

```python
# app/modules/users/models.py
from sqlalchemy.ext.hybrid import hybrid_property

class User(...):
    primer_nombre: Mapped[str]
    segundo_nombre: Mapped[str | None]
    primer_apellido: Mapped[str]
    segundo_apellido: Mapped[str | None]
    dependency_id: Mapped[uuid.UUID | None]  # FK -> dependencies

    @hybrid_property
    def full_name(self) -> str:
        # primer_nombre + ' ' + primer_apellido, omitiendo espacios sobrantes.
        return " ".join(p for p in (self.primer_nombre, self.primer_apellido) if p)
```

Como `hybrid_property`, `full_name` funciona tanto a nivel de instancia (serialización de
`UserRead`, `assignee_name`, dashboards) como, si hiciera falta, en expresiones SQL. El
contrato de salida no cambia: `UserRead.full_name` sigue existiendo y los consumidores
actuales no se enteran del desglose.

### 2. RBAC con roles, menús y dos pivotes

La autorización del área de administración se modela con cuatro tablas (ver
`docs/DATA-MODEL.md`):

```text
users ──< user_roles >── roles ──< role_menus >── menus
                                                     │ parent_id (árbol)
```

- **`roles`** — roles de RBAC por organización (`code` único por org: `ADMIN`, `MANAGER`,
  `MEMBER`, …). Distintos del rol de tenant.
- **`menus`** — actividades de la aplicación (nombre, ícono, ruta), jerárquicas vía
  `parent_id`. **Globales** (sin `organization_id`): la lista de actividades es la misma para
  todas las organizaciones; lo que varía por organización es qué roles las conceden.
- **`user_roles`** y **`role_menus`** — pivotes con `unique(user_id, role_id)` y
  `unique(role_id, menu_id)` para impedir duplicados.

Sobre este modelo:

- **`require_admin`** protege todos los endpoints `/admin/*`: exige que el llamante tenga un
  rol con `code = "ADMIN"` (vía `user_roles → roles`) en su organización.
- **La navegación se deriva de los permisos.** `GET /auth/me/menus` calcula la unión de
  menús que conceden los roles del usuario, anidados por `parent_id` y ordenados por `order`.
  El frontend pinta el menú con ese árbol: lo que un rol no concede, no aparece. Autorización
  y navegación quedan en una sola fuente de verdad (el backend).

### 3. Refresco de JWT en cookie `httpOnly`, con rotación

La sesión pasa a sostenerse con **dos** tokens (ver `docs/AUTH.md`):

- **Acceso** — HS256, `sub = user.id`, `type = "access"`, 30 min
  (`ACCESS_TOKEN_EXPIRE_MINUTES`). Viaja en el **cuerpo** del login y el frontend lo guarda
  **en memoria** (no en `localStorage`).
- **Refresco** — HS256, `sub = user.id`, `type = "refresh"`, `jti`, 7 días
  (`REFRESH_TOKEN_EXPIRE_DAYS`). Viaja en una cookie `httpOnly` `SameSite=Lax`
  (`Secure = COOKIE_SECURE`, `Path=/`).

Flujo aditivo, sin romper el login actual:

- `POST /auth/login` mantiene `access_token` en el cuerpo, agrega `user` y entrega
  `Set-Cookie: refresh_token`.
- `POST /auth/refresh` lee la cookie, valida (`type == "refresh"`, no expirado), emite un
  **nuevo** access y **rota** el refresco (nuevo `jti`, reescribe la cookie).
- `POST /auth/logout` borra la cookie de refresco (`204`).
- El claim `type` se valida en cada decodificación para que un token no se use fuera de su
  propósito.

El frontend y el backend hablan **al mismo origen** a través del proxy del dev-server de
Angular (`/api` → `http://backend:8000`), por lo que la cookie de refresco es de primera
parte y el navegador la adjunta automáticamente a `/auth/refresh` sin configuración especial
de credenciales CORS.

### 4. Reseed limpio ahora, Alembic después

Las nuevas tablas (`dependencies`, `roles`, `menus`, `user_roles`, `role_menus`), el cambio
de columnas en `users` y `dependency_id` se incorporan **sin migración Alembic**, coherente
con el ADR 0003. En esta fase la base se **recrea limpia** (`docker compose down -v`) y
`Base.metadata.create_all` construye el esquema completo. El seed se actualiza para crear las
dependencias, los roles, los menús (con su `role_menus`), el `admin@solercia.com` con rol
`ADMIN` y los miembros de demostración con nombre desglosado, **conservando** el seed de
proyectos/sprints/tareas de la fase 3 (para que el burndown y el rendimiento sigan
demostrables). Las migraciones controladas siguen diferidas hasta salir del MVP.

## Consecuencias

### Positivas

- **Compatibilidad total del nombre:** `full_name` calculado deja intactos `UserRead`,
  `assignee_name` y los dashboards; el desglose se gana sin reescribir consumidores.
- **Autorización extensible:** roles y menús configurables por dato (no por enum) permiten
  crear roles y reasignar actividades sin tocar código; la navegación se deriva sola.
- **Sesión más segura:** access corto en memoria + refresco `httpOnly` rotado reduce la
  superficie de XSS y limita la vida útil de un refresco filtrado.
- **Cambio aditivo en auth:** el login sigue devolviendo `access_token` en el cuerpo; el
  frontend actual no se rompe mientras se adopta el refresco.
- **Tenancy intacta:** conservar `OrganizationMember` mantiene la derivación de
  `organization_id` y `require_role` de los endpoints existentes sin cambios.

### Negativas / costos

- **Dos conceptos de «rol» conviviendo:** el rol de tenant (`organization_members.role`) y el
  rol de RBAC (`roles`/`user_roles`) coexisten. Es deuda conceptual: hay que documentar y
  vigilar que no se confundan. Se aceptó para no reescribir la autorización existente en esta
  fase; una unificación futura es posible pero no urgente.
- **`require_admin` consulta la BD:** verificar el rol `ADMIN` implica un join por petición a
  `/admin/*`. Es asumible para un área de administración de bajo tráfico; si crece, se
  cacheará por sesión.
- **Sin denylist de refresco aún:** el refresco se rota pero no se mantiene una lista de
  revocación por `jti`; un refresco robado es válido hasta su `exp` o hasta el siguiente uso
  legítimo que lo rote. Cerrar esa ventana (Redis + `jti`) queda como trabajo futuro
  (`docs/AUTH.md`, «Trabajo futuro»).
- **`full_name` calculado es de solo lectura:** no se puede asignar directamente; cualquier
  edición del nombre pasa por las cuatro columnas. Es lo correcto, pero exige cuidado en
  formularios y seeders que antes escribían `full_name`.
- **Reseed destructivo:** recrear la base limpia borra los datos existentes. Aceptable en el
  MVP (ADR 0003); deja de serlo en cuanto haya datos reales, momento en que se activará
  Alembic.

## Alternativas descartadas

- **Mantener `full_name` como columna y agregar las columnas de desglose en paralelo:**
  rechazada por **duplicar** la verdad (dos fuentes que pueden divergir) y exigir
  sincronización en cada escritura. La propiedad calculada elimina la duplicación.
- **Calcular `full_name` solo en el esquema Pydantic (no en el modelo):** rechazada porque
  dejaría sin `full_name` a los consumidores que leen el **modelo** ORM directamente
  (`assignee_name`, dashboards). La `hybrid_property` cubre ambos mundos.
- **Extender el enum `MemberRole` para los permisos:** rechazada por inflexible: agregar un
  rol o cambiar qué ve cada uno exigiría tocar código y reseed. RBAC por tablas lo vuelve un
  dato administrable.
- **Permisos por endpoint en lugar de por menú:** rechazada por ahora; el alcance de esta
  fase es administrar usuarios y derivar la navegación. Conceder por **actividad/menú** cubre
  el caso y es lo que el frontend necesita. Un modelo de permisos finos (acción × recurso) se
  puede superponer después sobre la misma base de roles.
- **Guardar el token en `localStorage`:** rechazada por exponer un token legible a cualquier
  JavaScript de la página (XSS). El acceso en memoria + refresco `httpOnly` es el patrón
  recomendado.
- **Refresco también en el cuerpo de la respuesta:** rechazada porque anularía la protección
  `httpOnly`; el refresco solo viaja como cookie.
- **Eliminar `OrganizationMember` y derivar el tenant desde `user_roles`:** rechazada en esta
  fase por riesgo: reescribiría la derivación de `organization_id` y la autorización de todos
  los endpoints ya funcionando. Se conserva la membresía para la tenancy y se suma RBAC para
  la administración.
- **Migración Alembic inmediata:** rechazada por coherencia con el ADR 0003; el reseed limpio
  resuelve el esquema sin el andamiaje de migraciones, que se activará al salir del MVP.
</content>
