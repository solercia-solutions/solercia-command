"""Actual DELETE route in an isolated ASGI app; no main, DB or real auth."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from httpx import ASGITransport, AsyncClient
import pytest


@pytest.fixture
def harness(monkeypatch):
    dependencies = ModuleType("app.dependencies")
    org, actor, task_id = uuid4(), uuid4(), uuid4()
    calls = []
    db = object()
    state = SimpleNamespace(org=org, actor=actor, task_id=task_id, calls=calls)

    async def membership(request: Request):
        if request.headers.get("authorization") != "Bearer synthetic":
            raise HTTPException(401, "No has iniciado sesión.")
        if request.headers.get("x-organization-id") != str(org):
            raise HTTPException(403, "No perteneces a esa organización.")
        return SimpleNamespace(organization_id=org)

    async def get_actor_id():
        return state.actor

    async def get_db():
        yield db

    class Service:
        def __init__(self, session):
            assert session is db

        async def delete_task(self, organization_id, requested_task_id, *, actor_id):
            calls.append((organization_id, requested_task_id, actor_id))

    dependencies.get_current_membership = membership
    dependencies.get_actor_id = get_actor_id
    with patch("pydantic_settings.sources.DotEnvSettingsSource.__call__", return_value={}), patch(
        "pydantic_settings.sources.SecretsSettingsSource.__call__", return_value={}
    ), monkeypatch.context() as isolated:
        isolated.setitem(sys.modules, "app.dependencies", dependencies)
        name = "app.modules.tasks._delete_test_router"
        path = Path(__file__).parents[1] / "app/modules/tasks/router.py"
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        isolated.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)
    module.TaskService = Service
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[module.get_db] = get_db
    state.app = app
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("null_actor", [False, True])
async def test_delete_204_forwards_trusted_tenant_task_and_actor(harness, null_actor):
    if null_actor:
        harness.actor = None
    async with AsyncClient(transport=ASGITransport(app=harness.app), base_url="http://test") as client:
        response = await client.delete(f"/tasks/{harness.task_id}", headers={
            "authorization": "Bearer synthetic", "x-organization-id": str(harness.org)})
    assert response.status_code == 204 and response.content == b""
    assert harness.calls == [(harness.org, harness.task_id, harness.actor)]


@pytest.mark.asyncio
@pytest.mark.parametrize("authorized,member,expected", [(False, True, 401), (True, False, 403)])
async def test_delete_keeps_membership_gate(harness, authorized, member, expected):
    headers = {"x-organization-id": str(harness.org if member else uuid4())}
    if authorized:
        headers["authorization"] = "Bearer synthetic"
    async with AsyncClient(transport=ASGITransport(app=harness.app), base_url="http://test") as client:
        response = await client.delete(f"/tasks/{harness.task_id}", headers=headers)
    assert response.status_code == expected
    assert harness.calls == []
