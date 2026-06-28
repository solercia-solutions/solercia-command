# Diseño técnico — Ciclo 2 (`@boki/ui`)

## Estructura de la librería

```
frontend/projects/boki-ui/
├── package.json            # @boki/ui, peerDependencies, version 0.1.0, publishConfig, sideEffects:false, license
├── ng-package.json         # ng-packagr (Angular Package Format)
├── tsconfig.lib.json / .prod.json
├── README.md / LICENSE     # uso + licencia propietaria
├── tailwind-preset.js      # mapeo token→utilidad (lo que el consumidor agrega a su tailwind.config)
├── assets/themes/default.json
└── src/
    ├── public-api.ts       # superficie pública (lo único exportado)
    └── lib/
        ├── theme/          # theme.model, theme.service, theme.provider, default-theme
        ├── logging/        # logger.service, log-level, logger.config (token)
        ├── errors/         # error-handler, http-error.interceptor, app-error, provideBokiErrors
        └── components/     # bk-card, bk-button (primeras piezas)
```

## Decisiones

1. **Librería aislada, no migración.** Se crea en paralelo a `src/app/shared/ui` (que el agente paralelo edita). La app NO se reapunta todavía → cero riesgo para modales/runtime. Migración = Fase 4.
2. **Empaquetado:** Angular library con **ng-packagr** (`ng build boki-ui`), semver, `peerDependencies` sobre `@angular/*` (no se embeben), `sideEffects:false` para tree-shaking, `public-api.ts` como única superficie.
3. **Theming portable:** el JSON es la fuente de verdad; `ThemeService` convierte hex→canales e inyecta `--sp-*`; `tailwind-preset.js` mapea utilidades. El consumidor: instala, agrega el preset, suelta un `default.json`, edita el JSON.
4. **Tokens a ampliar** (para la variabilidad pedida): blur, ancho de borde, densidad, y `motion.enter/exit` por componente (animaciones de apertura skinneables).
5. **Logging (`BokiLogger`):** niveles DEBUG/INFO/WARN/ERROR/NONE; nivel mínimo por `InjectionToken` (DEBUG dev / WARN prod); salida estructurada `{ts, level, ctx, msg, data}`; sink pluggable (consola por defecto, hook remoto); nunca `console.*` directo en componentes.
6. **Errores (best practices front):**
   - `BokiErrorHandler implements ErrorHandler`: captura no-controlados, loguea con `BokiLogger`, no traga, expone hook de notificación.
   - `bokiHttpErrorInterceptor` (funcional): mapea status → `AppError` tipado (401 sesión, 0 red, 4xx cliente, 5xx servidor), loguea y rethrow.
   - `AppError`: `{ code, userMessage, technical, cause }`.
   - `provideBokiErrors()`: cablea ErrorHandler + interceptor + config.
7. **DECISIÓN DEL OWNER (2026-06-28): NO se adopta Angular CDK.** Se evaluó CDK (overlay, drag&drop, accordion, table…) pero se decide **seguir 100% con componentes propios sin agregar dependencias ni features nuevas** por ahora. Implicación aceptada: el recorte del dropdown del `bk-select` dentro de modales se resuelve a mano (reposicionamiento) o se acepta, no con CDK Overlay. Prioridad: cero dependencias + licenciabilidad sobre conveniencia.
8. **Prefijo `bk-`** unificado (ya lo estandarizó el flujo paralelo).

## Verificación

- `ng build boki-ui` compila/empaqueta sin error (en host, que tiene node_modules).
- La app sigue sirviendo y **los modales siguen centrados** (Playwright: `dialog fullyVisible:true`).
