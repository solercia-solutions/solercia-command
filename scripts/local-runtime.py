#!/usr/bin/env python3
"""Passive-by-default local development supervisor (stdlib, macOS).

plan (default) and plist only read metadata and render stdout. Only explicit run
starts children. No install, launchctl, migrations, storage management or restart
loop. Database/schema and Redis must already be prepared independently.

Run requires LOCAL_RUNTIME_DATABASE_URL and LOCAL_RUNTIME_REDIS_URL in the
invoking environment; generic DATABASE_URL is intentionally NOT sufficient.
Optional LOCAL_RUNTIME_JWT_SECRET and LOCAL_RUNTIME_INTEGRATIONS_FERNET_KEY are
passed only to the backend. Secrets never enter argv, plans or plist output.

This is not a security sandbox: trusted checkout/dependencies and a single-user
execution context are prerequisites. No concurrent checkout modification is
supported. Only direct child handles are signalled (never PID files or port
owners). Descendants that detach are not managed. SIGKILL/crash can leave a stale
lock: refuse recovery rather than infer ownership. HTTP checks prove liveness,
not schema readiness, authentication, process identity or daily-use readiness.
"""
import argparse
import fcntl
import select
import json
import os
from pathlib import Path
import plistlib
import signal
import socket
import stat
import subprocess
import sys
import time
from urllib.parse import urlsplit


class RuntimeFailure(Exception):
    """Only static, credential-free messages cross the CLI boundary."""


class Configuration:
    def __init__(self, checkout, python, node):
        self.checkout = Path(checkout)
        self.python = Path(python)
        self.node = Path(node)


def validate_checkout(checkout, script):
    root = Path(checkout)
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise RuntimeFailure('Usa la ruta absoluta canónica del proyecto.')
    if Path(script).resolve() != root / 'scripts/local-runtime.py':
        raise RuntimeFailure('El controlador no pertenece a este proyecto.')
    if root.stat().st_uid != os.getuid():
        raise RuntimeFailure('El proyecto debe pertenecer al usuario actual.')


def make_plan(config):
    root = config.checkout
    if not root.is_absolute() or root.resolve(strict=True) != root:
        raise RuntimeFailure('Usa la ruta absoluta canónica del proyecto.')
    for executable in (config.python, config.node):
        if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
            raise RuntimeFailure('Falta un ejecutable absoluto de Python o Node ya instalado.')
    cli = root / 'frontend/node_modules/@angular/cli/bin/ng.js'
    required = [root / 'backend', root / 'frontend', root / 'backend/app/main.py',
                root / 'frontend/proxy.conf.local.json', cli]
    for path in required:
        resolved = path.resolve(strict=True)
        if root not in resolved.parents or path.stat().st_uid != os.getuid():
            raise RuntimeFailure('Una dependencia sale del proyecto o pertenece a otro usuario.')
    if not cli.is_file() or cli.resolve() != cli:
        raise RuntimeFailure('La CLI de Angular debe estar instalada dentro de este proyecto, sin enlaces.')
    return {
        'mode': 'Servidor de desarrollo Angular; no es un paquete de producción.',
        'profile': 'local_restricted',
        'prerequisites': 'PostgreSQL con esquema preparado y Redis externos; configuración explícita al ejecutar.',
        'limits': 'Sin instalación, migraciones, semillas, trabajos, túneles ni reinicio automático. Solo hijos directos.',
        'backend': {'cwd': str(root / 'backend'), 'argv': [str(config.python), '-m', 'uvicorn',
            'app.main:app', '--host', '127.0.0.1', '--port', '8081', '--workers', '1']},
        'frontend': {'cwd': str(root / 'frontend'), 'argv': [str(config.node), str(cli), 'serve',
            '--host', '127.0.0.1', '--port', '4242', '--proxy-config', 'proxy.conf.local.json']},
    }


def render_plist(config):
    make_plan(config)
    return plistlib.dumps({
        'Label': 'co.solercia.command.local-development',
        'ProgramArguments': [str(config.python), '-B', str(config.checkout / 'scripts/local-runtime.py'),
            'run', '--checkout', str(config.checkout), '--python', str(config.python), '--node', str(config.node)],
        'WorkingDirectory': str(config.checkout),
        'EnvironmentVariables': {'STARTUP_PROFILE': 'local_restricted'},
        'RunAtLoad': False,
        'KeepAlive': False,
        'ProcessType': 'Interactive',
    })


def child_environment(source):
    result = {'PATH': '/usr/bin:/bin', 'PYTHONDONTWRITEBYTECODE': '1',
              'STARTUP_PROFILE': 'local_restricted', 'NG_CLI_ANALYTICS': 'false',
              'EMAIL_ENABLED': 'false', 'SEED_DEMO_DATA': 'false'}
    for name, schemes in [('DATABASE_URL', ('postgresql+asyncpg',)), ('REDIS_URL', ('redis', 'rediss'))]:
        value = source.get('LOCAL_RUNTIME_' + name, '')
        try:
            parsed = urlsplit(value)
            valid = (parsed.scheme in schemes and parsed.hostname in ('localhost', '127.0.0.1', '::1')
                     and bool(parsed.path.strip('/')) and not parsed.fragment and not parsed.query)
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                valid = False
        except ValueError:
            valid = False
        if not valid:
            raise RuntimeFailure('Configura explícitamente LOCAL_RUNTIME_DATABASE_URL y LOCAL_RUNTIME_REDIS_URL en loopback; no se usan valores Docker.')
        result[name] = value
    for name in ('JWT_SECRET', 'INTEGRATIONS_FERNET_KEY'):
        if source.get('LOCAL_RUNTIME_' + name):
            result[name] = source['LOCAL_RUNTIME_' + name]
    return result


class InstanceLock:
    """Persistent inode + flock; never unlink or steal, including after crashes."""
    def __init__(self, root):
        self.path = root / '.local-runtime.lock'
        self.root = root
        self.fd = None
        self.owned = False

    def __enter__(self):
        try:
            self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            info = os.fstat(self.fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
                raise RuntimeFailure('El bloqueo existente no es seguro; no se modifica.')
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if os.fstat(self.fd).st_size:
                raise RuntimeFailure('Existe un bloqueo sin cierre confirmado; requiere inspección humana, sin recuperación automática.')
            self.identity = (info.st_dev, info.st_ino)
            self.marker = json.dumps({'checkout': str(self.root), 'uid': os.getuid(), 'pid': os.getpid()}).encode()
            os.write(self.fd, self.marker)
            self.owned = True
            return self
        except (OSError, RuntimeFailure):
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            raise RuntimeFailure('No se puede adquirir el bloqueo exclusivo; no se modifica ni adopta otra instancia.') from None

    def __exit__(self, *args):
        try:
            current = self.path.lstat()
            os.lseek(self.fd, 0, os.SEEK_SET)
            if (self.owned and (current.st_dev, current.st_ino) == self.identity
                    and os.read(self.fd, len(self.marker) + 1) == self.marker):
                os.ftruncate(self.fd, 0)
        finally:
            os.close(self.fd)
            self.fd = None


def ports_free():
    """Conservative bind check, never inspect or kill a port owner."""
    held = []
    try:
        for port in (8081, 4242):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            held.append(sock)
            sock.bind(('127.0.0.1', port))
        return True
    except OSError:
        return False
    finally:
        for sock in held:
            sock.close()


def http_ready(remaining):
    """Bounded nonblocking HTTP/1.0; unsupported framing fails closed.

    Absolute deadlines include trickling headers/bodies. Never use environment
    proxies, follow redirects, or accept a response larger than 16 KiB.
    """
    deadline = time.monotonic() + min(remaining, 1.5)
    for port, path, identity in [(8081, '/api/v1/health', True),
                                  (4242, '/', False), (4242, '/api/v1/health', True)]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setblocking(False)
            sock.connect_ex(('127.0.0.1', port))
            request = ('GET ' + path + ' HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n').encode()
            response = b''
            while True:
                budget = deadline - time.monotonic()
                if budget <= 0:
                    return False
                readable, writable, _ = select.select([sock] if not request else [], [sock] if request else [], [], budget)
                if writable:
                    request = request[sock.send(request):]
                if not readable:
                    continue
                chunk = sock.recv(4096)
                response += chunk
                if len(response) > 16384:
                    return False
                headers, separator, body = response.partition(b'\r\n\r\n')
                if separator:
                    status_line = headers.split(b'\r\n', 1)[0].split()
                    if len(status_line) < 2 or status_line[1] != b'200':
                        return False
                    if not identity:
                        break
                if not chunk:
                    if not separator or b'transfer-encoding:' in headers.lower():
                        return False
                    data = json.loads(body)
                    if not isinstance(data, dict) or data.get('status') != 'ok' or data.get('service') != 'solercia-pm':
                        return False
                    break
        except (OSError, ValueError):
            return False
        finally:
            sock.close()
    return time.monotonic() <= deadline


class Supervisor:
    def __init__(self, config, environment, *, spawn=subprocess.Popen, ready=http_ready,
                 ports_free=ports_free, clock=time, startup_timeout=45, shutdown_timeout=5):
        self.config = config
        self.environment = environment
        self.spawn = spawn
        self.ready = ready
        self.ports_free = ports_free
        self.clock = clock
        self.startup_timeout = startup_timeout
        self.shutdown_timeout = shutdown_timeout
        self.children = []
        self.stopping = False

    def request_stop(self, signum, frame):
        self.stopping = True

    def cleanup(self):
        # Popen handles serialize poll/wait with signalling on POSIX; never use
        # killpg after a leader may have been reaped (PGID reuse). No PID lookup.
        failed = False
        for child in reversed(self.children):
            try:
                if child.poll() is None:
                    child.terminate()
                try:
                    child.wait(timeout=self.shutdown_timeout)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=self.shutdown_timeout)
            except (OSError, subprocess.TimeoutExpired):
                failed = True
        if failed:
            raise RuntimeFailure('No se confirmó el cierre de todos los hijos; se requiere inspección humana.')

    def run(self):
        plan = make_plan(self.config)
        env = child_environment(self.environment)
        with InstanceLock(self.config.checkout) as lock:
            try:
                if not self.ports_free():
                    raise RuntimeFailure('Los puertos locales están ocupados; no se termina ni adopta ningún proceso.')
                deadline = self.clock.monotonic() + self.startup_timeout
                for name in ('backend', 'frontend'):
                    if self.stopping:
                        return
                    item = plan[name]
                    # Child output may include database credentials in exceptions.
                    # Do not forward it to terminal or LaunchAgent logs.
                    child_env = env if name == 'backend' else {
                        key: env[key] for key in ('PATH', 'NG_CLI_ANALYTICS', 'STARTUP_PROFILE')}
                    self.children.append(self.spawn(item['argv'], cwd=item['cwd'], env=child_env,
                        shell=False, start_new_session=True, stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
                while not self.stopping:
                    if any(child.poll() is not None for child in self.children):
                        raise RuntimeFailure('Un servicio terminó antes de confirmar disponibilidad.')
                    remaining = deadline - self.clock.monotonic()
                    if remaining <= 0:
                        raise RuntimeFailure('Se agotó el plazo de arranque; se detienen únicamente los hijos propios.')
                    if self.ready(remaining) and self.clock.monotonic() < deadline:
                        break
                    self.clock.sleep(min(0.1, max(0, deadline - self.clock.monotonic())))
                while not self.stopping:
                    if any(child.poll() is not None for child in self.children):
                        raise RuntimeFailure('Un servicio terminó; no hay reinicio automático.')
                    self.clock.sleep(0.1)
            except OSError:
                raise RuntimeFailure('No fue posible iniciar los servicios locales.') from None
            finally:
                try:
                    self.cleanup()
                except RuntimeFailure:
                    # Keep the marker if termination could not be confirmed.
                    lock.owned = False
                    raise


def main(argv=None):
    parser = argparse.ArgumentParser(description='Plan pasivo o ejecución local explícita; frontend de desarrollo.')
    parser.add_argument('action', nargs='?', choices=('plan', 'plist', 'run'), default='plan')
    parser.add_argument('--checkout', required=True, help='Ruta absoluta canónica de este proyecto.')
    parser.add_argument('--python', required=True, help='Python absoluto ya instalado con dependencias del backend.')
    parser.add_argument('--node', required=True, help='Node absoluto ya instalado.')
    args = parser.parse_args(argv)
    try:
        config = Configuration(args.checkout, args.python, args.node)
        validate_checkout(config.checkout, __file__)
        if args.action == 'plan':
            print(json.dumps(make_plan(config), ensure_ascii=False, indent=2))
        elif args.action == 'plist':
            sys.stdout.buffer.write(render_plist(config))
        else:
            if sys.platform != 'darwin' or os.getuid() == 0:
                raise RuntimeFailure('La ejecución admite únicamente macOS sin privilegios de administrador.')
            # Force the supervisor profile too; all later invocations reconstruct
            # child environments, regardless of inherited/default profile values.
            os.environ['STARTUP_PROFILE'] = 'local_restricted'
            supervisor = Supervisor(config, os.environ)
            previous = {}
            try:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    previous[sig] = signal.signal(sig, supervisor.request_stop)
                supervisor.run()
            finally:
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
        return 0
    except RuntimeFailure as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError):
        print('No fue posible validar o ejecutar el entorno local; no se muestran datos de configuración.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
