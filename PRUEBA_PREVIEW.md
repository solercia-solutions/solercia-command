# Guía de prueba — rama `preview` (OLA 2 + ola de UX + OLA 4 parcial)

Esta guía te permite probar todo lo entregado sobre la rama `preview`, sin tocar
`main`. Indica qué se puede probar sin credenciales externas (todo lo mockeable)
y qué requiere servicios o credenciales reales.

> **Novedades de la OLA 4** (cambios 25 a 32, sección 3): multi-empresa con selector
> de empresa activa, calendario laboral configurable por equipo, plantillas que ya
> no duplican al reaplicarse, sprints en borrador con autonombre, backlog estilo Jira
> con secciones colapsables, arrastrar y soltar entre sprints, y subtareas indentadas.
>
> **Novedades de la ola de UX** (sección 4): sidebar colapsable, edición y vinculación
> de proyectos desde la UI, onboarding de Equipos, sección de Conexiones, detalle de
> tareas en drawer, cronograma estilo Jira, estimación con puntos + tiempo, y
> personalización de apariencia por organización.
>
> La OLA 4 se detuvo en el cambio 32 por presupuesto. Lo que falta (cambios 33 a 41)
> está planificado y documentado en `openspec/OLA_4_PENDIENTE.md`.

## 1. Arranque del entorno

```bash
git switch preview
./gestion.sh on        # levanta Docker + frontend en el host + túnel
```

| Servicio | URL |
|----------|-----|
| Frontend | http://localhost:4242 |
| API + Swagger | http://localhost:8081/docs |
| Postgres | localhost:5432 |
| Redis | localhost:6379 |

Otros comandos: `./gestion.sh status` (estado y URL del túnel), `./gestion.sh logs`,
`./gestion.sh rebuild` (tras cambiar código del backend), `./gestion.sh off`.

El seed corre automáticamente al arrancar el backend (idempotente): organización
"Solercia", usuarios, menús, roles, 3 proyectos demo ("Plataforma Web" Scrum,
"Soporte Técnico" Kanban, "Mejoras Internas" Planner), un sprint y ~12 tareas.

> Nota: el backend publica el 8081 en el host (internamente sigue en 8000) porque el
> 8080 lo ocupa `traefik-idt`. Si algo no responde, revisa `./gestion.sh status`.

## 2. Credenciales de prueba

| Usuario | Contraseña | Rol |
|---------|-----------|-----|
| admin@solercia.com | `Admin123*` | Administrador |
| ana@solercia.com | `Demo123*` | Líder (manager) + colaborador |
| carlos@solercia.com | `Demo123*` | Colaborador |
| diana@solercia.com | `Demo123*` | Colaborador |

Para las pruebas por API, obtén un token y úsalo como Bearer:

```bash
TOKEN=$(curl -s -X POST http://localhost:8081/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@solercia.com","password":"Admin123*"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
```

> El login devuelve `access_token` en la raíz de la respuesta, no dentro de `data`
> (verificado contra el entorno real). Endpoints útiles para tantear la OLA 4:
> `GET /api/v1/organizations/mine`, `GET /api/v1/organizations/me/work-calendar`,
> `GET /api/v1/projects?project_kind=area`.

También puedes usar Swagger (http://localhost:8081/docs → botón "Authorize").

## 3. OLA 4 — lo nuevo (cambios 25 a 32)

Todo se prueba sin credenciales externas. Ingresa en http://localhost:4242 con
`admin@solercia.com` / `Admin123*`.

### 3.1 Multi-empresa y selector de empresa activa (cambios 25 y 26)

1. En **Administración → Empresas**, crea una segunda empresa (quedas admin de ella
   automáticamente). Agrega a `ana@solercia.com` como miembro con rol distinto.
2. Usa el **selector de empresa** del encabezado para cambiar entre las dos. Al
   cambiar, la aplicación recarga y todo el contexto cambia con ella: proyectos,
   tareas, menús y tema.
3. Comprueba el aislamiento: con la empresa nueva activa, no debe verse ni un solo
   proyecto o tarea de "Solercia". Si intentas abrir por URL el id de un proyecto de
   la otra empresa, debe responder "no encontrado", nunca mostrarlo.
4. Prueba la protección: intenta quitarle el rol de administrador al único admin de
   una empresa. Debe rechazarlo con un mensaje claro.

> Este bloque está respaldado por 52 pruebas automáticas de fuga entre empresas que
> recorren los 25 módulos del backend. La auditoría no encontró ninguna fuga real.

### 3.2 Calendario laboral por equipo (cambio 28)

1. En la empresa, define la jornada: horas por día y días laborales (por defecto 8h,
   lunes a viernes).
2. En un **proyecto raíz** (un equipo), define un override — por ejemplo, soporte que
   trabaja sábados. Los proyectos hijos lo heredan.
3. Consulta el calendario resuelto de un proyecto hijo: debe indicar de dónde viene el
   valor (`team`, `organization` o `default`).
4. Intenta poner un override en un proyecto que **no** es raíz: debe rechazarlo con un
   mensaje claro.

### 3.3 Plantillas que ya no duplican (cambio 27)

Este era un bug confirmado en la prueba anterior.

1. Instancia una plantilla organizacional y anota los proyectos creados.
2. Vuelve a instanciar **la misma plantilla con otro responsable**. Antes esto creaba
   un árbol duplicado completo; ahora debe reconciliar: el mismo árbol, con el
   responsable actualizado.
3. Verifica que los nodos quedan marcados por tipo: las áreas (contenedores del
   organigrama) se distinguen de los proyectos de trabajo real.
4. Renombra un proyecto creado desde plantilla y vuelve a instanciar: el rename debe
   respetarse, porque la reconciliación se ancla al registro interno, no al nombre.

### 3.4 Sprints en borrador (cambio 29)

1. En un proyecto Scrum, crea un sprint **solo con nombre**. Queda en estado Borrador,
   sin fechas.
2. Fíjate en el nombre sugerido: toma el del sprint anterior y le sube el consecutivo
   (`PANDORA 2026-1` → `PANDORA 2026-2`). Sin sprint previo usa la clave del proyecto.
3. Intenta iniciarlo sin fechas: el botón está deshabilitado y explica por qué.
4. Añade fechas y ahora sí inícialo.

### 3.5 Backlog estilo Jira con arrastrar y soltar (cambios 30, 31 y 32)

1. Entra al **Backlog** de un proyecto Scrum. Los sprints aparecen arriba como
   secciones colapsables, cada una con su nombre, fechas, conteo de historias, suma de
   horas y la acción que corresponde a su estado.
2. Colapsa y expande secciones; recarga la página: el estado del colapso se conserva.
3. **Arrastra** una historia del backlog a un sprint y entre sprints no iniciados. La
   tarjeta se mueve de inmediato; si algo falla, vuelve a su lugar con un aviso.
4. Prueba el camino accesible: el menú **"Mover a…"** hace lo mismo sin ratón.
5. Verifica las reglas: no debes poder soltar nada en un sprint cerrado.
6. Las **subtareas** aparecen indentadas bajo su padre, con su clave, estado,
   estimación y avatar.
7. Filtra por una persona que tenga una subtarea cuyo padre está asignado a otra: la
   subtarea **debe** aparecer igual, con el padre atenuado como contexto. Nada se
   oculta por su posición en la jerarquía.

## 4. Ola de UX (mejoras sobre el feedback) — todo sin credenciales externas

Ingresa en http://localhost:4242 con `admin@solercia.com` / `Admin123*`.

1. **Sidebar izquierdo colapsable**: el menú ahora es un sidebar a la izquierda
   (estilo boki-front). El botón de la esquina lo colapsa a solo iconos y el
   estado se recuerda al recargar. En móvil (ventana angosta) el sidebar se
   oculta y aparece una barra inferior de navegación.
2. **Editar y vincular proyectos**: en **Proyectos**, cada tarjeta tiene un botón
   de lápiz que abre un panel lateral (drawer) para cambiar nombre, descripción y
   código, y para asignar un **proyecto padre**. El árbol de **Jerarquía** refleja
   el cambio.
3. **Onboarding de Equipos**: menú **Equipos** → elige una plantilla (p. ej.
   "Jefe de Tecnología"), asígnale un líder (p. ej. Ana Torres) y genera el árbol
   de proyectos; queda visible en **Proyectos** y **Jerarquía**.
4. **Conexiones**: menú **Conexiones** → crea un conector **Demo (fake)** y pulsa
   "Conectar cuenta" (OAuth simulado, sin credenciales). También puedes crear un
   conector **Jira** y subir un CSV/XLSX para ver el import con vista previa.
   Outlook/Google/GLPI/Jira-API requieren credenciales reales (ver sección 4).
5. **Detalle de tarea en drawer**: en un proyecto, abre la vista **cuadrícula** o
   **cronograma** y haz clic en una tarea: el detalle se abre en un panel lateral
   (sin salir de la vista), con edición de estado, responsable, sprint y estimación.
   El select "Mover a sprint" del backlog se retiró; la reasignación se hace desde
   el drawer.
6. **Cronograma estilo Jira**: pestaña **Cronograma** de un proyecto Scrum
   ("Plataforma Web") → encabezado con días, banda de sprints, épicas agrupando sus
   historias y cada tarea como barra entre su fecha de inicio y su fecha límite.
7. **Estimación tipo Jira**: al crear/editar una tarea en Scrum hay **dos campos**:
   "Puntos de historia" (entero) y "Estimación original" en formato `1w 2d 4h`
   (semanas/días/horas, combinables). El formulario pide fecha de inicio y fecha
   límite.
8. **Apariencia por organización** (solo admin): menú **Administración →
   Apariencia** → cambia el color primario y verás la vista previa en vivo;
   Guardar lo persiste para toda la organización (recarga y sigue aplicado);
   Restablecer vuelve al tema por defecto. El interruptor claro/oscuro sigue
   funcionando encima del tema del tenant.

## 5. Qué probar por cada ítem de la OLA 2

### 3.1 Login local + SSO (cambio 20)

**Sin credenciales externas (UI):**
- Ingresa en http://localhost:4242 con admin@solercia.com / `Admin123*` → redirige a `/projects`.
- Verifica el logout y el ingreso con un usuario demo (menú reducido según rol).
- El botón "Ingresar con SSO" está en el login. Sin Keycloak configurado responde
  un 404 inerte (diseño anti-enumeración: la respuesta es idéntica si el SSO está
  apagado o mal configurado).

**Requiere servicio externo real:** el flujo SSO completo necesita un Keycloak
accesible y estas variables en el backend: `SSO_ENABLED=true`,
`OIDC_KEYCLOAK_ISSUER`, `OIDC_KEYCLOAK_CLIENT_ID`, `OIDC_KEYCLOAK_CLIENT_SECRET`,
`OIDC_KEYCLOAK_REDIRECT_URI`, y `SSO_POST_LOGIN_REDIRECT=http://localhost:4242/auth/callback`
(su valor por defecto apunta al puerto 4200). docker-compose no incluye Keycloak.

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

## 6. Estado de la suite y verificaciones

- Backend: **1352 pruebas, 0 fallas** (1096 al cerrar la OLA 2 → 1158 tras la ola de
  UX → 1352 al cerrar el cambio 32 de la OLA 4).
- Cada uno de los ocho cambios de la OLA 4 pasó por verificación independiente antes
  de integrarse. Dos fueron devueltos por hallazgos críticos y solo se integraron tras
  corregirlos: el cambio 27 (una promesa de la especificación sin implementar) y el 32
  (desincronización de índices de arrastre que podía guardar el orden equivocado).
- Migraciones `0021` a `0024` verificadas con ciclo real subir → bajar → subir.
- Red de regresión GLPI: 5 tests de persistencia real con dos sesiones
  independientes (validados por mutación).
- Frontend: build (AOT/tsc) y ESLint en verde.
- QA visual de `/hierarchy` con Playwright: PASS (desktop y móvil).

Comando para reproducir la suite backend:
```bash
cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/solercia_test \
  .venv/bin/python -m pytest -q
```

Build del frontend (requiere Node 22.22.3; el del sistema no alcanza para Angular CLI):
```bash
source ~/.nvm/nvm.sh && nvm use 22.22.3 && cd frontend && npm run build
```

## 7. Limitaciones conocidas en esta preview

- Conectores, clasificador de insumos, plantillas organizacionales e import de
  Jira no tienen pantalla en el frontend: se prueban por Swagger/curl (la UI de
  esas secciones es alcance post-MVP).
- El flujo SSO end-to-end requiere Keycloak externo (sección 5.1).
- En bases de datos sembradas antes de esta rama, "Jerarquía" y "Vista de jefe"
  pueden compartir el mismo orden en el menú (el seed no reordena filas
  existentes); cosmético, listado como pendiente.

### Específicas de la OLA 4

- **El frontend no tiene runner de pruebas** (`package.json` solo trae `build` y
  `lint`). Todo el comportamiento de UI de los cambios 28 a 32 se verificó por lectura
  de código y compilación AOT, no por pruebas automáticas. Con el arrastrar y soltar y
  la jerarquía de subtareas ya en juego, montar un runner es la mejora pendiente de
  mayor retorno: el bug crítico del cambio 32 existió precisamente porque nada lo podía
  atrapar automáticamente.
- **Dos pruebas manuales del cambio 26 quedaron sin ejecutar** por requerir a alguien
  frente a la pantalla: el selector de empresa cambiando en vivo y el CRUD de miembros.
- **La migración `0023`** (limpieza de árboles OAP-TI duplicados) se probó con datos
  sintéticos. Al levantar el entorno se aplica sobre la base real: vale la pena revisar
  el resultado con los datos de verdad.
- **Lo que aún no existe**: búsqueda y filtros en el backlog, estimación normalizada
  w/d/h, avance esperado vs. real, árbol de proyectos como vista principal, cambio de
  metodología, OAuth de Microsoft y Google reparado, panel de acciones de conectores e
  importación desde Jira. Todo eso son los cambios 33 a 41, planificados en detalle en
  `openspec/OLA_4_PENDIENTE.md`.
- **La dependencia `@solercia/ui`** sigue apuntando al tarball local. Hay una rama
  `chore/solercia-ui-npm` con la migración al paquete publicado 0.3.1 (que corrige
  menús flotantes y desbordamiento de selects), pendiente de tu decisión.
