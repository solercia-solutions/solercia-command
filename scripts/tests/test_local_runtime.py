"""Offline lifecycle contract: never launch applications or contact services."""
import importlib.util
import io
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'local-runtime.py'
spec = importlib.util.spec_from_file_location('local_runtime', SOURCE)
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


class Child:
    def __init__(self, stubborn=False):
        self.code = None
        self.actions = []
        self.stubborn = stubborn

    def poll(self):
        return self.code

    def terminate(self):
        self.actions.append('term')
        if not self.stubborn:
            self.code = 0

    def kill(self):
        self.actions.append('kill')
        self.code = -9

    def wait(self, timeout):
        self.actions.append('wait')
        if self.code is None:
            raise subprocess.TimeoutExpired('fake', timeout)
        return self.code


class Clock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Contract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='command space ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for name in ('backend/app/main.py', 'frontend/node_modules/@angular/cli/bin/ng.js',
                     'frontend/proxy.conf.local.json', 'scripts/local-runtime.py', 'python', 'node'):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{}')
        for name in ('python', 'node'):
            (self.root / name).chmod(0o700)
        self.config = runtime.Configuration(self.root, self.root / 'python', self.root / 'node')
        self.env = {'LOCAL_RUNTIME_DATABASE_URL': 'postgresql+asyncpg://user:secret@127.0.0.1/db',
                    'LOCAL_RUNTIME_REDIS_URL': 'redis://127.0.0.1:6379/0',
                    'STARTUP_PROFILE': 'default', 'NODE_OPTIONS': 'unsafe'}

    def test_plan_is_passive_and_argv_preserves_spaces(self):
        with patch.object(runtime.subprocess, 'Popen', side_effect=AssertionError), \
             patch.object(runtime.socket, 'socket', side_effect=AssertionError), \
             patch.object(runtime.os, 'open', side_effect=AssertionError):
            plan = runtime.make_plan(self.config)
        self.assertEqual(plan['backend']['argv'], [str(self.root / 'python'), '-m', 'uvicorn',
            'app.main:app', '--host', '127.0.0.1', '--port', '8081', '--workers', '1'])
        self.assertEqual(plan['frontend']['argv'][1], str(self.root / 'frontend/node_modules/@angular/cli/bin/ng.js'))
        self.assertIn('desarrollo', plan['mode'])
        self.assertNotIn('secret', str(plan))

    def test_plist_roundtrip_passive_no_secrets(self):
        with patch.dict(os.environ, self.env), patch.object(runtime.subprocess, 'Popen', side_effect=AssertionError):
            payload = runtime.render_plist(self.config)
        data = plistlib.loads(payload)
        self.assertFalse(data['RunAtLoad'])
        self.assertFalse(data['KeepAlive'])
        self.assertIn('run', data['ProgramArguments'])
        self.assertNotIn(b'secret', payload)
        self.assertEqual(data['EnvironmentVariables'], {'STARTUP_PROFILE': 'local_restricted'})

    def test_missing_dependency_and_cli_escape_refused(self):
        with self.assertRaises(runtime.RuntimeFailure):
            runtime.make_plan(runtime.Configuration(self.root, self.root / 'missing', self.root / 'node'))
        cli = self.root / 'frontend/node_modules/@angular/cli/bin/ng.js'
        # Test-owned file only; replacement never touches a repository target.
        cli.unlink()
        cli.symlink_to(self.root / 'node')
        with self.assertRaises(runtime.RuntimeFailure):
            runtime.make_plan(self.config)

    def test_sibling_checkout_refused(self):
        with self.assertRaises(runtime.RuntimeFailure):
            runtime.validate_checkout(self.root, self.root / 'sibling/scripts/local-runtime.py')
        runtime.validate_checkout(self.root, self.root / 'scripts/local-runtime.py')

    def test_explicit_services_and_sanitized_environment(self):
        for env in ({}, {'DATABASE_URL': self.env['LOCAL_RUNTIME_DATABASE_URL']},
                    dict(self.env, LOCAL_RUNTIME_DATABASE_URL='postgresql+asyncpg://app:app@postgres/db')):
            with self.assertRaises(runtime.RuntimeFailure) as caught:
                runtime.child_environment(env)
            self.assertNotIn('secret', str(caught.exception))
        result = runtime.child_environment(self.env)
        self.assertEqual(result['STARTUP_PROFILE'], 'local_restricted')
        self.assertEqual(result['DATABASE_URL'], self.env['LOCAL_RUNTIME_DATABASE_URL'])
        self.assertNotIn('NODE_OPTIONS', result)

    def supervisor(self, spawn=None, ready=None, free=None, children=None):
        clock = Clock()
        children = children if children is not None else [Child(), Child()]
        calls = []
        def start(argv, **kwargs):
            calls.append((argv, kwargs))
            return children[len(calls) - 1]
        supervisor = runtime.Supervisor(self.config, self.env, spawn=spawn or start,
            ready=ready or (lambda remaining: True), ports_free=free or (lambda: True),
            clock=clock, startup_timeout=1, shutdown_timeout=1)
        return supervisor, children, calls

    def test_second_spawn_failure_reaps_first(self):
        first = Child()
        calls = []
        def spawn(*args, **kwargs):
            calls.append(1)
            if len(calls) == 2:
                raise OSError('secret')
            return first
        supervisor, _, _ = self.supervisor(spawn=spawn)
        with self.assertRaises(runtime.RuntimeFailure) as caught:
            supervisor.run()
        self.assertNotIn('secret', str(caught.exception))
        self.assertEqual(first.actions, ['term', 'wait'])

    def test_occupied_ports_never_spawn(self):
        supervisor, children, calls = self.supervisor(free=lambda: False)
        with self.assertRaises(runtime.RuntimeFailure):
            supervisor.run()
        self.assertEqual(calls, [])
        self.assertEqual(children[0].actions, [])

    def test_startup_deadline_then_bounded_kill(self):
        supervisor, children, _ = self.supervisor(ready=lambda remaining: False,
                                                  children=[Child(True), Child(True)])
        with self.assertRaises(runtime.RuntimeFailure):
            supervisor.run()
        self.assertGreaterEqual(supervisor.clock.now, 1)
        for child in children:
            self.assertEqual(child.actions, ['term', 'wait', 'kill', 'wait'])

    def test_signal_stops_only_owned_children_and_profile_forced(self):
        supervisor, children, calls = self.supervisor()
        def ready(remaining):
            supervisor.request_stop(15, None)
            return True
        supervisor.ready = ready
        supervisor.run()
        for _, kwargs in calls:
            self.assertEqual(kwargs['env']['STARTUP_PROFILE'], 'local_restricted')
            self.assertFalse(kwargs['shell'])
            self.assertTrue(kwargs['start_new_session'])
        for child in children:
            self.assertEqual(child.actions, ['term', 'wait'])

    def test_child_exit_not_readiness(self):
        first = Child()
        first.code = 1
        supervisor, _, _ = self.supervisor(children=[first, Child()])
        with self.assertRaises(runtime.RuntimeFailure):
            supervisor.run()
        self.assertNotIn('term', first.actions)

    def test_lock_duplicate_foreign_stale_and_reuse(self):
        path = self.root / '.local-runtime.lock'
        with runtime.InstanceLock(self.root):
            with self.assertRaises(runtime.RuntimeFailure):
                with runtime.InstanceLock(self.root):
                    pass
        with runtime.InstanceLock(self.root):
            pass
        path.write_text('foreign or stale')
        before = path.read_bytes()
        with self.assertRaises(runtime.RuntimeFailure):
            with runtime.InstanceLock(self.root):
                pass
        self.assertEqual(path.read_bytes(), before)

    def test_lock_symlink_refused_without_modifying_target(self):
        target = self.root / 'untouched'
        target.write_text('foreign')
        (self.root / '.local-runtime.lock').symlink_to(target)
        with self.assertRaises(runtime.RuntimeFailure):
            with runtime.InstanceLock(self.root):
                pass
        self.assertEqual(target.read_text(), 'foreign')

    def test_stop_during_first_spawn_does_not_start_second(self):
        child = Child()
        def spawn(*args, **kwargs):
            supervisor.request_stop(2, None)
            return child
        supervisor, _, _ = self.supervisor(spawn=spawn)
        supervisor.run()
        self.assertEqual(len(supervisor.children), 1)
        self.assertEqual(child.actions, ['term', 'wait'])

    def test_unconfirmed_cleanup_preserves_lock(self):
        class Unkillable(Child):
            def kill(self):
                self.actions.append('kill')
        supervisor, _, _ = self.supervisor(ready=lambda remaining: False,
                                          children=[Unkillable(True), Child()])
        with self.assertRaises(runtime.RuntimeFailure):
            supervisor.run()
        self.assertTrue((self.root / '.local-runtime.lock').read_bytes())

    def test_foreign_uid_lock_unchanged(self):
        path = self.root / '.local-runtime.lock'
        path.write_text('foreign')
        path.chmod(0o600)
        with patch.object(runtime.os, 'getuid', return_value=os.getuid() + 1):
            with self.assertRaises(runtime.RuntimeFailure):
                with runtime.InstanceLock(self.root):
                    pass
        self.assertEqual(path.read_text(), 'foreign')

    def test_replaced_lock_is_not_erased(self):
        path = self.root / '.local-runtime.lock'
        with runtime.InstanceLock(self.root):
            # Both entries are owned by this temporary test directory.
            path.rename(self.root / 'old-lock')
            path.write_text('replacement')
        self.assertEqual(path.read_text(), 'replacement')

    def test_http_adapter_identity_and_deadline_without_network(self):
        class Socket:
            def __init__(self, response):
                self.response = response
                self.closed = False
            def setblocking(self, flag):
                pass
            def connect_ex(self, address):
                return 0
            def send(self, data):
                return len(data)
            def recv(self, size):
                result, self.response = self.response, b''
                return result
            def close(self):
                self.closed = True
        good = b'HTTP/1.0 200 OK\r\n\r\n{"status":"ok","service":"solercia-pm"}'
        sockets = [Socket(good), Socket(b'HTTP/1.0 200 OK\r\n\r\nhtml'), Socket(good)]
        with patch.object(runtime.socket, 'socket', side_effect=sockets), \
             patch.object(runtime.select, 'select', side_effect=lambda r, w, x, t: (r, w, [])):
            self.assertTrue(runtime.http_ready(1))
        self.assertTrue(all(sock.closed for sock in sockets))
        wrong = Socket(good.replace(b'solercia-pm', b'foreign'))
        with patch.object(runtime.socket, 'socket', return_value=wrong), \
             patch.object(runtime.select, 'select', side_effect=lambda r, w, x, t: (r, w, [])):
            self.assertFalse(runtime.http_ready(1))
        clock = Clock()
        def trickle(r, w, x, timeout):
            clock.sleep(timeout)
            return [], [], []
        with patch.object(runtime.socket, 'socket', return_value=Socket(b'')), \
             patch.object(runtime.select, 'select', side_effect=trickle), \
             patch.object(runtime.time, 'monotonic', clock.monotonic):
            self.assertFalse(runtime.http_ready(0.3))
        self.assertEqual(clock.now, 0.3)

    def test_main_errors_do_not_echo_configuration(self):
        output = io.StringIO()
        with patch('sys.stderr', output):
            result = runtime.main(['--checkout', '/missing/secret', '--python', '/secret', '--node', '/secret'])
        self.assertEqual(result, 1)
        self.assertNotIn('secret', output.getvalue())

    def test_default_cli_plan_no_run(self):
        out = io.StringIO()
        args = ['--checkout', str(self.root), '--python', str(self.root / 'python'),
                '--node', str(self.root / 'node')]
        with patch.object(runtime, '__file__', str(self.root / 'scripts/local-runtime.py')), \
             patch.object(runtime.Supervisor, 'run', side_effect=AssertionError), \
             patch('sys.stdout', out):
            self.assertEqual(runtime.main(args), 0)
        self.assertIn('desarrollo', out.getvalue())


if __name__ == '__main__':
    unittest.main()
