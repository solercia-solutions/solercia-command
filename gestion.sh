#!/bin/bash
# gestion.sh — EL script para correr Solercia Command en local (único punto de entrada).
#
#   ./gestion.sh on        Enciende todo: Docker (postgres + redis + backend :8080),
#                          front dev en el HOST (:4242, ng serve con recarga en caliente)
#                          y túnel devtunnel público (4242) para verlo desde el celular.
#   ./gestion.sh off       Apaga todo (front, túnel y contenedores; datos intactos).
#   ./gestion.sh status    Estado de cada pieza con sus URLs.
#   ./gestion.sh logs X    Sigue logs (front | tunel | backend | postgres | redis).
#   ./gestion.sh rebuild   Reconstruye la imagen del backend con el código actual.
#
# Puertos elegidos para NO pisarse con los otros productos de Solercia
# (solercia_flows usa 4200, 3000, 8000, 5433, 9000/9001 y 27017;
#  solercia_security usa 14200, 18000, 15432 y su `sgsi-test-pg` toma el 5432):
#   Front  :4242  ·  Backend :8081 (→ 8000 interno)  ·  Postgres :5434  ·  Redis :6380
#
# Por qué el front va FUERA de Docker en desarrollo: la imagen del frontend copia
# el código al construirse (compose sin volúmenes), así que el contenedor sirve
# el código de CUANDO se construyó la imagen — no el actual. Con ng serve en el
# host los cambios se ven al instante. El backend SÍ corre en Docker (aplica las
# migraciones de Alembic al arrancar); tras cambiar código backend: ./gestion.sh rebuild

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONT_DIR="$ROOT_DIR/frontend"
PID_DIR="$ROOT_DIR/.dev-pids"
NODE_VERSION="22"
FRONT_PORT=4242
# 8080 estaba ocupado por traefik-idt (Pandora); 8081 es el libre más cercano.
API_PORT=8081

mkdir -p "$PID_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

# El servicio "frontend" del compose queda fuera del flujo dev (usaría el mismo
# puerto 4242 con código congelado en la imagen); se detiene si está corriendo.
DEV_SERVICES=(postgres redis backend)

# ── Docker CLI (Docker Desktop a veces no lo pone en PATH) ──────────────────
find_docker() {
  command -v docker 2>/dev/null && return 0
  for c in "$HOME/.docker/bin/docker" "/Applications/Docker.app/Contents/Resources/bin/docker" \
           "/usr/local/bin/docker" "/opt/homebrew/bin/docker"; do
    [ -x "$c" ] && { echo "$c"; return 0; }
  done
  return 1
}
DOCKER="$(find_docker)" || { echo -e "${RED}[ERR]${NC} docker CLI no encontrado. Abre Docker Desktop o agrega ~/.docker/bin al PATH."; exit 1; }
export PATH="$(dirname "$DOCKER"):$HOME/.docker/bin:$PATH"
dc() { ( cd "$ROOT_DIR" && "$DOCKER" compose "$@" ); }

check_docker_running() {
  "$DOCKER" info >/dev/null 2>&1 || { echo -e "${RED}[ERR]${NC} Docker Desktop no está corriendo. Ábrelo y espera 'Engine running'."; exit 1; }
}

# ── Node vía nvm (o node del sistema si ya es >= 20) ────────────────────────
use_node() {
  export NVM_DIR="$HOME/.nvm"
  # shellcheck disable=SC1091
  [ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh" >/dev/null 2>&1
  if command -v nvm >/dev/null 2>&1 && nvm use "$NODE_VERSION" >/dev/null 2>&1; then
    return 0
  fi
  local major
  major=$(node -v 2>/dev/null | sed 's/^v\([0-9]*\).*/\1/')
  if [ -z "$major" ] || [ "$major" -lt 20 ]; then
    echo -e "${RED}[ERR]${NC} Se necesita Node >= 20 (ideal $NODE_VERSION vía nvm). Corre: nvm install $NODE_VERSION"
    exit 1
  fi
}

is_pid_alive() { [ -n "$1" ] && kill -0 "$1" 2>/dev/null; }
pid_of() { [ -f "$PID_DIR/$1.pid" ] && cat "$PID_DIR/$1.pid" || true; }

# ── Docker: BD + backend ────────────────────────────────────────────────────
start_docker() {
  check_docker_running
  echo -e "${BLUE}[DOCKER]${NC} Levantando: ${DEV_SERVICES[*]}"
  dc up -d "${DEV_SERVICES[@]}"
  echo -e "${BLUE}[DOCKER]${NC} Esperando al backend (:$API_PORT, aplica migraciones al arrancar)..."
  local api=""
  for i in $(seq 1 40); do
    api=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:$API_PORT/docs" 2>/dev/null || true)
    [ "$api" = "200" ] && break
    sleep 3
  done
  if [ "$api" = "200" ]; then
    echo -e "${GREEN}[DOCKER]${NC} backend → $api (Swagger: http://localhost:$API_PORT/docs)"
  else
    echo -e "${RED}[DOCKER]${NC} El backend no respondió en :$API_PORT — mira: ./gestion.sh logs backend"
    return 1
  fi
}

# ── Front dev en el host (:4242) ────────────────────────────────────────────
start_front() {
  local pid; pid=$(pid_of front)
  if is_pid_alive "$pid"; then echo -e "${YELLOW}[FRONT]${NC} Ya corre (PID $pid)."; return; fi
  rm -f "$PID_DIR/front.pid"
  # El contenedor frontend del compose publica el mismo 4242 con código viejo.
  dc stop frontend >/dev/null 2>&1 || true
  if lsof -nP -iTCP:$FRONT_PORT -sTCP:LISTEN >/dev/null 2>&1; then
    echo -e "${YELLOW}[FRONT]${NC} El puerto $FRONT_PORT estaba ocupado por un proceso huérfano; liberándolo..."
    lsof -nP -iTCP:$FRONT_PORT -sTCP:LISTEN -t | xargs kill 2>/dev/null || true
    sleep 2
  fi
  use_node
  if [ ! -d "$FRONT_DIR/node_modules" ]; then
    echo -e "${BLUE}[FRONT]${NC} node_modules no existe; instalando dependencias (primera vez)..."
    ( cd "$FRONT_DIR" && npm ci )
  fi
  echo -e "${BLUE}[FRONT]${NC} Iniciando ng serve en :$FRONT_PORT (dual-stack para el túnel y el celular)..."
  ( cd "$FRONT_DIR" && nohup npx ng serve --host :: --port $FRONT_PORT \
      --proxy-config proxy.conf.local.json < /dev/null > "$PID_DIR/front.log" 2>&1 & \
    echo $! > "$PID_DIR/front.pid" )
  local code=""
  for i in $(seq 1 60); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:$FRONT_PORT/" 2>/dev/null || true)
    [ "$code" = "200" ] && break
    is_pid_alive "$(pid_of front)" || { echo -e "${RED}[FRONT]${NC} ng serve murió — mira: ./gestion.sh logs front"; return 1; }
    sleep 3
  done
  echo -e "${GREEN}[FRONT]${NC} http://localhost:$FRONT_PORT → $code (PID $(pid_of front))"
}

stop_front() {
  local pid; pid=$(pid_of front)
  if is_pid_alive "$pid"; then pkill -P "$pid" 2>/dev/null || true; kill "$pid" 2>/dev/null || true; fi
  rm -f "$PID_DIR/front.pid"
  lsof -nP -iTCP:$FRONT_PORT -sTCP:LISTEN -t 2>/dev/null | xargs kill 2>/dev/null || true
  echo -e "${GREEN}[FRONT]${NC} Apagado."
}

# ── Túnel devtunnel (VS Code dev tunnels) ───────────────────────────────────
# El túnel es PROPIO de este proyecto (id guardado en .dev-pids/tunel.id) para
# no interferir con el túnel de solercia_flows si corre en paralelo. Por eso
# aquí NUNCA se hace pkill de todos los devtunnel: solo del PID nuestro.
DEVTUNNEL="/opt/homebrew/bin/devtunnel"
tunnel_id_file() { echo "$PID_DIR/tunel.id"; }

start_tunnel() {
  [ -x "$DEVTUNNEL" ] || DEVTUNNEL="$(command -v devtunnel 2>/dev/null || true)"
  [ -n "$DEVTUNNEL" ] || { echo -e "${YELLOW}[TÚNEL]${NC} devtunnel no instalado (brew install --cask devtunnel). Sigo sin túnel."; return 0; }
  if "$DEVTUNNEL" user show 2>&1 | grep -q "Not logged in"; then
    echo -e "${YELLOW}[TÚNEL]${NC} Sin sesión de devtunnel. Corre: devtunnel user login  — y vuelve a ejecutar './gestion.sh on'. Sigo sin túnel."
    return 0
  fi
  local pid; pid=$(pid_of tunel)
  if is_pid_alive "$pid"; then echo -e "${YELLOW}[TÚNEL]${NC} Ya corre (PID $pid)."; show_tunnel_urls; return 0; fi
  local tunnel_id=""
  [ -f "$(tunnel_id_file)" ] && tunnel_id=$(cat "$(tunnel_id_file)")
  if [ -z "$tunnel_id" ]; then
    echo -e "${BLUE}[TÚNEL]${NC} Creando túnel propio del proyecto (puerto $FRONT_PORT, anónimo)..."
    tunnel_id=$("$DEVTUNNEL" create --allow-anonymous 2>/dev/null | awk -F': *' '/Tunnel ID/ {print $2; exit}' | tr -d ' ')
    if [ -z "$tunnel_id" ]; then
      echo -e "${RED}[TÚNEL]${NC} No se pudo crear el túnel — revisa 'devtunnel create --allow-anonymous' a mano. Sigo sin túnel."
      return 0
    fi
    "$DEVTUNNEL" port create "$tunnel_id" -p $FRONT_PORT >/dev/null 2>&1 || true
    echo "$tunnel_id" > "$(tunnel_id_file)"
    echo -e "${GREEN}[TÚNEL]${NC} Túnel creado y guardado: $tunnel_id (la URL se conserva entre sesiones)"
  else
    echo -e "${BLUE}[TÚNEL]${NC} Hospedando túnel del proyecto: $tunnel_id"
  fi
  nohup "$DEVTUNNEL" host "$tunnel_id" < /dev/null > "$PID_DIR/tunel.log" 2>&1 &
  echo $! > "$PID_DIR/tunel.pid"
  sleep 8
  show_tunnel_urls
}

show_tunnel_urls() {
  if [ -f "$PID_DIR/tunel.log" ]; then
    grep -E "Connect via browser" "$PID_DIR/tunel.log" | tail -1 | sed "s/^/  /" || true
    echo -e "  ${YELLOW}Esa URL abre el front desde cualquier red (celular incluido).${NC}"
  fi
}

stop_tunnel() {
  local pid; pid=$(pid_of tunel)
  if is_pid_alive "$pid"; then pkill -P "$pid" 2>/dev/null || true; kill "$pid" 2>/dev/null || true; fi
  rm -f "$PID_DIR/tunel.pid"
  echo -e "${GREEN}[TÚNEL]${NC} Apagado (el de solercia_flows, si corre, queda intacto)."
}

# ── Comandos ────────────────────────────────────────────────────────────────
cmd_on() {
  local sin_tunel=""
  [ "$1" = "--sin-tunel" ] && sin_tunel=1
  start_docker
  start_front
  [ -z "$sin_tunel" ] && start_tunnel
  echo ""
  echo -e "${GREEN}══════════ SOLERCIA COMMAND ENCENDIDO ══════════${NC}"
  echo -e "  Front:    http://localhost:$FRONT_PORT"
  echo -e "  API:      http://localhost:$API_PORT  (Swagger: /docs)"
  echo -e "  Postgres: 127.0.0.1:5434 · Redis: 127.0.0.1:6380"
  echo ""
  echo -e "  Estado:  ${YELLOW}./gestion.sh status${NC}   Logs: ${YELLOW}./gestion.sh logs front${NC}"
  echo -e "  Apagar:  ${YELLOW}./gestion.sh off${NC}"
}

cmd_off() {
  stop_tunnel
  stop_front
  check_docker_running
  echo -e "${YELLOW}[DOCKER]${NC} Deteniendo contenedores (datos intactos)..."
  dc stop "${DEV_SERVICES[@]}" frontend 2>/dev/null || true
  echo -e "${GREEN}══════════ SOLERCIA COMMAND APAGADO ══════════${NC}"
  echo -e "  (los volúmenes de BD se conservan; './gestion.sh on' lo revive)"
}

cmd_status() {
  echo -e "${BLUE}═══ Estado Solercia Command ═══${NC}"
  if "$DOCKER" info >/dev/null 2>&1; then
    for svc in "${DEV_SERVICES[@]}"; do
      st=$(dc ps "$svc" --format '{{.Status}}' 2>/dev/null | head -1)
      [ -n "$st" ] && echo -e "  ${GREEN}●${NC} $svc — $st" || echo -e "  ${RED}○${NC} $svc — apagado"
    done
  else
    echo -e "  ${RED}○${NC} Docker Desktop apagado"
  fi
  local fp; fp=$(pid_of front)
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:$FRONT_PORT/" 2>/dev/null || true)
  if [ "$code" = "200" ]; then echo -e "  ${GREEN}●${NC} front :$FRONT_PORT — HTTP 200${fp:+ (PID $fp)}"; else echo -e "  ${RED}○${NC} front :$FRONT_PORT — sin respuesta"; fi
  local tp; tp=$(pid_of tunel)
  if is_pid_alive "$tp"; then echo -e "  ${GREEN}●${NC} túnel devtunnel (PID $tp)"; show_tunnel_urls; else echo -e "  ${RED}○${NC} túnel devtunnel"; fi
}

cmd_logs() {
  case "${1:-front}" in
    front) tail -f "$PID_DIR/front.log" ;;
    tunel|tunnel) tail -f "$PID_DIR/tunel.log" ;;
    *) dc logs -f "$1" ;;
  esac
}

cmd_rebuild() {
  check_docker_running
  local targets=("${@:-}"); [ -z "${targets[0]}" ] && targets=(backend)
  echo -e "${BLUE}[REBUILD]${NC} Reconstruyendo: ${targets[*]}"
  dc up -d --build "${targets[@]}"
  echo -e "${GREEN}[REBUILD]${NC} Listo."
}

case "${1:-help}" in
  on|encender|start|up) shift || true; cmd_on "$@" ;;
  off|apagar|stop|down) cmd_off ;;
  status|st) cmd_status ;;
  logs) shift; cmd_logs "$@" ;;
  rebuild) shift || true; cmd_rebuild "$@" ;;
  restart) cmd_off; sleep 2; cmd_on ;;
  front) start_front ;;
  tunel|tunnel) start_tunnel ;;
  *)
    echo "Uso: ./gestion.sh <comando>"
    echo ""
    echo "  on [--sin-tunel]   Enciende todo (Docker + front + túnel)"
    echo "  off                Apaga todo (datos de BD intactos)"
    echo "  status             Estado de cada pieza"
    echo "  logs [front|tunel|backend|postgres|redis]"
    echo "  rebuild [servicio] Reconstruye la imagen del backend (código nuevo)"
    echo "  restart            off + on"
    echo "  front | tunel      Enciende solo esa pieza"
    ;;
esac
