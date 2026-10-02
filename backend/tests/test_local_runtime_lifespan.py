"""Isolated startup orchestration: no application adapters or real resources."""
import ast
import asyncio
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import APIRouter
from pydantic import ValidationError
from pydantic_settings import BaseSettings

ROOT = Path(__file__).parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def runtime(monkeypatch):
    # Suppress dotenv and secret-file sources BEFORE any application import.
    original = BaseSettings.__init__
    def isolated(self, *args, **kwargs):
        kwargs.update(_env_file=None, _secrets_dir=None)
        original(self, *args, **kwargs)
    monkeypatch.setattr(BaseSettings, '__init__', isolated)
    config = load('_local_test_config', ROOT / 'app/config.py')
    engine = SimpleNamespace(dispose=AsyncMock(), connect=Mock())
    crypto = SimpleNamespace(validate_key=Mock())
    scheduler = object()
    doubles = {
        'settings': config.settings, 'engine': engine, 'crypto': crypto,
        'seed_default': AsyncMock(), 'start_scheduler': Mock(return_value=scheduler),
        'stop_scheduler': Mock(), 'register_reminders_job': Mock(),
        'register_delivery_jobs': Mock(), 'has_active_durable_channel': Mock(return_value=True),
        'register_exception_handlers': Mock(),
    }
    # Stub every app import, including routers, before executing the real main.
    # Unknown app imports fail closed instead of importing provider/DB modules.
    tree = ast.parse((ROOT / 'app/main.py').read_text())
    stubs = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or not node.module.startswith('app.'):
            continue
        stub = stubs.setdefault(node.module, ModuleType(node.module))
        for alias in node.names:
            if alias.name in doubles:
                value = doubles[alias.name]
            elif node.module.endswith('.router'):
                value = APIRouter()
            else:
                raise AssertionError(f'Unstubbed application dependency: {node.module}.{alias.name}')
            setattr(stub, alias.name, value)
        monkeypatch.setitem(sys.modules, node.module, stub)
    main = load('_local_test_main', ROOT / 'app/main.py')
    wait_for_db = main._wait_for_db
    main._wait_for_db = AsyncMock()
    return SimpleNamespace(main=main, config=config, engine=engine, crypto=crypto,
                           scheduler=scheduler, wait_for_db=wait_for_db)


def select(runtime, profile):
    runtime.main.settings = runtime.config.Settings(STARTUP_PROFILE=profile)


@pytest.mark.asyncio
@pytest.mark.parametrize('demo', [False, True])
async def test_local_disables_all_seed_and_scheduler_work(runtime, demo):
    select(runtime, 'local_restricted')
    runtime.main.settings.SEED_DEMO_DATA = demo
    async with runtime.main.lifespan(runtime.main.app):
        runtime.crypto.validate_key.assert_called_once()
        runtime.main._wait_for_db.assert_awaited_once()
    runtime.main.seed_default.assert_not_called()
    for name in ('start_scheduler', 'stop_scheduler', 'register_reminders_job',
                 'register_delivery_jobs', 'has_active_durable_channel'):
        getattr(runtime.main, name).assert_not_called()
    runtime.engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('durable', [False, True])
async def test_default_preserves_seed_and_shared_scheduler(runtime, durable):
    runtime.main.has_active_durable_channel.return_value = durable
    async with runtime.main.lifespan(runtime.main.app):
        runtime.main.seed_default.assert_awaited_once()
        runtime.main.start_scheduler.assert_called_once()
        runtime.main.register_reminders_job.assert_called_once_with(runtime.scheduler)
    assert runtime.main.register_delivery_jobs.call_count == int(durable)
    runtime.main.stop_scheduler.assert_called_once()
    runtime.engine.dispose.assert_awaited_once()


def test_invalid_profile_rejected_before_resources(runtime):
    with pytest.raises(ValidationError):
        runtime.config.Settings(STARTUP_PROFILE='unsafe')
    runtime.main._wait_for_db.assert_not_called()
    runtime.main.start_scheduler.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('profile', ['default', 'local_restricted'])
async def test_invalid_encryption_precedes_db_and_scheduler(runtime, profile):
    select(runtime, profile)
    runtime.crypto.validate_key.side_effect = ValueError('Clave inválida.')
    with pytest.raises(ValueError, match='Clave inválida'):
        async with runtime.main.lifespan(runtime.main.app):
            pytest.fail('No debe iniciar.')
    runtime.main._wait_for_db.assert_not_called()
    runtime.main.start_scheduler.assert_not_called()
    runtime.engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['db', 'seed', 'serving', 'channel'])
async def test_cleanup_on_partial_startup_or_serving_failure(runtime, failure):
    error = RuntimeError('Fallo simulado.')
    if failure == 'db':
        runtime.main._wait_for_db.side_effect = error
    elif failure == 'seed':
        runtime.main.seed_default.side_effect = error
    elif failure == 'channel':
        runtime.main.has_active_durable_channel.side_effect = error
    with pytest.raises(RuntimeError, match='Fallo simulado'):
        async with runtime.main.lifespan(runtime.main.app):
            if failure == 'serving':
                raise error
    runtime.engine.dispose.assert_awaited_once()
    assert runtime.main.stop_scheduler.call_count == int(failure in ('serving', 'channel'))


@pytest.mark.asyncio
@pytest.mark.parametrize('cleanup_type', [RuntimeError, asyncio.CancelledError])
@pytest.mark.parametrize('phase', ['startup', 'serving', 'cancellation'])
async def test_dispose_failure_preserves_original_exception(runtime, phase, cleanup_type, caplog):
    original = (asyncio.CancelledError('Cancelación simulada.')
                if phase == 'cancellation' else RuntimeError('Fallo original simulado.'))
    cleanup = cleanup_type('Detalle privado simulado de limpieza.')
    runtime.engine.dispose.side_effect = cleanup
    original_traceback = None

    async def fail_at_origin():
        nonlocal original_traceback
        try:
            raise original
        except BaseException:
            original_traceback = original.__traceback__
            raise

    if phase == 'startup':
        runtime.main._wait_for_db.side_effect = fail_at_origin
    with pytest.raises(type(original)) as caught:
        async with runtime.main.lifespan(runtime.main.app):
            await fail_at_origin()
    assert caught.value is original
    traceback = caught.value.__traceback__
    while traceback is not None and traceback is not original_traceback:
        traceback = traceback.tb_next
    assert traceback is original_traceback
    assert original.__context__ is None
    runtime.engine.dispose.assert_awaited_once()
    assert runtime.main.stop_scheduler.call_count == int(phase != 'startup')
    assert str(cleanup) not in caplog.text
    assert str(original) not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.asyncio
@pytest.mark.parametrize('cleanup_type', [RuntimeError, asyncio.CancelledError])
async def test_dispose_failure_on_normal_shutdown_remains_visible(runtime, cleanup_type):
    cleanup = cleanup_type('Fallo de limpieza simulado.')
    runtime.engine.dispose.side_effect = cleanup
    with pytest.raises(cleanup_type) as caught:
        async with runtime.main.lifespan(runtime.main.app):
            pass
    assert caught.value is cleanup
    runtime.engine.dispose.assert_awaited_once()
    runtime.main.stop_scheduler.assert_called_once()


@pytest.mark.asyncio
async def test_db_readiness_retries_are_bounded(runtime, monkeypatch):
    runtime.engine.connect.side_effect = OSError('Base de datos no disponible.')
    sleep = AsyncMock()
    monkeypatch.setattr(runtime.main.asyncio, 'sleep', sleep)
    with pytest.raises(RuntimeError, match='No se pudo conectar'):
        await runtime.wait_for_db(max_attempts=3, delay_seconds=0)
    assert runtime.engine.connect.call_count == 3
    assert sleep.await_count == 3
    runtime.main.seed_default.assert_not_called()
    runtime.main.start_scheduler.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['start_scheduler', 'register_reminders_job',
                                     'register_delivery_jobs', 'stop_scheduler'])
async def test_scheduler_failures_remain_best_effort_and_dispose(runtime, failure):
    getattr(runtime.main, failure).side_effect = RuntimeError('Fallo simulado.')
    async with runtime.main.lifespan(runtime.main.app):
        pass
    runtime.engine.dispose.assert_awaited_once()
    runtime.main.stop_scheduler.assert_called_once()
    if failure == 'start_scheduler':
        runtime.main.register_reminders_job.assert_not_called()
        runtime.main.register_delivery_jobs.assert_not_called()
