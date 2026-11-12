# Archive Report: 14-integration-ports

**Change**: 14-integration-ports — Núcleo hexagonal de puertos de integración solo-lectura + módulo `connectors` con OAuth genérico  
**Archived**: 2026-07-18  
**Artifact Store Mode**: hybrid  
**Status**: DONE

---

## Ciclo Completado

### Proposal (Observation #1620)
- **Capabilidades nuevas**: `integration-ports` (5 puertos read-only + registro + fake adapter), `connectors` (modelo de datos + OAuth + CRUD con permisos)
- **Constrains**: backend-only, strict TDD, rollback-required
- **Decisiones de arquitecto**: núcleo en `app/integrations/`, modelos en `app/modules/connectors/`, OAuth state en Redis con TTL, tokens cifrados con Fernet en tabla aislada
- **Status**: Ratificado (5 preguntas de propuesta resueltas por orquestador)

### Specification (Observation #1627)
- **Dominios nuevos**: `integration-ports` (14 requisitos, 31 escenarios), `connectors` (14 requisitos, 31 escenarios)
- **Formato**: español colombiano formal, Given/When/Then, DEBE/DEBERÍA/PUEDE
- **Decisiones ratificadas**: unicidad por `external_account_id` (no user+provider), state en Redis, Fernet para cifrado, credenciales en tabla separada, puertos solo-lectura estrictos
- **Status**: Completo; 0 preguntas abiertas hacia verify (3 abiertas para design, todas resueltas)

### Design (Observation #1629)
- **Estructura**: Motor `app/integrations/` + módulo `app/modules/connectors/` (espejo del patrón notify+modules/notifications)
- **6 correcciones post-validación**: RBAC con `require_role(admin, manager)` (primer consumidor real), método `authorize` como GET (no POST), ruta callback GLOBAL (no scoped), desconexión con ruta plana, enums concretos, fakeredis en dev
- **Errata sobre spec**: callback en `GET /connectors/oauth/callback` (global, no `{id}`/callback scoped) — ajuste técnico por requisito OAuth de `redirect_uri` estático, trazado explícitamente en spec
- **Status**: Validado; 5 decisiones de design ratificadas por orquestador

### Tasks (Observation #1639)
- **5 lotes / 5 commits**: `0119a92` (núcleo), `2c05762` (migración 0015 + modelos), `91ec780` (CRUD), `d1b99ed` (OAuth), `881af2e` (cuentas conectadas + VERIFY)
- **49 tareas planificadas → 49 completadas [x]**
- **Forecast**: ~2.200–2.600 líneas, High risk (lotes 1 y 4 > 400 líneas c/u por acoplamiento), stacked-to-main chained PRs, `delivery_strategy: exception-ok` ya cubre excepción
- **Serialización**: Migración 0015 sobre head real `0014` (21-project-hierarchy ya lo tomó)
- **Status**: Aplicado; ciclo RED→GREEN→VERIFY completado en todos los lotes

### Apply Progress (implicit, Observation #1639 referencia)
- **Commit inicial**: `0119a92` feat(integrations): núcleo hexagonal
- **Commits ejecutados**: `0119a92`, `2c05762`, `91ec780`, `d1b99ed`, `881af2e`, `6b33aea` (state.yaml apply: done)
- **HEAD final**: `d7b59e3` (correcciones post-revisión 4R: atomicidad callback, reconexión sin 500, guardia de llave Fernet)
- **Líneas generadas**: ~2.350 (dentro del forecast)
- **Desviaciones documentadas**: 5 desviaciones técnicas vs diseño original (callback global con pop de state, soft+purga de credenciales, redirect_uri opcional con allowlist, `AccessContext` con scopes+sink, firmas elaboradas de `oauth.py`), todas ratificadas y sin impacto en specs
- **Status**: Aplicado; 3 CRITICAL de revisión 4R corregidos en `d7b59e3`

### Verification (Observation #1677)
- **Verdict**: PASS WITH WARNINGS
- **14/14 requisitos, 31/31 escenarios COMPLIANT** — evidencia de ejecución runtime con 54 pruebas nuevas en 10 archivos de test
- **49/49 tareas confirmadas completas y coherentes con código**
- **Build**: ruff/mypy limpios en backend completo (205 archivos)
- **Tests**: 642 passed / 13 failed (preexistentes, zero regresión) + suite acotada 54/54 passed (exit 0)
- **Migration 0015**: ciclo upgrade/downgrade/upgrade verificado de forma independiente contra BD desechable; `alembic check` sin diff
- **Security**: 5 Security Requirements con test RED verificados; 3 CRITICAL de revisión 4R (callback atómico, reconexión, guardia de llave) corregidos en `d7b59e3` con evidencia RED→GREEN
- **AccessContext contract**: `scopes: tuple[str,...]` + `on_tokens_refreshed: Callable[[OAuthTokens], Awaitable[None]] | None` — presente en código y probado en runtime; listo para adaptadores 15/16 y cambio 22
- **WARNINGS**: 
  1. `docs/diagrams/er-model.md` líneas 583-587 desactualizado (soft-delete AMBAS vs soft-delete cuenta + DELETE física credenciales) — **CORREGIDO en esta sesión de archivado**
  2. Suite completa exit code 1 por deuda preexistente httpx/conftest — no bloqueante pero flagged para automatización
- **Status**: Verificado; todas las pruebas requisito→escenario→test cubiertas

---

## Artefactos Migrados al Archivo

| Artefacto | Observación Engram | Ubicación Archivo | Estado |
|-----------|-------------------|-------------------|--------|
| `proposal.md` | #1620 | `/specs/proposal.md` | Migrado ✅ |
| `specs/integration-ports/spec.md` | (parte de #1627) | `/specs/integration-ports/spec.md` | Migrado ✅ |
| `specs/connectors/spec.md` | (parte de #1627) | `/specs/connectors/spec.md` | Migrado ✅ |
| `design.md` | #1629 | `/specs/design.md` | Migrado ✅ |
| `tasks.md` | #1639 (tareas) | `/specs/tasks.md` | Migrado ✅ |
| `verify-report.md` | #1677 | `/specs/verify-report.md` | Migrado ✅ |
| `state.yaml` | (derivado) | `/state.yaml` | Migrado ✅ |
| `archive-report.md` | (este archivo) | `/archive-report.md` | Generado ✅ |

---

## Specs Principales Creadas

| Spec | Ubicación | Acción | Descripción |
|------|-----------|--------|-------------|
| `integration-ports` | `openspec/specs/integration-ports/spec.md` | CREATED | Nuevo dominio; 5 puertos read-only, registro, fake adapter, protocolo uniforme, frontera solo-lectura |
| `connectors` | `openspec/specs/connectors/spec.md` | CREATED | Nuevo dominio; CRUD con RBAC, OAuth genérico, cifrado Fernet, aislamiento multi-tenant |

**Política de fusión**: Ambos dominios son NUEVOS (no existían specs principales previas), por lo que se copiaron directamente en lugar de fusionar como delta ADDED/MODIFIED.

---

## Documentación Actualizada

| Documento | Cambio | Estado |
|-----------|--------|--------|
| `docs/diagrams/er-model.md` | Corrección de línea 583-587 (soft-delete vs purga de credenciales) | ✅ CORREGIDO |
| `openspec/specs/integration-ports/spec.md` | Creado (nuevo) | ✅ CREADO |
| `openspec/specs/connectors/spec.md` | Creado (nuevo) | ✅ CREADO |

---

## Commits Archivados

| Commit | Descripción | Lote | Estado |
|--------|-------------|------|--------|
| `0119a92` | feat(integrations): núcleo hexagonal de puertos oauth cifrado y adaptador fake | 1 | ✅ Archivado |
| `2c05762` | feat(connectors): migración 0015, modelos de conectores, cuentas y credenciales cifradas | 2 | ✅ Archivado |
| `91ec780` | feat(connectors): CRUD de conectores con RBAC y aislamiento multi-tenant | 3 | ✅ Archivado |
| `d1b99ed` | feat(connectors): flujo OAuth authorize/callback con cifrado y anti-replay | 4 | ✅ Archivado |
| `881af2e` | feat(connectors): listado y desconexión de cuentas conectadas | 5 | ✅ Archivado |
| `6b33aea` | chore: state.yaml apply: done | Meta | ✅ Archivado |
| `d7b59e3` | (correcciones post-revisión 4R: callback atómico, reconexión, guardia Fernet) | Hotfix | ✅ Archivado |

**HEAD al archivar**: `d7b59e3` en rama `feat/consume-solercia-ui`

---

## Métricas Finales

| Métrica | Valor |
|---------|-------|
| Requisitos (integration-ports + connectors) | 14/14 ✅ |
| Escenarios Given/When/Then | 31/31 ✅ |
| Tareas de implementación | 49/49 ✅ |
| Tests nuevos (10 archivos) | 54/54 ✅ |
| Tests preexistentes fallidos | 13 (zero regresión) |
| Tests preexistentes pasados | 642 ✅ |
| Líneas implementadas | ~2.350 (forecast ~2.200–2.600) |
| Migración Alembic | 0015 (down_revision="0014") ✅ |
| Ruff check (backend completo) | All checks passed ✅ |
| MyPy check (backend completo) | 205 archivos sin issues ✅ |
| Security Requirements probados | 5/5 (OAuth, cifrado, anti-CSRF, multi-tenant, anti-SSRF) ✅ |

---

## Decisiones Ratificadas

1. **Varias cuentas del mismo proveedor por usuario**: unicidad por `external_account_id` dentro del conector (NO user+provider) → permite conectar múltiples buzones
2. **OAuth state en Redis con TTL**: transitorios sin tabla → TTL nativo, no requiere limpieza
3. **Cifrado de tokens con Fernet**: clave simétrica desde entorno → frontera lista para migrar a KMS en el futuro
4. **Credenciales en tabla separada**: `connection_credentials` 1:1 con la cuenta, aísla secretos → soft-delete cuenta + purga física de credenciales
5. **Puertos read-only estrictos**: sin escritura hacia el proveedor en esta ola → adaptadores 15-19 extenderán si se necesita

---

## Deuda Técnica Trazada

| Deuda | Prioridad | Descripción | Seguimiento |
|-------|-----------|-------------|-------------|
| httpx/conftest preexistente (13 tests fallidos) | Baja | 13 fallas ajenas al cambio, documentadas, zero regresión | Fuera del alcance cambio 14 |
| Renovación automática de tokens | Media | `adapter.refresh` + `expires_at` listos; orquestación se difiere a 15-19/22 | Será parte de cambio 22 |

---

## Siguiente Paso Recomendado

**Cambio 15** (adaptador Microsoft 365): consume `integration-ports` y `connectors` sin cambios al núcleo (nuevo adaptador = clase registrada).

---

## Audit Trail Completo

Esta sesión de archive ha:
1. ✅ Fusionado las 2 specs delta (`integration-ports`, `connectors`) en las specs principales (`openspec/specs/`)
2. ✅ Movido la carpeta de cambio a `openspec/changes/archive/2026-07-18-14-integration-ports/` con todos los artefactos
3. ✅ Corregido el warning de documentación en `docs/diagrams/er-model.md`
4. ✅ Actualizado `state.yaml` con `archive: done`
5. ✅ Generado este `archive-report.md` con trazabilidad completa de Engram
6. ✅ Preparado para commit selectivo (specs principales + archive + docs + eliminación de carpeta original)
7. ✅ Registrado el ciclo en Engram bajo `sdd/14-integration-ports/archive-report`

**Todas las fases completadas: proposal → spec → design → tasks → apply → verify → archive ✅**
