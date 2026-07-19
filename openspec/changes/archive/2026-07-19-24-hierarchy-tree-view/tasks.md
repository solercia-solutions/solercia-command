# Tasks: 24 · Vista de árbol jerárquico de proyectos

## Review Workload Forecast

| Campo | Valor |
|-------|-------|
| Líneas estimadas | ~400–470 (sin harness de pruebas frontend: entidad ~60–90, nodo recursivo ~130–150, contenedor ~70–90, página ~110–150, ruta/nav ~15, i18n ~25–35) |
| Divergencia con design.md | design.md estimó ~380–420 sin descomponer entidad (model+service) por separado; sdd-tasks ajusta a ~400–470 al separar `project.model.ts` y `projects.service.ts` y al sumar el JSDoc del gap de `sol-tree` (2.3) |
| 400-line budget risk | Medium (cercano al presupuesto, pero cada commit individual de trabajo queda muy por debajo de 400 líneas) |
| Chained PRs recommended | No — 5 commits de trabajo ya mantienen cada diff revisable de forma independiente sobre una sola rama; no se necesitan PR nuevos |
| Suggested split | U1 tipos+API → U2 widget árbol → U3 página+ruta+navegación → U4 estados+accesibilidad → U5 i18n+checklist final |
| Delivery strategy | exception-ok (fijada por el orquestador) |
| Chain strategy | size-exception — commits convencionales directos a `feat/consume-solercia-ui`, un commit por unidad, sin PR encadenado nuevo |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: Medium

### Suggested Work Units

| Unit | Objetivo | Commit | Focused test command | Runtime harness | Rollback boundary |
|------|----------|--------|----------------------|------------------|--------------------|
| U1 | Tipos (`parent_project_id`, `ProjectProgressNode`, `TreeNodeVM`) + `tree()`/`progress()` en el service | 1 — `feat(hierarchy): agrega tipos y servicio para el arbol de proyectos` | `cd frontend && npx eslint 'src/entities/project/**/*.ts'` | N/A — sin superficie de UI aún; verificado por `npm run build` (type-check) | Revert commit; nada fuera de `entities/project/` depende todavía de estos tipos |
| U2 | Widget recursivo `project-tree` (nodo + contenedor, ARIA base, gap `sol-tree` documentado) | 2 — `feat(hierarchy): agrega el widget recursivo project-tree` | `cd frontend && npx eslint 'src/widgets/project-tree/**/*.ts'` | `cd frontend && npm start`; render manual del widget con datos mock (aún sin ruta) | Revert commit; el widget no está enlazado a ninguna ruta todavía |
| U3 | Página `hierarchy` + ruta lazy + enlace de navegación | 3 — `feat(hierarchy): agrega la pagina, la ruta lazy y el enlace de navegacion` | `cd frontend && npx eslint 'src/pages/hierarchy/**/*.ts' 'src/app/app.routes.ts' 'src/app/app.component.ts'` | `cd frontend && npm start`; navegar `/projects` → `/hierarchy` contra la API real | Revert commit; ruta y enlace desaparecen, resto de la app intacto |
| U4 | Estados carga/vacío/error parcial + teclado + responsive | 4 — `feat(hierarchy): agrega estados, navegacion por teclado y responsive` | `cd frontend && npm run lint` | `cd frontend && npm start`; forzar org. sin proyectos, forzar fallo de `/progress` de una raíz, probar Tab/Enter/Espacio y viewport móvil (DevTools) | Revert commit; U3 sigue funcional sin los estados finos |
| U5 | Claves i18n es-CO + checklist manual final | 5 — `feat(hierarchy): agrega claves i18n y cierra el checklist manual` | `cd frontend && npm run build && npm run lint` | `cd frontend && npm start`; checklist manual completo contra los 15 escenarios del spec | Revert commit; la vista sigue funcional con los textos previos |

## Fase 0 — Pre-requisito de dependencia (antes de U1)

- [x] 0.1 [Pre-requisito] Confirmar que `21-project-hierarchy` completó apply+verify+archive; verificar en el backend real que `GET /projects/{id}/tree` y `GET /projects/{id}/progress` existen y responden envelope `{data}`, y si `GET /projects` emite `parent_project_id` por ítem. Si NO lo emite, documentar en 3.1 la activación del fallback `tree()` por raíz (Decisión 1 del design). [R2]

  **Resultado**: 21 y 13 archivados (`openspec/changes/archive/2026-07-18-21-project-hierarchy`, `2026-07-19-13-ui-component-audit`). `backend/app/modules/projects/router.py` expone `GET /{id}/tree` y `GET /{id}/progress`, ambos devuelven `{"data": ...}`. `ProjectRead` (usado por `GET /projects`) SÍ incluye `parent_project_id`. Vía primaria confirmada; fallback `tree()` NO se activa (se implementa en 1.2 como fallback disponible, sin uso activo en 3.1).

## Fase 1 — U1: Tipos + API service (Commit 1)

- [x] 1.1 `entities/project/project.model.ts`: agregar `parent_project_id: string | null` a `Project`; agregar `ProjectProgressNode` (self/rollup anidado) y `TreeNodeVM` (view-model del bosque). [R2,R4,R5]
- [x] 1.2 `entities/project/projects.service.ts`: agregar `tree(id)`/`progress(id)`, HTTP GET delgado siguiendo el patrón de `list()`. [R2]
- [x] 1.3 VERIFY `cd frontend && npm run build && npx eslint 'src/entities/project/**/*.ts'`.

  **Resultado**: `npm run build` OK (5.3s, sin errores). `npx eslint 'src/entities/project/**/*.ts'` → "No issues found". Commit 1: `feat(hierarchy): agrega tipos y servicio para el arbol de proyectos`.

## Fase 2 — U2: Widget de árbol recursivo (Commit 2)

- [x] 2.1 Crear `widgets/project-tree/project-tree-node.component.ts` (+ template): nodo recursivo standalone/`OnPush`/signals; `role="treeitem"` con `role="group"` anidado para hijos, `aria-expanded` reflejando signal local `expanded`; compone `SolCard` + `SolBadge` (metodología) + `SolProgressBar` (`value=rollup.done`/`max=rollup.total`, `total===0` → "sin tareas") + `SolIcon` (chevron-right/chevron-down) + acción "ir al proyecto" (`routerLink` a `/projects/{id}`); se renderiza a sí mismo para los hijos. [R3,R4,R5,R6,R9]
- [x] 2.2 Crear `widgets/project-tree/project-tree.component.ts` (+ `index.ts`): contenedor `role="tree"`, recibe `TreeNodeVM[]` como input y renderiza `project-tree-node` por cada raíz. [R3,R9]
- [x] 2.3 Agregar JSDoc en `project-tree-node.component.ts` documentando el gap: `@solercia/ui@0.3.0` no expone `sol-tree`, árbol propio pendiente de aporte a la librería (criterio del 13). [R9]
- [x] 2.4 VERIFY `cd frontend && npm run build && npx eslint 'src/widgets/project-tree/**/*.ts'`.

  **Resultado**: `npx eslint 'src/widgets/project-tree/**/*.ts'` → "No issues found". `npm run build` OK. Nota de verificación: como el widget aún no está enlazado a ninguna ruta, `ng build` no incluye estos archivos en su grafo de módulos; se corrió además `npx tsc --noEmit -p tsconfig.json` (incluye todo `src/**/*.ts` por defecto) → "No errors found", confirmando el tipado real del componente recursivo antes de enlazarlo en la Fase 3. Commit 2: `feat(hierarchy): agrega el widget recursivo project-tree`.

## Fase 3 — U3: Página + ruta + navegación (Commit 3)

- [x] 3.1 Crear `pages/hierarchy/hierarchy.component.ts` (+ template): host standalone/`OnPush`/signals; en `ngOnInit` llama `projectsService.list()`, agrupa por `parent_project_id` (raíces = `parent_project_id == null`; huérfano → se promueve a raíz), `forkJoin` de `progress(rootId)` por raíz, mapea a `TreeNodeVM[]`; si `list()` no emite `parent_project_id`, activa el fallback `tree()` por raíz (0.1, Decisión 1 del design). [R1,R2]

  **Resultado**: `GET /projects` SÍ emite `parent_project_id` (confirmado en 0.1) → vía primaria activa, fallback `tree()` NO se invoca (queda disponible en el service desde U1, sin consumidor). `forkJoin` de esta primera versión NO tiene todavía `catchError` individual por raíz (falla total si cualquier `/progress` falla) — se refina en la Fase 4 (4.1) a resiliencia parcial por rama.
- [x] 3.2 Modificar `app/app.routes.ts`: ruta lazy `path: 'hierarchy'` con `loadComponent` + `authGuard`, como hermana de `projects/:id` (antes del wildcard). [R1]
- [x] 3.3 Modificar `app/app.component.ts`: agregar enlace a `/hierarchy` en `fallbackLinks` (nav de solo texto). [R1]
- [x] 3.4 VERIFY `cd frontend && npm run build && npm run lint`; manual: navegar `/projects` → `/hierarchy`, confirmar chunk lazy y bosque con varias raíces (escenarios "Navegación desde la lista de proyectos", "Bosque con varias sombrillas").

  **Resultado**: `npm run build` OK — genera el chunk perezoso `hierarchy-component` (7.05 kB) separado del bundle inicial, confirmando `loadComponent` real. `npx eslint` sobre los 3 archivos → "No issues found". Verificación manual interactiva (clic real en el enlace, render del bosque contra datos reales) NO se pudo ejecutar en esta sesión: no hay herramienta de navegador disponible para este agente y `curl`/`wget` están bloqueados por una herramienta local del entorno (interceptados por `context-mode`); el contrato de backend ya se verificó por lectura directa de código fuente en 0.1. Pendiente de una pasada de QA manual humana o con herramienta de navegador en `sdd-verify`.

## Fase 4 — U4: Estados y accesibilidad (Commit 4)

- [x] 4.1 `pages/hierarchy/hierarchy.component.ts` (+ template): estado de carga mientras el `forkJoin` no resuelve; estado vacío cuando la organización no tiene proyectos; error legible por rama cuando `/progress` de una raíz falla (`catchError` individual dentro del `forkJoin`), sin bloquear el render de las demás raíces. [R7]
- [x] 4.2 `widgets/project-tree/project-tree.component.ts` + `project-tree-node.component.ts`: Enter/Espacio en el nodo enfocado expande/colapsa o activa "ir al proyecto"; roving tabindex entre los `treeitem` visibles. [R8]

  **Nota de implementación**: se agregó `widgets/project-tree/tree-focus-state.ts` (servicio `TreeFocusState` inyectable, ~10 líneas) para evitar un import circular entre `project-tree.component.ts` (que provee el estado) y `project-tree-node.component.ts` (que lo inyecta recursivamente); no está en la tabla "File Changes" del design.md porque es un detalle de implementación del mismo widget, no un archivo de otra capa. `role="treeitem"` se movió del `<div>` interno original al host del propio componente (`host: {...}` en el decorador) para que el elemento enfocable coincida exactamente con el que participa en la consulta `querySelectorAll('[role="treeitem"]')` del roving tabindex.
- [x] 4.3 Revisar breakpoints Tailwind mobile-first en ambos templates: sin scroll horizontal, controles con área táctil suficiente, indentación por profundidad legible en móvil. [R8]

  **Resultado**: fila del nodo con `flex-wrap` (pasa a `sm:flex-nowrap` desde 640px) → en móvil los elementos bajan de línea en vez de forzar scroll horizontal; nombre con `truncate` dentro de `min-w-0 flex-1`; controles de acción (chevron, "ir al proyecto") en `h-9 w-9` (36px), igual al tamaño de los botones de ícono del header (`app.component.ts`); indentación `depth() * 16` px, acotada por `MAX_DEPTH` del 21 (máx. ~64-80px), legible incluso en un viewport de 375px.
- [x] 4.4 VERIFY manual: "Carga inicial", "Organización sin proyectos", "Falla parcial de una raíz", "Uso en viewport móvil", "Navegación por teclado expande un nodo"; `npm run build && npm run lint`.

  **Resultado**: `npm run build` OK (chunk `hierarchy-component` 8.98 kB) y `npm run lint` → "No issues found" sobre TODO el repo (no solo los archivos tocados). `npx tsc --noEmit -p tsconfig.json` → "No errors found". Verificación de los 5 escenarios por lectura de código (sin navegador disponible en esta sesión, ver nota de 3.4): "Carga inicial" → `loading()` se activa antes del primer `subscribe` y se apaga solo tras resolver `list()`+`forkJoin`; "Organización sin proyectos" → rama `roots().length === 0` con card de estado vacío; "Falla parcial de una raíz" → `catchError` por observable dentro del `forkJoin` (4.1) confirmado por lectura, cada raíz resuelve independiente; "Uso en viewport móvil" → clases responsive de 4.3; "Navegación por teclado expande un nodo" → `onKeydown` con `Enter`/`Espacio` llamando `activate()`, que en un nodo con hijos alterna `expanded` (el `aria-expanded` del host es un `computed` derivado de esa misma señal, cambia a `true` de forma reactiva). Pendiente de una pasada de QA manual humana o con herramienta de navegador (misma limitación documentada en 3.4).

## Fase 5 — U5: i18n + checklist final (Commit 5)

- [x] 5.1 `assets/i18n/es-CO.json`: agregar claves `hierarchy.*` (título, enlace de navegación, carga, vacío, error por rama, "ir al proyecto", `aria-label` de expandir/colapsar) en español colombiano formal con tuteo. [R10]

  **Nota**: la clave del enlace de navegación (`nav.links.hierarchy`) se agregó en U3 (Fase 3), no aquí, porque `app.component.ts` no se vuelve a tocar en esta fase y ya usa 100% i18n para ese arreglo (ver nota de 3.3). El namespace `hierarchy.*` completo (título, subtítulo, carga, vacío, errores, aria-labels del nodo/árbol) se agregó en este commit.
- [x] 5.2 Reemplazar cualquier texto embebido restante en `hierarchy.component`, `project-tree.component` y `project-tree-node.component` por claves de `I18nService`; confirmar cero strings hardcodeados. [R10]

  **Resultado**: `rg` sobre los tres archivos por los literales en español usados en Fases 1-4 (Árbol, Cargando, Todavía, Colapsar, Expandir, Ir al proyecto, Sin tareas, No se pudo, No fue posible) → 0 coincidencias. Los mensajes de error de red/carga/rama pasaron de literales en TS a `this.i18n.translate('hierarchy.errors.*')`.
- [x] 5.3 VERIFY final `cd frontend && npm run build && npm run lint` en verde.

  **Resultado**: `npm run build` OK (chunk `hierarchy-component` 9.53 kB). `npm run lint` sobre TODO el repo → "No issues found". `npx tsc --noEmit -p tsconfig.json` → "No errors found".
- [x] 5.4 VERIFY checklist manual completo contra los 15 escenarios del spec (tabla abajo) y marcar los Success Criteria de `proposal.md`.

  **Limitación de esta sesión**: no hubo herramienta de navegador disponible para este agente, y `curl`/`wget` quedaron interceptados por una herramienta local del entorno (`context-mode`) al intentar un smoke test contra un backend vivo en `:8000` (además, el intento de levantar `docker compose up -d backend` falló por conflicto de puerto con otro proceso ya escuchando en `127.0.0.1:8000`, contenedor limpiado con `docker compose rm -f backend`). El checklist de abajo se verificó por **lectura de código** contra cada escenario del spec, más `ng build`/`eslint`/`tsc --noEmit` en verde. Se recomienda una pasada de QA manual humana o con herramienta de navegador antes de mergear (misma nota ya dejada en 3.4 y 4.4).

### Checklist manual (15 escenarios del spec)

| # | Escenario | Req | Verificación (lectura de código) |
|---|-----------|-----|-----------------------------------|
| 1 | Navegación desde la lista de proyectos | R1 | `fallbackLinks` en `app.component.ts` incluye `/hierarchy`; ruta lazy con `authGuard` registrada antes del wildcard; `ng build` genera el chunk `hierarchy-component` separado del bundle inicial. |
| 2 | Bosque con varias sombrillas | R2 | `buildForest()` agrupa por `parent_project_id`, empuja cada proyecto sin padre (o huérfano) a `rootProjects`; `project-tree` itera `nodes()` con `@for` y renderiza un `project-tree-node` por raíz. |
| 3 | Expandir revela los hijos | R3 | `expanded` es una señal local por nodo; `@if (hasChildren() && expanded())` renderiza `role="group"` con los hijos indentados por `depth() * 16`. |
| 4 | Proyecto raíz sin hijos | R3 | `hasChildren()` en `false` → se renderiza un `<span>` espaciador en vez del botón chevron; `aria-expanded` queda `null` (`hasChildren() ? expanded() : null`), sin control de expandir/colapsar. |
| 5 | Roll-up de una sombrilla (18/20) | R4 | `flattenRollup` copia `node.rollup.{done,total}` (ya agregado por el backend) a un `Map`; el template imprime `{{ rollup.done }}/{{ rollup.total }}` + `sol-progress-bar` proporcional. |
| 6 | Proyecto hoja sin tareas (0/0) | R4 | `node().rollup!.total === 0` → texto "Sin tareas" (i18n `hierarchy.node.noTasks`), sin barra ni error (design.md Decisión 3: reemplaza el literal "0/0" por un estado "sin tareas" más legible; interpretación documentada del spec). |
| 7 | Metodologías mixtas en el subárbol | R5 | `badgeVariant` es un `computed` sobre `this.node().methodology` de la instancia propia; cada nodo recursivo tiene su propio `node` input, sin heredar del padre. |
| 8 | Clic en un nodo navega al workspace | R6 | `<a [routerLink]="['/projects', node().id]">` presente en cada fila; en nodos hoja, `Enter`/`Espacio` también navega vía `router.navigate(['/projects', node().id])`. |
| 9 | Carga inicial | R7 | `loading` se activa antes del primer `subscribe` a `list()` y sólo se apaga tras resolver el `forkJoin` de `/progress`; template muestra `role="status"` mientras tanto. |
| 10 | Organización sin proyectos | R7 | `rootProjects.length === 0` → `roots.set([])` + tarjeta de estado vacío explícita (i18n `hierarchy.empty.*`). |
| 11 | Falla parcial de una raíz | R7 | Cada `progress(root.id)` tiene su propio `catchError` dentro del `forkJoin` (no uno global); la raíz fallida recibe `rollupError` (mensaje i18n `hierarchy.errors.branch`), las demás resuelven con sus datos normales. |
| 12 | Uso en viewport móvil | R8 | Fila `flex-wrap` (pasa a `sm:flex-nowrap` desde 640px) evita scroll horizontal; controles `h-9 w-9` (36px, igual al header); indentación acotada por `MAX_DEPTH` del 21. |
| 13 | Navegación por teclado expande un nodo | R8 | `onKeydown` con `Enter`/`Espacio` llama `activate()`, que en nodos con hijos alterna `expanded`; el `aria-expanded` del host es un `computed` derivado de esa misma señal → cambia a `true` de forma reactiva. |
| 14 | Gap de `sol-tree` documentado | R9 | JSDoc en `project-tree-node.component.ts` documenta explícitamente que `@solercia/ui@0.3.0` no exporta `sol-tree` y que queda pendiente de aporte a la librería (criterio del 13). |
| 15 | Tuteo formal en las etiquetas | R10 | `rg` sobre `hierarchy.*` en `es-CO.json` y los tres componentes contra patrones de voseo rioplatense (`podés`, `querés`, `tenés`, `hacé`, `arrastrá`, `seleccioná`, `verificá`, `ingresá`, `completá`, `enviá`, `usá`, `sos`) → 0 coincidencias; tildes verificadas manualmente (Árbol, colapsar, expandir, etc.). |

## Trazabilidad de requisitos

R1 Acceso desde la navegación · 3.2,3.3,3.4
R2 Composición del bosque en el cliente · 0.1,1.1,1.2,3.1,3.4
R3 Render top-down con expandir/colapsar · 2.1,2.2,2.4,4.4
R4 Avance roll-up visible por nodo · 1.1,2.1,4.4
R5 Indicador de metodología por proyecto · 1.1,2.1,4.4
R6 Navegación al proyecto · 2.1,4.4
R7 Estados de carga, vacío y error · 3.1,4.1,4.4
R8 Responsive y accesible · 2.1,4.2,4.3,4.4
R9 Primitivos de @solercia/ui y gap documentado · 2.1,2.2,2.3,5.4
R10 Textos en español colombiano formal · 5.1,5.2,5.4
