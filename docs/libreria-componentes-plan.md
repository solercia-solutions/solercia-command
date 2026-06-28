# Plan: librería de componentes propia, "skin por JSON", compartible y licenciable

> Orientación estratégica. Objetivo: convertir `shared/ui` + el motor de theming en una **librería Angular propia** (`@boki/ui`), reutilizable entre proyectos, que **cambia de piel editando un JSON** (color, fuente, tamaño, borde, sombra, blur, animaciones) sin que dos proyectos se parezcan, sin depender de UI de terceros, y con **autoría limpia** para poder licenciarla.

---

## 1. El problema que resuelve (y por qué te pasa hoy)

Hoy "le decís al agente: cópiate este código" y **no copia todo** → divergencia entre proyectos. Eso NO se arregla copiando mejor. Se arregla con **una sola fuente de verdad**: un paquete versionado que los proyectos **instalan**, no copian.

```
Antes (drift):                        Después (paquete):
gestion_proyectos/shared/ui  ──┐      @boki/ui  v1.4.2  (un repo, un dueño)
boki-front/shared/components ──┤        ▲        ▲
otros/...                     ──┘        │ npm i  │ npm i
  (3 copias que divergen)          gestion_proyectos   boki-front   otros
```

Regla: **el código vive UNA vez. Los proyectos dependen de una versión.** Subís una mejora → `npm version` → los proyectos hacen `npm update`. Cero copia-pega, cero "se me olvidó traer un archivo".

---

## 2. Arquitectura recomendada (3 paquetes)

| Paquete | Qué contiene | Por qué separado |
|---|---|---|
| `@boki/ui` | Los componentes (`bk-card`, `bk-button`, `bk-modal`, `bk-select`, `bk-table`, `bk-text-input`, form, etc.) | El producto reutilizable |
| `@boki/theme` | `ThemeService`, `theme.model.ts`, `theme.provider.ts`, `default.json` y el **esquema de tokens** | La "piel" se versiona aparte; un proyecto puede actualizar componentes sin tocar su tema |
| `@boki/tailwind-preset` | El `tailwind.config` que mapea tokens → utilidades (`bg-surface`, `shadow-md`…) | Lo que ya construimos; el consumidor lo agrega a su `tailwind.config.js` |

**Cómo lo consume un proyecto nuevo:**
1. `npm i @boki/ui @boki/theme`
2. En `tailwind.config.js`: `presets: [require('@boki/tailwind-preset')]`
3. `provideTheme()` en el bootstrap, apuntando a SU `default.json`.
4. **Skin = editar ese JSON.** Listo.

---

## 3. Cómo se construye técnicamente (Angular library)

Esto es lo estándar de Angular, no hay que inventar:

```
ng generate library boki-ui      # crea projects/boki-ui con ng-packagr
```

- `ng-packagr` compila a un paquete instalable (formato Angular Package Format).
- `ng build boki-ui` → `dist/boki-ui` → `npm publish`.
- **Versionado semántico** (semver): `1.4.2` = major.minor.patch. `CHANGELOG.md`.
- **Dónde publicar (privado)**: GitHub Packages (gratis para repos privados) o un **Verdaccio** self-hosted (registro npm propio). Recomendación: GitHub Packages para empezar.

Esto te da exactamente lo que querés: un **artefacto discreto, versionado, con dueño y LICENSE** — base para licenciar.

---

## 4. "Cambia de piel sin parecerse": qué tokens faltan

El motor de hoy ya cubre color, radio, sombra, tipografía y motion. Para la variabilidad que pediste hay que **ampliar el esquema del JSON**:

| Eje que pediste | Token a agregar |
|---|---|
| Blur (glass, overlays) | `blur: { sm, md, lg }` → utilidades `backdrop-blur-*` por token |
| Bordes | `border: { width: {hairline, thin, thick}, ... }` |
| Tamaños/densidad | `density: cómoda \| compacta` → escala de alturas y paddings |
| **Animaciones de apertura** | `motion.enter`, `motion.exit` (duración + easing + transform inicial) por componente (modal, dropdown, toast) |

Con esto, un proyecto "serio" (entidad pública) usa radios chicos, sombras suaves, sin glow; otro proyecto usa radios grandes, blur fuerte, animaciones marcadas — **mismo código, JSON distinto, no se parecen.**

---

## 5. La decisión importante: ¿100% propio o un primitivo headless?

Tu principio de "no depender de terceros" es **correcto para tu meta** (producto licenciable, sin enredos de licencias ajenas, control total). Lo valido. **Pero** hay una excepción que te recomiendo considerar con criterio:

- **Reinventar bien** posicionamiento de overlays, *focus-trap* accesible, *virtual scroll* para listas de miles, y *drag&drop*, es MUCHÍSIMO trabajo y fácil de hacer mal (accesibilidad, edge cases).
- **Angular CDK** (`@angular/cdk`) es **headless**: da el COMPORTAMIENTO (overlay, focus-trap, a11y, drag-drop, virtual-scroll) **sin imponer ningún estilo**. No hace que tus proyectos "se parezcan" — la piel sigue siendo 100% tuya. Y es MIT (permisiva).
- Justo el bug de los modales de hoy se elimina de raíz con `CDK Overlay`: renderiza el modal en una capa a nivel `<body>`, **inmune al problema del `transform` ancestro**. Y el posicionamiento del `bk-select` también.

Recomendación honesta: **CDK como ÚNICA dependencia de comportamiento** (headless), todo lo visual y los tokens 100% tuyos. Si aún así querés cero dependencias, se puede — pero sabé que es más mantenimiento y más riesgo de a11y. Lo dejo como decisión tuya.

---

## 6. Licenciamiento / "patentar" (con honestidad — no soy abogado)

Quiero ser claro acá porque es importante para tus contratos:

- **El código se protege con DERECHO DE AUTOR, no con patente.** El copyright es automático sobre obra original: vos sos el autor. "Patentar código" como tal **no aplica**; se patenta una *invención/método* novedoso (jurisdiccional, caro, rara vez vale la pena para una UI kit).
- **Ruta realista en Colombia**: registrar el **soporte lógico ante la DNDA** (Dirección Nacional de Derecho de Autor). Te da fecha cierta y prueba de autoría — útil para **proveedor exclusivo / contratación directa** con entidades públicas.
- **Higiene de autoría (crítico)**: para reclamar autoría única necesitás **procedencia limpia en git**. Hoy tenés un riesgo: el flujo paralelo hace `git add -A` y mezcla cambios; eso **ensucia la autoría**. Para `@boki/ui` conviene: repo separado, commits con tu identidad, `LICENSE` propietaria, headers de copyright en cada archivo, y una política de contribución (CLA) que mantenga la obra como tuya.
- Para lo contractual/patente puntual: **consultá un abogado de PI**. Yo te dejo la base técnica (artefacto versionado + LICENSE + registro DNDA + git limpio).

---

## 7. Ruta de migración (fases)

1. **Estandarizar prefijo `bk-`** — ya hecho.
2. **Crear `projects/boki-ui`** (`ng generate library`) y mover `shared/ui` + el motor de theming ahí. Repo propio.
3. **Ampliar el esquema de tokens** (blur, bordes, densidad, motion enter/exit).
4. **Publicar privado** (GitHub Packages) con semver + CHANGELOG + LICENSE + headers.
5. **Consumir el paquete** desde `gestion_proyectos` y `boki-front` (reemplazar las copias locales).
6. **Gobernanza/IP**: LICENSE propietaria, registro DNDA, política de contribución.

---

## 8. Pendientes UX concretos que entran en esta librería

- **`bk-modal`**: agregar tamaños anchos (`xl`, `2xl`, full) + apilado en móvil + (idealmente) CDK Overlay para robustez de posicionamiento.
- **Asignar roles con +20 opciones**: ya existe `bk-select` (multi + buscable). El problema es que **la pantalla de roles usa checkboxes planos, no `bk-select`**. Cambiarlo a `bk-select [multiple]` resuelve el caso elegantemente.
- **Animaciones de apertura** de `bk-modal`/`bk-select`: hoy abren instantáneo; agregar enter/leave por token.
- **Capa "vibe" opcional** (glass + glow + scroll-reveal): como tokens/directivas opt-in, para proyectos que quieran un look más dinámico sin afectar a los "serios".
