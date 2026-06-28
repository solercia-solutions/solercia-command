# Tareas — Ciclo 2 (`cycle2-design-system`)

> Marcá `[x]` al completar. Validación final con `sdd-verify` o revisión manual contra el código.

## Fase 0 — Bugfix modales ✅
- [x] 0.1 Diagnosticar el descentrado (causa: `transform` persistente de `.sp-animate-in`)
- [x] 0.2 Corregir (quitar fill-mode `both`) — `frontend/src/styles.scss`
- [x] 0.3 Evidencia antes/después (light/dark/mobile) — `docs/screenshots/modales/`
- [x] 0.4 Commit `bee1a27`

## Fase 1 — Plan de librería ✅
- [x] 1.1 Documento de planificación — `docs/libreria-componentes-plan.md`
- [x] 1.2 Comparación/portabilidad a boki-front y licenciamiento

## Fase 2 — Arrancar `@boki/ui` ✅
- [x] 2.1 Scaffold `projects/boki-ui` (package.json, ng-package.json, tsconfig.lib, public-api, LICENSE, README, headers)
- [x] 2.2 Theme engine portado (model/service/provider + default.json) + `tailwind-preset.js`
- [x] 2.3 `BokiLogger` (niveles, config por token, estructurado, sink pluggable)
- [x] 2.4 Manejo de errores (`BokiErrorHandler` + `bokiHttpErrorInterceptor` + `AppError` + `provideBokiErrors()`)
- [x] 2.5 Componentes base `bk-card`, `bk-button` en la librería
- [x] 2.6 Registrar build (angular.json + `ng-packagr`) y verificar `ng build boki-ui` OK (`✔ Built @boki/ui`)
- [x] 2.7 Verificar app + modales con Playwright (`fullyVisible:true`) + commit
- [x] 2.8 Recomendación de skills de estilo (`frontend-design`) — ver resumen/README

## Fase 3 — Quick wins UX ✅
- [x] 3.1 `bk-modal`: tamaños `xl`/`2xl`/full + apilado móvil (usuarios usa `xl`)
- [x] 3.2 Roles: reemplazar checkbox-list por `bk-select` multi + buscable (vía `formControlName`)
- [x] 3.3 Animaciones de apertura de `bk-modal`/`bk-select` (por token: `bk-anim-*`)
- Nota: dropdown del `bk-select` se recorta levemente dentro del modal (overflow). Fix de raíz = CDK Overlay (Fase 4).

## Fase 4 — Migrar la app a `@boki/ui` ⬜
- [ ] 4.1 Reapuntar imports de `shared/ui` al paquete (ventana coordinada)
- [ ] 4.2 Verificación de regresión (Playwright)

## Fase 5 — Spike "vibe" dinámico ⬜ (opcional)
- [ ] 5.1 Tokens de blur/glow + superficie glass
- [ ] 5.2 Directiva scroll-reveal escalonado
- [ ] 5.3 Demo con skill `frontend-design`

## Fase 6 — Empaquetado / IP ⬜
- [ ] 6.1 Publish privado (GitHub Packages/Verdaccio) + CHANGELOG + semver
- [ ] 6.2 LICENSE propietaria + headers + política de contribución
- [ ] 6.3 Registro de soporte lógico (DNDA)
