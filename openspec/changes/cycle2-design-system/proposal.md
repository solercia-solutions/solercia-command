# Propuesta — Ciclo 2: Sistema de diseño y librería de componentes `@boki/ui`

- **Change id:** `cycle2-design-system`
- **Estado:** en ejecución (Fases 0–1 hechas, Fase 2 en curso)
- **Artifact store:** openspec (archivos visibles/marcables)
- **Origen:** `docs/TRANSCRIPCIONES.md` → "CICLO 2 DISEÑO"

## 1. Contexto

El frontend (base `boki-front`) ya tiene un motor de theming por JSON en runtime y un set de componentes con prefijo `bk-`. El usuario quiere consolidar esto en una **librería propia reutilizable y "skin por JSON"**, corregir bugs de UI introducidos, y dejar una base licenciable. Stack: Angular 20 (standalone, signals, Tailwind, `@angular/cdk` disponible) + FastAPI + Postgres + Redis, vía docker-compose. Trabaja un agente en paralelo sobre el mismo repo (backend alerts/notifications + admin), por lo que la coordinación y no-pisar-código es un requisito.

## 2. Problema

1. **Bug:** los modales se descentran y se cortan arriba (regresión de estilo).
2. **Drift entre proyectos:** "le digo al agente que copie y no copia todo" → divergencia. No hay una fuente de verdad versionada.
3. **Falta variabilidad de marca:** se quiere cambiar color/fuente/tamaño/borde/sombra/blur/animación por JSON sin que dos proyectos se parezcan.
4. **UX puntual:** asignar roles con +20 opciones (checkbox-list) y modales angostos.
5. **Transversal:** falta logging y manejo de excepciones estandarizados en el front.

## 3. Objetivos

- Arrancar `@boki/ui` como **librería Angular empaquetable** (ng-packagr), con theme engine, **logging** y **manejo de errores** de primera clase.
- Que **editar un JSON** re-tematice todo (incluido blur, bordes, densidad, animaciones de apertura).
- Corregir el bug de modales y los quick-wins de UX.
- Base para licenciar (LICENSE propietaria, procedencia limpia, registro DNDA).

## 4. No-objetivos (de este ciclo)

- NO migrar toda la app a consumir el paquete todavía (el agente paralelo está moviendo `shared/ui`; se hace cuando se estabilice — Fase 4).
- NO publicar al registro privado aún (se deja listo; publish real = Fase 6).
- NO construir el "vibe" dinámico (neón/glass/scroll-reveal) en esta tanda — queda como spike opt-in (Fase 5).
- NO patentar (el código se protege con derecho de autor; "patente" no aplica).

## 5. Alcance por fases

| Fase | Entregable | Estado |
|------|-----------|--------|
| 0 | Modales centrados + evidencia | ✅ |
| 1 | Plan de librería (`docs/libreria-componentes-plan.md`) | ✅ |
| 2 | Scaffold `@boki/ui` + theme core + `BokiLogger` + manejo de errores + `bk-card`/`bk-button` + build verificado | 🔵 en curso |
| 3 | Quick wins UX: modales `xl/2xl` + apilado móvil, roles → `bk-select`, animaciones de apertura | ⬜ |
| 4 | Migrar la app a `@boki/ui` (reemplazar copias locales) | ⬜ |
| 5 | Spike "vibe" dinámico opt-in | ⬜ (opcional) |
| 6 | Publish privado + LICENSE + DNDA | ⬜ |

## 6. Enfoque

Librería aislada en `frontend/projects/boki-ui/` (no toca el runtime de la app → modales y app intactos). Tres piezas: `@boki/ui` (componentes), theme engine portable, y `tailwind-preset`. Logging y errores como servicios/proveedores de la librería. Detalle técnico en `design.md`.

## 7. Comparación: propuesta vs. lo que ya estoy ejecutando

| Punto de la propuesta | ¿Coincide con lo ejecutado? | Nota |
|---|---|---|
| Fase 0 — bug modales | ✅ Idéntico | Causa real hallada (transform persistente de `.sp-animate-in`), corregido y con evidencia antes/después. |
| Fase 1 — plan librería | ✅ Idéntico | `docs/libreria-componentes-plan.md` ya cubre empaquetado, theming, CDK y licenciamiento. |
| Fase 2 — `@boki/ui` | 🔵 Arrancada, alineada | Tareas nativas #1–#4 creadas (scaffold, theme, logger, errores). Se ejecuta como librería aislada (no migración) → coincide con el no-objetivo de no tocar la app aún. |
| Logging / errores | ✅ Coincide | Eran transversales en el goal; están en la Fase 2 como `BokiLogger` + `BokiErrorHandler` + interceptor. |
| Fase 3 — UX (roles/modales anchos) | ⚠️ Pendiente | Diagnosticado (roles = checkbox-list; `bk-select` existe). NO ejecutado para no pisar `users-page`/`roles-page` del agente paralelo. |
| Fase 5 — vibe dinámico | ⚠️ Fuera de alcance | El usuario lo puso "sobre la mesa"; queda como spike, no se ejecuta en Fase 2. |
| Licencia/DNDA | ✅ Coincide | Aclarado en el plan; ejecución de LICENSE/headers entra en Fase 2; registro DNDA en Fase 6. |

**Desviación a validar:** la Fase 2 NO migra la app (deliberado, por concurrencia). Si querés ver `@boki/ui` ya consumido por la app, eso es Fase 4 y conviene coordinar una ventana con el agente paralelo.
