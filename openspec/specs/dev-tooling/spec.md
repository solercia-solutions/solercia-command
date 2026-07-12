# Spec — Fundación de herramientas de desarrollo backend (dev-tooling)

> **Origen**: cambio [01-fundacion-tdd](../../changes/archive/2026-07-11-01-fundacion-tdd/)

> Nueva capacidad introducida por el cambio `01-fundacion-tdd`. Describe el comportamiento que DEBE existir después de aplicar el cambio.

## Propósito

Base de herramientas backend que hace viable el TDD estricto exigido en los cambios 02-10: BD de test provisionada, fixtures compartidos de pytest, flujo de migraciones Alembic reproducible y línea base limpia de ruff/mypy.

## Requisitos

- **R1**: `docker-compose.yml` DEBE provisionar la base de datos `solercia_test` junto a `solercia`, accesible sin pasos manuales adicionales.
- **R2**: `backend/tests/conftest.py` DEBE exponer fixtures compartidos (cliente HTTP async, sesión de BD, factory de tenant/usuario) que reemplacen el bootstrap duplicado por archivo de test.
- **R3**: La suite existente de 43 tests DEBE seguir pasando tras migrar a los fixtures compartidos (ADITIVOS, no reescritos).
- **R4**: DEBE existir una revisión Alembic baseline tal que `alembic upgrade head` sobre una BD vacía produzca un esquema equivalente al actual `Base.metadata.create_all`.
- **R5**: El flujo de migraciones para cambios futuros DEBE estar documentado: todo cambio de modelo se expresa como una nueva revisión Alembic generada con `--autogenerate`.
- **R6**: `ruff check` y `mypy` DEBEN correr sin hallazgos sobre el backend, con comandos y dependencias documentados.
- **R7**: El setup de entorno local (venv + `requirements.txt` + `requirements-dev.txt`) DEBE estar documentado y ser reproducible sin conocimiento tácito del equipo.

### Escenarios centrales

**R1 — Los tests de integración ya no se saltan silenciosamente**
- Dado el setup documentado (`docker compose up` + `TEST_DATABASE_URL` apuntando a `solercia_test`)
- Cuando se ejecuta `pytest tests/ -v`
- Entonces ningún test se salta por `TEST_DATABASE_URL not set`.

**R1 — Sin TEST_DATABASE_URL, el skip es explícito (edge case)**
- Dado un entorno sin `TEST_DATABASE_URL` configurado (ej. corrida rápida solo unitaria)
- Cuando se ejecuta `pytest tests/ -v`
- Entonces los tests de integración se saltan con una razón explícita en el reporte, sin fallar silenciosamente ni pasar en falso.

**R2 — Fixture compartido sin bootstrap propio**
- Dado un archivo de test nuevo bajo `backend/tests/`
- Cuando declara los fixtures compartidos como parámetros
- Entonces obtiene cliente y datos de tenant/usuario funcionales sin duplicar lógica de setup ya existente en otros archivos.

**R3 — Suite existente permanece verde**
- Dado los 43 tests existentes integrados con los fixtures compartidos (ADITIVOS)
- Cuando se ejecuta `pytest tests/ -v` con `TEST_DATABASE_URL` configurado
- Entonces los 43 tests pasan sin regresiones de comportamiento.

**R4 — Baseline Alembic equivalente a create_all**
- Dado una base de datos vacía
- Cuando se ejecuta `alembic upgrade head`
- Entonces el esquema resultante tiene las mismas tablas, columnas y constraints que hoy genera `create_all`, y un `alembic revision --autogenerate` posterior contra esa misma BD no reporta diffs pendientes.

**R5 — Cambio de modelo exige nueva revisión**
- Dado el flujo de migraciones documentado
- Cuando un desarrollador modifica un modelo SQLAlchemy (campo o tabla nueva)
- Entonces el flujo indica cómo generar (`alembic revision --autogenerate`) y aplicar la revisión correspondiente antes de mergear.

**R6 — Lint y type-check limpios**
- Dado el código actual de `backend/app` y `backend/tests`
- Cuando se ejecutan `ruff check` y `mypy` según lo documentado
- Entonces ambos comandos terminan sin hallazgos (exit code 0).

**R7 — Setup reproducible desde cero**
- Dado un checkout limpio y las instrucciones documentadas
- Cuando se crea el venv y se instalan `requirements.txt` + `requirements-dev.txt`
- Entonces se puede ejecutar `pytest`, `ruff check` y `mypy` sin pasos adicionales no documentados.

## Fuera de alcance

- Paginación estándar, auditoría `created_by`/`updated_by` y cualquier feature de producto nueva (cambios 02+).
- Frontend: congelado (`constraint frontend-frozen`), no se toca.

## Referencias

- `docker-compose.yml`
- `backend/tests/conftest.py`, `backend/tests/test_*.py`
- `backend/alembic/` (`versions/`, `env.py`)
- `backend/requirements-dev.txt`, `backend/pyproject.toml`
