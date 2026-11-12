# Solercia Command

Centro operativo de trabajo multi-tenant que reúne proyectos, tareas, alertas y
agenda operativa. Puede reemplazar Jira y Microsoft Planner; cada proyecto elige
su metodología al crearse (Planner, Kanban, Scrum o personalizada), y esa elección
define las columnas del tablero, los estados permitidos, los sprints y el modo de
estimación.

La pantalla **Conexiones** vincula tu buzón de Microsoft 365 a través de
**Solercia Connect**, un servicio hermano que corre en tu equipo, abre un navegador
supervisado para el inicio de sesión y lee correo, calendario y transcripciones.

## Quickstart de desarrollo local

Los pasos son deterministas: cada uno dice qué ejecutar y qué salida esperar.
Si una verificación no coincide, detente y revisa la tabla de problemas al final.

### 0. Requisitos (verifica antes de empezar)

```bash
docker info >/dev/null && echo "docker OK"            # Docker Desktop encendido
node -v                                                # v22.x (o >= 20)
ls ../solercia-connect/.venv/bin/solercia-connect-service   # Connect instalado
ls ../solercia-connect/.env.local                      # configuración de Connect
```

Si Connect no está instalado, en `../solercia-connect` ejecuta `make setup` y
`make setup-browser` (instala Playwright y Chromium). `devtunnel` es opcional:
solo sirve para abrir el frontend desde el celular.

### 1. Secretos (una sola vez)

Command y Connect comparten una clave local de API. Genera una y escríbela en los
dos archivos, que están ignorados por git:

```bash
KEY=$(openssl rand -hex 32)
# Connect
printf 'SOLERCIA_CONNECT_API_KEY=%s\nSOLERCIA_CONNECT_BROWSER_FALLBACK=true\nSOLERCIA_CONNECT_HTTP_INTERACTIVE_LOGIN=true\n' "$KEY" >> ../solercia-connect/.env.local
# Command (raíz del repo; el compose la inyecta al backend)
printf 'SOLERCIA_CONNECT_API_KEY=%s\n' "$KEY" >> .env
chmod 600 .env ../solercia-connect/.env.local
```

Si ya existían esas líneas, edítalas en lugar de duplicarlas. Verifica que las
claves coincidan y no estén vacías:

```bash
diff <(rg -o '^SOLERCIA_CONNECT_API_KEY=.*' .env) \
     <(rg -o '^SOLERCIA_CONNECT_API_KEY=.*' ../solercia-connect/.env.local) && echo "claves iguales"
```

Salida esperada: `claves iguales`.

### 2. Levantar Solercia Connect (en el host, fuera de Docker)

```bash
cd ../solercia-connect
mkdir -p .dev-logs
env -i HOME="$HOME" USER="$USER" SHELL=/bin/zsh LANG=en_US.UTF-8 \
  TMPDIR="$(getconf DARWIN_USER_TEMP_DIR)" \
  PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin \
  SOLERCIA_CONNECT_ENV_FILE="$PWD/.env.local" \
  nohup .venv/bin/solercia-connect-service > .dev-logs/service.log 2>&1 &
sleep 3
curl -s http://127.0.0.1:8765/v1/health
cd -
```

Salida esperada (lo importante es `"status":"ready"` e `"interactive_login":true`):

```json
{"schema":"solercia.connect/v1","ok":true,"operation":"health","status":"ready", ... "data":{"version":"0.4.0","bind_host":"127.0.0.1","interactive_login":true}, ...}
```

Se usa `env -i` con un `TMPDIR` explícito porque Chromium necesita un directorio
temporal que exista durante toda la vida del proceso.

### 3. Levantar Command

```bash
./gestion.sh on
./gestion.sh status
```

Salida esperada de `status` (todas las líneas con ●):

```
● postgres — Up ... (healthy)
● redis — Up ...
● backend — Up ...
● front :4242 — HTTP 200 (PID ...)
● túnel devtunnel (PID ...)            ← solo si devtunnel está instalado y con sesión
● Solercia Connect :8765 — listo (login interactivo por HTTP: true)
```

Tras cambiar código del backend ejecuta `./gestion.sh rebuild`; el frontend se
recarga solo.

### 4. Entrar

1. Abre http://localhost:4242 e inicia sesión con `admin@solercia.com` / `Admin123*`.
2. En el menú lateral, entra a **Conexiones**.

### 5. Primera conexión de Microsoft 365

1. Pulsa **Conectar Solercia Connect**.
2. Escribe tu correo institucional, deja **Outlook (correo y calendario)** y el
   interruptor **Inicio de sesión con navegador** activado, y pulsa **Conectar**.
3. La tarjeta aparece con el estado:
   - **Conectada**: ya existe una sesión de navegador vigente para esa cuenta.
   - **Requiere iniciar sesión**: pulsa **Iniciar sesión**. Se abre un Chromium de
     Connect en tu equipo; ingresa usuario, contraseña y segundo factor en la página
     de Microsoft. La tarjeta se actualiza sola y muestra «Sesión de Microsoft 365
     activa para <correo>».

Command nunca recibe ni guarda tu contraseña: viven en el perfil de navegador de
Connect.

### 6. Rutina diaria

1. Verifica que Connect responda (`./gestion.sh status` muestra su línea en ●).
2. En la tarjeta, pulsa **Refrescar sesión** si el estado es «Requiere iniciar
   sesión». Si el perfil sigue vigente, Microsoft no pide credenciales.
3. Elige el periodo (**Hoy**, **7 días**, **30 días**) y pulsa **Sincronizar ahora**.
   El toast indica cuántos correos nuevos entraron y cuántas tareas se crearon.

Los correos llegan como insumos de la bandeja de entrada (`GET /api/v1/intake/items`).
Se convierten en tareas solo cuando existe una regla de intake activa
(`POST /api/v1/intake/rules`); sin reglas quedan en estado `pending`.

### 7. Apagar

```bash
./gestion.sh off                                   # front, túnel y contenedores (datos intactos)
lsof -nP -iTCP:8765 -sTCP:LISTEN -t | xargs kill   # servicio de Connect
```

### Problemas frecuentes

| Síntoma | Causa | Qué hacer |
|---|---|---|
| `status` muestra «Solercia Connect :8765 — sin respuesta» | El servicio no está corriendo | Repite el paso 2 |
| `health` devuelve `"interactive_login":false` | Falta la API key o alguna de las dos banderas en `.env.local` | Revisa el paso 1 y reinicia Connect |
| Tarjeta en «Clave de Connect rechazada» | Las claves de `.env` y `.env.local` no coinciden | Igualalas, `./gestion.sh rebuild`, reinicia Connect |
| «Playwright Chromium could not start; install the browser runtime» | `TMPDIR` inválido en el proceso, o falta el binario de la versión de Playwright | Relanza con el comando del paso 2; si persiste, `cd ../solercia-connect && .venv/bin/python -m playwright install chromium` |
| «Ya hay un inicio de sesión en curso en Connect» | Hay un Chromium abierto de un intento anterior | Termina o cierra ese navegador y reintenta |
| El backend responde 404 en `/connectors/solercia-connect` | La imagen del backend es vieja | `./gestion.sh rebuild` |
| Puerto 4242 ocupado | Quedó un `ng serve` huérfano | `./gestion.sh off` y luego `on` |

## URLs y puertos

| Recurso | URL / puerto |
|---------|--------------|
| Interfaz de usuario (ng serve en el host) | http://localhost:4242 |
| API base | http://localhost:8081/api/v1 |
| Documentación de la API (Swagger) | http://localhost:8081/docs |
| PostgreSQL | 127.0.0.1:5434 |
| Redis | 127.0.0.1:6380 |
| Solercia Connect (host) | http://127.0.0.1:8765 |

Los puertos se eligieron para no chocar con `solercia_flows` ni `solercia_security`.
Dentro de Docker el backend sigue escuchando en 8000 y llega a Connect por
`host.docker.internal:8765`.

## Credenciales de demostración

| Campo | Valor |
|-------|-------|
| Correo | admin@solercia.com |
| Contraseña | Admin123* |

## Cómo registrar un proyecto

1. Ingresa a http://localhost:4242 e inicia sesión con las credenciales de
   demostración.
2. En la pantalla de proyectos, haz clic en **Crear proyecto**.
3. Escribe el nombre del proyecto y, opcionalmente, una descripción.
4. Selecciona la metodología que necesitas:
   - **Planner**: estados simples, sin sprints ni puntos de historia.
   - **Kanban**: flujo continuo con tablero, sin sprints.
   - **Scrum**: backlog, sprints y estimación por puntos de historia (Fibonacci).
   - **Personalizada**: define tus propios estados y columnas.
5. Guarda. El proyecto queda almacenado en PostgreSQL y aparece en tu lista.

## Comandos útiles

| Comando | Descripción |
|---------|-------------|
| `./gestion.sh on` | Levanta Docker (postgres, redis, backend), el front en el host y el túnel. |
| `./gestion.sh off` | Apaga todo; los datos se conservan. |
| `./gestion.sh status` | Estado de cada pieza, incluida la salud de Solercia Connect. |
| `./gestion.sh logs X` | Sigue logs de `front`, `tunel`, `backend`, `postgres` o `redis`. |
| `./gestion.sh rebuild` | Reconstruye la imagen del backend con el código actual. |
| `make up` / `make down` / `make logs` / `make ps` | Atajos equivalentes sobre `docker compose` (flujo sin `gestion.sh`). |

## Variables de entorno

`env.example` documenta todas las variables. El compose inyecta las del backend;
las que dependen de tu equipo van en `.env` (raíz, ignorado por git):

| Variable | Dónde | Para qué |
|---|---|---|
| `SOLERCIA_CONNECT_API_KEY` | `.env` de Command y `.env.local` de Connect | Autenticación entre el backend y Connect; deben ser iguales |
| `SOLERCIA_CONNECT_BASE_URL` | compose (`http://host.docker.internal:8765`) | Dónde está Connect visto desde el contenedor |
| `SOLERCIA_CONNECT_DEFAULT_TARGET` | compose (`outlook`) | Destino por defecto al registrar una conexión |
| `JWT_SECRET` | compose | Cámbialo en cualquier ambiente que no sea de desarrollo |
| `INTEGRATIONS_FERNET_KEY` | `.env` (obligatoria) | Cifra en reposo las credenciales de las integraciones; genera una distinta por ambiente (ver `env.example`) |

## Licencia

Copyright (C) 2026 Cristian Camilo Calderón Tapia.

Solercia Command es software libre: puedes usarlo, estudiarlo, modificarlo y
redistribuirlo bajo los términos de la Licencia Pública General Affero de GNU
(GNU AGPL), versión 3, publicada por la Free Software Foundation. Se distribuye
SIN NINGUNA GARANTÍA; consulta el archivo [LICENSE](LICENSE). Si ofreces una versión
modificada como servicio en red, debes poner su código fuente a disposición de
quienes usan ese servicio.
