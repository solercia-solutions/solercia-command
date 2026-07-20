# Guía de prueba — rama `preview` (OLA 2 estabilizada)

Esta guía te permite probar todo lo entregado en la OLA 2 sobre la rama `preview`,
sin tocar `main`. Indica qué se puede probar sin credenciales externas (todo lo
mockeable) y qué requiere servicios o credenciales reales.

## 1. Arranque del entorno

```bash
git switch preview
docker compose up -d --build
```

| Servicio | URL |
|----------|-----|
| Frontend | http://localhost:4200 |
| API + Swagger | http://localhost:8000/docs |
| Postgres | localhost:5432 |
| Redis | localhost:6379 |

El seed corre automáticamente al arrancar el backend (idempotente): organización
"Solercia", usuarios, menús, roles, 3 proyectos demo ("Plataforma Web" Scrum,
"Soporte Técnico" Kanban, "Mejoras Internas" Planner), un sprint y ~12 tareas.

> Nota: si el puerto 8000 está ocupado por otro contenedor (por ejemplo `boki-ai`),
> deténlo primero: `docker stop boki-ai`.

## 2. Credenciales de prueba

| Usuario | Contraseña | Rol |
|---------|-----------|-----|
| admin@solercia.com | `Admin123*` | Administrador |
| ana@solercia.com | `Demo123*` | Líder (manager) + colaborador |
| carlos@solercia.com | `Demo123*` | Colaborador |
| diana@solercia.com | `Demo123*` | Colaborador |

Para las pruebas por API, obtén un token y úsalo como Bearer:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@solercia.com","password":"Admin123*"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")
```

También puedes usar Swagger (http://localhost:8000/docs → botón "Authorize").

## 3. Qué probar por cada ítem de la OLA

### 3.1 Login local + SSO (cambio 20)

**Sin credenciales externas (UI):**
- Ingresa en http://localhost:4200 con admin@solercia.com / `Admin123*` → redirige a `/projects`.
- Verifica el logout y el ingreso con un usuario demo (menú reducido según rol).
- El botón "Ingresar con SSO" está en el login. Sin Keycloak configurado responde
  un 404 inerte (diseño anti-enumeración: la respuesta es idéntica si el SSO está
  apagado o mal configurado).

**Requiere servicio externo real:** el flujo SSO completo necesita un Keycloak
accesible y estas variables en el backend: `SSO_ENABLED=true`,
`OIDC_KEYCLOAK_ISSUER`, `OIDC_KEYCLOAK_CLIENT_ID`, `OIDC_KEYCLOAK_CLIENT_SECRET`,
`OIDC_KEYCLOAK_REDIRECT_URI`. docker-compose no incluye Keycloak.

### 3.2 Jerarquía de proyectos y árbol visual (cambios 21 y 24)

**Sin credenciales externas (UI + API):**
1. En la UI, entra a **Jerarquía** (menú principal) → árbol de proyectos con
   roll-up por nodo (tareas completadas/total, porcentaje y barra de progreso),
   estados de carga/vacío/error y soporte de teclado (flechas, Enter/Espacio).
2. Crea un subproyecto para ver el árbol anidado (como admin):
   ```bash
   # ID del padre: tómalo de GET /api/v1/projects
   curl -s -X POST http://localhost:8000/api/v1/projects \
     -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"name":"Subproyecto de prueba","methodology":"planner","parent_project_id":"<ID_PADRE>"}'
   ```
3. Recarga `/hierarchy` → el padre muestra chevron; expande y colapsa el nodo.
4. Prueba el reparenting: `PATCH /api/v1/projects/{id}/parent` con
   `{"parent_project_id": null}` (a raíz) o un UUID. Rechazos esperados:
   ciclo (409), auto-padre (422), profundidad > 5 (422).
5. Responsive: reduce la ventana a ancho móvil — el menú colapsa a hamburguesa
   y el árbol no se desborda.

### 3.3 Plantillas organizacionales (cambio 23)

**Sin credenciales externas (API, como admin o manager):**
```bash
# 1. Lista las 5 plantillas del sistema (Jefe OAP-TI, Jefe de Planeación,
#    Jefe de Tecnología, Gerente de Gestión Corporativa, Equipo de desarrollo)
curl -s http://localhost:8000/api/v1/org-role-templates -H "Authorization: Bearer $TOKEN"

# 2. Instancia una (usa el id devuelto arriba; lead = uuid de un miembro activo,
#    por ejemplo el de ana@solercia.com desde GET /api/v1/users)
curl -s -X POST http://localhost:8000/api/v1/org-role-templates/<TEMPLATE_ID>/instantiate \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"lead_user_id":"<USER_ID>"}'
```
Resultado: se genera el árbol de proyectos de la plantilla (visible en
`/projects` y en `/hierarchy`), con el responsable asignado. Es idempotente:
volver a instanciar reconcilia, no duplica. Errores esperados: 422
`lead_not_member`, 403 si lo intenta un colaborador.

### 3.4 Conectores con adaptador fake (cambios 14-19)

No hay página de conectores en el frontend: **se prueba por API/Swagger**.

**Sin credenciales externas — adaptador `fake` (OAuth simulado, datos en memoria):**
```bash
# 1. Crear el conector fake
CONN_ID=$(curl -s -X POST http://localhost:8000/api/v1/connectors \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"provider":"fake","credential_kind":"oauth"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['id'])")

# 2. Iniciar el "OAuth" (NO seguir el redirect; copiar el state del Location)
curl -si "http://localhost:8000/api/v1/connectors/$CONN_ID/authorize" \
  -H "Authorization: Bearer $TOKEN" | grep -i '^location'

# 3. Completar el callback con el state copiado (el code puede ser cualquiera)
curl -s "http://localhost:8000/api/v1/connectors/oauth/callback?code=x&state=<STATE>"
# → {"message":"Cuenta conectada."}
```
Con eso queda una cuenta conectada con datos simulados de correo, calendario,
tareas, notas y tickets — el insumo del clasificador (3.5).

**Jira por archivo (cambio 18) — sin credenciales:** crea un conector
`{"provider":"jira","credential_kind":"api_token"}` y sube un CSV/XLSX a
`POST /api/v1/connectors/{id}/jira/import-file` (multipart, campo `file`,
máx. 10 MB) → devuelve los issues normalizados sin persistir tareas.

**Requieren credenciales o servicios reales:**
- Microsoft 365 (15) y Google (16): OAuth real (client_id/secret + consentimiento).
- GLPI (17): instancia GLPI real en la allowlist (por defecto
  `http://localhost:8080/glpi/apirest.php`) + app_token y user_token. La
  homologación de usuarios y la cola de no homologados (`/api/v1/glpi-sync/*`)
  dependen de ese conector. Su red de persistencia quedó cubierta por tests
  (`backend/tests/test_glpi_sync_persistence.py`).
- Jira por API REST: email + api_token de Jira Cloud (`*.atlassian.net`).
- MCP (19): puedes registrar el conector apuntando a `http://localhost:<puerto>`
  sin validación, pero listar recursos/herramientas exige un servidor MCP
  (Streamable HTTP) corriendo local. No se incluye uno de demo.

### 3.5 Clasificador de insumos (cambio 22)

**Sin credenciales externas (API), continuando desde 3.4:**
```bash
# 1. (Opcional) Regla tema→respondiente: todo lo que venga del fake se convierte
#    en tarea asignada a Ana
curl -s -X POST http://localhost:8000/api/v1/intake/rules \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"name":"Todo lo del fake","criteria":[{"field":"source_provider","operator":"equals","value":"fake"}],"convert_to_task":true,"assignee_id":"<USER_ID_ANA>","rule_order":0}'

# 2. Disparar la ingesta (lee las cuentas conectadas de la organización)
curl -s -X POST http://localhost:8000/api/v1/intake/pull -H "Authorization: Bearer $TOKEN"

# 3. Ver los insumos y la bitácora
curl -s "http://localhost:8000/api/v1/intake/items?status=pending" -H "Authorization: Bearer $TOKEN"
curl -s http://localhost:8000/api/v1/intake/runs -H "Authorization: Bearer $TOKEN"

# 4. Convertir manualmente un insumo pendiente en tarea
curl -s -X POST http://localhost:8000/api/v1/intake/items/<ITEM_ID>/convert \
  -H "Authorization: Bearer $TOKEN"
```
Qué verificar: los ítems clasificados por regla generan tareas automáticamente;
los pendientes se convierten a mano; la primera conversión sin proyecto destino
crea el proyecto por defecto **"Tareas Outlook"** (visible luego en `/projects`
y `/hierarchy`); un segundo `pull` no duplica ítems ya importados.

### 3.6 Auditoría de componentes UI (cambio 13)

Transversal: toda la UI usa `@solercia/ui` ≥ 0.3.0. Se verifica navegando —
tema claro/oscuro, componentes consistentes en login, proyectos, tablero,
jerarquía y administración.

## 4. Estado de la suite y verificaciones

- Backend: **1096 pruebas, 0 fallas** (las 13 legacy que "siempre fallaban"
  fueron resueltas: 9 reescritas in-process y 4 eliminadas por redundantes, con
  su cobertura preservada en otras pruebas).
- Red de regresión GLPI: 5 tests de persistencia real con dos sesiones
  independientes (validados por mutación).
- Frontend: build (AOT/tsc) y ESLint en verde.
- QA visual de `/hierarchy` con Playwright: PASS (desktop y móvil).

Comando para reproducir la suite backend:
```bash
docker compose up -d postgres redis
cd backend && source .venv/bin/activate && \
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test pytest tests/ -q
```

## 5. Limitaciones conocidas en esta preview

- Conectores, clasificador de insumos, plantillas organizacionales e import de
  Jira no tienen pantalla en el frontend: se prueban por Swagger/curl (la UI de
  esas secciones es alcance post-MVP).
- El flujo SSO end-to-end requiere Keycloak externo (sección 3.1).
- En bases de datos sembradas antes de esta rama, "Jerarquía" y "Vista de jefe"
  pueden compartir el mismo orden en el menú (el seed no reordena filas
  existentes); cosmético, listado como pendiente.
