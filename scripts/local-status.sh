#!/bin/bash
# Solo consulta instancias existentes. Dependencias: python3 (biblioteca estándar), curl.
# SOLERCIA_FRONTEND_URL: http://127.0.0.1:4242
# SOLERCIA_BACKEND_URL: http://127.0.0.1:8081
# Bases permitidas: http/https, localhost/127.0.0.1/[::1], puerto 1..65535.
# No admite rutas, consultas, credenciales ni fragmentos; admite una barra final.
# --open requiere además el comando open de macOS; nunca inicia servicios.
set -eu
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'Estado: unknown. Falta la dependencia python3.' >&2
    exit 1
fi
exec python3 - "$@" <<'PY'
import json
import os
import re
import shutil
import subprocess
import sys

print('schema_0026=unknown; runtime=unknown')
print('Funciones: valores predeterminados=false; estado efectivo=unknown')
print('La disponibilidad HTTP no confirma preparación funcional, migraciones ni base de datos.')

def fail(message):
    print(message, file=sys.stderr)
    sys.exit(1)

if sys.argv[1:] not in ([], ['--open']):
    fail('Uso: local-status.sh [--open]')

urls = []
for name, default in [('SOLERCIA_FRONTEND_URL', 'http://127.0.0.1:4242'),
                      ('SOLERCIA_BACKEND_URL', 'http://127.0.0.1:8081')]:
    value = os.environ.get(name, default)
    match = re.fullmatch(r'https?://(?:localhost|127\.0\.0\.1|\[::1\])(?::([0-9]{1,5}))?/?', value)
    if not match or (match.group(1) is not None and not 1 <= int(match.group(1)) <= 65535):
        fail('Estado: unknown. URL local no válida en ' + name + '.')
    urls.append(value.removesuffix('/'))

# Todas las bases se validan antes de buscar open o realizar cualquier solicitud.
for dependency in ['curl'] + (['open'] if sys.argv[1:] else []):
    if not shutil.which(dependency):
        fail('Estado: unknown. Falta la dependencia ' + dependency + '.')

def probe(url, identity):
    command = ['curl', '-q', '--noproxy', '*', '--silent', '--proto', '=http,https',
               '--connect-timeout', '2', '--max-time', '5', '--max-filesize', '16384',
               '--range', '0-16383', '--write-out', '\n%{http_code}', '--url', url]
    try:
        # El límite de lectura protege también ante respuestas sin Content-Length.
        # Cerrar el pipe limita memoria; max-time limita la vida del proceso propio.
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as process:
            response = process.stdout.read(16389)
            process.stdout.close()
            code = process.wait()
        if code:
            return 'unreachable'
        if len(response) > 16388:
            return 'unknown'
        body, separator, status = response.rpartition(b'\n')
        if not separator or not re.fullmatch(b'2[0-9]{2}', status):
            return 'unreachable'
        if identity:
            data = json.loads(body)
            if not isinstance(data, dict) or data.get('status') != 'ok' or data.get('service') != 'solercia-pm':
                return 'unknown'
        return 'reachable'
    except (OSError, ValueError, RecursionError):
        return 'unknown'

frontend, backend = urls
states = []
for label, url, identity in [('Frontend', frontend, False),
                             ('Backend', backend + '/api/v1/health', True),
                             ('Proxy del frontend', frontend + '/api/v1/health', True)]:
    state = probe(url, identity)
    states.append(state)
    print(label + ': ' + state)
if states != ['reachable'] * 3:
    fail('No se abre la aplicación: comprueba las instancias existentes. No se inició ningún servicio.')
if sys.argv[1:]:
    try:
        result = subprocess.run(['open', frontend], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        fail('No fue posible abrir el navegador.')
    if result.returncode:
        fail('No fue posible abrir el navegador.')
    print('Se solicitó abrir la instancia existente. No se instaló ningún servicio persistente.')
PY
