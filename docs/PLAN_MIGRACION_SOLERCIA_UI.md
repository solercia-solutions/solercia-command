# Plan de migración: `boki-front` → `@solercia/ui`

> Documento de planeación técnica. Objetivo: extraer los componentes, utilidades y theming reutilizables de `boki-front` hacia una librería Angular publicable y compartible (`@solercia/ui`), dejando fuera el código de negocio y la deuda técnica.
>
> Fuentes: análisis de `/Users/camilocalderont/Proyectos/SOLERCIA/solercia_flows/boki-front` (componentes, widgets y sistema de estilos) + estado actual de la librería destino `frontend/projects/boki-ui` (`@boki/ui` v0.1.0).

---

## 0. Resumen ejecutivo

- **El activo está más sano de lo esperado, pero hay que separar dos mundos.** `boki-front` tiene **dos generaciones** de componentes compartidos conviviendo:
  - **Gen 2** (`src/shared/`, prefijo `bk-*`): standalone, Signals, `OnPush`, CSS + tokens `--bk-*`. **Esta es la librería candidata.** Está limpia.
  - **Gen 1** (`src/app/shared/`, sufijo `*-theme`): hereda un `BaseComponent` deprecado, usa `@Input/@Output` viejos, sin `OnPush`, construye clases Tailwind contra un `theme` que **siempre es null**. **Deuda técnica — no se migra tal cual.**
- **Decisión de estilos (tu duda del CSS puro):** los componentes **NO usan Tailwind**, usan CSS puro + variables `--bk-*`. **Eso no es un defecto: es lo que hace la librería portable.** Recomendación: **NO hacer la librería dependiente de Tailwind**; empaquetar los componentes como están + un `tokens.css`, y dejar el preset de Tailwind como algo **opcional**.
- **El trabajo real** no es "copiar": es (1) tomar solo la Gen 2, (2) descartar/reescribir la Gen 1, (3) cortar el acoplamiento a negocio de 9 widgets, y (4) limpiar estilos hardcodeados antes de publicar.

**Números:**

| Área | Total | ✅ migra limpio | ⚠️ migra con refactor | ❌ no migra |
|------|-------|-----------------|----------------------|-------------|
| Componentes/utilidades `shared/` | 56 comp. (98 archivos .ts) | 18 | 22 | 16 |
| Widgets | 14 | 4 | 9 (✂️ partir) | 1 |

---

## 1. Hallazgo clave: dos generaciones de componentes

| | **Gen 2 — la base de la librería** | **Gen 1 — deuda a retirar** |
|---|---|---|
| Carpeta | `src/shared/ui/`, `src/shared/lib/`, `src/shared/tokens/` | `src/app/shared/` |
| Nomenclatura | `bk-button`, `bk-select`… | `button-theme`, `form-select-theme`… |
| API | `input()` / `output()` / `computed()` / `signal()` | `@Input()` / `@Output()` decorators |
| Detección | `ChangeDetectionStrategy.OnPush` | sin `OnPush` |
| Estilos | CSS puro + tokens `--bk-*` | clases Tailwind vía `BaseComponent` (que es `null`) |
| Estado | Producción, limpio | `@deprecated`, dead code en el theming |

**Regla de oro del plan:** migrar **Gen 2**. La Gen 1 tiene equivalentes modernos ya construidos en Gen 2 (`button-theme`→`bk-button`, `modal-theme`→`bk-modal`, `form-input-theme`→`bk-input`, `form-select-theme`→`bk-select`). Esos se **eliminan**, no se migran. Solo se reescriben los pocos de Gen 1 que **no tienen equivalente** (ver §4.3).

> El `BaseComponent` (`src/app/shared/components/base/base.component.ts`) tiene `theme: any = null` y está marcado `@deprecated`. Todos los `*-theme` ejecutan `this.theme?.theme?.colors?...` que siempre resuelve `undefined` y cae a fallbacks hardcodeados. **El patrón nunca funcionó.** No entra a la librería bajo ninguna forma.

---

## 2. Estrategia de estilos: la decisión sobre Tailwind (tu duda)

**Diagnóstico:** en `boki-front`, Tailwind y el sistema de tokens viven **separados**. `tailwind.config.js` define colores estáticos (`brand-blue: '#1E3A8A'`) que **no** están conectados a las variables `--bk-*`. Los componentes de `shared/ui/` **no usan Tailwind en absoluto**: usan CSS puro consumiendo `var(--bk-*)` con fallbacks. Tailwind solo aparece, de forma puntual, en páginas y en el código legacy.

**Por qué el CSS puro NO es el problema:** una librería que depende de Tailwind obliga a **cada app consumidora** a instalar Tailwind y configurarlo con exactamente los mismos tokens, o los componentes se rompen. En cambio, CSS + variables `--bk-*` hace la librería **autocontenida**: el consumidor solo define las variables (o usa los defaults).

**Decisión recomendada — Opción B (autocontenida):**

| Opción | Cómo | Veredicto |
|--------|------|-----------|
| A) Depender de Tailwind | El consumidor configura Tailwind con los tokens | ❌ Acoplamiento severo; además habría que **reescribir** los componentes (hoy no usan Tailwind) |
| **B) CSS + variables (recomendada)** | Empaquetar los componentes como están + exportar `tokens.css` | ✅ Portable, cero build-tools en el consumidor, funciona ya |
| C) Híbrido | B + preset de Tailwind **opcional** para apps que quieran los tokens como utilidades | ✅ Es el "extra" sobre B; el `tailwind-preset.js` que ya existe en `@boki/ui` cumple este rol |

**La librería exporta:**
1. Los componentes de `shared/ui/` (CSS puro + `--bk-*`).
2. Un **`tokens.css`** con las variables y sus valores por defecto (extraído del `:root` de `styles.css`).
3. El theming (`ThemeService` + `provideTheme()` + contrato del JSON) como **entry-point separado** (`@solercia/ui/theming`).
4. *(Opcional)* el `tailwind-preset.js` para apps que usen Tailwind y quieran los tokens como utilidades.

---

## 3. Inventario clasificado — qué migra

### 3.1 Átomos `src/shared/ui/` (Gen 2) — primer lote, el más limpio

| Componente | Selector | Estado | Acción |
|-----------|----------|--------|--------|
| `badge` | `bk-badge` | ✅ limpio | Migrar tal cual |
| `button` | `bk-button` | ✅ limpio | Migrar tal cual |
| `card` | `bk-card` | ✅ limpio | Migrar tal cual |
| `checkbox` | `bk-checkbox` | ✅ limpio (CVA) | Migrar tal cual |
| `input` | `bk-input` | ✅ limpio (CVA) | Migrar tal cual |
| `icon` + `icon.registry` | `bk-icon` | ✅ limpio | Migrar tal cual (Heroicons MIT) |
| `modal` | `bk-modal` | ✅ limpio | Migrar tal cual |
| `spinner` | `bk-spinner` | ✅ limpio | Migrar tal cual |
| `day-picker` | `bk-day-picker` | ⚠️ trivial | Reemplazar `color:#fff` por `var(--bk-color-white,#fff)` |
| `file-upload` | `bk-file-upload` | ⚠️ trivial | Limpiar hex redundantes junto a tokens |
| `form-field` | `bk-form-field` | ⚠️ menor | Confirmar/migrar API a signals, limpiar hex |
| `select` | `bk-select` | ⚠️ refactor | Reemplazar el hack `(this as any).__wrapper` por `@HostListener('document:click')` |

### 3.2 Utilidades, theming e infraestructura — migrables

| Elemento | Ruta | Acción |
|----------|------|--------|
| `AlertService` + `alert.model` | `src/shared/lib/alerts/` | ✅ Migrar |
| `form-errors`, `debounce.util`, `TruncatePipe` | `src/shared/lib/` | ✅ Migrar |
| `theme.model` / `theme.provider` / `index` | `src/shared/tokens/` | ✅ Migrar |
| `ThemeService` | `src/shared/tokens/theme.service.ts` | ⚠️ Migrar — requiere `HttpClient` en el consumidor (`provideHttpClient()`); hacer la URL del JSON **configurable** en `provideTheme(url)` |
| `auth.interceptor` + `auth.tokens` + `api.model` | `src/shared/api/` | ✅ Migrar — ya desacoplado vía `AUTH_TOKEN_GETTER` (InjectionToken) |

### 3.3 Widgets — `src/widgets/`

**✅ Presentacionales puros (4 — migran tal cual):**
`confirm-dialog`, `service-list-item`, `company-booking-card`, `image-gallery-hero`.

**✂️ Partir en presentacional + contenedor (9 — refactor ~1-2 h c/u):**

| Widget | Acoplamiento a cortar | Refactor |
|--------|----------------------|----------|
| `alert-center` | Inyecta `AlertService` | Recibir `alerts` por `input`, emitir `dismiss` por `output`; el contenedor se queda en la app |
| `header` | Lee `ThemeService.logo()` | `logo = input(...)`; componer con `ThemeService` en la app |
| `data-table` | Outputs de dominio (`scheduleClicked`…) | Quitarlos; usar slot `<ng-content select="[rowActions]">` |
| `calendar` | Mapa `stateId→color` hardcodeado | Aceptar `input<StateColorMap>` |
| `gallery-viewer` | Tipos de BD + categorías `venue/service/…` | Generalizar a `GalleryGroup[]` |
| `booking-sidebar` | Tipos de `@entities` + locale `es-CO` | Interfaces propias + `locale` por input |
| `sidebar` | SVG inline vía `DomSanitizer` | Usar `bk-icon` + registro de íconos |
| `stat-card` | SVG inline vía `DomSanitizer` | Usar `bk-icon` |
| `layout-shell` | Compone widgets concretos + `ThemeToggle` | Extraer `SpLayoutShellBase` con slots `ng-content` |

**❌ Se queda en la app (1):** `public-layout` — branding y textos de Boki hardcodeados; no es abstraíble.

---

## 4. Qué NO migra (y por qué)

### 4.1 Infraestructura acoplada a la app
- `error.interceptor.ts` — redirige a rutas y borra storage keys de negocio.
- `app.constants.ts`, `route.constants.ts`, `storage.keys.ts` — config de la app.
- Interfaces de dominio (`company`, `client`, `appointment`, `plan`…) — modelos de negocio.

### 4.2 Componentes de negocio / dead code
- `data-grid` (Gen 1) — componente de negocio con `any` extensivo.
- `snack-bar` + `snack-bar.service` — DOM imperativo + hex hardcodeados → reemplazar por `AlertService` + alert-center de Gen 2.
- `BaseComponent` — `@deprecated`, dead code.
- `theme-components.module.ts` — `NgModule` envolviendo standalone (anti-patrón Angular 17+).
- `solercia-credit-theme`, `public-layout` — branding específico.
- `truncate-text-pipe` (Gen 1) — duplicado de `TruncatePipe` (Gen 2).
- `form-select-theme` — usa un **segundo sistema de theming** (clases Tailwind guardadas como strings en JSON), incompatible. Se elimina; su lugar lo toma `bk-select`.

### 4.3 Gen 1 a evaluar (reescribir solo si no hay equivalente Gen 2)
- **Sin equivalente, vale reescribir como `sp-*` moderno:** `form-textarea-theme`, `form-toggle-theme` (switch), `tabs` (Gen 1; verificar si `bk-tabs` ya cubre), tipografía (`h1/h2/section/header/nav-item/main-container`), `dropdown/*` (avatar, menú de usuario).
- **Con equivalente Gen 2 → eliminar:** `button-theme`, `modal-theme`, `form-input-theme`, `form-select-theme`.

---

## 5. Refactors obligatorios antes de publicar

**Componentes:**
1. **Retirar `BaseComponent` y el patrón `*-theme`** (dead code).
2. **Unificar duplicados Gen 1 ↔ Gen 2** (eliminar los Gen 1 con equivalente).
3. **Migrar `@Input/@Output` → signals** en los componentes Gen 1 que sí se reescriban (22 archivos usan decorators viejos; 36 no tienen `OnPush`).
4. **Arreglar `bk-select`**: reemplazar `(this as any).__wrapper` por `@HostListener('document:click')` tipado.
5. **`::ng-deep` en `service-list-item`**: resolver con una variante del botón, no perforando encapsulación.

**Estilos:**
6. **Extraer `tokens.css`** publicable desde el `:root` de `styles.css`.
7. **Eliminar colores hardcodeados:** `day-picker:191` (`#fff`), `snack-bar` (`#07202d`,`#d13438`), `plans.component.scss` (20+ hex) → tokens `--bk-*`.
8. **`ThemeService` con URL configurable** (`provideTheme(url)`) en vez de la ruta `assets/themes/default.json` hardcodeada; documentar `provideHttpClient()` como requisito.
9. **Eliminar el segundo sistema de theming** (clases Tailwind en JSON de `form-select-theme`).

**Naming (decisión de marca):**
10. **Renombrar `bk-*` → `sp-*` y `--bk-*` → `--sp-*`** para alinear con la marca **Solercia** (`@solercia/ui`, prefijo `sp-` = Solercia Platform). Los selectores sin namespace de Gen 1 (`button-theme`, `h1-theme`) colisionan en multi-librería. *(Nota: `gestion_proyectos/frontend` ya usa una mezcla `bk-*`/`sp-*`; unificar todo a `sp-*` en este paso.)*

---

## 6. Plan de migración por fases

| Fase | Contenido | Resultado |
|------|-----------|-----------|
| **0. Preparar librería** | En `@solercia/ui`: `tokens.css`, `public-api.ts`, `peerDependencies` (`@angular/*`, `@angular/common/http`), entry-points (`/theming`), renombrar paquete `@boki/ui`→`@solercia/ui` | Andamiaje listo |
| **1. Átomos limpios** | Los 8 `bk-*` ✅ + lib + tokens + api desacoplada | Primer release usable (`0.2.0`) |
| **2. Átomos con refactor** | `day-picker`, `file-upload`, `form-field`, `bk-select` (fix `__wrapper`) | Set de form controls completo |
| **3. Widgets puros** | `confirm-dialog`, `service-list-item`, `company-booking-card`, `image-gallery-hero` | Composiciones básicas |
| **4. Widgets a partir** | Los 9 ✂️ con patrón container/presentational | Widgets ricos (data-table, calendar, sidebar…) |
| **5. Theming** | `ThemeService` + `provideTheme(url)` + contrato JSON como `@solercia/ui/theming` | Theming por JSON runtime reutilizable |
| **6. Gen 1 sin equivalente** | Reescribir `textarea`, `toggle`, `tabs`, tipografía, `dropdown` como `sp-*` modernos | Paridad funcional con boki-front |
| **7. Limpieza en boki-front** | Eliminar Gen 1, reapuntar imports a `@solercia/ui` | boki-front consume la librería; cero duplicados |

> El renombrado `bk-*`→`sp-*` (refactor #10) conviene hacerlo **en la Fase 0/1**, antes de acumular componentes, para no renombrar dos veces.

---

## 7. Buenas prácticas de la Gen 2 a preservar (el estándar de la librería)

Sirven de checklist de calidad para todo lo que entre a `@solercia/ui`:

1. Standalone + `OnPush` + Signals (`input/output/computed/signal/effect/viewChild`).
2. Tokens CSS `--bk-*` coherentes (color, spacing, sizing, radius, shadow, z-index) aplicados por `ThemeService`.
3. `ControlValueAccessor` completo en form controls (`input`, `select`, `checkbox`), sin suscripciones colgadas.
4. Desacoplamiento por `InjectionToken` (`AUTH_TOKEN_GETTER`), no por herencia.
5. `ICON_REGISTRY` inmutable (`as const`) con nombres de ícono type-safe.
6. Barrels `index.ts` por carpeta como puntos de entrada limpios.
7. Cero `.subscribe()` sin gestión en `src/shared/`.

---

## 8. Decisiones pendientes (requieren tu visto bueno)

1. **Naming `bk-*` → `sp-*` y `--bk-*` → `--sp-*`** — recomendado, alinea con la marca Solercia. Impacta `boki-front` y `gestion_proyectos` (que ya mezcla ambos). ¿Confirmamos `sp-`?
2. **Tailwind preset opcional** — mantener `tailwind-preset.js` como extra (Opción C) o quitarlo y quedarnos 100% en CSS+tokens (Opción B pura).
3. **`ThemeService` y `HttpClient`** — dejarlo como entry-point que exige `provideHttpClient()`, o ofrecer también una variante que reciba el tema ya cargado (sin HTTP) para apps que no quieran esa dependencia.
4. **Alcance de la Gen 1** — ¿reescribimos las tipografías y el `dropdown` (Fase 6), o los dejamos fuera del primer alcance y la app los mantiene hasta nuevo aviso?

---

## Anexo — Estado de la librería destino (`@boki/ui` v0.1.0)

- Ubicación: `frontend/projects/boki-ui/` (ng-packagr, `dest: dist/boki-ui`, `entryFile: src/public-api.ts`).
- Ya tiene scaffold de **theme + logging + manejo de errores** y exporta un **`tailwind-preset.js`**.
- Acción: renombrar a `@solercia/ui`, agregar `tokens.css`, definir `peerDependencies` y los entry-points, y empezar a poblar con la Fase 1.
