# Archive Report: 15-adapter-microsoft365

**Cambio**: 15-adapter-microsoft365 (Primer adaptador real sobre los puertos del cambio 14: Microsoft Graph, solo lectura, autorización delegada)  
**Estado**: ARCHIVADO ✅  
**Fecha de archivo**: 2026-07-19  
**Ciclo SDD**: proposal → spec → design → tasks → apply → verify → archive (completo)

---

## Artefactos de Cambio

| Artefacto | Estado | Engram ID | Archivo archivado |
|-----------|--------|-----------|-------------------|
| Proposal | ✅ Done | 1637 | `proposal.md` |
| Specification | ✅ Done | 1645 | `spec.md` |
| Design | ✅ Done | 1648 | `design.md` |
| Tasks | ✅ Done (49/49) | 1660 | `tasks.md` |
| Apply Progress | ✅ Done | 1694 | (referencia histórica) |
| Verification Report | ✅ PASS | 1701 | `verify-report.md` |
| Archive Report | ✅ Este documento | TBD | `archive-report.md` |

---

## Resumen Ejecutivo

El cambio 15-adapter-microsoft365 implementa el **primer adaptador real** sobre el núcleo hexagonal del cambio 14 (integration-ports). El adaptador consume Microsoft Graph en modo **solo lectura** con autorización delegada (Entra ID/Azure AD), implementando cuatro puertos del 14:

- `MailReaderPort` (Outlook)
- `CalendarReaderPort` (Calendario)
- `ExternalTaskReaderPort` (Planner, sin Microsoft To Do)
- `MeetingNotesReaderPort` (Transcripciones de Teams, con degradación por falta de consent)

**Ciclo completado**: 8 requisitos, 10 escenarios, 49 tareas TDD (8 lotes con commits estrictamente under-400-líneas), 729 tests PASS (13 fallas legacy pre-existentes, cero regresión), revisión 4R con recibo nativo APPROVED.

---

## Trazabilidad del Ciclo

### Fase 1: Proposal (1637)
- **Requisitos**: definición del alcance, mapeo capacidad→endpoint Graph, riesgos (transcripciones requieren admin consent, 429 throttling, fuga de tokens), plan de rollback aditivo.
- **Decisiones**: tenant=`organizations` por defecto, degradación de meeting_notes sin consent, flujo OAuth confidential-client (PKCE diferido).
- **Ronda de preguntas abiertas**: (1) tenant fijo vs multi-tenant, (2) transcripciones fallback, (3) Planner vs To Do, (4) defaults de ventana temporal.

### Fase 2: Specification (1645)
- **Requisitos formales**: 8 requerimientos numerados (M365-R1 a M365-R8), 10 escenarios BDD.
- **Mapping a puertos del 14**: cada puerto mapea a un endpoint Graph específico y a un scope delegado.
- **Restricciones**: solo lectura (0 escritura), auto-registro sin editar núcleo, degradación aislada por capacidad.
- **Depende de**: `integration-ports` spec (14) sin cambios.

### Fase 3: Design (1648)
- **Arquitectura**: paquete `app/integrations/adapters/microsoft365/` (7 archivos), GraphClient httpx inyectable, TDD contra fixtures reales.
- **Decisiones arquitectónicas 5 ADRs**:
  1. Scopes de transcripciones opt-in (no en set por defecto) → aísla degradación.
  2. Detección de meeting_notes por introspección sin red → fallback en runtime al `403`.
  3. Refresh dentro del adaptador (401→refresh→retry once) → respeta "cero cambios al núcleo".
  4. Flujo confidential-client + PKCE diferido → state single-use + client_secret suficientes.
  5. `external_account_id` = claim `oid` (no UPN) → estabilidad + evita GET /me extra.
- **Defaults ratificados**: `since`=30d, `limit`=50, `MAX_PAGES`=20, `CALENDAR_FUTURE_DAYS`=90.
- **Threat Matrix cubierto** con RED tests: sin fuga de tokens, anti-SSRF/host fijo, TLS obligatorio, backoff acotado.

### Fase 4: Tasks (1660)
- **Estructura**: 8 lotes + 1 tarea de VERIFY final. Cada lote RED→GREEN→VERIFY (TDD estricto).
- **Contar**: 49 tareas (Lote 1: 7, Lote 2: 6, Lote 3: 7, Lote 4: 6, Lote 5: 6, Lote 6: 6, Lote 7: 6, Lote 8: 5).
- **Trazabilidad**: cada tarea RED mapea explícitamente a un requisito (M365-R1–R8) y escenario de spec.
- **Forecast**: ~1.600–1.900 líneas acumuladas, High risk presupuestario → cada lote individual <400 líneas (decisión correcta).
- **Estrategia de entrega**: commits convencionales directos a `feat/consume-solercia-ui`, sin PR, stacked-to-main.

### Fase 5: Apply (1694 + histórico)
- **Commits realizados**: 8 commits convencionales (7ac8da2, 36a0e9f, adf641f, 3616b53, 2af258d, 9e85e75, bcd3418, 72b0630).
- **Fix commit 774ca29**: +6 tests nuevos (scopes nunca vacíos, clamp de backoff, Planner 403→[], 4xx/5xx distinción, etc.).
- **Todos los 49 ítems implementados y verificados en el código real**.
- **Desviaciones as-built documentadas**:
  - Endpoint de transcripciones: `/me/onlineMeetings/getAllTranscripts` en vez del per-reunión mencionado (evita multi-hop fuera de presupuesto).
  - Planner `assignee`: primer oid de `assignments` (no email, requeriría `$expand`).
  - Planner `url`: siempre `None` (Planner v1.0 no expone).

### Fase 6: Verification (1701 — PASS)
- **Conteo**: 729 PASS / 13 FAILED (legacy pre-existentes, cero regresión). Suite determinista (2 corridas 188.79s vs 188.26s).
- **Completeness**: 49/49 tareas `[x]`, 8/8 requisitos cubiertos, 10/10 escenarios COMPLIANT con test real.
- **Build**: ruff + mypy 100% limpios en `app/integrations/adapters/microsoft365/`.
- **Revisión nativa 4R**: lineage `review-3cd4e895bb13c963` → terminal_state: `approved`, 0 CRITICAL, 2 WARNING (documentales), 2 SUGGESTION.
- **Frontera solo-lectura**: guard AST + grep independiente → único POST es OAuth a login, nunca Graph.
- **ER-model**: 0 cambios (confirma aditivo puro).

---

## Spec Sync to Main Specs

| Acción | Fuente | Destino | Resultado |
|--------|--------|---------|-----------|
| Create | `openspec/changes/15-adapter-microsoft365/specs/adapter-microsoft365/spec.md` | `openspec/specs/adapter-microsoft365/spec.md` | ✅ Creado (nueva capacidad, no delta) |

**Notas de fusión**:
- Este spec es una **especificación completa** (no un delta) → copiar directamente.
- Depende de `14-integration-ports` spec sin cambios al 14.
- Requiere 8 requisitos, 10 escenarios, todos implementados y probados.

---

## Cambio del Archivo

```
openspec/changes/15-adapter-microsoft365/
  ├── proposal.md
  ├── specs/adapter-microsoft365/spec.md
  ├── design.md
  ├── tasks.md
  ├── verify-report.md
  └── state.yaml

↓ MOVIDO A:

openspec/changes/archive/2026-07-19-15-adapter-microsoft365/
  ├── proposal.md
  ├── specs/adapter-microsoft365/spec.md
  ├── design.md
  ├── tasks.md
  ├── verify-report.md
  ├── state.yaml (actualizado: archive: done)
  └── archive-report.md (este documento)
```

---

## Validación de Puertas de Archivo

### Gate 1: Recibo de Revisión Nativa ✅
- **Estado**: `reviewGate.result: allow`
- **Transacción**: `review-3cd4e895bb13c963`
- **Terminal**: `approved`
- **Risk Level**: `high`
- **Lentes**: review-risk, review-resilience, review-readability, review-reliability (4R)
- **Hallazgos**: 0 CRITICAL, 2 WARNING (documentales), 2 SUGGESTION → corregidos en 774ca29
- **Resultado**: ✅ ALLOW — Primera serie de cambio 15 con recibo nativo APPROVED.

### Gate 2: Completitud de Tareas ✅
- **Tareas totales**: 49
- **Tareas `[x]`**: 49
- **Tareas incompletas**: 0
- **Desajuste reportado**: apply-progress citó "39/39" → conteo real es 49/49 (error documental, no de código). Todos los 49 ítems verificados contra implementación real.
- **Resultado**: ✅ PASS — Todos los ítems completados e implementados.

### Gate 3: Requisitos y Escenarios ✅
- **Requisitos de spec**: 8 (M365-R1 a M365-R8)
- **Escenarios**: 10 (cubiertos por tests RED explícitos)
- **Compliance**: 10/10 COMPLIANT con test real en verde
- **Resultado**: ✅ PASS — Spec completamente implementada y verificada.

### Gate 4: Integridad de Cambios ✅
- **ER-model**: sin cambios (usa tablas del 14: connectors, connected_accounts, connection_credentials)
- **Núcleo del 14**: sin cambios (ports.py, oauth.py, registry.py, crypto.py intactos)
- **Archivo-nivel**: C4 architecture actualizado, ortografía colombiana (vía/autorización/organización/reunión)
- **Tests legacy**: 0 regresión (13 fallas pre-existentes idénticas en 2 corridas)
- **Resultado**: ✅ PASS — Cambio aditivo puro, sin daño colateral.

---

## Commits Implementados

| # | SHA (abreviado) | Mensaje | Líneas | Estado |
|---|-----------------|---------|--------|--------|
| 1 | 7ac8da2 | `feat(microsoft365): cliente graph base con paginacion y tls obligatorio` | ~180 | ✅ PASS |
| 2 | 36a0e9f | `feat(microsoft365): resiliencia 401 refresh y 429 backoff del cliente graph` | ~240 | ✅ PASS |
| 3 | adf641f | `feat(microsoft365): handshake oauth entra id y registro del adaptador` | ~320 | ✅ PASS |
| 4 | 3616b53 | `feat(microsoft365): lectura de correo via mailreaderport` | ~180 | ✅ PASS |
| 5 | 2af258d | `feat(microsoft365): lectura de calendario via calendarreaderport` | ~160 | ✅ PASS |
| 6 | 9e85e75 | `feat(microsoft365): lectura de tareas planner via externaltaskreaderport` | ~150 | ✅ PASS |
| 7 | bcd3418 | `feat(microsoft365): notas de reunion con degradacion por consentimiento` | ~200 | ✅ PASS |
| 8 | 72b0630 | `feat(microsoft365): frontera solo lectura docs c4 y httpx en requirements` | ~170 | ✅ PASS |
| — | 774ca29 | `fix(microsoft365): scopes default, backoff clamp, planner 403, logging sin fuga` | +293/-32 | ✅ PASS |

**Total**: ~1.790 líneas netas (sin cambios al 14 ni migraciones), todos bajo presupuesto 400-líneas por lote.

---

## Desviaciones y Notas de As-Built

### 1. Endpoint de Transcripciones (WARNING documental, no CRITICAL)
- **Design decía**: `/me/onlineMeetings/{id}/transcripts` (per-reunión)
- **As-built implementó**: `/me/onlineMeetings/getAllTranscripts` (estado paginado global)
- **Razón**: Graph no ofrece "listar todas mis reuniones" sin filtro previo con scopes delegados → evita multi-hop fuera del presupuesto del lote.
- **Impacto**: Ambos escenarios de M365-R6 (consentimiento otorgado / no otorgado) pasan idénticamente. No rompe spec.
- **Documentación**: Anotado en docstring de `ports.py::GraphMeetingNotesReader` + esta nota.
- **Recomendación**: Actualizar design.md en siguiente pase de mantenimiento de docs (no bloquea).

### 2. Planner `assignee` (SUGGESTION, no bloqueante)
- **Mapeo**: primer `oid` de `assignments` (no email)
- **Razón**: Graph no devuelve email del oid sin `$expand` → fuera del presupuesto del lote.
- **Impacto**: No viola M365-R5 (spec no exige email). UX mejora si ola 22 resuelve oid→email.
- **Documentación**: Docstring de `mappers.map_external_task`.

### 3. Planner `url` (SUGGESTION, no bloqueante)
- **Valor**: siempre `None`
- **Razón**: Planner v1.0 no expone `webUrl`; v2.0 puede hacerlo en futuro.
- **Impacto**: No viola M365-R5. Mejora futura aceptada.

### 4. Persistencia de tokens rotados (diseño esperado, no un defecto)
- **Estado**: Sink `on_tokens_refreshed` probado, pero sin wiring de producción a persistencia real.
- **Razón**: Ningún router/servicio construye `AccessContext` con sink real apuntando a BD. Difiere a ola 22 (wiring del engine).
- **Documentación**: Explícito en design.md "Open Questions" y apply-progress.
- **Recomendación**: Ola 22 incluya test de persistencia de dos sesiones independientes cuando se cablee.

---

## Cambios en OLA_2.md

Fila 15 (`15-adapter-microsoft365`):
- Cambiar `verify: [ ]` → `verify: [x]`
- Cambiar `archive: [ ]` → `archive: [x]`

---

## Archivos Persistidos en Engram

| Artefacto | Observation ID | Topic Key | Tipo |
|-----------|----------------|-----------|------|
| Proposal | 1637 | `sdd/15-adapter-microsoft365/proposal` | architecture |
| Specification | 1645 | `sdd/15-adapter-microsoft365/spec` | architecture |
| Design | 1648 | `sdd/15-adapter-microsoft365/design` | architecture |
| Tasks | 1660 | `sdd/15-adapter-microsoft365/tasks` | architecture |
| Verify Report | 1701 | `sdd/15-adapter-microsoft365/verify-report` | architecture |
| **Archive Report** | **TBD** | **`sdd/15-adapter-microsoft365/archive-report`** | **architecture** |

Todos los artefactos persisten con `capture_prompt: false` (son salidas de pipeline automático, no decisiones humanas).

---

## Próximos Pasos (Follow-ups, Fuera del Alcance de Este Cambio)

1. **Ola 22 (clasificador/wiring del engine)**:
   - Wiring del sink `on_tokens_refreshed` a persistencia real en BD de connected_accounts.
   - Test de persistencia de dos sesiones independientes (confirmado esperado, no defecto).
   - Consumo del adaptador microsoft365 para lectura de correo/calendario/tareas/notas.

2. **Ola 16 (Google Calendar/Tasks)**:
   - Reutilizar puertos del 14 (CalendarReaderPort, ExternalTaskReaderPort).
   - Precedente establecido por este adaptador.

3. **Ola 17–18 (GLPI/Jira para TicketReaderPort)**:
   - TicketReaderPort queda aquí sin cobertura.
   - Este adaptador NO implementa tickets (por diseño).

4. **Documentación de mantenimiento (próxima oportunidad)**:
   - Actualizar design.md con endpoint getAllTranscripts como as-built.

---

## Ciclo Cerrado ✅

El cambio 15-adapter-microsoft365 ha completado el ciclo SDD:

| Fase | Resultado | Observación |
|------|-----------|-------------|
| Proposal | ✅ 1637 | Alcance, riesgos, decisiones pre-spec |
| Specification | ✅ 1645 | 8 reqs, 10 escenarios, formal |
| Design | ✅ 1648 | 5 ADRs, Threat Matrix, interfaces |
| Tasks | ✅ 1660 | 49 tareas TDD en 8 lotes |
| Apply | ✅ (8 commits + fix) | 729 PASS, 0 regresión |
| Verify | ✅ 1701 | PASS: 10/10 escenarios, 0 CRITICAL |
| **Archive** | ✅ Este documento | Trazabilidad completa, specs fusionados |

**Estado final**: ARCHIVADO. Listo para que la ola 22 consuma el adaptador microsoft365 sin sorpresas.
