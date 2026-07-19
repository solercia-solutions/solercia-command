# Inventario 1:1 — consumo de `@solercia/ui` en `frontend/src/`

Auditoría de cada `*.component.ts` bajo `pages/`, `widgets/` y `app/` (requisito R1). Clasificación:

- **Consume**: ya importa componentes de `@solercia/ui` (directo o vía `@shared/ui`) y no tiene SVG inline.
- **Reemplazar**: tenía chrome hecho a mano (SVG inline y/o modal/formulario manual) con equivalente en la librería 0.3.0 — migrado en este cambio.
- **Sin equivalente**: el ícono o el componente no existe en `@solercia/ui` 0.3.0 — se conserva la implementación local y queda documentado como pendiente de aporte a la librería.

## Tabla de clasificación (16 archivos)

> Nota: el inventario original de `tasks.md` contaba 15 archivos. `pages/auth-callback/auth-callback.component.ts` se agregó en el cambio 20 (SSO), posterior a la redacción de `tasks.md`; se incluye aquí para mantener la auditoría 1:1 vigente sobre el árbol real. Ya consume `SolCardComponent` y no tiene SVG inline.

| Ruta | Categoría | Detalle |
|------|-----------|---------|
| `app/app.component.ts` | Reemplazar | 8 SVG inline → 6 migran a `SolIcon`, 2 de logout se conservan (sin equivalente) |
| `pages/executive/executive.component.ts` | Reemplazar | 1 SVG inline (triángulo de riesgo) → `SolIcon` |
| `pages/login/login.component.ts` | Consume | `SolButtonComponent` (vía `@solercia/ui`), cero SVG inline |
| `pages/performance/performance.component.ts` | Consume | Sin SVG inline |
| `pages/projects/projects.component.ts` | Consume | Sin SVG inline |
| `pages/auth-callback/auth-callback.component.ts` | Consume | `SolCardComponent`; agregado en el cambio 20, sin SVG inline |
| `pages/admin/dependencies/dependencies-page.component.ts` | Consume | `SolModalComponent`/`SolIconButtonComponent`, sin SVG inline |
| `pages/admin/menus/menus-page.component.ts` | Consume | `SolModalComponent`/`SolIconButtonComponent`, sin SVG inline |
| `pages/admin/roles/roles-page.component.ts` | Consume | `SolModalComponent`/`SolIconButtonComponent`, sin SVG inline |
| `pages/admin/users/users-page.component.ts` | Consume | `SolModalComponent`/`SolIconButtonComponent`/`SolSelectComponent`, sin SVG inline |
| `pages/task-detail/task-detail-page.component.ts` | Consume | `SolSelectComponent`/`SolInputComponent`/`SolBadgeComponent`/`SolRichEditorComponent`, sin SVG inline |
| `widgets/burndown-chart/burndown-chart.component.ts` | Consume | Sin SVG inline |
| `widgets/velocity-chart/velocity-chart.component.ts` | Consume | Sin SVG inline |
| `widgets/notification-panel/notification-panel.component.ts` | Reemplazar | Spinner SVG → `SolSpinner`; chip manual → `SolBadge`; `@Output`→`output()` |
| `widgets/project-workspace/project-workspace.component.ts` | Reemplazar | 5 SVG inline → 3 migran a `SolIcon`, 2 se conservan (sin equivalente) |
| `widgets/task-modal/task-modal.component.ts` | Reemplazar | Modal/formulario manual → `SolModal` + controles Sol; corrige `close`→`closed` |

## Pendientes de aporte a la librería (SVG sin equivalente en `ICON_REGISTRY` 0.3.0)

| Ícono | Archivo(s) | Uso |
|-------|-----------|-----|
| `arrow-right-on-rectangle` (×2) | `app/app.component.ts` | Botón de cerrar sesión (desktop + menú móvil) |
| `arrow-left` | `widgets/project-workspace/project-workspace.component.ts` | Enlace "Volver a proyectos" |
| `flag` | `widgets/project-workspace/project-workspace.component.ts` | Indicador de tarea en riesgo (tarjeta del tablero) |

Confirmado por inspección de `ICON_REGISTRY` en `frontend/node_modules/@solercia/ui/fesm2022/solercia-ui.mjs`: ninguno de los 4 nombres anteriores existe en el registro 0.3.0. Los 4 SVG se conservan sin cambios hasta que la librería los incorpore.

## Gap documentado: layout shell (R5)

`app/app.component.ts` migra sus 8 SVG inline a `SolIcon`, pero el header/sidebar sigue siendo composición local de la aplicación. `@solercia/ui` 0.3.0 no exporta un `SolLayoutShell`; sustituirlo queda fuera de alcance de este cambio y se documenta como pendiente de aporte futuro a la librería.

## Dependencias de terceros — `chart.js` y `@angular/cdk` (R6)

`frontend/node_modules/@solercia/ui/package.json#peerDependencies` declara `@angular/cdk ^22.0.0` y `chart.js ^4.5.1` (usadas en runtime por `SolChart`/`SolKanbanBoard`). `rg` sobre `frontend/src/` confirma **cero imports directos** de `chart.js` o `@angular/cdk` en el código de la aplicación. Ambas se **conservan** en `frontend/package.json` como peer dependencies justificadas de `@solercia/ui` 0.3.0 — retirarlas rompería el build (`SolChart`/`SolKanbanBoard` fallarían en runtime). No se modifica `package.json`.

## Trazabilidad

Ver `openspec/changes/13-ui-component-audit/tasks.md` (Fases 1–6) y `design.md` (mapa de reemplazo por widget) para el detalle de la migración ejecutada por unidad de trabajo.
