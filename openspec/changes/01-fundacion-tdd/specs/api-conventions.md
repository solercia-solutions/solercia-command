# Delta for api-conventions

> Cambio `01-fundacion-tdd`. Delta contra `openspec/specs/api-conventions/spec.md` (línea base as-built 2026-07-11).

## MODIFIED Requirements

### Requirement: Inicialización de esquema gestionada por Alembic

El esquema de base de datos DEBE originarse y evolucionar mediante revisiones de Alembic versionadas. `Base.metadata.create_all` DEJA de ser el mecanismo que define el esquema en el arranque de la aplicación: el arranque asume que las migraciones ya se aplicaron y se limita a ejecutar `seed_default` sobre el esquema ya migrado. `seed_default` NO cambia de comportamiento (sigue siendo idempotente).

(Previously: descrito de forma informal en "Alcance as-built" — "en startup, `db_init.init_db` crea el esquema con `Base.metadata.create_all` y ejecuta `seed_default` idempotente... CERO revisiones Alembic (solo .gitkeep)". No existía revisión real ni camino de migraciones.)

#### Scenario: alembic upgrade head sobre BD limpia

- Dado una base de datos vacía (test, dev o CI)
- Cuando se ejecuta `alembic upgrade head`
- Entonces el esquema resultante es equivalente al que hoy produce `Base.metadata.create_all` (mismas tablas y columnas).

#### Scenario: El arranque de la aplicación ya no recrea el esquema con create_all

- Dado un entorno donde las migraciones Alembic ya se aplicaron
- Cuando la aplicación arranca (`lifespan` / `db_init.init_db`)
- Entonces el arranque NO ejecuta `create_all` para definir el esquema; solo corre `seed_default` sobre el esquema ya migrado.

#### Scenario: seed_default sigue siendo idempotente (comportamiento sin cambios)

- Dado una base de datos ya sembrada y migrada
- Cuando la aplicación reinicia
- Entonces `seed_default` no crea duplicados (comportamiento de R4 de la spec principal, sin cambios).

## ADDED Requirements

### Requirement: Flujo de migraciones documentado para cambios futuros

Todo cambio de esquema posterior a la línea base DEBE expresarse como una nueva revisión de Alembic generada con `alembic revision --autogenerate`, revisada y versionada junto con el código que la origina.

#### Scenario: Cambio de modelo requiere revisión antes de mergear

- Dado un modelo SQLAlchemy modificado (campo o tabla nueva)
- Cuando se ejecuta `alembic revision --autogenerate` contra una BD con el baseline aplicado
- Entonces se genera una revisión no vacía que describe el cambio, lista para revisión de código.

## Notas para el archivado

- En "Alcance as-built", reemplazar la línea de "Esquema y seed" para reflejar el flujo gestionado por Alembic (ya no `create_all` en startup).
- En "Limitaciones y deuda conocida", retirar el punto "Esquema por `create_all` en startup: Alembic instalado pero sin ninguna revisión — no hay camino de migraciones" (queda resuelto por este cambio).
- R1, R2, R3 y R4 de la spec principal NO cambian.
