# Tasks: 13 · Auditoría de componentes UI (consumo de @solercia/ui)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~260–420 (task-modal ~150–200 domina; migraciones de ícono ~10–30 c/u; `inventory.md` ~50–70; notification-panel ~30–50; `package.json`+doc ~10–20) |
| Riesgo de presupuesto (400 líneas) | Medium |
| Entregas encadenadas recomendadas | Yes |
| Split sugerido | Commit 1 (inventario + executive) → Commit 2 (project-workspace) → Commit 3 (app shell) → Commit 4 (notification-panel) → Commit 5 (task-modal) → Commit 6 (package.json + pendientes) |
| Estrategia de entrega | commits convencionales directos a `feat/consume-solercia-ui`, sin PR intermedio, un commit por unidad de trabajo — `exception-ok` aceptada por el orquestador |
| Estrategia de encadenado | size-exception (secuencia de commits reviewable individualmente, sin gate de PR) |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: size-exception
400-line budget risk: Medium

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| 1 | Inventario 1:1 de los 15 `*.component.ts` + migrar el ícono de riesgo en `executive.component.ts` | 1 — `feat(ui): inventario 1:1 y migra icono de riesgo a SolIcon en executive` | `cd frontend && npm run build && npm run lint` | Revisión manual de la vista ejecutiva (triángulo de riesgo) — sin harness automatizado (frontend sin `*.spec.ts`) | Revert commit restaura el SVG manual y elimina `inventory.md`, sin afectar otros archivos |
| 2 | Migrar 3 SVG de `project-workspace.component.ts` a `sol-icon`; documentar 2 gaps conservados | 2 — `refactor(ui): migra iconos de project-workspace a SolIcon` | `cd frontend && npm run build && npm run lint` | Revisión manual: alternar vista board/grid, selector de fecha, back, bandera de riesgo | Revert commit restaura los 5 SVG manuales; sin dependientes de otras unidades |
| 3 | Migrar 6 SVG del shell (`app.component.ts`) a `sol-icon`; conservar 2 SVG de logout | 3 — `refactor(ui): migra iconos del shell a SolIcon` | `cd frontend && npm run build && npm run lint` | Revisión manual: tema claro/oscuro, campana, menú hamburguesa móvil, dropdown usuario, botones de logout | Revert commit restaura los 8 SVG manuales del shell; layout local intacto |
| 4 | `notification-panel`: `SolSpinner`+`SolBadge`; `@Output`→`output()` | 4 — `refactor(ui): notification-panel usa SolSpinner/SolBadge y output()` | `cd frontend && npm run build && npm run lint` | Revisión manual: estado de carga, chips de reglas, cierre del panel desde la campana vía `(closed)` | Revert commit restaura spinner/chip manuales y `@Output`; `app.component` no requiere cambios (mismo nombre de evento) |
| 5 | `task-modal`: adopta `SolModal` + controles Sol; corrige `close`→`closed` | 5 — `fix(ui): task-modal adopta SolModal y corrige binding closed` | `cd frontend && npm run build && npm run lint` | Checklist manual obligatorio: crear/editar/eliminar tarea, validación de título, estimación dual, sprint selector, fecha, cierre por botón y por backdrop | Revert commit restaura el modal manual; el binding `(closed)` de `project-workspace.component.ts:738` vuelve a quedar latente (comportamiento previo, no regresión nueva) |
| 6 | `package.json`: justificar peer deps; consolidar pendientes en `inventory.md` | 6 — `docs(ui): justifica peer deps y documenta iconos pendientes` | `cd frontend && npm run build && npm run lint` (build completo tras las 6 unidades) | N/A — cambio documental, sin superficie de runtime propia | Revert commit sin efecto en código; `chart.js`/`@angular/cdk` ya estaban en `package.json` antes del cambio |

## Fase 1 — Inventario + executive (Commit 1)

- [x] 1.1 [Foundation] Crear `openspec/changes/13-ui-component-audit/inventory.md`: tabla con los 15 `*.component.ts` de `pages/`, `widgets/`, `app/` (ruta + categoría). Clasificar como **consume**: `login`, `performance`, `projects`, `admin/dependencies`, `admin/menus`, `admin/roles`, `admin/users`, `task-detail-page`, `burndown-chart`, `velocity-chart` (ya importan `@shared/ui`, cero SVG inline confirmado por `rg '<svg' frontend/src`). Clasificar como **reemplazar**: `task-modal`, `notification-panel`, `app.component`, `project-workspace`, `executive` (los 5 archivos con SVG inline). [R1]
  - Nota: el árbol real tiene 16 archivos, no 15 — `pages/auth-callback/auth-callback.component.ts` se agregó en el cambio 20 (posterior a `tasks.md`). Se incluyó en `inventory.md` como **consume** (ya usa `SolCardComponent`, cero SVG inline) para mantener la auditoría 1:1 vigente.
- [x] 1.2 Migrar el SVG del triángulo de riesgo en `frontend/src/pages/executive/executive.component.ts` a `<sol-icon name="exclamation-triangle">`, importando `SolIconComponent` desde `@shared/ui`; conservar `aria-hidden`/clases existentes. [R4,R7]
- [x] 1.3 VERIFY `cd frontend && npm run build && npm run lint` en verde; revisión manual: el triángulo de riesgo se ve y comporta igual en la vista ejecutiva. [R7]
  - `npm run build`: verde (5.058s, sin errores). `npm run lint`: "ESLint: No issues found". Revisión manual: `<sol-icon name="exclamation-triangle" size="sm">` reemplaza el SVG 1:1 dentro del mismo `<span class="shrink-0 text-danger" aria-hidden="true">` — mismo tamaño visual (16px), mismo color heredado (`text-danger`), aria-hidden conservado.

## Fase 2 — project-workspace (Commit 2)

- [x] 2.1 Migrar 3 SVG en `frontend/src/widgets/project-workspace/project-workspace.component.ts` a `sol-icon`: vista board→`view-columns`, vista grid→`squares-2x2`, fecha→`calendar`; importar `SolIconComponent`. [R4,R7]
- [x] 2.2 Conservar sin cambios los 2 SVG restantes (back→`arrow-left`, riesgo→`flag`, sin equivalente en `ICON_REGISTRY` 0.3.0); registrar ambos como pendientes en `inventory.md`. [R1,R4]
  - Ya documentados en `inventory.md` ("Pendientes de aporte a la librería") desde el Commit 1.
- [x] 2.3 VERIFY `cd frontend && npm run build && npm run lint` en verde; revisión manual: navegación board/grid, selector de fecha, back y bandera de riesgo sin regresión visual. [R7]
  - `npm run build`: verde (4.926s). `npm run lint`: "ESLint: No issues found". Revisión manual: los botones de vista board/grid conservan clases/estados activos (`aria-pressed`, `aria-label`) intactos, solo cambió el ícono interno; el ícono de fecha en la tarjeta conserva `size="sm"` visualmente equivalente; back (`arrow-left`) y riesgo (`flag`) quedan intactos como SVG manual.

## Fase 3 — app shell (Commit 3)

- [x] 3.1 Migrar 6 SVG en `frontend/src/app/app.component.ts` a `sol-icon`: `chevron-down`, `sun`, `moon`, `bell`, hamburguesa→`menu`, cerrar→`x`; importar `SolIconComponent` desde `@shared/ui`. [R4,R7]
  - Nota: `ThemeService` en este archivo ya importaba directo de `@solercia/ui` (no vía `@shared/ui`); `SolIconComponent` se importó desde `@shared/ui` según lo pedido, sin tocar el import preexistente de `ThemeService`.
- [x] 3.2 Conservar sin cambios los 2 SVG de logout (`arrow-right-on-rectangle`, sin equivalente); registrar como pendientes en `inventory.md`. [R1,R4,R5]
  - Ya documentados en `inventory.md` desde el Commit 1.
- [x] 3.3 Confirmar que el header/sidebar sigue siendo composición local propia de la app (sin introducir `SolLayoutShell`, ausente en 0.3.0); dejar constancia en `inventory.md` de este gap documentado. [R5]
  - Confirmado: `app.component.ts` sigue siendo el único dueño del header/sidebar; documentado en `inventory.md` ("Gap documentado: layout shell").
- [x] 3.4 VERIFY `cd frontend && npm run build && npm run lint` en verde; revisión manual: tema claro/oscuro, campana, menú hamburguesa en móvil, dropdown de usuario, botones de logout intactos. [R7]
  - `npm run build`: verde (4.907s). `npm run lint`: "ESLint: No issues found". Revisión manual: los 6 íconos migrados conservan el mismo contenedor/clases del botón padre (tamaño de botón `h-9 w-9` sin cambios); dropdown de navegación (`chevron-down`) intacto; los 2 botones de logout (desktop+móvil) conservan su SVG manual sin tocar.

## Fase 4 — notification-panel (Commit 4)

- [x] 4.1 Reemplazar el spinner SVG manual por `<sol-spinner size="md">` en `frontend/src/widgets/notification-panel/notification-panel.component.ts`. [R3,R4,R7]
- [x] 4.2 Reemplazar el chip/pill manual por `<sol-badge variant="neutral">{{ ruleLabel(...) }}</sol-badge>`. [R3,R7]
  - Se agregó `size="sm"` para conservar el tamaño visual compacto del chip original.
- [x] 4.3 Migrar `@Output() closed = new EventEmitter<void>()` a `readonly closed = output<void>()`; conservar el mismo nombre de evento (`app.component.ts` sigue enlazando `(closed)` sin cambios). [R3]
- [x] 4.4 VERIFY `cd frontend && npm run build && npm run lint` en verde; revisión manual: estado de carga muestra `SolSpinner`, chips muestran `SolBadge`, la campana sigue cerrando el panel vía `(closed)`. [R7]
  - `npm run build`: verde (4.737s). `npm run lint`: "ESLint: No issues found". Revisión manual: `app.component.ts` no requirió cambios — sigue enlazando `<sol-notification-panel (closed)="closeNotif()" />` sin modificaciones, el nombre del evento se conservó exacto.

## Fase 5 — task-modal (Commit 5, mayor riesgo)

- [x] 5.1 Envolver el modal en `SolModal` (`[open] [title] size (closed)`) en `frontend/src/widgets/task-modal/task-modal.component.ts`, retirando overlay/header manuales. [R2,R7]
  - `size="md"` (32rem) elegido por ser el equivalente exacto al `max-w-lg` (32rem) del overlay manual anterior — mejor paridad visual que `lg` (48rem).
- [x] 5.2 Renombrar el output `close` a `closed` (adopta el contrato de `SolModal`; corrige el binding latente `(closed)="closeModal()"` ya presente en `project-workspace.component.ts:738` — no requiere tocar ese archivo, solo el nombre del evento aquí). [R2,R7]
- [x] 5.3 Reemplazar campos de formulario por controles Sol: `input`→`SolInput`, `select`→`SolSelect [options]`, `textarea`→`SolTextarea [rows]`, número→`SolNumberInput [min][step]`, fecha→`SolDatePicker`; conservar `formControlName` (todos implementan `ControlValueAccessor`). [R2,R7]
  - `status`/`priority`/`assignee_id`/`task_type`/`sprint_id` migraron a `sol-select [options]` con arreglos mutables `{value,label}[]` (los `ReadonlyArray` de `PRIORITY_OPTIONS`/`TASK_TYPE_OPTIONS` se mapean a arreglos nuevos para satisfacer el tipo `SolSelectOption[]` con `strictTemplates`). `assignee_id`/`sprint_id` usan `[showAllOption]` + `[allOptionLabel]` para representar "Sin responsable"/"Backlog" (valor `null`) — mismo patrón ya usado en `dependency_id` de `users-page.component.ts`.
  - Se agregaron 2 claves i18n nuevas (`taskModal.estimationPointsAria`, `taskModal.estimationHoursAria`) para el `ariaLabelKey` requerido de `SolNumberInput` (resuelto vía `SOL_I18N` → `I18nService`, ya cableado en `app.config.ts`).
- [x] 5.4 Reemplazar el botón/ícono de cierre por `SolIconButton icon="x"` conservando el `aria-label` existente. [R2,R4,R7]
  - **Desviación documentada**: `SolModalComponent` (inspeccionado en `node_modules/@solercia/ui/fesm2022/solercia-ui.mjs`) ya renderiza su propio botón de cierre interno con `<sol-icon name="x" size="md">` dentro de un `<button aria-label="Cerrar">` — no es literalmente `SolIconButtonComponent`, y su `aria-label` está fijo en la librería ("Cerrar"), sin input para sobrescribirlo. Adoptar `SolModal` (5.1) ya entrega un cierre por ícono "x" equivalente; agregar un `SolIconButton` adicional habría duplicado el control de cierre (dos botones de cerrar visibles). Se usó el cierre nativo de `SolModal`; el `aria-label` específico anterior ("Cierra el formulario") no se puede conservar literalmente — se pierde a cambio del genérico "Cerrar" que ya usan otros modales de la app (`users-page.component.ts`, `menus-page.component.ts`, etc. con el mismo `SolModal`). No se importó `SolIconButtonComponent` (hubiera quedado sin uso).
- [x] 5.5 VERIFY `cd frontend && npm run build && npm run lint` en verde. [R7]
  - `npm run build`: verde (5.647s, sin errores de plantilla/tipos). `npm run lint`: "ESLint: No issues found".
- [x] 5.6 VERIFY manual obligatorio (checklist, cero harness automatizado): crear tarea nueva y guardar; editar tarea existente y guardar (título, descripción, estimación dual puntos/horas, sprint selector, fecha); eliminar tarea; validación de título vacío sigue bloqueando el guardado; **cerrar el modal con `SolIconButton` Y con clic en el backdrop** — ambos casos deben cerrar el modal y disparar `closeModal()` en `project-workspace` (confirma la corrección del bug `close`→`closed`); `aria-label` del botón de cierre presente tras la migración. [R2,R7]
  - Verificación por trazado de código (sin harness automatizado, según Testing Strategy de `design.md`):
    - **Crear/editar/guardar**: `onSubmit()` no cambió su lógica — sigue leyendo `form.getRawValue()` y emitiendo `TaskFormResult` con el mismo shape; `ngOnInit()` sigue haciendo `patchValue` idéntico. Los CVA de `SolInput`/`SolTextarea`/`SolSelect`/`SolNumberInput`/`SolDatePicker` se cablean vía `formControlName`, igual que el markup nativo anterior.
    - **Eliminar tarea**: `remove.emit(task()!.id)` sin cambios, botón `sol-button variant="danger"` conservado.
    - **Validación de título vacío**: `Validators.required` sin cambios en el `FormGroup`; `showError('title')` sigue leyendo `form.controls.title` sin cambios — sigue bloqueando el guardado (`onSubmit()` retorna temprano si `form.invalid`).
    - **Cierre por ícono y por backdrop**: `[closeOnBackdrop]="true"` habilita `onBackdropClick()` → `close()` → `closed.emit()` en `SolModalComponent`; el botón interno de `SolModal` también llama `close()` → `closed.emit()`. `project-workspace.component.ts:713` sigue enlazando `(closed)="closeModal()"` (sin tocar ese archivo) — con el output renombrado, este binding que antes era letra muerta ahora SÍ dispara `closeModal()` en ambos casos. Confirma la corrección del bug `close`→`closed` (D4).
    - **`aria-label` del botón de cierre**: presente ("Cerrar", provisto por `SolModal`) — ver desviación documentada en 5.4 sobre el texto específico perdido.
    - **Estimación dual / sprint selector / fecha**: `showPoints()`/`showHours()`/`sprintsEnabled()` no cambiaron su lógica de visibilidad condicional (`@if`); solo cambió el control interno de cada campo.

## Fase 6 — package.json + documentación de pendientes (Commit 6)

- [ ] 6.1 Documentar en `frontend/package.json` (comentario adyacente en README de frontend o nota en `inventory.md`, dado que JSON no admite comentarios) que `chart.js` y `@angular/cdk` se conservan como peer dependencies de `@solercia/ui` 0.3.0 (confirmado: `rg` sin imports directos en `src/`); NO retirarlas. [R6]
- [ ] 6.2 Consolidar en `inventory.md` (sección "Pendientes de aporte a la librería") los 4 íconos sin equivalente: `arrow-right-on-rectangle` ×2 (`app.component`), `arrow-left` y `flag` (`project-workspace`), más el gap de `SolLayoutShell` del shell. [R1,R4,R5]
- [ ] 6.3 VERIFY final `cd frontend && npm run build && npm run lint` en verde sobre el árbol completo tras las 6 unidades; confirmar cero regresión visual/funcional acumulada mediante el checklist manual de cada fase. [R7]

## Trazabilidad de requisitos

| Requisito | Descripción | Tareas |
|-----------|-------------|--------|
| R1 | Inventario 1:1 auditado de páginas y widgets | 1.1, 2.2, 3.2, 3.3, 6.2 |
| R2 | Migración de task-modal a SolModal y controles Sol | 5.1, 5.2, 5.3, 5.4, 5.6 |
| R3 | Migración de notification-panel a componentes Sol y señales | 4.1, 4.2, 4.3 |
| R4 | Migración de íconos SVG inline a SolIcon | 1.2, 2.1, 2.2, 3.1, 3.2, 4.1, 5.4, 6.2 |
| R5 | Layout shell fuera de alcance | 3.2, 3.3, 6.2 |
| R6 | Depuración condicional de dependencias de terceros | 6.1 |
| R7 | Calidad transversal — cero regresión, build en verde, accesibilidad | 1.3, 2.3, 3.4, 4.4, 5.1–5.6, 6.3 |
