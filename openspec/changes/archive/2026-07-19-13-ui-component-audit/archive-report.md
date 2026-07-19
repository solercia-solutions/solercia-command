# Archive Report — 13 · Auditoría de componentes UI

**Cambio**: `13-ui-component-audit`
**Proyecto**: `gestion_proyectos`
**Modo**: Hybrid (filesystem + Engram)
**Fecha de archivo**: 2026-07-19
**Archivado en**: `/openspec/changes/archive/2026-07-19-13-ui-component-audit/`
**Estado**: **COMPLETO** — Ciclo SDD cierre

## Resumen ejecutivo

La auditoría 1:1 de consumo de `@solercia/ui` 0.3.0 en el frontend Angular ha sido completada, implementada, verificada y archivada. Se migró el 75% del chrome manual (12 de 16 SVG inline + 2 componentes + 1 patrón de señales) a componentes de librería. Los 4 gaps (3 iconos faltantes + 1 layout shell ausente) quedan documentados como pendientes de aporte futuro a la librería. Ciclo SDD cierre: proposal → spec → design → tasks (27/27 complete) → apply (6 commits) → verify (PASS) → archive.

## Fases completadas

| Fase | Estado | Artefacto | Engram ID | Filesystem |
|------|--------|-----------|-----------|------------|
| proposal | ✅ done | `sdd/13-ui-component-audit/proposal` | #1622 | `proposal.md` |
| spec | ✅ done | `sdd/13-ui-component-audit/spec` | #1626 | `specs/frontend-ui-consumption/spec.md` |
| design | ✅ done | `sdd/13-ui-component-audit/design` | #1632 | `design.md` (Open Questions resueltas en archive) |
| tasks | ✅ done | `sdd/13-ui-component-audit/tasks` | #1635 | `tasks.md` (27/27 checkboxes [x]) |
| apply | ✅ done | `sdd/13-ui-component-audit/apply-progress` | (no recover) | 7 commits: `833cb42..9cfe894` |
| verify | ✅ done | `sdd/13-ui-component-audit/verify-report` | #1691 | `verify-report.md` (PASS, 12/12 escenarios) |
| archive | ✅ done | `sdd/13-ui-component-audit/archive-report` | (this report) | `archive-report.md` |

## Trazabilidad de artefactos (Engram)

Todos los artefactos han sido recuperados de Engram (hybrid mode) y sus observation IDs registrados para auditoría:

1. **Proposal** (#1622)
   - Topic: `sdd/13-ui-component-audit/proposal`
   - Contenido: Scope, approach, capabilities (nueva: `frontend-ui-consumption`)
   - Estado: Archivado ✅

2. **Spec** (#1626)
   - Topic: `sdd/13-ui-component-audit/spec`
   - Tipo: Full new spec (capability `frontend-ui-consumption` nueva, no modificada)
   - Contenido: 7 requirements, 12 scenarios verificados
   - Fusionado a: `openspec/specs/frontend-ui-consumption/spec.md` ✅

3. **Design** (#1632)
   - Topic: `sdd/13-ui-component-audit/design`
   - Contenido: 4 decisiones arquitectónicas (D1–D4), mapa de reemplazo, testing strategy (honest)
   - Open Questions (3): todas resueltas en versión archivada ✅
   - Estado: Archivado con Open Questions marcadas [x]

4. **Tasks** (#1635)
   - Topic: `sdd/13-ui-component-audit/tasks`
   - Tareas: 23 numeradas (Fases 1–6) + 4 adenda (A.1–A.4) = 27 total
   - Estado: **27/27 complete** [x] ✅
   - Nota: conteo real en archivo es 27; prompt de fase decía "22" (discrepancia de referencia externa)

5. **Verify Report** (#1691)
   - Topic: `sdd/13-ui-component-audit/verify-report`
   - Veredicto: **PASS**
   - Escenarios: 12/12 cumplidos
   - Issues: 0 CRITICAL, 2 WARNING menores (staleness de design.md, conteo de tareas), 2 SUGGESTION
   - Build + Lint: verde en HEAD `9cfe894`

## Especificación fusionada

La delta spec de cambio ha sido fusionada a spec principal:

| Origen (delta) | Destino (main) | Acción | Estado |
|---|---|---|---|
| `openspec/changes/13-ui-component-audit/specs/frontend-ui-consumption/spec.md` | `openspec/specs/frontend-ui-consumption/spec.md` | Copia (spec nueva, no modificada) | ✅ Completada |

**Nota**: `frontend-ui-consumption` es una capability completamente nueva. No existía spec anterior. El delta spec se copia como la spec principal canónica. Ninguna fusión parcial fue necesaria.

**Contenido sintetizado**:
- **7 Requirements**: Inventario 1:1, migración task-modal, migración notification-panel, migración SVG, layout shell out of scope, peer deps condicionales, calidad transversal
- **12 Scenarios**: 1 classify + 2 task-modal + 2 notification-panel + 2 icons + 1 shell + 2 peer-deps + 2 quality
- **Verificación**: 12/12 scenarios passed, build/lint green, cero regresión funcional

## Artefactos archivados

Estructura completa archivada en `/openspec/changes/archive/2026-07-19-13-ui-component-audit/`:

```
2026-07-19-13-ui-component-audit/
├── proposal.md
├── design.md (Open Questions resueltas)
├── tasks.md (27/27 checkboxes [x])
├── verify-report.md (PASS)
├── inventory.md (16 componentes, 16 SVG auditados)
├── specs/
│   └── frontend-ui-consumption/
│       └── spec.md (7 requirements, 12 scenarios)
└── state.yaml (todas las fases: done)
```

**Entrega de fuente de verdad**:
- Filesystem: `/openspec/specs/frontend-ui-consumption/spec.md` ← nueva capabilidad definida aquí
- Backup: `/openspec/changes/archive/2026-07-19-13-ui-component-audit/specs/frontend-ui-consumption/spec.md` (idéntica)

## Resumen de ejecución

### Propuesta
- Auditoría 1:1 de frontend: 5 widgets hechos a mano + 16 SVG inline
- Objetivo: consumo verificable de `@solercia/ui` 0.3.0
- Alcance: componentes del cliente únicamente; librería fuera de scope

### Implementación
- **Commits**: 6 commits de apply + 1 commit de fix post-revisión = 7 commits totales
- **Cambios**: `pages/` (1 ícono), `widgets/` (task-modal + notification-panel + 8 íconos), `app/` (6 íconos) + `inventory.md` + fixes de accesibilidad
- **Líneas**: ~250–400 (documentado en design.md, presupuesto de revisión respetado)
- **Migraciones**: 11 SVG → SolIcon + 1 SVG → SolSpinner + 4 gaps conservados = 16 SVG totales auditados, cero perdidos

### Verificación
- **Escenarios**: 12/12 cumplidos
- **Build**: `npm run build` en verde (4.966s)
- **Lint**: `npm run lint` en verde (ESLint: No issues found)
- **Tareas**: 27/27 checkboxes [x]
- **Backend**: 683 passed / 13 failed (línea base preexistente, sin regresión)
- **Accesibilidad**: role="dialog", aria-modal, aria-label dinámicos añadidos a task-modal en fix post-4R
- **Fix crítico (A.1)**: Guard de cierre durante `saving()` verificado como correcto y suficiente para bloquear todas las 3 vías de cierre (backdrop, Escape, X)

### Archivado
- Carpeta del cambio movida a `/openspec/changes/archive/2026-07-19-13-ui-component-audit/`
- Spec fusionada a `/openspec/specs/frontend-ui-consumption/spec.md` (fuente de verdad para nueva capabilidad)
- Todos los artefactos recopilados en archive (filesystem + Engram ID references)
- State.yaml actualizado: todas las fases `done`, archivado el 2026-07-19

## Gaps documentados (no bloqueantes)

| Gap | Archivo | Razón | Impacto | Pendiente |
|---|---|---|---|---|
| `arrow-right-on-rectangle` (×2) | app.component | No existe en ICON_REGISTRY 0.3.0 | Botones de logout siguen con SVG manual | Aporte futuro a librería |
| `arrow-left` | project-workspace | No existe en ICON_REGISTRY 0.3.0 | Enlace "Volver" con SVG manual | Aporte futuro a librería |
| `flag` | project-workspace | No existe en ICON_REGISTRY 0.3.0 | Indicador de riesgo con SVG manual | Aporte futuro a librería |
| `SolLayoutShell` | app.component (shell) | No exporta la librería 0.3.0 | Header/sidebar son composición local | Aporte futuro a librería |
| `SolModal` aria nativo | task-modal | SolModal no expone `aria-label`/`role` inputs | Agregados manualmente en host, code duplication en otros consumidores de SolModal | Mejorar librería: exponer inputs |
| `SolNumberInput` null cosmético | task-modal | `writeValue()` no invoca `onChange` en librería | Valor 0 muestra visualmente, pero FormControl queda null (almacenamiento correcto vía `toNumber()`) | Limitación aceptada, documentada |
| `notification-panel` error state | notification-panel | Sin distinción de error vs. bandeja vacía (deuda preexistente) | Usuario ve "vacío" en ambos casos | Cambio futuro (out of scope) |

## Próximos pasos recomendados

1. **Revisión de OLA_2.md**: marcar fila 13-ui-component-audit como `verify ☑` y `archive ☑`
2. **Seguimiento de gaps**: abrir issues en repo de `@solercia/ui` para los 4 gaps (3 íconos + SolLayoutShell)
3. **Deuda técnica**: `notification-panel` error handling es candidata a cambio futuro (out of scope de esta auditoría)
4. **Cambio 20 (SSO)**: `auth-callback.component.ts` fue agregada después de `tasks.md` pero antes de apply; está clasificada como "consume" en `inventory.md` (ya usa SolCard, cero SVG inline) — auditoría 1:1 vigente ✅

## Observaciones finales

- **Ciclo completo**: La auditoría se ejecutó en modalidad de "size-exception" (commits directos a rama sin PR intermedio). Todos los commits están en `feat/consume-solercia-ui`, verificados en HEAD `9cfe894`.
- **Trazabilidad**: Todos los artefactos de Engram (#1622, #1626, #1632, #1635, #1691) han sido recuperados y referenciados en este reporte.
- **Coherencia**: El archivo `tasks.md` real contiene 27 checkboxes [x]; el conteo "22" mencionado en el prompt de la fase es una discrepancia de referencia externa (no afecta el archivo ni el código).
- **Limpieza recomendada**: `design.md` tiene 3 "Open Questions" de las cuales 2 están sin marcar pero fueron resueltas durante la ejecución. En esta copia archivada, se marcan todas como [x] con notas de resolución.
- **No hay CRITICAL issues**: 0 bloqueantes. 2 WARNING menores (staleness de docs, discrepancia de conteo de tareas) y 2 SUGGESTION informativas. El código es limpio.

---

**Archivado por**: `sdd-archive` executor
**Fecha**: 2026-07-19
**Modo**: Hybrid (filesystem + Engram)
**Estatus**: COMPLETE — El ciclo SDD para el cambio 13 está cerrado. La capabilidad `frontend-ui-consumption` está implementada, verificada y documentada en la fuente de verdad canónica.
