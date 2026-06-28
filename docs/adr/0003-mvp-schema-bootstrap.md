# ADR 0003 — Arrancado del esquema con `create_all` + seed idempotente; Alembic diferido

- **Estado:** Aceptado
- **Fecha:** 2026-06-26
- **Decisores:** Equipo Solercia PM
- **Relacionado:** `docs/ARCHITECTURE.md` (sección 5), `docs/adr/0001-multitenancy-row-level.md`

---

## Contexto

El MVP debe cumplir un criterio de aceptación concreto: `docker compose up --build` levanta
los cuatro servicios y, sin pasos manuales, la persona usuaria inicia sesión con el admin
semilla (`admin@solercia.com` / `Admin123*`) y crea un proyecto que persiste en PostgreSQL.

Eso exige que, al arrancar el backend, la base de datos tenga:

1. **El esquema** (tablas `organizations`, `users`, `projects`).
2. **Datos semilla mínimos:** una organización por defecto y el usuario administrador.

Hay dos enfoques para gestionar el esquema:

- **`create_all` al arranque:** SQLAlchemy crea las tablas que falten a partir de los
  modelos declarativos. Cero configuración, ideal para arrancar.
- **Migraciones versionadas (Alembic):** cada cambio de esquema es una migración revisable y
  reproducible; soporta `ALTER`, backfills y rollback.

En el MVP el esquema todavía cambia con frecuencia y aún no hay datos de producción que
preservar, por lo que el costo de mantener migraciones formales no se justifica al inicio.

## Decisión

Para el MVP, en el arranque de la aplicación (FastAPI *lifespan*):

1. Ejecutar `Base.metadata.create_all` para crear las tablas que no existan.
2. Ejecutar un **seed idempotente** que garantice la organización por defecto y el usuario
   administrador, usando *upsert* / verificación previa para que correr varias veces no
   duplique datos.

Y dejar **Alembic andamiado pero diferido**: el directorio `alembic/` y su `env.py` quedan
configurados (apuntando a `Base.metadata` y a `DATABASE_URL`), pero **no se generan ni
aplican migraciones** durante el MVP. Esto deja la transición lista sin pagar su costo ahora.

```python
# app/bootstrap/seed.py
from sqlalchemy import select
from app.core.security import hash_password
from app.models import Organization, User


async def bootstrap_schema_and_seed(engine, session_factory) -> None:
    # 1) Create tables that do not yet exist (MVP only; replaced by Alembic later).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2) Idempotent seed: default organization + admin user.
    async with session_factory() as session:
        org = await _get_or_create_org(session, name="Solercia")
        await _ensure_admin_user(
            session,
            organization_id=org.id,
            email="admin@solercia.com",
            password="Admin123*",
            full_name="Administrador Solercia",
        )
        await session.commit()


async def _get_or_create_org(session, name: str) -> Organization:
    existing = await session.scalar(
        select(Organization).where(Organization.name == name)
    )
    if existing:
        return existing
    org = Organization(name=name)
    session.add(org)
    await session.flush()  # populate org.id before seeding the admin
    return org


async def _ensure_admin_user(
    session, organization_id, email: str, password: str, full_name: str
) -> None:
    existing = await session.scalar(select(User).where(User.email == email))
    if existing:
        return  # idempotent: do not recreate or overwrite
    session.add(
        User(
            organization_id=organization_id,
            email=email,
            full_name=full_name,
            hashed_password=hash_password(password),
            is_active=True,
        )
    )
```

```python
# app/main.py — lifespan hook
from contextlib import asynccontextmanager
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    await bootstrap_schema_and_seed(engine, session_factory)
    yield


app = FastAPI(lifespan=lifespan)
```

## Consecuencias

### Positivas

- **Cero pasos manuales:** `docker compose up --build` deja el sistema usable de inmediato,
  cumpliendo el criterio de aceptación.
- **Iteración rápida del modelo** durante el MVP: cambiar un modelo y reiniciar basta para
  crear tablas nuevas.
- **Seed idempotente seguro:** reiniciar el contenedor no duplica la organización ni el
  admin, y no sobrescribe credenciales existentes.
- **Sin deuda de andamiaje:** Alembic ya queda configurado, así que adoptarlo después no
  exige preparar la infraestructura desde cero.

### Negativas / límites conocidos

- **`create_all` no altera tablas existentes.** Solo crea las que faltan; **no** aplica
  `ALTER` cuando cambia una columna de una tabla ya creada. En desarrollo esto se resuelve
  recreando el volumen de datos, pero **no es válido para producción**.
- **Sin historial ni rollback** de cambios de esquema mientras Alembic esté diferido.
- **Riesgo si se prolonga:** mantener este enfoque más allá del MVP, con datos reales, puede
  provocar derivas de esquema difíciles de reconciliar. Por eso la transición tiene
  disparador explícito (ver abajo).

## Ruta de migración hacia Alembic

Disparadores para activar migraciones formales (cualquiera de ellos):

- Hay datos de los que no se puede prescindir (primer entorno compartido o productivo).
- El esquema se estabiliza y los cambios pasan a ser incrementales.
- Se incorpora más de una persona desarrolladora tocando el modelo en paralelo.

Pasos de la transición:

1. Generar la **migración base** a partir del esquema actual:
   `alembic revision --autogenerate -m "baseline schema"`. Revisarla a mano para confirmar
   que refleja los modelos.
2. Para entornos ya creados con `create_all`, **sellar** la base con la revisión base:
   `alembic stamp head` (marca el esquema existente como migrado sin reaplicar DDL).
3. Reemplazar la llamada a `create_all` del arranque por `alembic upgrade head` (en el
   *lifespan*, en el `entrypoint` del contenedor o como job de despliegue).
4. **Conservar** el seed idempotente: el seeding de datos mínimos sigue siendo válido y
   complementa a las migraciones.
5. A partir de ahí, **todo cambio de esquema es una migración** revisable; se prohíbe volver
   a `create_all` para modificaciones.
