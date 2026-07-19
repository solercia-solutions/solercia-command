# frontend-ui-consumption Specification

## Purpose

Política verificable de consumo de `@solercia/ui` en `frontend/src/`. Cierra la auditoría 1:1 de páginas y widgets, migra el *chrome* pendiente hecho a mano (task-modal, notification-panel, 16 SVG inline) a componentes de la librería y define cuándo se retiran dependencias UI de terceros. No cubre el repositorio de `@solercia/ui` ni rediseño visual más allá del reemplazo 1:1.

## Requirements

### Requirement: Inventario 1:1 auditado de páginas y widgets

Cada `*.component.ts` bajo `pages/`, `widgets/` y `app/` DEBE clasificarse como *consume librería*, *reemplazar* o *sin equivalente*, con ruta y categoría documentadas.

#### Scenario: Clasificación verificable de cada componente

- DADO un componente con o sin equivalente en `@solercia/ui` 0.3.0
- CUANDO se audita
- ENTONCES queda clasificado como consume, reemplazar o sin equivalente; lo "sin equivalente" se documenta como pendiente de aporte a la librería

### Requirement: Migración de task-modal a SolModal y controles Sol

`task-modal.component.ts` DEBE usar `SolModal` y los controles `SolInput`, `SolTextarea`, `SolSelect`, `SolNumberInput`, `SolDatePicker` en lugar del markup manual, y `SolIconButton`/`SolIcon` para el cierre. El comportamiento y las claves i18n existentes DEBEN conservarse.

#### Scenario: Editar y guardar conserva el comportamiento previo

- DADO el modal de tarea sobre `SolModal`
- CUANDO el usuario edita con los controles Sol y guarda
- ENTONCES la tarea se actualiza igual que antes, sin perder validaciones ni datos

#### Scenario: Cerrar el modal conserva accesibilidad

- DADO el modal abierto
- CUANDO se activa el ícono de cierre migrado
- ENTONCES el modal se cierra y conserva su `aria-label`

### Requirement: Migración de notification-panel a componentes Sol y señales

`notification-panel.component.ts` DEBE usar `SolSpinner`, `SolBadge` y `SolIconButton`/`SolIcon` en lugar del chrome manual, y DEBE migrar sus `@Output()/EventEmitter` a `output()`.

#### Scenario: Carga usa SolSpinner

- DADO el panel cargando datos
- CUANDO se renderiza el estado intermedio
- ENTONCES se muestra `SolSpinner` en vez del spinner manual previo

#### Scenario: Consumidores siguen recibiendo eventos

- DADO un componente padre suscrito a los eventos del panel
- CUANDO el panel emite vía `output()`
- ENTONCES el padre lo recibe igual que con `@Output()`, sin cambio de contrato

### Requirement: Migración de íconos SVG inline a SolIcon

Los 16 SVG inline en 5 archivos (task-modal, notification-panel, app.component [8], project-workspace [5], executive [1]) DEBEN migrar a `SolIconComponent`, conservando `aria-label`/`aria-hidden`. Si un ícono no existe en el registro, el SVG DEBE conservarse sin cambios y documentarse como pendiente de librería.

#### Scenario: Ícono con equivalente se migra

- DADO un SVG con equivalente en el registro de `SolIcon`
- CUANDO se reemplaza por `SolIconComponent`
- ENTONCES se ve y se comporta igual, conservando el atributo de accesibilidad

#### Scenario: Ícono sin equivalente se documenta y conserva

- DADO un SVG sin equivalente en el registro
- CUANDO se audita
- ENTONCES el SVG se conserva sin cambios y queda documentado como pendiente, sin bloquear el resto de la migración

### Requirement: Layout shell fuera de alcance

El header/sidebar de `app.component.ts` DEBE seguir siendo composición local de la aplicación; NO DEBE reemplazarse por un componente de librería en este cambio, porque `@solercia/ui` 0.3.0 no expone `SolLayoutShell`. Queda documentado como pendiente de aporte futuro a la librería.

#### Scenario: El shell conserva su estructura local tras migrar íconos

- DADO que `app.component.ts` migra sus 8 SVG inline a `SolIcon`
- CUANDO se completa esa migración
- ENTONCES el header/sidebar sigue siendo composición local propia de la app, sin introducir `SolLayoutShell`

### Requirement: Depuración condicional de dependencias de terceros

`chart.js` y `@angular/cdk` SOLO DEBEN retirarse de `package.json` si ninguna importación en `src/` los usa Y no son peer dependencies de `@solercia/ui` 0.3.0. Si lo son, o siguen en uso, DEBEN conservarse y quedar documentadas como justificadas.

#### Scenario: Peer dependency se conserva

- DADO que `chart.js` o `@angular/cdk` es peer dependency de `@solercia/ui` 0.3.0
- CUANDO se audita `package.json`
- ENTONCES la dependencia se conserva, documentada como justificada

#### Scenario: Dependencia sin uso ni peer dep se retira

- DADO que ni `src/` ni la librería requieren la dependencia
- CUANDO se audita `package.json`
- ENTONCES la dependencia se retira y el build del frontend sigue en verde

### Requirement: Calidad transversal — cero regresión, build en verde, accesibilidad

Cada widget migrado DEBE mantener `ng build` y `eslint` del frontend en verde, DEBE preservar el comportamiento funcional previo (cero regresión) y DEBE conservar los `aria-label`/roles de accesibilidad existentes.

#### Scenario: Build y lint pasan tras cada migración

- DADO un widget migrado a componentes de `@solercia/ui`
- CUANDO se ejecutan `ng build` y `eslint` del frontend
- ENTONCES ambos terminan sin errores

#### Scenario: Sin regresión funcional ni de accesibilidad

- DADO el comportamiento y los atributos de accesibilidad del widget antes de migrar
- CUANDO se compara con el widget migrado
- ENTONCES el comportamiento funcional es idéntico y los `aria-label` siguen presentes
