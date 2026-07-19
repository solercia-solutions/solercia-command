# Design: 13 · Auditoría de componentes UI (consumo de @solercia/ui)

## Technical Approach

Migración de consumo, sin lógica nueva. Cada widget pendiente sustituye su *chrome* manual por el componente `sol-*` equivalente importado desde `@shared/ui` (re-export puro de `@solercia/ui`, ver `frontend/src/shared/ui/index.ts`). Los SVG inline pasan a `SolIconComponent` cuando el nombre existe en `ICON_REGISTRY`; si no existe se conserva el SVG y se documenta como pendiente de aporte (no se implementa aquí). El layout shell (`app/app.component.ts`) NO se sustituye por un `SolLayoutShell` (la librería no lo exporta — decisión ratificada): solo migran sus íconos. Se fragmenta por unidad (widget = PR) para respetar el presupuesto de revisión.

## Architecture Decisions

### D1 — SolIcon solo cuando el nombre existe en el registro; si no, gap documentado
| Opción | Tradeoff | Decisión |
|--------|----------|----------|
| Migrar todo SVG a `sol-icon` forzando aproximaciones | Deriva visual no aprobada (arrow→chevron, flag→triangle) | Rechazada |
| Migrar solo los que tienen equivalente 1:1; el resto queda como SVG + pendiente | Fidelidad visual intacta; deuda visible y acotada | **Elegida** |

### D2 — `chart.js` y `@angular/cdk` se conservan (son peer deps)
`@solercia/ui/package.json#peerDependencies` declara `@angular/cdk ^22.0.0` y `chart.js ^4.5.1`; `SolChart`/`SolKanbanBoard` los requieren en runtime. `rg` en `frontend/src/` confirma cero imports directos. Retirarlos rompería el build. **Se conservan y se documentan como peer deps justificadas** (no se retiran).

### D3 — `notification-panel`: átomos sí, contenedor no
El panel es un *dropdown* anclado bajo la campana (posicionado por `app.component`, `absolute right-0 top-full`), no un modal centrado: `SolModal` tiene semántica incorrecta. Se migran spinner→`SolSpinner` y chip→`SolBadge`; el contenedor permanece manual. Gap: la 0.3.0 no exporta popover/dropdown-panel → pendiente.

### D4 — `task-modal`: adoptar `SolModal` y alinear el output a `closed`
Hoy `task-modal` emite `close`, pero `project-workspace` (línea 738) enlaza `(closed)="closeModal()"` → binding latente sin efecto (el botón cerrar/backdrop no cierra desde el padre). Al adoptar `SolModal` (output `closed`), el widget expone `closed` y el binding existente del padre queda correcto: la migración también corrige el defecto latente.

## Mapa de reemplazo por widget

| Widget (archivo) | Manual → Sol | Mapeo inputs/outputs | Íconos → SolIcon | Gaps (conservar SVG) |
|---|---|---|---|---|
| `pages/executive/executive.component.ts` | ya usa `SolCard` | — | 1: triángulo riesgo → `exclamation-triangle` | — |
| `widgets/project-workspace/…component.ts` | ya consume Kanban/Timeline/Modal/Card/Button | — | 3: vista board → `view-columns`; vista grid → `squares-2x2`; fecha → `calendar` | 2: back → `arrow-left`; riesgo → `flag` |
| `app/app.component.ts` (shell, se mantiene) | — | — | 6: `chevron-down`, `sun`, `moon`, `bell`, hamburguesa → `menu`, cerrar → `x` | 2: logout ×2 → `arrow-right-on-rectangle` |
| `widgets/notification-panel/…component.ts` | spinner SVG → `SolSpinner`; chip pill → `SolBadge variant="neutral"` | `@Output() closed = new EventEmitter` → `readonly closed = output<void>()` (mismo nombre; `app.component (closed)` intacto) | — (spinner es SolSpinner) | — |
| `widgets/task-modal/task-modal.component.ts` | overlay+header+cerrar → `SolModal` (`[open] [title] size (closed)`); `input`→`SolInput`; `select`→`SolSelect [options]`; `textarea`→`SolTextarea [rows]`; number→`SolNumberInput [min][step]`; date→`SolDatePicker`; cerrar → `SolIconButton icon="x"` | reemplazar `close` por `closed`; conservar `save`/`remove`; formulario reactivo se re-cablea a los CVA (todos implementan `ControlValueAccessor`) | 1: cerrar → `x` (vía SolIconButton) | — |

Total 16 SVG: 11 → `SolIcon`, 1 → `SolSpinner`, 4 gaps conservados (`arrow-right-on-rectangle`×2, `arrow-left`, `flag`).

## Orden de unidades de trabajo

1. **U1 · executive** (1 ícono) — menor riesgo. Verifica: `ng build`+`eslint`, render del triángulo.
2. **U2 · project-workspace** (3 íconos + 2 gaps) — solo íconos, sin cambio de comportamiento.
3. **U3 · app shell** (6 íconos + 2 gaps logout) — alta visibilidad, solo íconos; verificar tema claro/oscuro, campana, nav móvil.
4. **U4 · notification-panel** (`SolSpinner`/`SolBadge` + `output()`) — verificar carga, chips, `(closed)` desde la campana.
5. **U5 · task-modal** (`SolModal`+controles Sol, mayor riesgo) — verificar crear/editar/eliminar, validación de título, estimación dual, sprint selector, cierre.
6. **U6 · package.json + doc de pendientes** — comentar `chart.js`/`@angular/cdk` como peer deps; registrar los 3 íconos faltantes como pendientes de librería.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `pages/executive/executive.component.ts` | Modify | +`SolIconComponent`; 1 SVG → `sol-icon` |
| `widgets/project-workspace/project-workspace.component.ts` | Modify | +`SolIconComponent`; 3 SVG → `sol-icon`; corregir `(closed)` del `sol-task-modal`; 2 gaps |
| `app/app.component.ts` | Modify | +`SolIconComponent` (desde `@shared/ui`); 6 SVG → `sol-icon`; 2 SVG logout conservados |
| `widgets/notification-panel/notification-panel.component.ts` | Modify | `SolSpinner`+`SolBadge`; `@Output`→`output()` |
| `widgets/task-modal/task-modal.component.ts` | Modify | `SolModal`+`SolInput/Select/Textarea/NumberInput/DatePicker`+`SolIconButton`; `close`→`closed` |
| `frontend/package.json` | Modify | Comentario/justificación de peer deps (sin retirar) |

## Interfaces / Contracts

```
<sol-icon name="calendar" size="sm" />                 // name required, SolIconName
<sol-icon-button icon="x" [ariaLabel]="…" (clicked)="…" />  // icon + ariaLabel required
<sol-modal [open]="true" [title]="…" size="lg" (closed)="…"> …form… </sol-modal>
<sol-spinner size="md" />   <sol-badge variant="neutral">{{ ruleLabel(...) }}</sol-badge>
// SolInput/Select/Textarea/NumberInput/DatePicker: ControlValueAccessor → formControlName
```

## Testing Strategy

No existe harness de pruebas en el frontend (sin `*.spec.ts`, sin karma/jest/vitest, sin script `test` en `package.json`). Plan honesto por unidad:

| Capa | Qué se verifica | Cómo |
|------|-----------------|------|
| Build | Compilación de producción sin errores de plantilla | `npm run build` (`ng build`) |
| Lint | Estilo y reglas (incluye plantillas Angular) | `npm run lint` (`eslint .`) |
| Revisión manual | Paridad visual/funcional 1:1, `aria-label`, teclado, i18n | Checklist por widget (crear/editar tarea, cierre de modal, campana, tema, chips) |

Añadir harness de pruebas queda fuera de alcance.

## Threat Matrix

N/A — sin routing, shell, subprocesos, automatización VCS/PR, clasificación de ejecutables ni integración de procesos. Cambio de consumo de UI en el cliente.

## Migration / Rollout

Refactor de solo frontend, aditivo, sin BD ni backend. Cada widget es un PR reversible en `feat/consume-solercia-ui`. Presupuesto estimado ~250–400 líneas autoras (task-modal ~150–200 domina). `Decision needed before apply: Yes` · `Chained PRs recommended: Yes` · `400-line budget risk: Medium`. Rollback: revertir el commit del widget restaura el chrome manual.

## Open Questions (Resolved in Archive)

- [x] `chart.js`/`@angular/cdk` — RESUELTO: son peer deps de `@solercia/ui`; se conservan (D2).
- [x] Confirmar que corregir el binding `close`→`closed` de `task-modal` (D4) es aceptable dentro de este cambio (corrige defecto latente, no solo migra). — CONFIRMADO EN VERIFY: accepted & implemented in commit 0a35768 + fix in 9cfe894.
- [x] Ratificar los 3 íconos faltantes (`arrow-right-on-rectangle`, `arrow-left`, `flag`) como pendientes de aporte a la librería (gaps conservados como SVG). — CONFIRMADO: documentados como gaps en inventory.md, ninguno se perdió, todos auditados (16 total: 12 migrados + 4 conservados).
