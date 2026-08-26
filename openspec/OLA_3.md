# Briefing autónomo — Cierre y estabilización de la OLA 2 (Solercia Project Manager)

## Rol y objetivo
Sos el orquestador de este trabajo. COORDINÁS y delegás en subagentes; no ejecutás todo
en un solo hilo. Objetivo único de esta sesión: dejar la OLA 2 lista para que un humano la
PRUEBE en una rama `preview` con el entorno levantado, sin tocar `main`. Trabajás de forma
autónoma y no parás hasta cumplir la Definition of Done. Al terminar, entregás instrucciones
concretas de prueba.

## Contexto del repositorio
- Proyecto: `/Users/camilocalderont/Proyectos/SOLERCIA/solercia-command` (git).
- La OLA 2 completa (12 cambios SDD, 13–24) YA está implementada y archivada en la rama
  `feat/consume-solercia-ui`. Ver `openspec/OLA_2.md` (documento orquestador con la tabla de
  estado en 12/12) y `openspec/changes/archive/2026-07-1*`.
- Suite backend: 1082 pruebas en verde + 13 fallas legacy preexistentes (`test_attachments`,
  `test_comments`, `test_sprint_close`, `test_subtasks`, `test_task_key` — todas
  `httpx.LocalProtocolError` por `TEST_AUTH_TOKEN` sin setear contra servidor vivo).
- Backend: FastAPI + SQLAlchemy async + Alembic (head `0019`). Frontend: Angular 20 + `@solercia/ui`.
- Test runner backend: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -v` (venv en `backend/.venv`; postgres y redis vía `docker compose up -d postgres redis`; base `solercia_test` ya creada).
- Frontend: usar Node 22.22.3 (`source ~/.nvm/nvm.sh && nvm use 22.22.3`) antes de `npm run build`/`lint`.

## Estrategia de ramas (CLAVE — el usuario quiere PROBAR)
1. Creá la rama `preview` desde `feat/consume-solercia-ui` (que ya tiene toda la OLA 2). Esta es
   la rama de integración donde el usuario prueba TODO junto.
2. Cada bloque de trabajo nuevo va en su propia feature branch (`fix/intake-pii-encryption`,
   `chore/legacy-tests`, etc.) partiendo de `feat/consume-solercia-ui`.
3. Al cerrar cada feature branch (con su ciclo TDD + verificación), la mergeás a `preview`.
4. NO toques `main` en ninguna circunstancia. El merge a `main` es decisión posterior del usuario.
5. Commits convencionales en español, SIN atribución de IA, staging selectivo (nunca `.gitignore`,
   `.codegraph/`, `docs/PLAN_MIGRACION_SOLERCIA_UI.md`).

## Plan de trabajo (en este orden — estabilizar antes de features)

### Paso 1 — QA del árbol jerárquico (24) y validación consolidada
- Levantá el stack (`docker compose up -d`) y el frontend; verificá interactivamente (o con
  Playwright si está disponible como MCP) la vista `/hierarchy`: enlace visible en el menú,
  expandir/colapsar, roll-up por nodo, estados carga/vacío/error, responsive.
- Corré la suite backend completa sobre el estado consolidado y confirmá qu
  son las 13 legacy conocidas. Documentá el resultado.


### Paso 2 — Pruebas legacy: INVESTIGAR valor antes de decidir (el usuario
- NO las arregles a ciegas. Primero, para cada una de las 13, determiná QUÉ verifica y si ese
  comportamiento ya está cubierto por otra prueba que sí pasa.
- Decidí con criterio y justificá por prueba:
  - **Redundante u obsoleta** → eliminala (documentá qué la reemplaza).
  - **Aporta valor pero es black-box contra servidor vivo** → reescribila como test in-process
    (httpx.AsyncClient/ASGI, como el resto de la suite) para que corra sin `TEST_AUTH_TOKEN`.
  - **Válida pero genuinamente no ejecutable acá** → `xfail`/`skip` con raz
- Meta: `pytest` sale en verde limpio (o con skips justificados), sin "siempre fallan 13".
- Entregá un cuadro resumen: prueba → veredicto → acción → justificación.
- Feature branch propia → merge a `preview`.

### Paso 3 — Cerrar la red de regresión del GLPI (17)
- El verify del 17 dejó trazado que faltan tests de dos `AsyncSession` inde
  engine para sus 5 flujos de escritura (`run_sync`, `resolve_unmatched_entry`,
  `ignore_unmatched_entry`, `revoke_link`, `register_api_token_credentials`
  falta la red que atrape una regresión futura. Agregalos. Feature branch → merge a `preview`.

### Paso 4 — (Solo si el usuario lo pide después) Features post-MVP
- NO las implementes en esta sesión salvo pedido explícito: `LLMClassifier` vía `ClassifierPort`,
  scheduler APScheduler de ingesta automática, transcripciones M365 con admin consent.
- Dejalas listadas como próximos pasos en el reporte final.

## Gotchas conocidos (lecciones del maratón — no las repitas)
- El fixture de BD con SAVEPOINT de `conftest.py` ENMASCARA commits faltantes. Todo flujo que
  persiste necesita al menos un test con DOS `AsyncSession` independientes
- Los endpoints de resolución/asignación manual son donde se cuela el cruce de tenant: validá
  siempre `is_org_member` y el scoping por `organization_id`.
- Aislá por ítem en los lotes (un ítem malformado no debe tumbar el lote co
- Los `forkJoin` de Angular necesitan `timeout` por rama antes del `catchError`.
- Los cambios de navegación en el frontend deben verificar la vía de menú dirigido por BD
  (`_MENU_SEED` en `db_init.py`), no solo `fallbackLinks`.

## Definition of Done
1. Rama `preview` con la OLA 2 + los pasos 1–4 integrados, todo verificado.
2. Suite backend verde limpia (13 legacy resueltas según el paso 3); frontend build/lint/tsc verdes.
3. `docs/diagrams/er-model.md` y `c4-architecture.md` actualizados si algún paso tocó BD/arquitectura.
4. Entorno LEVANTADO y probable: `docker compose up` funcionando, seed corrido.
5. Un README de prueba corto (`PRUEBA_PREVIEW.md`) con: URL del frontend (l
   Swagger (localhost:8000/docs), credenciales de prueba (usuario admin sembrado), y una guía
   paso a paso de qué probar por cada ítem de la OLA (login local + SSO, je
   conectores con adaptador fake, árbol visual, clasificador de insumos). Aclarando qué se puede
   probar sin credenciales externas reales (todo lo mockeable) y qué requie
6. Reporte final: qué se hizo, la decisión sobre las 13 legacy con justificación, y los próximos
   pasos (features post-MVP + merge de `preview` a `main` pendiente de apro

## Autonomía
No pares a preguntar salvo un bloqueo genuino que solo el usuario pueda res
credencial externa). Delegá el trabajo pesado en subagentes; serializá los applies que tocan la
misma base de datos/migraciones. Al final, entregá el reporte y las instrucciones de prueba en el
último mensaje.





