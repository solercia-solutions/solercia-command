# ADR 0001 — Multi-tenancy a nivel de fila vía `organization_id`

- **Estado:** Aceptado
- **Fecha:** 2026-06-26
- **Decisores:** Equipo Solercia PM
- **Relacionado:** `docs/ARCHITECTURE.md` (secciones 3 y 7), `docs/adr/0003-mvp-schema-bootstrap.md`

---

## Contexto

Solercia Project Manager es **multi-tenant**: varias organizaciones comparten la misma
instalación y cada una solo debe ver sus propios datos (usuarios, proyectos y, más
adelante, sprints y tareas). Necesitamos un mecanismo de aislamiento que sea correcto desde
el primer día, simple de operar para el MVP y con una ruta de endurecimiento clara.

Las opciones evaluadas para aislar tenants en PostgreSQL fueron:

1. **Aislamiento por fila (discriminador `organization_id`)** — una sola base de datos y un
   solo esquema; cada tabla de tenant lleva una columna `organization_id` y todas las
   consultas se filtran por ella.
2. **Esquema por tenant** — un esquema de PostgreSQL por organización dentro de la misma
   base de datos; el aislamiento lo da el `search_path`.
3. **Base de datos por tenant** — una base de datos física por organización.

| Criterio                        | Por fila            | Esquema/tenant        | BD/tenant             |
| ------------------------------- | ------------------- | --------------------- | --------------------- |
| Complejidad operativa           | Baja                | Media                 | Alta                  |
| Costo de aprovisionar un tenant | Insertar una fila   | Crear esquema + DDL   | Crear BD + migrar     |
| Migraciones de esquema          | Una sola pasada     | N esquemas a migrar   | N bases a migrar      |
| Aislamiento (fuerza)            | Lógico (aplicación) | Fuerte (namespace)    | Muy fuerte (físico)   |
| Riesgo de fuga entre tenants    | Olvido de filtro    | Bajo                  | Casi nulo             |
| Consultas analíticas cruzadas   | Triviales           | Difíciles (UNION ALL) | Muy difíciles         |
| Escalado de muchos tenants      | Excelente           | Degrada (límite de esquemas) | Costoso        |

## Decisión

Para el MVP adoptamos **aislamiento a nivel de fila mediante una columna `organization_id`**
(UUID, FK a `organizations`) en todas las tablas con datos de tenant.

Reglas que hacen segura esta decisión:

1. **El `organization_id` se deriva del token JWT**, nunca del cuerpo de la petición en
   operaciones de tenant. El usuario autenticado pertenece a una organización y ese valor
   manda.
2. **El filtro por tenant se concentra en la capa de repository.** Cada query agrega
   `WHERE organization_id = :tenant_id`. Ningún service ni router debe construir SQL de
   tenant sin pasar por el repository, de modo que un olvido puntual no abra una fuga.
3. **Las búsquedas por id que no encuentran fila dentro del tenant devuelven `404`**, no
   `403`, para no revelar la existencia de recursos ajenos.

Ejemplo del patrón en el repository (SQLAlchemy 2.0 async):

```python
class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_tenant(self, organization_id: UUID) -> list[Project]:
        stmt = (
            select(Project)
            .where(Project.organization_id == organization_id)  # tenant filter
            .order_by(Project.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_for_tenant(
        self, project_id: UUID, organization_id: UUID
    ) -> Project | None:
        stmt = select(Project).where(
            Project.id == project_id,
            Project.organization_id == organization_id,  # tenant filter
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
```

## Consecuencias

### Positivas

- **Simplicidad operativa:** un único esquema, una única pasada de migración, un seed
  trivial. Encaja con `create_all` + seed idempotente del MVP (ADR 0003).
- **Aprovisionar un tenant nuevo es insertar una fila** en `organizations`; sin DDL.
- **Consultas cruzadas y métricas globales** (uso por organización, totales) son directas.
- **Escala bien** a muchos tenants pequeños, escenario típico de un SaaS de gestión.

### Negativas / riesgos

- **El aislamiento depende de la aplicación.** Una consulta que olvide el filtro puede
  filtrar datos entre tenants. Lo mitigamos concentrando el filtro en el repository y
  prohibiendo SQL de tenant fuera de esa capa; conviene reforzarlo con pruebas que
  verifiquen que un usuario no ve recursos de otra organización.
- **No hay barrera física.** Un bug de aplicación tiene mayor radio de impacto que en
  esquema/BD por tenant.
- **Requisitos de residencia o cifrado por tenant** (algunos sectores regulados) no se
  cubren con este modelo y empujarían hacia esquema o BD por tenant.

## Endurecimiento futuro

A medida que el producto madure, sin reescribir el modelo de datos:

1. **Índices compuestos** liderados por `organization_id` (p. ej. `(organization_id, id)`,
   `(organization_id, created_at)`) para mantener el rendimiento al crecer los tenants.
2. **Row-Level Security (RLS) de PostgreSQL:** activar políticas por tabla que fuercen
   `organization_id = current_setting('app.current_tenant')`. La aplicación setea el tenant
   por transacción y la base de datos rechaza accesos cruzados aunque la consulta olvide el
   `WHERE`. Esto convierte el aislamiento lógico en una garantía a nivel de motor.
3. **Default global de tenant en el ORM:** un evento/loader que inyecte el filtro de tenant
   automáticamente, reduciendo la dependencia de recordarlo en cada query.
4. **Migración selectiva a esquema o BD por tenant** para clientes enterprise con
   requisitos de aislamiento físico, manteniendo el modelo por fila para el resto.
