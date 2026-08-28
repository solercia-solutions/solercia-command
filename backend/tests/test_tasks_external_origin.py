"""Tests for the external-origin anchor on tasks (change 43-tareas-origen-externo).

Covers spec `tasks` scenarios 10-13 and 16-26 (design.md rebanada B): the
closed `source` vocabulary, the read seam `TaskRepository.get_by_external_key`,
the write path `TaskService.create_task(..., external_origin=...)`, API
immutability of the anchor and its exposure in `TaskRead`. Scenarios 14-15
(equality filters) belong to rebanada C and are NOT covered here.

Every anchored row in this file is created through
`TaskService(session).create_task(..., external_origin=(source, external_key))`
— never with a raw `UPDATE` (design.md D-D): the anchor already has a
legitimate write path, and testing against an `UPDATE` would test a path the
application never uses.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import Organization
from app.modules.projects.models import Project
from app.modules.tasks.models import Task
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.schemas import TaskCreate
from app.modules.tasks.service import TaskService
from app.modules.tasks.sources import KNOWN_TASK_SOURCES, validate_task_source
from app.modules.users.models import User
from app.shared.exceptions import AppException
from tests.conftest import skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_project(
    client: AsyncClient, token: str, name: str = "External Origin Project"
) -> str:
    response = await client.post(
        "/projects", json={"name": name, "methodology": "kanban"}, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return str(response.json()["data"]["id"])


# ---- Pure unit tests: no DB, no @skip_no_db (design.md "Estructura de los dos
# archivos nuevos") ----------------------------------------------------------


def test_planner_is_rejected_as_a_task_source() -> None:
    """Escenario 11: `planner` no es un valor válido de `source`."""

    with pytest.raises(AppException) as exc_info:
        validate_task_source("planner")

    assert exc_info.value.code == "invalid_task_source"
    assert exc_info.value.status_code == 422
    assert "planner" not in exc_info.value.detail


def test_every_registered_adapter_provider_is_a_known_task_source() -> None:
    """Escenario 10 — guardia contra deriva del catálogo de adaptadores.

    Nace en rojo únicamente porque `sources.py` aún no existe; una vez verde
    queda como guardia permanente (design.md D-C).

    Filtra `_ADAPTERS` a instancias cuya clase vive bajo
    `app.integrations.adapters.*` (los siete adaptadores reales que
    `app/db_init.py` importa). Es necesario porque `_ADAPTERS` es un registro
    global de proceso, compartido por toda la sesión de pytest:
    `tests/test_integration_registry.py` y `tests/test_connectors_api_token.py`
    registran ahí sus propios adaptadores de prueba (``test-outlook``,
    ``test-gmail``, ``fake-api-token``), sin limpieza al terminar — una
    brecha de aislamiento preexistente, ajena a este cambio, que solo se
    manifiesta al correr la suite completa en cierto orden. Sin el filtro,
    esta guardia sería un falso positivo dependiente del orden de ejecución.
    """

    import app.db_init  # noqa: F401 — registers every real adapter as a side effect
    from app.integrations.registry import _ADAPTERS

    registered_providers = {
        adapter.provider
        for adapter in _ADAPTERS.values()
        if type(adapter).__module__.startswith("app.integrations.adapters.")
    }
    assert registered_providers <= KNOWN_TASK_SOURCES
    assert validate_task_source("microsoft365") == "microsoft365"


def test_is_context_and_merge_into_are_not_persisted_columns() -> None:
    """Escenario 24 — guardia: ninguna es columna real de `Task`."""

    column_names = {column.name for column in Task.__table__.columns}
    assert "is_context" not in column_names
    assert "merge_into" not in column_names


def test_patch_records_no_history_entry_for_source_or_external_key() -> None:
    """Escenario 23 — guardia: `_HISTORY_TRACKED_FIELDS` no las incluye."""

    assert "source" not in TaskService._HISTORY_TRACKED_FIELDS
    assert "external_key" not in TaskService._HISTORY_TRACKED_FIELDS


# ---- Escritura reservada: create_task(..., external_origin=...) -----------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_task_with_external_origin_persists_and_exposes_the_anchor(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """Escenario 18: `create_task` con `external_origin` válido persiste y
    expone el ancla, y una relectura la conserva."""

    _, token = user
    project_id = await _create_project(client, token)
    service = TaskService(session)

    created = await service.create_task(
        tenant.id,
        uuid.UUID(project_id),
        TaskCreate(title="Importada de Jira"),
        external_origin=("jira", "PROJ-1"),
    )

    assert created.source == "jira"
    assert created.external_key == "PROJ-1"

    reread = await service.get_task(tenant.id, created.id)
    assert reread.source == "jira"
    assert reread.external_key == "PROJ-1"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_create_task_rejects_an_anchor_already_active_in_the_organization(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """Escenario 19: un ancla ya activa en otro proyecto de la misma
    organización aborta la creación con 409, sin insertar ninguna fila."""

    _, token = user
    project_a = await _create_project(client, token, "Origen A")
    project_b = await _create_project(client, token, "Origen B")
    service = TaskService(session)

    await service.create_task(
        tenant.id,
        uuid.UUID(project_a),
        TaskCreate(title="Tarea original"),
        external_origin=("jira", "PROJ-1"),
    )

    with pytest.raises(AppException) as exc_info:
        await service.create_task(
            tenant.id,
            uuid.UUID(project_b),
            TaskCreate(title="Tarea duplicada"),
            external_origin=("jira", "PROJ-1"),
        )

    assert exc_info.value.code == "task_external_anchor_conflict"
    assert exc_info.value.status_code == 409

    response = await client.get(f"/projects/{project_b}/tasks", headers=_auth(token))
    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_external_anchor_conflict_does_not_consume_task_number(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """A rejected cross-project anchor must leave the target counter intact."""

    _, token = user
    project_a = await _create_project(client, token, "Counter source")
    project_b = await _create_project(client, token, "Counter target")
    service = TaskService(session)

    await service.create_task(
        tenant.id,
        uuid.UUID(project_a),
        TaskCreate(title="Original"),
        external_origin=("jira", "PROJ-counter"),
    )

    with pytest.raises(AppException) as exc_info:
        await service.create_task(
            tenant.id,
            uuid.UUID(project_b),
            TaskCreate(title="Rejected duplicate"),
            external_origin=("jira", "PROJ-counter"),
        )

    assert exc_info.value.code == "task_external_anchor_conflict"

    manual = await service.create_task(
        tenant.id, uuid.UUID(project_b), TaskCreate(title="First accepted task")
    )
    assert manual.task_number == 1


# ---- Costura de repositorio: get_by_external_key ---------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_by_external_key_finds_an_anchor_inside_the_organization(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """Escenario 20."""

    _, token = user
    project_id = await _create_project(client, token)
    service = TaskService(session)
    created = await service.create_task(
        tenant.id,
        uuid.UUID(project_id),
        TaskCreate(title="Anclada"),
        external_origin=("jira", "PROJ-1"),
    )

    repo = TaskRepository(session)
    found = await repo.get_by_external_key(tenant.id, "jira", "PROJ-1")

    assert found is not None
    assert found.id == created.id


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_by_external_key_never_crosses_organizations(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    second_tenant: Organization,
    user: tuple[User, str],
) -> None:
    """Escenario 21."""

    _, token = user
    project_id = await _create_project(client, token)
    service = TaskService(session)
    await service.create_task(
        tenant.id,
        uuid.UUID(project_id),
        TaskCreate(title="Anclada en A"),
        external_origin=("jira", "PROJ-1"),
    )

    repo = TaskRepository(session)
    found = await repo.get_by_external_key(second_tenant.id, "jira", "PROJ-1")

    assert found is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_by_external_key_excludes_soft_deleted_tasks_and_projects(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """Escenario 22, dos casos: `Task.is_active=false` y `Project.is_active=false`."""

    _, token = user
    service = TaskService(session)
    repo = TaskRepository(session)

    # Caso 1: la propia tarea fue borrada suavemente.
    project_a = await _create_project(client, token, "Proyecto A")
    task_a = await service.create_task(
        tenant.id,
        uuid.UUID(project_a),
        TaskCreate(title="Tarea borrada"),
        external_origin=("jira", "PROJ-1"),
    )
    await service.delete_task(tenant.id, task_a.id)
    assert await repo.get_by_external_key(tenant.id, "jira", "PROJ-1") is None

    # Caso 2: la tarea sigue activa pero su proyecto fue borrado suavemente.
    project_b = await _create_project(client, token, "Proyecto B")
    await service.create_task(
        tenant.id,
        uuid.UUID(project_b),
        TaskCreate(title="Proyecto borrado"),
        external_origin=("jira", "PROJ-2"),
    )
    project_row = await session.get(Project, uuid.UUID(project_b))
    assert project_row is not None
    project_row.is_active = False
    await session.flush()

    assert await repo.get_by_external_key(tenant.id, "jira", "PROJ-2") is None


# ---- Conviven: task_key + external_key -------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_detail_exposes_task_key_and_external_key_side_by_side(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """Escenario 12."""

    _, token = user
    project_id = await _create_project(client, token)
    service = TaskService(session)
    created = await service.create_task(
        tenant.id,
        uuid.UUID(project_id),
        TaskCreate(title="Importada"),
        external_origin=("jira", "PROJ-123"),
    )

    response = await client.get(f"/tasks/{created.id}", headers=_auth(token))
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["task_key"] is not None
    assert data["external_key"] == "PROJ-123"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_listing_and_executive_dashboard_expose_source_and_external_key(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """Escenario 13 — sin editar `TaskService._to_read` ni
    `DashboardService._to_read`. La tarea vencida y sin completar cae en
    `at_risk` del panel ejecutivo."""

    _, token = user
    project_id = await _create_project(client, token)
    service = TaskService(session)
    past_due = datetime.now(UTC) - timedelta(days=1)
    await service.create_task(
        tenant.id,
        uuid.UUID(project_id),
        TaskCreate(title="Vencida y anclada", due_date=past_due),
        external_origin=("jira", "PROJ-77"),
    )

    listing = await client.get(f"/projects/{project_id}/tasks", headers=_auth(token))
    assert listing.status_code == 200, listing.text
    anchored_in_list = [
        task for task in listing.json()["data"] if task["external_key"] == "PROJ-77"
    ]
    assert len(anchored_in_list) == 1
    assert anchored_in_list[0]["source"] == "jira"

    dashboard = await client.get("/dashboard/executive", headers=_auth(token))
    assert dashboard.status_code == 200, dashboard.text
    anchored_at_risk = [
        task
        for task in dashboard.json()["data"]["at_risk"]
        if task.get("external_key") == "PROJ-77"
    ]
    assert len(anchored_at_risk) == 1
    assert anchored_at_risk[0]["source"] == "jira"


# ---- Inmutabilidad del ancla por API ---------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_post_with_external_key_in_the_body_is_ignored_without_a_validation_error(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Escenario 16."""

    _, token = user
    project_id = await _create_project(client, token)

    response = await client.post(
        f"/projects/{project_id}/tasks",
        json={"title": "Intento de secuestro", "external_key": "T-05", "source": "jira"},
        headers=_auth(token),
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["external_key"] is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_patch_with_source_never_alters_an_existing_anchor(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """Escenario 17."""

    _, token = user
    project_id = await _create_project(client, token)
    service = TaskService(session)
    created = await service.create_task(
        tenant.id,
        uuid.UUID(project_id),
        TaskCreate(title="Anclada por un importador"),
        external_origin=("jira", "PROJ-1"),
    )

    response = await client.patch(
        f"/tasks/{created.id}",
        json={"status": "Doing", "source": "mcp"},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "Doing"
    assert data["source"] == "jira"
    assert data["external_key"] == "PROJ-1"


# ---- Exact external-origin filters (change 43, rebanada C) ----------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_source_and_external_key_filters_compose_with_status(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """Escenario 14: each exact filter narrows the same listing."""

    _, token = user
    project_id = await _create_project(client, token)
    service = TaskService(session)

    await service.create_task(
        tenant.id,
        uuid.UUID(project_id),
        TaskCreate(title="Expected", status="Doing"),
        external_origin=("checklist_xlsx", "T-05"),
    )
    await service.create_task(
        tenant.id,
        uuid.UUID(project_id),
        TaskCreate(title="Wrong key", status="Doing"),
        external_origin=("checklist_xlsx", "T-06"),
    )
    await service.create_task(
        tenant.id,
        uuid.UUID(project_id),
        TaskCreate(title="Wrong source", status="Doing"),
        external_origin=("jira", "T-05"),
    )

    response = await client.get(
        f"/projects/{project_id}/tasks",
        params={
            "status": "Doing",
            "source": "checklist_xlsx",
            "external_key": "T-05",
        },
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["title"] == "Expected"
    assert data[0]["source"] == "checklist_xlsx"
    assert data[0]["external_key"] == "T-05"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_a_filter_without_matches_returns_an_empty_collection_with_200(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """Escenario 15: a non-match is an empty successful collection."""

    _, token = user
    project_id = await _create_project(client, token)
    await TaskService(session).create_task(
        tenant.id, uuid.UUID(project_id), TaskCreate(title="Manual task")
    )

    response = await client.get(
        f"/projects/{project_id}/tasks",
        params={"source": "checklist_xlsx", "external_key": "T-404"},
        headers=_auth(token),
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"] == []
