# Verify Report: 24 · Vista de árbol jerárquico de proyectos

**Fecha**: 2026-07-19
**Rama**: `feat/consume-solercia-ui`
**HEAD verificado**: `0a62720` (rango de trabajo `3b7567c..2ed98dd` + `c48cadc` docs + `0a62720` fix 4R)
**Modo**: artefactos completos (proposal + specs + design + tasks) — verificación por lectura + comandos reales (`npm run build`, `npm run lint`, `tsc --noEmit`, `pytest`), sin harness de pruebas de componentes Angular (constraint heredada de `13-ui-component-audit`).

## Veredicto final

**PASS**

## Resumen ejecutivo

0 CRITICAL, 0 WARNING, 1 SUGGESTION. Los 2 CRITICAL y 1 WARNING de la revisión 4R (enlace `/hierarchy` invisible en la navegación dirigida por BD, `forkJoin` sin timeout por rama, texto plano en vez de `SolSpinner`) están corregidos en `0a62720` y verificados con evidencia de ejecución real (build/lint/tsc en verde, 1042 passed/13 legacy en pytest, `test_menu_seed.py` en verde).

## 1. Completitud de tareas (tasks.md)

24/24 tareas marcadas `[x]`, 6/6 fases. Sin tareas pendientes. Coincide con lo declarado en `sdd/24-hierarchy-tree-view/apply-progress`.

## 2. Evidencia de ejecución

| Comando | Resultado | Detalle |
|---|---|---|
| `cd frontend && npm run build` | ✅ OK | 5.2s, sin errores; chunk lazy `hierarchy-component` (9.64 kB) separado del bundle inicial — confirma `loadComponent` real |
| `cd frontend && npm run lint` | ✅ OK | "ESLint: No issues found" sobre todo el repo |
| `cd frontend && npx tsc --noEmit -p tsconfig.json` | ✅ OK | "TypeScript: No errors found" |
| `cd backend && pytest tests/ -q` (TEST_DATABASE_URL contra Postgres real) | ✅ 1042 passed, 13 failed | Los 13 son fallas legacy preexistentes en `test_attachments.py`, `test_comments.py`, `test_sprint_close.py`, `test_subtasks.py`, `test_task_key.py` — ninguna toca menús/jerarquía/auth |
| `cd backend && pytest tests/test_menu_seed.py -v` | ✅ 1 passed | Prueba nueva del fix (R1 backend) |
| `cd backend && pytest tests/test_menus_pagination.py tests/test_auth.py tests/test_auth_sso.py tests/test_sso_service.py tests/test_adapter_google_oauth.py -q` | ✅ 49 passed | Regresión de menús/auth/SSO — sin ruptura por el cambio en `_MENU_SEED`/`_ROLE_MENU_SEED` |

Total pytest: **1042 passed / 13 failed**, exactamente el número esperado de fallas legacy. `test_menu_seed.py` en verde.

## 3. Verificación de los 2 CRITICAL y 1 WARNING de la revisión 4R (commit `0a62720`)

### CRITICAL 1 — Enlace `/hierarchy` inalcanzable en la navegación dirigida por BD

**Causa raíz confirmada por lectura**: `app.component.ts` usa `fallbackLinks()` (que sí incluía `/hierarchy` desde U3) solo cuando `useMenuNav()` es `false` (`menu.loaded() && menu.menus().length > 0`). En una organización normal con menú cargado desde BD, `fallbackLinks` nunca se renderiza — la navegación real depende 100% de `_MENU_SEED`/`_ROLE_MENU_SEED` de `backend/app/db_init.py`, que antes del fix NO tenía fila para `/hierarchy`.

**Fix verificado en `backend/app/db_init.py`**:
- `_MENU_SEED` agrega `("Jerarquía", "list-tree", "/hierarchy", None, 1)` como entrada de nivel raíz (no hija de "Administración").
- `_ROLE_MENU_SEED` concede "Jerarquía" a `MANAGER` (`["Proyectos", "Jerarquía", "Vista de jefe", "Rendimiento"]`) y a `MEMBER` (`["Proyectos", "Jerarquía"]`); `ADMIN` ya tenía `"*"` (todo). Confirmado por lectura directa de línea 138-142.
- `_ensure_menus`/`_ensure_role_menus` corren en cada arranque y solo insertan filas faltantes (comentario explícito en el código, líneas 121-124) → orgs ya seedeadas recogen "Jerarquía" en su próximo restart sin migración de datos.
- `backend/tests/test_menu_seed.py` (nuevo, 63 líneas) prueba: (a) el menú "Jerarquía" existe con `path == "/hierarchy"`; (b) todo rol que ve "Proyectos" también ve "Jerarquía"; (c) idempotencia (una sola fila `/hierarchy` tras re-ejecutar el seed). **1 passed**.

**Veredicto**: CRITICAL corregido y probado en runtime real contra Postgres. El enlace ahora es alcanzable en la navegación dirigida por BD para `admin`/`manager`/`member`.

### CRITICAL 2 — `forkJoin` sin timeout por rama congelaba toda la vista

**Fix verificado en `frontend/src/pages/hierarchy/hierarchy.component.ts`**:
- `PROGRESS_TIMEOUT_MS = 15_000` (línea 21).
- Cada `Observable` de `this.projectsService.progress(root.id)` dentro del `.map()` que arma el array de `forkJoin` aplica `.pipe(timeout(PROGRESS_TIMEOUT_MS), map(...), catchError(...))` — el `timeout` está ANTES de `catchError`, por lo que una rama que expira cae al mismo `catchError` que una rama que falla por error HTTP, produciendo un `ProgressOutcome` con `error` poblado en vez de propagar el error al `forkJoin` completo (línea 136-150).
- Cada rama del `forkJoin` es un observable independiente con su propio `catchError` — una rama lenta/colgada NUNCA bloquea la resolución de las demás. `forkJoin` solo espera a que cada observable individual emita (o su `catchError` produzca un valor), no exige éxito global.

**Veredicto**: CRITICAL corregido — R7 ("Falla parcial de una raíz") ahora cubre tanto fallas HTTP como cuelgues por timeout, sin bloquear el resto del bosque. Confirmado por lectura de código; sin harness de pruebas de componentes Angular disponible para runtime (constraint del proyecto, ver sección 6).

### WARNING — Texto plano en vez de `SolSpinner`

**Fix verificado**: `hierarchy.component.ts` importa `SolSpinnerComponent` de `@shared/ui` (línea 11) y lo usa en el estado de carga (`<sol-spinner size="md" />` dentro de `role="status"`, líneas 41-45), en vez del `<p>` de texto plano anterior. Consistente con el requisito "Primitivos de @solercia/ui" (R9).

**Veredicto**: WARNING corregido.

### Limpieza adicional en el mismo commit (no bloqueante, ya incluida)

- Se eliminó el campo `status: string` no usado de `TreeNodeVM` (`project.model.ts`) y su asignación en `toNode()` — verificado que no queda ninguna referencia huérfana a `node().status` en `hierarchy.component.ts` ni en `widgets/project-tree/`.
- Errata del escenario 6 ("0/0" → "Sin tareas") documentada explícitamente en `spec.md` (líneas 61-64) como nota aclaratoria ligada a la Decisión 3 del design — no es una desviación silenciosa, está trazada.

## 4. Matriz de cumplimiento de los 10 requisitos / 15 escenarios

| # | Escenario | Req | Evidencia | Estado |
|---|---|---|---|---|
| 1 | Navegación desde la lista de proyectos | R1 | `_MENU_SEED`/`_ROLE_MENU_SEED` (backend, fix), `fallbackLinks` (frontend, fallback), ruta lazy `hierarchy` con `authGuard` en `app.routes.ts:37-43`, chunk lazy confirmado en build | ✅ |
| 2 | Bosque con varias sombrillas | R2 | `buildForest()` agrupa por `parent_project_id`; huérfano se promueve a raíz (`hierarchy.component.ts:107-121`) | ✅ |
| 3 | Expandir revela los hijos | R3 | `expanded` señal local; `@if (hasChildren() && expanded())` con `role="group"`, indentación `depth()*16` (`project-tree-node.component.ts:125-131`) | ✅ |
| 4 | Proyecto raíz sin hijos | R3 | `hasChildren()` falso → spacer sin botón chevron, `aria-expanded` null | ✅ |
| 5 | Roll-up de una sombrilla (18/20) | R4 | `flattenRollup` + `sol-progress-bar` proporcional (`project-tree-node.component.ts:100-111`) | ✅ |
| 6 | Proyecto hoja sin tareas | R4 | `total === 0` → "Sin tareas" (i18n `hierarchy.node.noTasks`); errata trazada en spec.md | ✅ |
| 7 | Metodologías mixtas en el subárbol | R5 | `badgeVariant` computed por instancia, sin herencia del padre | ✅ |
| 8 | Clic en un nodo navega al workspace | R6 | `routerLink` a `/projects/{id}` en cada fila + `Enter`/`Espacio` en hoja | ✅ |
| 9 | Carga inicial | R7 | `loading` activo antes del primer `subscribe`, `role="status"` con `sol-spinner` (fix WARNING) | ✅ |
| 10 | Organización sin proyectos | R7 | `rootProjects.length === 0` → estado vacío i18n | ✅ |
| 11 | Falla parcial de una raíz | R7 | `timeout(15s)` + `catchError` por rama dentro del `forkJoin` (fix CRITICAL 2) | ✅ |
| 12 | Uso en viewport móvil | R8 | `flex-wrap`→`sm:flex-nowrap`, controles `h-9 w-9`, indentación acotada | ✅ (lectura) |
| 13 | Navegación por teclado expande un nodo | R8 | `onKeydown` Enter/Espacio/flechas, roving tabindex vía `TreeFocusState` DI | ✅ |
| 14 | Gap de `sol-tree` documentado | R9 | JSDoc en `project-tree-node.component.ts:34-38` | ✅ |
| 15 | Tuteo formal en las etiquetas | R10 | `rg` contra patrones de voseo rioplatense en `es-CO.json` + los 3 componentes → 0 coincidencias (re-verificado en esta fase) | ✅ |

10/10 requisitos, 15/15 escenarios con evidencia de lectura + build/lint/tsc en verde. Sin harness de pruebas de componentes Angular en este proyecto (decisión heredada de `13-ui-component-audit`, documentada en `design.md` → "Testing Strategy"); por eso la cobertura de escenarios de UI es por lectura de código + verificación estática, no por test runtime de componente. Esto es un límite de proyecto ya aceptado en fases previas, no un hallazgo nuevo de esta verificación.

## 5. Coherencia con el design.md

- Decisión 1 (lista plana + `/progress` por raíz, fallback `tree()`) — implementada tal cual; fallback presente pero sin consumidor activo porque `GET /projects` sí emite `parent_project_id` (confirmado en Fase 0). Sin desviación.
- Decisión 2 (nodo recursivo auto-referente) — implementada tal cual, incluyendo el patrón de `ElementRef<HTMLElement>` explícito para evitar el error `TS2347` documentado en el apply.
- Decisión 3 (barra de avance con `SolProgressBarComponent`, "sin tareas" en vez de "0/0") — implementada, con errata trazada en el spec.
- `TreeFocusState` (archivo no listado en la tabla "File Changes" del design) está justificado en tasks.md 4.2 como detalle de implementación interno del widget para evitar un import circular — aceptable, no es una desviación de arquitectura.
- Sin desviaciones de diseño que rompan algún requisito del spec.

## 6. Honestidad de la cobertura declarada

Confirmado por lectura de `tasks.md` (notas de 3.4, 4.4, 5.4) y `proposal.md` (sección "Success Criteria", línea 70): la sesión de apply documentó explícitamente que no tuvo herramienta de navegador disponible ni acceso a `curl`/`wget` (interceptados por una herramienta local del entorno), y que el checklist de 15 escenarios se verificó por **lectura de código + `ng build`/`eslint`/`tsc --noEmit` en verde**, no por interacción real de navegador. Esto queda trazado como pendiente de QA manual humana o con herramienta de navegador antes de mergear — no se presenta como cobertura de runtime fingida. Esta fase de verify confirma esa misma limitación (sin herramienta de navegador ni Playwright/Cypress en el proyecto) y no encontró ninguna afirmación de "probado en navegador" que sea falsa.

**Riesgo residual no bloqueante**: la QA interactiva de navegador (clic real en el enlace de menú, expandir/colapsar visual, Tab/flechas reales, viewport móvil real, timeout real de 15s en una rama) sigue pendiente. Se recomienda como último paso antes de mergear a `main`, fuera del alcance de esta fase de verify (sin herramienta de navegador disponible tampoco en esta sesión de verify).

## 7. Regresión

- `pytest tests/test_menus_pagination.py tests/test_auth.py tests/test_auth_sso.py tests/test_sso_service.py tests/test_adapter_google_oauth.py -q` → **49 passed**. Login, SSO, auth-callback y menús intactos; el cambio en `_MENU_SEED`/`_ROLE_MENU_SEED` no rompió ningún test existente de menús.
- `npm run lint` corrió sobre TODO el repo (no solo los archivos tocados) → sin issues, sin regresión de estilo en otros módulos.
- Los 13 tests fallidos en pytest son exactamente los mismos archivos legacy no relacionados con este cambio (`attachments`, `comments`, `sprint_close`, `subtasks`, `task_key`).

## Issues

### CRITICAL
Ninguno.

### WARNING
Ninguno.

### SUGGESTION

1. **QA interactiva de navegador pendiente** (no bloqueante para archive, sí recomendada antes de merge a `main`): validar en vivo el flujo completo — clic en "Jerarquía" desde el menú dirigido por BD, expandir/colapsar visual, navegación por teclado con foco visible, timeout real de 15s simulando una rama lenta, y viewport móvil real. Ya está trazado honestamente en `proposal.md`/`tasks.md`; se reitera aquí como recordatorio para antes de mergear, no como bloqueo de esta fase.

## Conclusión

24/24 tareas completas, 10/10 requisitos y 15/15 escenarios cubiertos con evidencia de lectura + comandos reales en verde, los 2 CRITICAL y 1 WARNING de la revisión 4R corregidos y verificados en el commit `0a62720` con evidencia de ejecución (pytest real contra Postgres, `test_menu_seed.py` en verde, build/lint/tsc en verde), sin regresión en login/SSO/auth/menús. **Veredicto: PASS**.
