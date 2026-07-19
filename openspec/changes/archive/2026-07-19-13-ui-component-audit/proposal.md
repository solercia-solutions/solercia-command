# Proposal: 13 · Auditoría de componentes UI (consumo de @solercia/ui)

## Intent

La rama `feat/consume-solercia-ui` ya migró vistas y widgets clave a `@solercia/ui` (0.1.1 → 0.2.0 → 0.3.0), pero la migración no es exhaustiva: quedan componentes hechos a mano con equivalente directo en la librería y dependencias UI de terceros que ya no se usan en `src/`. Esto reintroduce deuda visual, duplica mantenimiento e incumple la regla del repo "componentes de `@solercia/ui` antes que componentes nuevos". Este cambio cierra la auditoría 1:1 del frontend y reemplaza lo pendiente.

## Scope

### In Scope
- Inventario 1:1 de páginas y widgets de `frontend/src/`, clasificando cada uno: consume librería | reemplazar | sin equivalente.
- Reemplazar el *chrome* hecho a mano por componentes de `@solercia/ui` en los widgets pendientes (ver Áreas afectadas).
- Migrar los SVG inline (16 en 5 archivos) a `SolIconComponent`.
- Modernizar `notification-panel` de `@Output/EventEmitter` a `output()` (convención de señales).
- Depurar `package.json`: confirmar `chart.js` y `@angular/cdk` como peer deps de la librería o retirarlos si no se usan.
- Documentar los componentes sin equivalente como pendientes de aporte a la librería.

### Out of Scope
- El repositorio de `@solercia/ui` (fuera de este repo): solo se consume, no se modifica. Los faltantes se documentan, no se implementan aquí.
- Cambios de backend, migraciones de BD y rediseño visual (más allá del reemplazo 1:1).
- Actualizar la versión de la librería por encima de 0.3.0.

## Capabilities

### New Capabilities
- `frontend-ui-consumption`: política verificable de consumo de `@solercia/ui` (cero componentes duplicados con equivalente) + checklist de auditoría.

### Modified Capabilities
- None.

## Approach

Auditar cada archivo `*.component.ts` bajo `pages/`, `widgets/` y `app/`. Donde exista equivalente en la librería (0.3.0 expone SolModal, SolInput, SolTextarea, SolSelect, SolNumberInput, SolDatePicker, SolIcon, SolIconButton, SolSpinner, SolBadge, entre otros), sustituir el markup manual conservando comportamiento e i18n. Migrar íconos inline a `SolIconComponent`; si un ícono no está en el registro, documentarlo como pendiente. Verificar peer deps antes de tocar `package.json`. Fragmentar en PRs por widget para respetar el presupuesto de revisión.

## Affected Areas

| Área | Impacto | Descripción |
|------|---------|-------------|
| `frontend/src/widgets/task-modal/task-modal.component.ts` | Modified | Modal y campos (input/select/textarea/date/number) a mano → SolModal + controles Sol; ícono de cierre → SolIconButton/SolIcon |
| `frontend/src/widgets/notification-panel/notification-panel.component.ts` | Modified | Diálogo/spinner/chips a mano → SolSpinner/SolBadge/SolIconButton; `@Output` → `output()` |
| `frontend/src/app/app.component.ts` | Modified | 8 SVG inline del shell → SolIcon (el layout se mantiene: sin equivalente en la librería) |
| `frontend/src/widgets/project-workspace/project-workspace.component.ts` | Modified | 5 SVG inline sueltos → SolIcon (ya consume Kanban/Timeline/Modal/Card/Button) |
| `frontend/src/pages/executive/executive.component.ts` | Modified | 1 SVG inline → SolIcon |
| `frontend/package.json` | Modified | Depurar `chart.js` y `@angular/cdk` (retirar o dejar solo como peer dep de la librería) |

## Risks

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|------------|
| Un ícono inline no existe en el registro de SolIcon | Media | Documentar como pendiente de aporte; fallback temporal |
| `chart.js`/`@angular/cdk` son peer deps requeridas por SolChart/SolKanban | Alta | Verificar el build antes de retirar; no remover si son peer deps |
| El reemplazo del modal/form cambia DOM y estilos | Media | Revisión visual y de comportamiento; conservar clases de token |
| La migración supera el presupuesto de revisión (400 líneas) | Media | Fragmentar en PRs por widget |

## Rollback Plan

Cambio de solo frontend, aditivo/refactor, sin migración de BD ni backend. Revertir los commits restaura los componentes hechos a mano y las dependencias de `package.json`. Cada PR por widget se revierte de forma independiente.

## Dependencies

- `@solercia/ui` ≥ 0.3.0 (ya vendorizado en `frontend/vendor/`).
- Rama `feat/consume-solercia-ui` como base.
- Repositorio de la librería: fuera de alcance (solo consumo).

## Success Criteria

- [ ] Inventario 1:1 documentado: cada página/widget clasificado (consume | reemplazar | sin equivalente).
- [ ] `task-modal` y `notification-panel` reemplazan su chrome manual por componentes de `@solercia/ui`.
- [ ] Los 16 SVG inline migrados a `SolIcon` (o el faltante documentado como pendiente).
- [ ] `notification-panel` usa `output()` en lugar de `@Output/EventEmitter`.
- [ ] `package.json` sin dependencias UI de terceros sin uso; `chart.js`/`@angular/cdk` justificadas como peer deps o retiradas.
- [ ] Componentes sin equivalente documentados como pendientes de aporte a la librería.
- [ ] `ng build` y `eslint` del frontend en verde.
