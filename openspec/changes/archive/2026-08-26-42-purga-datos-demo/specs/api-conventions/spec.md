# Delta for api-conventions

> Nota para `sdd-archive`: la bala "Esquema y seed" del `## Alcance as-built` (línea 20 de la línea base) describe `seed_default` como creador incondicional de "admin + 3 usuarios demo, proyectos/tareas demo". Al fusionar este delta, esa bala DEBE actualizarse para reflejar que la semilla estructural sigue incondicional y la semilla demo (usuarios, proyectos, tareas de muestra) queda condicionada por `SEED_DEMO_DATA` (ver R4 abajo y la capability `data-maintenance`).

## MODIFIED Requirements

### Requirement: R4 — Seed idempotente con semilla estructural incondicional y semilla demo condicionada

`seed_default` DEBE ser idempotente: arranques repetidos no duplican datos. La semilla estructural (organización "Solercia", 3 dependencias, roles ADMIN/MANAGER/MEMBER, 8 menús, role_menus, usuario `admin@solercia.com`, 4 alert rules, catálogo de 5 `org_role_templates` de sistema) DEBE ejecutarse SIN condición en cada arranque. La semilla de datos demo (usuarios `ana@`/`carlos@`/`diana@`, proyectos y tareas de muestra, sprint demo) DEBE ejecutarse ÚNICAMENTE cuando `settings.SEED_DEMO_DATA` sea `true`, leído EN TIEMPO DE LLAMADA (nunca fijado en una constante de módulo capturada al importar). Con `SEED_DEMO_DATA=false` (valor por defecto), ningún dato demo se crea en el primer arranque ni se recrea en arranques sucesivos, aunque ya existan tareas en la base.
(Previously: "`seed_default` DEBE ser idempotente: arranques repetidos no duplican datos" — sin distinguir semilla estructural de semilla demo; ambas corrían siempre.)

#### Scenario: Seed idempotente
- Dado una base de datos ya sembrada
- Cuando la aplicación reinicia
- Entonces `seed_default` no crea duplicados

#### Scenario: Demo desactivada por defecto
- Dado `settings.SEED_DEMO_DATA = false` y una base de datos vacía
- Cuando `seed_default` corre
- Entonces existen "Solercia" y `admin@solercia.com`, pero ningún usuario demo se crea

#### Scenario: Miembros demo no reviven sin el flag
- Dado una base purgada (sin usuarios demo) con `SEED_DEMO_DATA=false`
- Cuando la aplicación reinicia
- Entonces ningún usuario demo se recrea, aunque ya existan tareas reales en la base

### Requirement: R5 — Inicialización de esquema gestionada por Alembic

El esquema de base de datos DEBE originarse y evolucionar mediante revisiones de Alembic versionadas. El arranque asume que las migraciones ya se aplicaron y se limita a ejecutar `seed_default` sobre el esquema ya migrado. `seed_default` sigue siendo idempotente; dentro de él, la semilla estructural corre sin condición y la semilla de datos demo queda condicionada por `settings.SEED_DEMO_DATA` (ver R4). La introducción del flag `SEED_DEMO_DATA` es un cambio de `Settings`, no de esquema: NO requiere ninguna revisión Alembic nueva.
(Previously: "`seed_default` NO cambia de comportamiento (sigue siendo idempotente)" — sin mencionar la distinción entre semilla estructural y semilla demo, ni la ausencia de migración asociada.)

#### Scenario: Inicialización de esquema gestionada por Alembic
- Dado una base de datos vacía
- Cuando se ejecuta `alembic upgrade head`
- Entonces el esquema resultante es equivalente al que hoy produce `Base.metadata.create_all` (mismas tablas y columnas)

#### Scenario: El arranque ya no recrea el esquema con create_all
- Dado un entorno donde las migraciones Alembic ya se aplicaron
- Cuando la aplicación arranca
- Entonces el arranque NO ejecuta `create_all` para definir el esquema; solo corre `seed_default` sobre el esquema ya migrado

#### Scenario: Sin migración nueva para el flag de semilla demo
- Dado el flag `SEED_DEMO_DATA` agregado a `Settings`
- Cuando se ejecuta `alembic revision --autogenerate` contra la base con el baseline aplicado
- Entonces no se genera ninguna revisión nueva relacionada con este cambio, porque el esquema no varió

## ADDED Requirements

### Requirement: Alcance del borrado suave y excepción de mantenimiento para borrado físico

El requisito R3 (borrado suave: `is_active` + `deleted_at`) DEBE aplicarse a las operaciones de dominio en tiempo de ejecución (endpoints de la API y servicios de negocio invocados desde ellos). El sistema PUEDE exponer, fuera de la API HTTP, una operación de mantenimiento que ejecute borrado físico (DELETE real, no soft delete) SIEMPRE QUE: (1) viva en un caso de uso dedicado (`backend/app/maintenance/`) que sea dueño de su propia transacción, nunca en un repositorio de dominio que haga `commit`; (2) exija un respaldo (`--backup-file`) verificado — archivo existente y de tamaño mayor a cero bytes — antes de ejecutar cualquier borrado; (3) por defecto se ejecute en modo `--dry-run` (solo reporta, no borra) y exija la bandera explícita `--execute` para aplicar el borrado; (4) NUNCA se exponga como endpoint HTTP.

#### Scenario: Borrado suave sigue aplicando al dominio en tiempo de ejecución
- Dado una tarea activa
- Cuando se llama `DELETE /tasks/{id}` desde la API
- Entonces la tarea queda con `is_active=false` y `deleted_at` poblado, y la fila NO se elimina físicamente

#### Scenario: La operación de mantenimiento exige backup verificado
- Dado un script de mantenimiento invocado con `--execute` sin `--backup-file` válido
- Cuando se ejecuta
- Entonces la operación se rechaza antes de borrar cualquier fila

#### Scenario: El mantenimiento nunca se expone por HTTP
- Dado el backend en ejecución
- Cuando se inspeccionan las rutas registradas bajo `/api/v1`
- Entonces ninguna ruta ejecuta borrado físico de datos
