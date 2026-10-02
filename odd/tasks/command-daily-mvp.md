# Command — ODD

## Autoridad y límites
Orden autorizado: organizaciones/aislamiento → importación → expedientes → diario/Mac → IA local/BYOK/agentes → Jira. Sin promesa de cierre total. Historia: [P1](../../docs/plans/command-personal-daily-mvp.md), [planes 2026](../../docs/plans/command-institutional-plans-2026.md), [multiempresa](../../docs/plans/command-multi-company-work-management.md). SDD histórico separado de ODD; autoridad/estado intactos.

Escritura delegada única; preservar staged/untracked. TDD backend estricto (`openspec/config.yaml`); excepción caracterización PG sin RED inventado. Frontend: build/browser sintético. Checkpoint documental sin pruebas funcionales. Evaluación nativa indisponible, no aprobación.

Sin copia/carga real, correo, migración operativa, proveedor real ni commits. Originales intactos, flags false; sin arranque implícito, cambios intake ni fusión/eliminación automática. S3/local sin elegir.

## Tareas
- [x] T01 Contexto y tres planes reconciliados; delta guardado (Engram 5434); espejo completo anterior 5414 desactualizado, actualización pendiente del padre.
- [x] T02 Barrera SMTP antes de mensaje/red; no aprobación de envíos.
- [x] T03 Verificación independiente SMTP: 20 pruebas históricas.
- [x] T04 Email excluido antes de claim; filas/reintentos intactos, otros canales funcionan (34).
- [x] T05 Parser/manifiesto CSV/XLSX puro, límites y corrección XML namespaces/jerarquía (94).
- [x] T05b Inventario: 830 archivos/198 directorios/645357465 bytes; CSV 177626 bytes, 11 campos, 185 filas = 180 candidatas + 5 fechas prosa/sentinela sin resolver. Sin copia/BD; no convertir a null ni excluir automáticamente.
- [x] T05c Runner cancelable/terminable, ownership/cuarentena; no sandbox OS/RSS/CPU ni admisión distribuida.
- [x] T05d Preview API autenticada, streaming limitado/no-store, apagada por defecto (149).
- [x] T05e Preview UI build/browser: errores/conteos/texto seguro/cancelación/tardías/organización/teclado/390 px; no crea tareas.
- [x] T05g Creación opt-in transaccional flush-only; legacy conserva commit (161).
- [x] G01 Generales: 7 estados, guards, is_system false, migración 0026 tras 0025 (195).
- [x] G02 Provisioning caller-owned, lock antes de lookup incluidos inactivos, conflictos sin reparación/takeover, parent explícito, flush-only (222).
- [x] G03 PG histórico: 1 migración + 9 provisioning/rollback/aislamiento/concurrencia; instancia retirada.
- [x] G04 Nueva organización/admin/Generales atómicos con autobegin: 236 offline + 13 PG (1 migración/12 provisioning). Requiere 0026 futura; sin HTTP vivo/startup/backfill.
- [x] T05h Hechos confiables de revisión: 277 offline + 1 PG; no confirma/persiste lote.
- [x] T05i Opciones/review API: 378 offline históricos; brecha SQL cerrada con 6 PG actuales, consultas alcanzadas.
- [x] T05j Borrador UI verificado: ngModel DOM/modelo corregido; destino canónico, responsable/fecha/exclusión, paginación/cancelación.
- [ ] T05f Confirmación/persistencia implementada como CLI (2026-10-01), pendiente de aplicación real por el padre. **Identidad de negocio decidida:** `(organización, source="checklist_xlsx", external_key="CHECKLIST_TAREAS:<ID>")`; el ID T-NN del checklist es estable entre versiones; CSV y XLSX son la misma fuente; nunca título ni hash. Proyecto solo por `Categoría` (segmento «Pandora» → PAN; primer segmento de seguridad → SGSI; resto → GENERALES y listado); estado sin columna en PAN → GENERALES y listado. Fechas solo explícitas (12:00 Bogotá); «Sin fecha» en prosa (5) y centinelas quedan nulas y listadas. Re-ejecución: sin cambios no escribe; diferencias se informan y solo se escriben con `--update-existing`; ancla eliminada no se resucita; no mueve de proyecto. Código: `backend/app/modules/task_import/checklist_{import,apply}.py`, `backend/scripts/import_sdm_tasks.py`; seguimiento de planes: `backend/app/modules/plans/importers/followup{,_apply}.py`, `backend/scripts/feed_plan_followup.py`. Recibos: 40 offline + 4 PG propios (55521); ensayo en clon propio (55520): 199 tareas creadas, re-aplicación 199 sin cambios; 4 reportes PAI periodo II + 49 enlaces, re-aplicación 0 escrituras. Retención/almacenamiento de archivos siguen sin elegir (solo se registra la carpeta relativa en la descripción).
- [ ] G05 Organizaciones existentes/backfill/startup y aislamiento integral: definir alcance antes de mutar.
- [ ] T06 Expedientes/auditoría universal: representación CREATE sin especificar y brecha transaccional; justificación/procedencia IA y versiones/retornos incompletos. Reorder ya cumple contrato: `order` no se audita deliberadamente (spec tasks, líneas 202–220); cambio de sprint sí.
- [x] T06a PATCH 16 campos: 414 offline históricos independientes.
- [x] T06b Historial de movimiento: 426 offline históricos independientes.
- [x] T06c Historial soft delete: 441 offline históricos independientes; no auditoría universal.
- [x] T06d Ordenamiento de actividad: alias público `changed_at`, 22 pruebas independientes; no cierra T06.
- [ ] T07 Operación diaria/Mac: integración real, alertas, ciclo de servicios, recuperación/respaldo/restauración pendientes.
- [x] T07a Backend diario: dominio 19, servicio/adaptador 99, API 271 históricos; PG previo con fixtures completos. Claves actuales: 1 PG verificado, consultas alcanzadas.
- [x] T07b UI diaria verificada: política explícita, Bogotá sugerida/Honolulu calendario, enlaces/advertencias/grupos/cancelación/organización/logout/390 px. Fecha/zona personal no elegida.
- [x] T07c Mac: harness fake/sintaxis 3 scripts pasaron; liveness/abrir instancia existente, no LaunchAgent ni inicio.
- [x] T07d `STARTUP_PROFILE=local_restricted`: sin seed/scheduler; default intacto, cifrado y comprobaciones DB conservados. Cleanup preserva errores originales tras corrección confirmada: 24 pruebas independientes/0.33 s. Espera DB acotada por intentos, no tiempo total; cancelación inyectada, no recursos reales.
- [x] T07e `scripts/local-runtime.py` + `scripts/tests/test_local_runtime.py`: plan pasivo por defecto, plist a stdout y `run` explícito para futuro desarrollo Angular local; loopback fijo, `LOCAL_RUNTIME_DATABASE_URL`/`LOCAL_RUNTIME_REDIS_URL` preparados sin imprimir URLs. Lock, handles de hijos propios y deadline de readiness: 19 pruebas independientes. Solo hijos directos; descendientes Angular no probados. Plist requiere entorno futuro; no empaquetado productivo ni cierre T07.
- [ ] T08 BYOK/local/agentes y salida autorizada: no cumplimiento ni aprobación de correo implementados.
- [x] T08a [Privacidad](../../docs/plans/command-ai-privacy-controls.md): 3 PDF contextuales y secciones DOCX verificadas; borrador pendiente CIGD, anexo distrital/GT-GU-4 faltantes. No dictamen jurídico.
- [x] T08b Barrera temporal real: 38 + 5 health aisladas históricas. Fake/configuración pasiva funcionan; toda IA real bloqueada incluido HTTP local. Restaurar tests de transporte retirados y auditar bypass de helpers privados antes de habilitar.
- [ ] T09 Jira/piloto/paridad por acordar; Bitbucket/PR/CI separados, renovación visual diferida.

## Recibos actuales y seguridad
**Bloqueo del runner cerrado:** verificador independiente, runner exacto completo de **35 selecciones: 607 passed, 1 warning, 11.24 s, exit 0**; los 44 cuerpos async nuevos sí se ejecutaron. Corrección del escritor limitada a 12 decoradores `pytest.mark.asyncio` (4 actividad, 8 lifespan); RED 44 failed/2 passed → GREEN 46 passed. Fallo combinado histórico conservado: 44 failed, 563 passed, 1 warning, 11.29 s, exit 1; faltaban marcadores, el aislado usaba `asyncio_mode=auto` y el combinado no, por lo que esos cuerpos no se ejecutaban; no eran 44 regresiones funcionales demostradas. Separadamente: supervisor **19 passed/0.030 s**, harness fake launcher y 3 comprobaciones bash de sintaxis pasaron. No acredita independencia del orden, PG nuevo ni arranque real; no cierra otros pendientes.
Consolidado offline anterior, sustituido por el recibo actual sin borrar su historia: **33 selecciones, 561 passed, 1 warning, 11.41 s, exit real 0**, sin reintento de subconjunto. Shell: harness fake y 3 comprobaciones bash individuales pasaron. PG separado: **opciones 6 passed/2.47 s; diario claves 1 passed/0.58 s**. 7 casos PG de dos alcances; no sumar con offline/históricos ni afirmar suite completa/producción. Recibos del padre, no ejecutados aquí. Cortes aislados previos: 22/24/19, sin sumarlos entre sí ni al histórico. PG histórico no repetido. Sin arranque real, instalación, registro plist ni migración DB. Comprobación independiente no equivale a aprobación nativa.

Todos los contenedores propios retirados; último CID `98075ae62042`, identidad exacta y ausencia comprobadas por el padre. PG futuro propio/desechable/localhost/sintético, sin `.env`/bases existentes; lifecycle del padre. Baseline y pipeline Alembic `env.py` no ejecutados. Logs temporales preservados, salidas acotadas ≤6000 caracteres.

## Incidente y continuidad
`backend/tests/test_dashboard_daily_service.py` untracked fue vaciado y restaurado EXACTO: 8180 bytes/19 tests, SHA-256 `dad8236363eb288993c440928b837d4498c9cfbb27e6e79788b481805783a6de`; preservado después, según recibo. Restauración previa.

## Migración 0026 — aplicada (2026-09-30)
Prueba sobre copia desechable del volumen recuperado (`solercia-pg-mig0026-20260930125402`, red `none`, loopback): `alembic upgrade 0026` con código actual montado RO; huella por tabla (conteo + md5 de contenido, sin `is_system`) idéntica en las 45 tablas salvo `alembic_version`; columna `is_system boolean NOT NULL DEFAULT false`, constraint validado; rechaza marcar proyecto no GENERALES y acepta forma GENERALES (ambos con rollback). `downgrade 0025` → huella idéntica a la previa; `upgrade 0026` otra vez → idéntica. Original: se arrancó SOLO `gestion_proyectos-postgres-1` (recuperación automática normal, redo sin errores), huella previa idéntica al clon, `upgrade 0026` aplicado, huella posterior idéntica al clon migrado. Backend/redis/frontend originales siguen detenidos; PG original queda corriendo en 127.0.0.1:5434. Inventario: 1 organización (Solercia), 1 usuario admin, proyectos PAN/SDM/SEG, **0 tareas**, 82 ítems de intake, 2 cuentas conectadas. No existen tenants IDARTES ni SDMujer propios.

Siguiente: protocolo y autorización de despliegue seguro/restauración; resolver retención/identidad/almacenamiento/cinco fechas antes de T05f; definir representación CREATE y cerrar brecha transaccional antes de T06 (reorder ya cumple contrato); elegir política diaria y validar integración/jornada solo con autorización. No sustituir decisiones con scaffolding/pruebas repetidas. Gobernanza IA pendiente; pruebas verdes no habilitan flags/proveedores.

Aprendizaje: prueba offline/PG y operación real no equivalen; barrera no es autorización, hash no es identidad ni adjunto es cierre. **Delta guardado en Engram 5434; espejo completo 5414 desactualizado, actualización pendiente del padre:** `odd/command-daily-mvp/tasks`.
