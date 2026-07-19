# Tasks: 13 · Auditoría de componentes UI (consumo de @solercia/ui)

**STATUS: 27/27 tasks complete [x]** (23 numeradas Fases 1–6 + 4 Adenda A.1–A.4)

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~260–420 (task-modal ~150–200 domina; migraciones de ícono ~10–30 c/u; `inventory.md` ~50–70; notification-panel ~30–50; `package.json`+doc ~10–20) |
| Riesgo de presupuesto (400 líneas) | Medium |
| Entregas encadenadas recomendadas | Yes |
| Estrategia de entrega | commits convencionales directos a `feat/consume-solercia-ui`, sin PR intermedio — `exception-ok` aceptada |

Decision needed before apply: No
Chained PRs recommended: Yes
400-line budget risk: Medium

## Commits ejecutados (git log)

1. `833cb42 feat(ui): inventario 1:1 y migra icono de riesgo a SolIcon en executive`
2. `6e55900 refactor(ui): migra iconos de project-workspace a SolIcon`
3. `7b227d0 refactor(ui): migra iconos del shell a SolIcon`
4. `f17be24 refactor(ui): notification-panel usa SolSpinner/SolBadge y output()`
5. `0a35768 fix(ui): task-modal adopta SolModal y corrige binding closed`
6. `e039b79 docs(ui): justifica peer deps y documenta iconos pendientes`
7. `9cfe894` (post-apply) — fix: guard de cierre durante saving + accesibilidad modal + poda i18n

## Fase 1 — Inventario + executive (Commit 1) — [x] DONE

- [x] 1.1 Crear `inventory.md` con tabla de 16 `*.component.ts` clasificados (consume | reemplazar | sin equivalente). [R1]
- [x] 1.2 Migrado el SVG del triángulo de riesgo en `executive.component.ts` a `<sol-icon name="exclamation-triangle">`. [R4,R7]
- [x] 1.3 VERIFY build+lint verde. [R7]

## Fase 2 — project-workspace (Commit 2) — [x] DONE

- [x] 2.1 Migrados 3 SVG a `sol-icon`: board→`view-columns`, grid→`squares-2x2`, fecha→`calendar`. [R4,R7]
- [x] 2.2 Conservados sin cambios: back→`arrow-left`, riesgo→`flag` (sin equivalente en ICON_REGISTRY 0.3.0), documentados en inventory.md. [R1,R4]
- [x] 2.3 VERIFY build+lint verde. [R7]

## Fase 3 — app shell (Commit 3) — [x] DONE

- [x] 3.1 Migrados 6 SVG a `sol-icon`: `chevron-down`, `sun`, `moon`, `bell`, `menu`, `x`. [R4,R7]
- [x] 3.2 Conservados 2 SVG de logout (`arrow-right-on-rectangle`, sin equivalente). [R1,R4,R5]
- [x] 3.3 Confirmado: header/sidebar sigue siendo composición local, sin `SolLayoutShell` (ausente en 0.3.0). [R5]
- [x] 3.4 VERIFY build+lint verde. [R7]

## Fase 4 — notification-panel (Commit 4) — [x] DONE

- [x] 4.1 Spinner SVG → `<sol-spinner size="md">`. [R3,R4,R7]
- [x] 4.2 Chip manual → `<sol-badge variant="neutral" size="sm">`. [R3,R7]
- [x] 4.3 `@Output()/EventEmitter` → `readonly closed = output<void>()`, mismo nombre de evento. [R3]
- [x] 4.4 VERIFY build+lint verde. [R7]

## Fase 5 — task-modal (Commit 5, mayor riesgo) — [x] DONE

- [x] 5.1 Modal envuelto en `SolModal` (size="md"=32rem, equivalente a max-w-lg). [R2,R7]
- [x] 5.2 Output `close`→`closed`, corrige binding latente en project-workspace. [R2,R7]
- [x] 5.3 Campos migrados a SolInput/SolTextarea/SolSelect/SolNumberInput/SolDatePicker, todos vía `formControlName` (CVA). [R2,R7]
- [x] 5.4 Desviación documentada: `SolModal` ya renderiza botón de cierre interno con aria-label genérico ("Cerrar"), no específico ("Cierra el formulario"). [R2,R4,R7]
- [x] 5.5 VERIFY build+lint verde. [R7]
- [x] 5.6 VERIFY manual: crear/editar/eliminar/validar/cierre por botón y backdrop; aria-label presente. [R2,R7]

## Fase 6 — package.json + documentación de pendientes (Commit 6) — [x] DONE

- [x] 6.1 Documentado en `inventory.md` que `chart.js` y `@angular/cdk` son peer deps de `@solercia/ui` 0.3.0 (cero imports directos en src/); se conservan. [R6]
- [x] 6.2 Consolidados en `inventory.md` los 4 íconos pendientes + gap de `SolLayoutShell`. [R1,R4,R5]
- [x] 6.3 VERIFY final build+lint verde sobre árbol completo. Conteo: 12 migrados (11 SolIcon + 1 SolSpinner) + 4 conservados = 16 SVG auditados, cero perdidos. [R7]

## Adenda — fixes post-Commit 6 (Commit 7 = 9cfe894)

- [x] A.1 [CRITICAL, behavior-activated] Guard de cierre durante `saving()`: el botón Cancelar `[disabled]="saving()"`; `<sol-modal [closeOnBackdrop]="!saving()" (closed)="onModalClosed()">`. Análisis del guard confirmado por lectura de `SolModalComponent` en la librería.
- [x] A.2 [WARNING, accesibilidad] Modal agrega `role="dialog"`, `aria-modal="true"`, `[attr.aria-label]` dinámico. Claves i18n `taskModal.createAria`/`taskModal.editAria` en `es-CO.json`.
- [x] A.3 [WARNING] Poda de `taskModal.closeAria` (clave huérfana). Claves vivas: `createAria`/`editAria`.
- [x] A.4 [deuda preexistente, trazada — no corregida] `notification-panel` sin estado de error diferenciado; candidato a cambio futuro.

## Trazabilidad de requisitos

| Requisito | Descripción | Tareas | Estado |
|-----------|-------------|--------|--------|
| R1 | Inventario 1:1 auditado de páginas y widgets | 1.1, 2.2, 3.2, 3.3, 6.2 | [x] |
| R2 | Migración de task-modal a SolModal y controles Sol | 5.1, 5.2, 5.3, 5.4, 5.6 | [x] |
| R3 | Migración de notification-panel a componentes Sol y señales | 4.1, 4.2, 4.3 | [x] |
| R4 | Migración de íconos SVG inline a SolIcon | 1.2, 2.1, 2.2, 3.1, 3.2, 4.1, 5.4, 6.2 | [x] |
| R5 | Layout shell fuera de alcance | 3.2, 3.3, 6.2 | [x] |
| R6 | Depuración condicional de dependencias de terceros | 6.1 | [x] |
| R7 | Calidad transversal — cero regresión, build en verde, accesibilidad | 1.3, 2.3, 3.4, 4.4, 5.1–5.6, 6.3 | [x] |
