# Sistema de diseño Solercia — del "panel admin 2014" a un dashboard 2026

> Documento de aprendizaje. Explica **qué había antes**, **qué hay ahora** y, sobre todo, **por qué**. La idea es que entiendas los conceptos, no solo que copies el código. El sistema quedó montado para ser tu base de front reutilizable y portable a `boki-front`.

---

## 1. Resumen

Se hizo en **dos commits**, a propósito:

1. **Calcado** (`feat(theme): traer motor de theming por JSON desde boki-front`): se trajo el motor de theming por JSON de `boki-front` **tal cual**, dejándolo montado y cargando, sin cambiar el look. Es el punto de partida fiel.
2. **Modernización** (este cambio): se reescribió el **contenido** del JSON y se conectaron los tokens a Tailwind, de modo que **editando un archivo JSON** cambia toda la apariencia. Aquí ocurre el salto visual.

La regla de oro que vas a ver repetida: **la apariencia vive en datos (tokens), no regada en clases por todos los componentes.** Por eso modernizar fue, en gran parte, cambiar valores en un solo lugar.

---

## 2. El problema: ¿por qué se veía "bootstrap-like"?

No era Bootstrap, ni Tailwind, ni Angular. Era que **el sistema de diseño estaba a medio construir**: solo tenía colores planos y todo lo demás eran los valores por defecto de Tailwind, elegidos a ojo. Diagnóstico concreto del estado anterior:

| Síntoma | Causa real |
|---|---|
| Las cards no "flotaban" | La página (`#F8FAFC`) y la superficie (`#FFFFFF`) eran casi el mismo blanco (≈3 puntos de luminosidad) y la sombra era `shadow-sm` por defecto en todo. Sin jerarquía de elevación. |
| Colores lavados | Los tintes se hacían con transparencias (`bg-brand/10`, `bg-muted/15`), no con una escala/tono pensado. Bajo contraste. |
| Sin jerarquía visual | Solo dos pesos tipográficos (`font-medium`, `font-semibold`) y saltos de tamaño arbitrarios. Los números de KPI pesaban igual que los títulos. |
| Todo "duro" y estático | Una sola fuente (Inter) para todo, sin fuente display; solo `transition-colors`; cero microinteracciones. |
| Aire muerto / genérico | Radios por defecto (`rounded-xl` = 12px) y espaciados sin sistema. |
| En móvil no se podía navegar | La barra de navegación estaba oculta en móvil (`sm:flex`) y no había menú alternativo. |

---

## 3. La arquitectura: theming por JSON en runtime

### Flujo completo

```
assets/themes/default.json        (1) el tema, en hex legible, light + dark
        │  fetch al arrancar (APP_INITIALIZER, en theme.provider.ts)
        ▼
ThemeService.applyCssVariables()  (2) convierte hex → "R G B" e inyecta --sp-*
        │
        ▼
:root { --sp-brand: 79 70 229; ... }   (3) variables CSS en el documento
        │
        ▼
tailwind.config.js                (4) utilidades mapeadas a esas variables:
   brand: rgb(var(--sp-brand) / <alpha-value>)
        │
        ▼
<div class="bg-surface shadow-md rounded-xl">   (5) los componentes solo usan clases
```

Puntos clave del diseño:

- **El JSON guarda hex** (legible para humanos/diseñadores). El `ThemeService` los convierte a **canales RGB** (`"79 70 229"`) al inyectarlos. ¿Por qué canales y no hex? Porque Tailwind necesita el formato `rgb(var(--x) / <alpha-value>)` para poder aplicar transparencias (`bg-brand/10`). Esta fue una adaptación necesaria respecto a `boki-front`, que inyectaba hex directo.
- **`styles.scss` tiene un espejo estático** de los mismos tokens en `:root` y `.dark`. Sirve para (a) el **primer pintado** antes de que arranque Angular (sin parpadeo) y (b) **fallback** si el JSON no carga. Mantenlo sincronizado con el JSON.
- **Runtime, no build-time**: como el tema se carga por `fetch`, mañana puedes apuntar `loadTheme()` a `/api/tenants/sdmujer/theme.json` y cada entidad tiene su marca **sin recompilar**. Eso es exactamente lo que necesita un producto multi-tenant.

### Tokens semánticos por modo (concepto importante)

En vez de escribir `dark:` en cada componente, los colores se definen **por modo** dentro del JSON (`light` y `dark`). El componente dice `bg-surface` y "surface" significa blanco en claro y azul-grisáceo profundo en oscuro. La lógica de tema vive en datos, no en plantillas.

Además se introdujeron **soft-tokens** (`brandSoft` + `brandSoftFg`, `successSoft` + `successSoftFg`, etc.): un fondo de tinte **sólido** con su color de texto, en lugar de una transparencia. Resultado: chips y badges con contraste real, no lavados.

---

## 4. Los principios que se aplicaron

1. **Profundidad de superficie.** Página, superficie, elevado y hundido (`page`, `surface`, `elevated`, `sunken`) son cuatro niveles distintos. Ahora las cards se despegan del fondo.
2. **Jerarquía de elevación.** Una escala real de sombras (`xs → sm → md → lg → xl`) con propósito: reposo, hover, overlays. Ya no es `shadow-sm` en todo.
3. **Ritmo tipográfico.** Fuente **display** (Manrope) para títulos + **Inter** para cuerpo, pesos con intención y **`tabular-nums`** en los números de KPI (no "bailan" al cambiar).
4. **Color contenido.** El color de marca es **acento**, no relleno. Tintes sólidos con contraste para estados.
5. **Movimiento con propósito.** Transiciones suaves, hover-lift en elementos interactivos y un fade-in de entrada. Respeta `prefers-reduced-motion`.
6. **Responsive de verdad.** Se agregó **navegación móvil** (botón hamburguesa + panel) porque antes en móvil no había forma de navegar.

---

## 5. Antes vs Después (detalle a detalle)

### Superficies y color (modo claro)

| Token | Antes | Ahora | Por qué |
|---|---|---|---|
| `page` (fondo) | `#F8FAFC` | `#F4F6FB` | Un poco más frío/oscuro para separar de la superficie. |
| `surface` (card) | `#FFFFFF` | `#FFFFFF` | Se mantiene; la diferencia ahora se nota por contraste + sombra. |
| `elevated` | — | `#FFFFFF` | Nivel para overlays/menús con sombra mayor. |
| `sunken` | — | `#EDF1F8` | Fondos hundidos (tracks de barras, hovers). |
| `brand` | `#2563EB` (azul) | `#4F46E5` (índigo) | Índigo refinado, más "SaaS 2026", profesional. |
| `brandHover` | — (`/90` alpha) | `#4338CA` | Hover con color real, no opacidad. |
| `text` | `#0F172A` | `#0B1220` | Negro azulado más profundo, mejor contraste. |
| `muted` / `subtle` | `#64748B` | `#5A6B85` / `#8A99B3` | Dos niveles de texto secundario en vez de uno. |
| `border` / `borderStrong` | `#E2E8F0` | `#E5E9F2` / `#D3DAE8` | Borde sutil + borde fuerte para hover/foco. |
| tintes de estado | `bg-x/10` (alpha) | `xSoft` + `xSoftFg` sólidos | Contraste real en chips. |

### Modo oscuro

| Token | Antes | Ahora | Por qué |
|---|---|---|---|
| `page` | `#0F172A` | `#0A0F1C` | Más profundo; da espacio a la elevación. |
| `surface` | `#1E293B` | `#131A2B` | Separa claramente de la página. |
| `elevated` | — | `#1B2438` | Tercer nivel para menús/overlays. |
| `brand` | `#3B82F6` | `#6366F1` | Índigo coherente con el claro, legible sobre oscuro. |
| sombras | iguales que claro | escala propia más profunda | En oscuro la sombra se apoya más en opacidad. |

### Forma, sombra, tipografía, motion

| Categoría | Antes | Ahora |
|---|---|---|
| Radio | Defaults Tailwind (`lg`=8, `xl`=12) | Escala propia (`lg`=14, `xl`=18, `2xl`=24) → más suave/moderno |
| Sombra | `shadow-sm` por defecto en todo | Escala `xs→xl` con valores diseñados (luz suave en claro, profunda en oscuro) |
| Tipografía | Solo Inter | Inter (cuerpo) + **Manrope** (display) + `tabular-nums` en métricas |
| Motion | `transition-colors` | Tokens de duración/curva, hover-lift, fade-in, `prefers-reduced-motion` |
| Navegación móvil | Inexistente | Hamburguesa + panel desplegable |

---

## 6. Archivos y su rol

| Archivo | Rol |
|---|---|
| `src/assets/themes/default.json` | **La fuente de verdad del tema.** Editas esto para re-tematizar. |
| `src/app/core/theme.model.ts` | Contrato TypeScript del JSON (tipos). |
| `src/app/core/theme.service.ts` | Carga el JSON, convierte hex→canales, inyecta `--sp-*`, maneja claro/oscuro. |
| `src/app/core/theme.provider.ts` | `APP_INITIALIZER` que carga el tema antes de arrancar. |
| `src/styles.scss` | Espejo estático de tokens (primer pintado + fallback) + base + scrollbar + animación. |
| `tailwind.config.js` | Mapea utilidades (`bg-surface`, `shadow-md`, `rounded-xl`…) a las variables. |
| `src/index.html` | Carga las fuentes (Inter + Manrope) y aplica el modo antes del arranque (anti-parpadeo). |
| `src/app/shared/ui/{card,button,badge,page-header}.component.ts` | Componentes base que heredan los tokens. |
| `src/app/app.component.ts` | Shell: header, navegación (desktop + **móvil**), toggle de tema. |
| `src/assets/config/theme-config.json` | **Legado de boki-front.** Mapa de clases Tailwind "hardcodeadas". Se trajo por fidelidad pero **NO se usa**: mezclar valores reales con strings de clases es un anti-patrón. Aquí queda como referencia de lo que **no** conviene hacer. |

---

## 7. Cómo re-tematizar (o crear un tenant)

1. Copia `default.json` a, por ejemplo, `sdmujer.json`.
2. Cambia los hex de `color` (al menos `brand`, `brandHover`, `brandSoft`, `brandSoftFg`) para la marca de la entidad.
3. Apunta `loadTheme()` a ese archivo (o a un endpoint del backend resuelto desde el tenant del JWT).
4. Listo: cambia toda la app, claro y oscuro, sin tocar componentes ni recompilar.

> Recuerda mantener `styles.scss` con los valores del tenant **por defecto** (es el primer pintado). Los tenants alternos los resuelve el `ThemeService` en runtime.

---

## 8. Cómo llevar esto a boki-front

El motor es portable. En `boki-front`:

1. Copia `theme.model.ts`, `theme.service.ts`, `theme.provider.ts` y `assets/themes/default.json` (ajusta rutas de import).
2. Reemplaza el `tailwind.config.js` por el mapeo de tokens de aquí.
3. Sincroniza `styles.scss` con los mismos `--sp-*`.
4. Migra los componentes que usen clases sueltas (`bg-gray-50`, etc.) a los tokens semánticos (`bg-surface`, `text-muted`…). Ahí es donde estaba el `theme-config.json` legado: ya no se necesita.

---

## 9. Capturas

- **Antes**: `docs/screenshots/before/`
- **Después**: `docs/screenshots/after/`

Nomenclatura: `{pantalla}-{desktop|mobile}-{light|dark}.png`. Compara, por ejemplo, `executive-desktop-light.png` en ambas carpetas.

---

## 10. Próximos pasos sugeridos

- Pulir pantallas de tablero/backlog con los nuevos tokens (las llevaba otro flujo de trabajo en paralelo).
- Exponer un endpoint de tema por tenant en el backend y conectar `loadTheme()`.
- Considerar un selector de densidad (cómoda/compacta) como otro token.
