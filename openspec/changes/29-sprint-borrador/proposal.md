# Proposal: 29 · Sprint borrador (creación con solo nombre + autonombre)

## Intent

Hoy crear un sprint obliga a decidir fechas y nace `active` (`sprints/service.py:68`), lo que rompe el flujo estilo Jira que pidió el usuario: abrir un sprint vacío al vuelo, llenarlo desde el backlog y recién entonces fecharlo e iniciarlo. Este cambio (OLA 4, fase 4.2) permite crear un sprint SOLO con nombre, en estado `draft` sin fechas, con un nombre sugerido automáticamente, y separa "añadir fechas" de "iniciar sprint".

## Scope

### In Scope
- Estado de arranque `draft` (creación) además de `active`/`closed`; transición `draft → active` (iniciar) y `active → closed` (ya existe).
- Autonombre en la creación: base del último sprint del proyecto + consecutivo (`PANDORA 2026-1` → `PANDORA 2026-2`); sin anterior → `<CODE> Sprint 1` (CODE = `projects.code`).
- Creación mínima: `POST /projects/{id}/sprints` acepta nombre vacío → el servidor sugiere el autonombre; endpoint de sugerencia para precargar la UI.
- Acción "Iniciar sprint" (`POST /sprints/{id}/start`): valida fechas presentes; sin ellas devuelve 422 con mensaje claro en español.
- "Añadir fechas" reutiliza `PATCH /sprints/{id}` (ya soporta `start_date`/`end_date`).
- UI: botón "Crear sprint" liviano (solo nombre, autonombre editable), badge "Borrador", acción "Añadir fechas" e "Iniciar sprint" deshabilitado hasta tener fechas.
- TDD: no se puede iniciar sin fechas; consecutivo correcto con nombres no convencionales (sin número final, con año tipo `2026-1`).

### Out of Scope
- Controles de metodología al iniciar (avisos de historias sin estimación) → cambio 42.
- Drag & drop backlog↔sprint (cambio 31) y vista de sprints agrupados (cambio 30).
- Unicidad de nombres de sprint (no existe hoy y no se introduce).

## Capabilities

### New Capabilities
- None

### Modified Capabilities
- `sprints`: nuevo estado `draft` de arranque, autonombre en creación, acción de inicio con validación de fechas y guardas de transición.

## Approach

`Sprint.status` NO es un enum de BD sino un `String(20)` validado en el servicio (`_ALLOWED_STATUSES`) y `start_date`/`end_date` ya son nullable, así que `draft` se agrega SIN migración de esquema: solo se amplía el whitelist y `create_sprint` pasa a nacer `draft` (el default de columna sigue `active` para compatibilidad). El gate de sprints ya lee `get_strategy(project.methodology).sprints_enabled` (limpio, sin `if methodology ==`), por lo que `draft` solo aplica donde la strategy habilita sprints. El autonombre consulta el último sprint por `created_at` (cualquier estado), parsea con regex la ÚLTIMA corrida numérica conservando el separador y la incrementa; sin previo usa `code`; sin número final trata el existente como implícito y sufija ` 2`. El autonombre es SUGERENCIA editable, no unicidad forzada.

## Affected Areas

| Area | Impacto | Descripción |
|---|---|---|
| `backend/app/modules/sprints/{service,schemas,router,repository}.py` | Modified | `draft`, autonombre, `/start`, guardas |
| `backend/tests/**` | New | Contratos: iniciar sin fechas, consecutivo |
| `frontend/.../project-workspace.component.ts` | Modified | Estado borrador + acciones |
| `frontend/src/entities/workspace/workspace.service.ts` | Modified | `startSprint`, autonombre |
| `frontend/src/assets/i18n/es-CO.json` | Modified | Textos (tuteo) |

## Risks

| Riesgo | Prob. | Mitigación |
|---|---|---|
| Regex confunde año `2026-1` con consecutivo | Media | Capturar última corrida numérica + separador; TDD |
| Nombre no convencional sin número final | Media | Regla explícita (sufijo ` 2`); TDD |
| `active` cambia de "creado" a "iniciado" | Baja | Sprints previos intactos; solo aplica a nuevos |
| Sprint `draft` sin fechas en burndown/velocity | Baja | Ya guardado por `start/end None` y por no estar `closed` |

## Rollback Plan

Cambio solo de código, sin migración ni datos tocados: revertir el commit restaura el comportamiento previo. Sprints creados como `draft` durante la vigencia pueden tratarse como `active` en lectura si se revierte.

## Dependencies

- `depends_on: []` técnico. El apply se ordena tras cerrar la fase 4.1 (25→26→27→28) por secuencia de la ola.

## Success Criteria

- [ ] Sprint creable solo con nombre → nace `draft` sin fechas.
- [ ] Autonombre correcto: consecutivo desde el último sprint; `<CODE> Sprint 1` sin previo; nombres no convencionales.
- [ ] "Iniciar sprint" falla sin fechas (422 en español) y transiciona `draft → active` con fechas.
- [ ] UI muestra borrador, "Añadir fechas" e "Iniciar sprint" condicionado.
- [ ] Suite backend en verde (TDD primero).

## Proposal question round

Supuestos a validar: (1) `draft` como valor nuevo del `status` string (sin migración de enum, default de columna sigue `active`) en vez de reintroducir `planned`; (2) autonombre es sugerencia editable, sin unicidad forzada; en colisión se incrementa best-effort; (3) nombre sin número final → sufijo ` 2` (el existente cuenta como 1); (4) `POST /sprints/{id}/start` dedicado (espeja `/close`) en vez de PATCH genérico de status; (5) fallback de `<CODE> Sprint 1` cuando `projects.code` es null (ej. primeras letras del nombre o "Sprint 1"). Se puede correr una segunda ronda si el usuario quiere revisar la regla de sufijo o el fallback de clave.
