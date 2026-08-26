# OLA 5 — Solercia Command como centro real de SDMujer

**Estado**: EN EJECUCIÓN — iniciada el 2026-08-26 sobre la línea base `b5b0399` (rama de trabajo `feat/42-purga-datos-demo`, derivada de `feat/adaptador-solercia-connect`).
**Plan aprobado**: `~/.claude/plans/quiero-que-me-ayudas-proud-quokka.md` (fuera del repo; decisiones persistidas en Engram, proyecto `gestion_proyectos`, observaciones #3682–#3689).
**Preflight SDD de la sesión**: ejecución automática · artefactos híbridos (openspec + Engram) · PRs encadenados automáticos cuando el pronóstico lo exija · presupuesto de revisión 2000 líneas.

## 1. Objetivo

Convertir Solercia Command en la herramienta de trabajo real del usuario para SDMujer: purgar los datos de demostración, importar el checklist de tareas (131 filas, consolidadas), modelar los planes institucionales (PSPI, PTR, PAI, PTEP) como dimensión transversal N:N, ingerir correo de entrada y salida vía Solercia Connect, y agregar un componente de IA con puertos y adaptadores intercambiables (LLM local u OpenAI/Anthropic compatibles) que sugiera clasificación, cierre y enlaces a planes sin acoplar el núcleo.

## 2. Decisiones resueltas (2026-08-26)

| Tema | Decisión |
|---|---|
| Tenant y jerarquía | Un solo tenant (`Solercia`). `SDMUJER` (area, planner, `SDM`) > `SEGURIDAD` (proyecto, custom, `SEG`) + `PANDORA` (proyecto, kanban, `PAN`). |
| Estados de SEGURIDAD | Tablero custom de 7 columnas, con `Completada` **última** porque el estado terminal es posicional (`allowed_statuses()[-1]`): `Sin iniciar, En curso, Diferida, Recurrente, Gestionada aparte, Removida, Completada`. La exclusión de `Removida`/`Gestionada aparte` del denominador de avance se difiere al cambio 44. |
| Datos demo | Se borran físicamente (excepción documentada al borrado suave) con respaldo `pg_dump` previo y verificado. Se conservan: org `Solercia`, `admin@solercia.com`, las 5 plantillas de sistema `org_role_templates`, conectores `jira`/`google`/`microsoft365`, `alert_rules`, roles, menús, dependencias. |
| Semilla | `SEED_DEMO_DATA=false` obligatorio antes de purgar: `seed_default()` recrea miembros demo incondicionalmente y siembra tareas demo cuando `COUNT(tasks)==0`. |
| Planes | Dimensión transversal N:N en Command (`plans`, `plan_activities`, `plan_activity_reports`, `plan_activity_links`, `task_plan_activities`) con `public_id` para referencias futuras desde Security. Del PAI se importan solo las 11 actividades propias (políticas 11 y 12). |
| Checklist | Se consolida antes de importar: 4 fusiones, subtareas, 7 tareas de contexto y contradicciones, en un CSV que el usuario revisa antes de ejecutar. El registro es fuente de verdad; el análisis se valida con él. |
| Pandora | Subproyecto propio; Jason Rizo y Santiago Carreño como usuarios `viewer` sin login, asignables. |
| Correo | Connect gana `mail.inbox.list` + `internetMessageId`/`folder`; Command reutiliza su adaptador `solercia_connect` (corrige 3 bugs de contrato, agrega transporte por archivo de sobre para la ruta navegador, ventana en `intake/pull`). Rango objetivo: 2026-06-01 → 2026-08-27 (fin exclusivo), segmentado por mes. |
| IA | `LlmPort` + adaptadores `openai_compatible`/`anthropic`/`fake`; el LLM solo sugiere, nunca cambia estado ni envía correos; sugerencias persistidas en `assistant_suggestions`. |

## 3. Cambios de la ola y dependencias

```
0 (línea base git) → 42 → 43 → 44 → 45
                           ↘ 46 (connect) ─┐
                           ↘ 48 ───────────┼→ 47 → 49 → 50 → 51
```

| № | Cambio | Repo | Entrega | Depende de | Estado |
|---|---|---|---|---|---|
| 0 | Línea base git | ambos | Commit `b5b0399` en Command; Connect ya estaba bajo git (`f3e967e`) | — | ✅ 2026-08-26 |
| 42 | `purga-datos-demo` | command | `SEED_DEMO_DATA`, casos de uso `app/maintenance/{purge,bootstrap}.py`, CLI `backend/scripts/purge_demo_data.py`, jerarquía `SDMUJER > SEGURIDAD + PANDORA` | 0 | 🟨 explore ✅ · propose en curso |
| 43 | `tareas-origen-externo` | command | `tasks.source` + `tasks.external_key` (único por proyecto+source+key); el cambio 40 se reancla | 42 | ⬜ |
| 44 | `importar-checklist-xlsx` | command | Importador con `checklist_consolidation.csv` revisable, enrutamiento SEGURIDAD/PANDORA, etiquetas, miembros Jason/Santiago | 43 | ⬜ |
| 45 | `planes-actividades` | command | Tablas de planes, API `/plans`, importadores DOCX (PSPI, PTR) y XLSX (PAI), vista «Planes» | 44 | ⬜ |
| 46 | `mail-inbox-list` | connect | Capacidad de bandeja de entrada en ambas rutas + `internetMessageId`/`folder` | 0 | ⬜ (requiere `sdd-init` en Connect) |
| 47 | `ingesta-connect-inbox` | command | Spec as-built del adaptador, transporte por archivo, ventana en pull, corrección de bugs, catálogo frontend | 43, 46 | ⬜ |
| 48 | `puerto-llm` | command | `LlmPort` + adaptadores + registry por env + `GET /assistant/health` | — | ⬜ |
| 49 | `clasificador-llm` | command | `LlmClassifier`, `assistant_suggestions`, casos de uso, reglas semilla, API de triage | 45, 47, 48 | ⬜ |
| 50 | `triage-ui` | command | Pantalla «Bandeja» (checklist `ux-psicologia`) | 49 | ⬜ |
| 51 | `borrador-cierre` | command | `DraftClosureEmail` + botón «Proyectar correo de cierre» (copiable; envío manual) | 49 | ⬜ |

Los cambios 33–41 de la Ola 4 permanecen planificados y sin aplicar; esta ola no los reordena.

## 4. Línea base técnica

- Suite backend sobre `b5b0399`: **1367 pasan, 3 fallan** (preexistentes, dependientes del reloj: `tests/test_adapter_microsoft365.py` puerto Planner/transcripciones). Cualquier `verify` compara contra esta línea.
- Head de Alembic: `0024_add_work_calendar`. El cambio 42 no agrega migraciones; el 43 y el 45 sí.
- Servicios: Postgres `127.0.0.1:5434` (`solercia`, `solercia_test`), Redis `127.0.0.1:6380`, backend `:8081`, frontend `:4242`.

## 5. Reglas operativas de la sesión autónoma (noche del 2026-08-26)

- Nunca `push`, nunca `main`; una rama por cambio; conventional commits en español sin atribución de IA.
- Ningún borrado físico sin `pg_dump` verificado en `/Users/camilocalderont/Proyectos/SOLERCIA/backups/`.
- Los conectores reales (`jira`, `google`, `microsoft365`) no se tocan; solo se borra `fake`.
- Nada que requiera login interactivo del usuario (barrido de correos por navegador) se ejecuta sin él.
- Progreso guardado en Engram fase por fase; este documento se actualiza al cerrar cada cambio.

## 6. Bitácora

- 2026-08-26 · Plan aprobado; decisiones persistidas (#3682–#3686); preflight SDD; línea base git `b5b0399`; rama `feat/42-purga-datos-demo`; suite base 1367/3.
- 2026-08-26 · 42 `explore` ✅ (#3687, `openspec/changes/42-purga-datos-demo/exploration.md`): tres correcciones al plan (compuerta de semilla, `Completada` última, plantillas de sistema se conservan). `propose` lanzado.
- 2026-08-26 · Connect: línea base `make test` 402 ok / 4 live deseleccionadas (2 s); `sdd-init` ✅ (Engram #3691/#3692, `openspec/config.yaml`, registro de 92 skills) comprometido en la rama `feat/46-mail-inbox-list` (`71aea46`).
- 2026-08-26 · 42 `propose` ✅ (#3693; cinco preguntas abiertas resueltas por el orquestador con los supuestos de la propuesta), `spec` ✅ (#3694: 15 requisitos / 35 escenarios en `data-maintenance` nueva + deltas `api-conventions`, `multi-tenancy`, `org-role-templates`, `intake-classifier`), `design` ✅ (#3696: paquete `app/maintenance/` con adaptador único, transacción única con dry-run = mismo código + rollback, CLI `python -m scripts.purge_demo_data`, 8 invariantes bloqueantes; ≈1900 líneas estimadas → rebanadas encadenadas). Validador de contrato del diseño en curso.
- 2026-08-26 · 46 `explore` ✅ (#3695, `solercia-connect/openspec/changes/46-mail-inbox-list/exploration.md`): tope efectivo de 100 mensajes/invocación (truncación silenciosa) → decisiones A3 + B2 + C2/C3 + D1, Gmail fuera de alcance. `propose` ✅ (#3698), `spec` ✅ (#3701: 25 requisitos / 31 escenarios en `mail-inbox-list`, `mail-record-contract`, `mail-query-limits`, `capability-advertisement`). `design` en curso.
- 2026-08-26 · 46 `design` ✅ (#3702: puerto segregado `InboxMailProviderPort` ratificado como refinamiento de A3; tabla `_OUTLOOK_MAIL_READS` que impide proyecciones divergentes); validador PASS_WITH_NOTES (2 ALTO → tareas: prueba de rechazo Gmail y aserción `test_application.py:207`); planificación comprometida en Connect (`1620c98`); `tasks` ✅ (#3704, `99551d7`: 79 tareas / 3 rebanadas PR1 Graph → PR2 navegador → PR3 enrutamiento y docs; riesgo Medium; «Decision needed before apply: No»); `apply` de PR1 en curso en `feat/46-pr1-graph` (intento `pr1-bandeja-por-graph-y-campos-de-registro`).
- 2026-08-26 · 42 validador de diseño PASS_WITH_NOTES (4 brechas de pruebas → tareas obligatorias); planificación comprometida (`0c8351c`); `tasks` ✅ (#3700, `2bcc995`): 7 fases / 70 tareas / 4 rebanadas encadenadas (1 → 2a → 2b → 3, ≈2170 líneas; «Chained PRs recommended: Yes», «Decision needed before apply: No»). Ledger nativo: intento `rebanada-1-compuerta-seed-demo-data` reclamado (`proceed`).
- 2026-08-26 · 42 **rebanada 1 ✅** (`29f8fb3` en `feat/42-s1-compuerta-seed`, integrada al tracker por ff → `6a50e66`): `SEED_DEMO_DATA: bool = False` en `Settings`, compuerta en `_ensure_demo_members`/`_seed_demo_workitems` leída en tiempo de llamada, `docker-compose.yml`/`env.example`; 6 pruebas TDD (`tests/test_seed_demo_flag.py`) incluida la de reinicio sin resurrección de miembros; suite 1373 ok / 3 preexistentes; `ruff`/`mypy` limpios; intento cerrado `passed` (evidencia `sha256:f9694bf0…`). Rebanada 2a en curso en `feat/42-s2a-purga` (intento `rebanada-2a-ruta-de-purga`).
