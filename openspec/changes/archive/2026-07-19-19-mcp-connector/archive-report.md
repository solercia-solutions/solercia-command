# Archive Report: 19-mcp-connector

## Executive Summary

El cambio 19-mcp-connector (adaptador genérico MCP para recursos externos read-only) ha completado su ciclo SDD integral: propuesta, especificaciones, diseño, tareas, aplicación (TDD estricto), verificación (PASS con auditoría independiente de seguridad DNS-rebinding), y está archivado como `openspec/changes/archive/2026-07-19-19-mcp-connector/`. El cambio introduce el puerto `ExternalResourceReaderPort` al núcleo del 14 (capacidad `external_resources`), extiende los enums de credenciales y conectores, e implementa un adaptador `mcp` auto-registrado con enforcement de solo-lectura, anti-SSRF, aislamiento multi-tenant, y suite completa de 1010 tests verificados.

## Archive Metadata

| Campo | Valor |
|-------|-------|
| Cambio | 19-mcp-connector |
| Archivado en | `openspec/changes/archive/2026-07-19-19-mcp-connector/` |
| Fecha de archivo | 2026-07-19 |
| Modo artifact_store | hybrid |
| Dependencia | 14-integration-ports (ARCHIVADO) |
| Estado general | Completado y archivado |

## Artefactos Archivados

### Propuesta (#1643)
- **Origen Engram**: `sdd/19-mcp-connector/proposal` (ID 1643)
- **Ubicación archivo**: `proposal.md`
- **Contenido**: Declaración de intención, scope, capacidades nuevas/modificadas, riesgos, criterios de éxito, preguntas de ratificación resueltas.

### Especificaciones (#1656)

Tres specs con 16 requisitos totales y 36 escenarios Given/When/Then:

1. **integration-ports** (delta): 
   - ADDED: Puerto `ExternalResourceReaderPort` (capacidad `external_resources`) con 2 escenarios
   - MODIFIED: Protocolo de adaptador uniforme (adquisición directa) con 3 escenarios  
   - MODIFIED: Frontera solo-lectura estricta (excepción acotada de `call_tool`) con 3 escenarios
   - **Ubicación archivo**: `specs/integration-ports/spec.md`

2. **connectors** (delta):
   - ADDED: Extensión del enum `credential_kind` con `none` (2 escenarios)
   - ADDED: Registro de conector con credencial directa (3 escenarios)
   - **Ubicación archivo**: `specs/connectors/spec.md`

3. **mcp-connector** (spec nueva):
   - 11 requisitos (MC-R1 a MC-R11) con 23 escenarios de descubrimiento, lectura, invocación controlada, timeout, anti-SSRF, contenido inerte, frontera de lectura, aislamiento multi-tenant, servidor fake
   - **Ubicación archivo**: `specs/mcp-connector/spec.md`

**Origen Engram**: `sdd/19-mcp-connector/spec` (ID 1656)

### Diseño (#1659)
- **Origen Engram**: `sdd/19-mcp-connector/design` (ID 1659)
- **Ubicación archivo**: `design.md`
- **Contenido**: Enfoque técnico, decisiones arquitectónicas (SDK oficial vs. JSON-RPC propio, estructura de paquete, ciclo de sesión, config del conector, enforcement read-only, anti-SSRF con IP-pin), flujo de datos, cambios de archivo, contratos de interfaz, estrategia de testing, matriz de amenazas, migración y rollout, preguntas abiertas.
- **Correcciones aplicadas**: Línea 28 (tabla Anti-SSRF) y notas de Open Questions actualizadas para reflejar que el bloqueo de rangos privados es no-op documentado para hosts allowlisted; el IP-pin es el mecanismo que cierra DNS-rebinding (auditoría independiente en verify-report 639cda4).

### Tareas (#1668)
- **Origen Engram**: `sdd/19-mcp-connector/tasks` (ID 1668)
- **Ubicación archivo**: `tasks.md`
- **Contenido**: 8 lotes (Lote 0 bloqueante, Lotes 1-7 con commits), 7 commits verificados, trazabilidad R→lote, review workload forecast (High risk, size:exception), todas las tareas marcadas completas [x].
- **Commits referenciados**: 05465ea..8d2715d (apply principal) + 639cda4 (fix 4R), agregado a notas de Lote 7.

### Verificación (#1734)
- **Origen Engram**: `sdd/19-mcp-connector/verify-report` (ID 1734)
- **Ubicación archivo**: No persisted (contenido integrado abajo)
- **Veredicto**: PASS
- **Métricas**:
  - 16/16 requisitos COMPLIANT
  - 36/36 escenarios COMPLIANT (23 mcp-connector + 8 integration-ports + 5 connectors)
  - 8/8 escenarios adicionales del fix 4R cubiertos (9 tests nuevos: 5+2+2)
  - 0 CRITICAL, 2 WARNING (cosméticos, no bloqueantes), 3 SUGGESTION
  - Suite: 1010 passed / 13 failed (legacy pre-existentes, no relacionadas)
  - mypy + ruff: limpios (259 archivos)
  - HEAD verificado: 639cda4 (commit de corrección 4R)
  - **Auditoría de seguridad (independiente)**: DNS-rebinding cerrado por IP-pin; eliminación de `_is_private_or_reserved` es no-op para hosts allowlisted (la evaluación de rango privado nunca se disparaba para esos hosts en el flujo real); el spec MC-R7 exige permitir rangos privados si están allowlisted — sin regresión verificada.
  - **Gotcha operativo documentado**: `pytest` sin `TEST_DATABASE_URL` produce SKIPPED silenciosos en tests REST de connectors_mcp.
  - **Desviaciones as-built**:
    - `mcp==1.12.0` pinneado (última compatible con pydantic==2.10.4; 1.28.1 requiere ≥2.11.0)
    - `sse-starlette==2.2.1` pinneado (transitividad de mcp; versiones más recientes chocan con fastapi==0.115.6)
    - `MCP_BLOCK_PRIVATE_NETWORKS` es no-op documentado para hosts allowlisted (simplificación tras auditoría)
    - Bloqueo de rangos privados/reservados movido de barrera independiente a no-op (pero IP-pin sigue cierre TOCTOU)

## Spec Deltas Fusionados en Main Specs

Tras completar la verificación y antes del archivo, los deltas se incorporaron en las specs principales:

### 1. `openspec/specs/integration-ports/spec.md`
- ✅ Insertado: Puerto `ExternalResourceReaderPort` (nueva sección, 2 escenarios)
- ✅ Modificado: Protocolo de adaptador uniforme → adquisición directa (credencial token/none)
- ✅ Modificado: Frontera solo-lectura estricta → excepción acotada `call_tool`

### 2. `openspec/specs/connectors/spec.md`
- ✅ Extendido: `credential_kind` enum → agregado `none`
- ✅ Agregado: Registro de conector con credencial directa (mismo `POST /connectors`, sin flujo OAuth)

### 3. `openspec/specs/mcp-connector/spec.md` (NUEVA)
- ✅ Creada: Spec completa del adaptador MCP con 11 requisitos, 23 escenarios

## Trazabilidad de Observaciones Engram

| Fase | Topic Key | Observation ID | Estado |
|------|-----------|----------------|--------|
| proposal | `sdd/19-mcp-connector/proposal` | 1643 | active |
| spec | `sdd/19-mcp-connector/spec` | 1656 | active |
| design | `sdd/19-mcp-connector/design` | 1659 | active |
| tasks | `sdd/19-mcp-connector/tasks` | 1668 | active |
| verify-report | `sdd/19-mcp-connector/verify-report` | 1734 | active |
| archive-report | `sdd/19-mcp-connector/archive-report` | (this) | active |

## Ciclo Completado

| Fase | Fecha | Veredicto | Notas |
|------|-------|-----------|-------|
| proposal | 2026-07-18 | ✅ approved | Preguntas ratificadas |
| specs | 2026-07-18 | ✅ approved | 3 specs (16 req, 36 esc) |
| design | 2026-07-18 | ✅ approved | Decisiones arquitectónicas (SDK oficial, IP-pin, sesión efímera) |
| tasks | 2026-07-18 | ✅ approved | 8 lotes, 7 commits |
| apply | 2026-07-19 | ✅ done | 05465ea..8d2715d + fix 639cda4 (9 tests) → 1010 total |
| verify | 2026-07-19 | ✅ PASS | 16/16 req, 36/36 esc, 0 CRITICAL, auditoría DNS OK |
| archive | 2026-07-19 | ✅ done | Folder moved, specs merged, OLA_2.md updated |

## Dependencias y Orden de Ejecución

- **Depende de**: 14-integration-ports (ARCHIVADO ✅)
- **Orden estricto de applies**: 17 → 18 → 19 (verificado en pre-flight Lote 0)
- **Cabeza Alembic**: 0017 (sin migración propia del 19)

## Contenido del Archivo

```
openspec/changes/archive/2026-07-19-19-mcp-connector/
├── state.yaml                    # Estado: todas las fases done
├── proposal.md                   # Propuesta completa
├── design.md                     # Diseño con correcciones de DNS-rebinding
├── tasks.md                      # 8 lotes, 7 commits, nota del fix 639cda4
├── archive-report.md             # Este documento
└── specs/
    ├── mcp-connector/
    │   └── spec.md               # Spec nueva (11 req, 23 esc)
    ├── integration-ports/
    │   └── spec.md               # Delta (3 modified/added)
    └── connectors/
        └── spec.md               # Delta (2 added)
```

## Riesgos Residuales

**Ninguno bloqueante**. Los 2 WARNINGs del verify fueron cosméticos (mentiones desfasadas de "bloqueo de rangos privados" en alto nivel — corregidas en esta copia archivada). La auditoría independiente de DNS-rebinding confirmó sin regresión. Todos los CRITICALs fueron resueltos en 639cda4 con RED tests y recibido verde en verify final.

## Próximos Pasos

- ✅ Cambio archivado y cerrado
- ⏭️ El siguiente cambio en la OLA 2 (ej. 20-sso-keycloak, 21-project-hierarchy, 22-intake-classifier, 23-org-role-templates, 24-hierarchy-tree-view, 13-ui-component-audit) puede proceder según su planificación de dependencias.

## Autor y Validación

- **Archivado por**: sdd-archive executor (Haiku 4.5)
- **Fecha**: 2026-07-19 14:00 (approx)
- **Validación**: Todas las fases (proposal → spec → design → tasks → apply → verify) completadas. Estado.yaml marca archivo: done. OLA_2.md actualizado.
