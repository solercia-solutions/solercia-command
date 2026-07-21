# OLA 4 — Estado de cierre y trabajo pendiente

> **Fecha de corte**: 2026-07-20 · **Rama**: `preview` · **Motivo del corte**: presupuesto.
> La ola se detuvo deliberadamente al cerrar el cambio 32. Los cambios 33 a 41 quedan
> **planificados por completo** (proposal, spec, design y tasks escritos y revisados)
> pero **sin implementar**. Este documento es el punto de partida para retomarlos.

---

## 1. Qué quedó entregado

Ocho cambios completaron su ciclo SDD íntegro (`apply → verify → archive → merge a preview`)
y están archivados en `openspec/changes/archive/`.

| № | Cambio | Qué entrega | Suite al cerrar |
|---|--------|-------------|-----------------|
| 25 | `multiempresa-scoping` | Batería de 52 tests de fuga cross-tenant sobre 25 módulos. Cero fugas reales encontradas. | 1210 |
| 26 | `admin-empresas` | CRUD de empresas, membresías multi-empresa con roles, selector de empresa activa por header `X-Organization-Id`. | 1249 |
| 27 | `plantillas-idempotentes` | Instanciación idempotente (reconcilia, nunca duplica), limpieza de duplicados OAP-TI, `project_kind` (area/proyecto). | 1272 |
| 28 | `calendario-laboral` | Horas y días laborales configurables con herencia empresa → equipo → proyecto. | 1302 |
| 29 | `sprint-borrador` | Sprint creable solo con nombre (estado `draft`), autonombre consecutivo, guarda de fechas para iniciar. | 1332 |
| 30 | `backlog-sprints-agrupados` | Backlog con sprints como secciones colapsables estilo Jira, con agregados calculados en el servidor. | 1337 |
| 31 | `backlog-drag-drop` | Arrastrar y soltar entre backlog y sprints con Angular CDK, reorden transaccional (`POST /tasks/reorder`). | 1345 |
| 32 | `jerarquia-subtareas` | Subtareas indentadas bajo su padre; regla de producto: la subtarea asignada siempre aparece al filtrar por su responsable. | 1352 |

**Migraciones aplicadas**: `0021` (unique de membresías), `0022` (`project_kind`),
`0023` (dedup del ledger + reconciliación de árboles duplicados), `0024` (calendario laboral).
Todas verificadas con ciclo real `upgrade → downgrade → upgrade` contra bases desechables.

---

## 2. Qué falta — cambios 33 a 41

Los nueve cambios restantes tienen **la planificación SDD completa** en
`openspec/changes/<nombre>/`: `proposal.md`, `specs/`, `design.md`, `tasks.md` y `state.yaml`
con `apply: pending`. Retomar cualquiera de ellos **no requiere volver a planificar**:
se entra directo a la fase `apply` siguiendo su `tasks.md`.

| № | Cambio | Fase | Tareas | Migración | Qué falta hacer |
|---|--------|------|--------|-----------|-----------------|
| 33 | `busqueda-filtros` | 4.2 | 36 | No | Barra de filtros compartida entre backlog y cronograma: búsqueda por clave (`SDM-7`) y texto con expansión/resaltado de secciones colapsadas, avatares multi-selección con "+N", filtros por épica, tipo y rango de fechas. Extiende `assignee_id` a repetible en el backend (con TDD). |
| 34 | `estimacion-normalizada` | 4.2 | 39 | No | Parser único w/d/h → horas en el backend usando el calendario del cambio 28, y formateador único de despliegue (`6h`, `2d 3h`, `1w 2d`). Elimina la conversión local de 8h/5d que hoy vive a fuego en el frontend. |
| 35 | `avance-esperado-vs-real` | 4.3 | 59 | **Sí** | % esperado a la fecha vs. % real por proyecto con rollup por área, semáforo con umbrales por empresa, tendencia de 4 semanas vía snapshots semanales, alerta de refuerzo accionable y corte mensual por área. Es el cambio más grande de los pendientes. |
| 36 | `proyectos-jerarquia-unificada` | 4.3 | 34 | Solo seed de menú | El árbol pasa a ser la vista principal de Proyectos, con edición inline de nombre y descripción en el nodo, distinción visual por `project_kind` y toggle "solo hojas". |
| 37 | `cambio-metodologia` | 4.3 | 45 | No | Cambiar la metodología de un proyecto existente con asistente de mapeo de estados y columnas, transaccional, vía Strategy. Requiere un flag `commit` en el service de boards para lograr transacción única. |
| 38 | `oauth-ms-google` | 4.4 | 48 | No | **Causa raíz ya diagnosticada con evidencia**: `authorize()` usa `OAUTH_REDIRECT_ALLOWLIST[0]` como `redirect_uri` (una página del SPA en un puerto obsoleto), así que el código del proveedor nunca llega al callback del backend. Se repara con una URL de callback configurable por variable de entorno, más un botón "Probar conexión" que ejecute una operación real. |
| 39 | `conector-capacidades` | 4.4 | 21 | No | Panel de acciones por conector derivado de las capacidades del adaptador (nada de "conectado" sin acciones), eliminando los condicionales por proveedor que hoy tiene el frontend. |
| 40 | `jira-import-usuario` | 4.4 | 55 | **Sí** | Flujo elegir proyecto → previsualizar → importar, con anclas `source`/`external_key` para que reimportar reconcilie en vez de duplicar. |
| 41 | `jira-import-admin` | 4.4 | 42 | **Sí** | Importación masiva del sitio completo con cola persistida, ejecución en segundo plano, progreso por sondeo y reanudación idempotente. Viabilidad ya probada contra el sitio real (36 proyectos, permiso `ADMINISTER`). |

**Total pendiente**: 379 tareas desglosadas.

### Orden obligatorio y compuertas

El orden no es negociable porque cada cambio consume artefactos del anterior:

```
33 y 34  →  35 → 36 → 37  →  38 → 39 → 40 → 41
```

- **34 antes que 40/41**: la importación de Jira convierte estimaciones con el parser del 34.
- **35 después de 27 y 28** (ya cerrados): usa `project_kind` y el calendario laboral.
- **38 antes que 39**: el panel de acciones reutiliza el helper de verificación del 38.
- **39 antes que 40**, y **40 antes que 41**: el modo administrador reutiliza el pipeline de importación por proyecto.

Cada `tasks.md` abre con una **Fase 0** que verifica en disco las precondiciones y
**reancla el `down_revision` de Alembic al head real** antes de escribir código. El head
actual es `0024_add_work_calendar`.

---

## 3. Pendientes que no son cambios SDD

### 3.1 Decisión sobre la dependencia `@solercia/ui` — rama `chore/solercia-ui-npm`

Durante el cambio 31, un agente migró la librería del tarball fijo
(`file:./vendor/solercia-ui-0.3.0.tgz`) a npm `^0.3.1` para desbloquearse. **Se demostró
experimentalmente que no era necesaria** (el build pasa verde con el tarball), así que se
extrajo de la rama del cambio y quedó preservada en `chore/solercia-ui-npm`.

Queda como decisión del dueño del proyecto. Vale la pena tomarla porque la versión 0.3.1
corrige bugs reales: menús flotantes del `sol-rich-editor` y desbordamiento de selects
dentro de modales y drawers.

**Gotcha si se adopta**: el paquete publicado exporta su propio `SolDrawerComponent` con
otra API (`side`/`variant`/`closeable`, **sin** el input `blur` que usan las vistas), y
colisiona con el drawer local homónimo. El tarball ocultaba la colisión. El arreglo es
cambiar el `export *` por un export nombrado en `frontend/src/shared/ui/index.ts`, porque
en TypeScript el export nombrado gana sobre el de estrella.

### 3.2 Verificación manual en navegador (cambio 26)

Dos tareas del cambio 26 quedaron sin ejecutar por requerir un humano frente a la pantalla:
probar el selector de empresa activa cambiando entre organizaciones, y el CRUD de miembros
en vivo. El código está completo y compilando; falta la prueba de clic.

### 3.3 Migración `0023` contra la base de desarrollo

La limpieza de árboles OAP-TI duplicados se probó con datos sintéticos en tests. Se aplica
sobre la base real al levantar el entorno (`./gestion.sh rebuild`). Conviene revisar el
resultado con datos reales antes de considerar cerrado ese frente.

### 3.4 Deuda técnica documentada en las verificaciones

- **No existe runner de pruebas en el frontend** (`package.json` solo tiene `build` y `lint`).
  Todo el comportamiento de UI de los cambios 28 a 32 se verificó por inspección de código
  más compilación AOT. Con el drag & drop y la jerarquía de subtareas ya en juego, invertir
  en un runner (Vitest) es la mejora de mayor retorno pendiente.
- **Migración 0023**: el caso de empate exacto entre árboles duplicados se resuelve con un
  índice único parcial que excluye las filas empatadas y emite un `warnings.warn` efímero.
  Antes de producción conviene persistir esos casos en una bitácora consultable.
- El código `sprint_already_closed` se reutiliza con dos semánticas (409 al cerrar, 422 al
  iniciar), distinguibles solo por el código de estado y el endpoint.

---

## 4. Cómo retomar

```bash
git switch preview
git switch -c feat/<nombre-del-cambio> preview     # ej. feat/busqueda-filtros

# El plan ya existe; se entra directo a implementar:
#   openspec/changes/33-busqueda-filtros/tasks.md
```

Reglas de la ola que siguen vigentes: TDD estricto (prueba primero), commits convencionales
en español sin atribución de IA, una rama por cambio desde `preview`, nunca tocar `main`,
y cerrar cada cambio con `verify` y `archive` antes del merge.

**Comando de la suite backend**:

```bash
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test \
  .venv/bin/python -m pytest -q
```

**Build del frontend** (requiere Node 22.22.3; el del sistema no alcanza para Angular CLI):

```bash
source ~/.nvm/nvm.sh && nvm use 22.22.3 && cd frontend && npm run build
```

---

## 5. Fase 4.5 — nunca confirmada

El cambio 42 (`controles-sprint`: avisos al iniciar sprint sin estimaciones, snapshot de
alcance comprometido, cierre guiado) sigue **pendiente de confirmación explícita** del
usuario, tal como quedó en la sección 3 de `OLA_4.md`. No tiene planificación SDD escrita.
