"""Cross-tenant isolation battery (change 25 — multiempresa-scoping).

Fija como contrato verificable la invariante: "una consulta autenticada como
empresa A jamás devuelve, modifica ni elimina ids de empresa B", en cada
módulo tenant-scoped de ``app/modules``. No introduce un filtro global de
SQLAlchemy: el aislamiento sigue siendo manual, consulta por consulta (ver
``design.md``, Decisión 1). La superficie compartida por diseño (``menus``,
plantillas ``system`` de ``org_role_templates``) se prueba con la aserción
inversa: catálogo idéntico para A y B, nunca fuga.

Contrato de aserción (design.md, Decisión 2):
- Listados / búsqueda global / dashboards: 200; ``ids ⊆ A``; ``b.id ∉ ids``.
- Detalle / update / delete por id de B autenticado como A: **404** (nunca
  403 —confirmaría existencia—, nunca 200).
- Recursos anidados (checklists/comments de una task de B): 404 vía join al
  padre.

``two_orgs`` (``conftest.py``) sigue siendo la base (org/user/token/project/
task/alert_rule/notification por organización). Las entidades pesadas por
módulo se construyen aquí con seed-helpers co-ubicados — ``two_orgs`` core
permanece intacto (design.md, Decisión 1: "solo core barato").

El **meta-test** (``test_all_modules_are_classified``) introspecciona
``app/modules/*`` por filesystem y exige que cada paquete pertenezca a
``TENANT_SCOPED | GLOBAL | INFRA_NO_READ`` — un módulo nuevo sin clasificar
rompe la suite y fuerza triaje.
"""

import os
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import TwoOrgs, skip_no_db

# ---------------------------------------------------------------------------
# Clasificación de los 28 módulos de app/modules (tasks.md, Fase 0.3)
# ---------------------------------------------------------------------------

# Módulos tenant-scoped: ninguna operación de una organización debe exponer,
# modificar ni eliminar entidades de otra (listado/detalle/update/delete).
TENANT_SCOPED: frozenset[str] = frozenset(
    {
        "projects",
        "tasks",
        "sprints",
        "boards",
        "dependencies",
        "task_links",
        "checklists",
        "time_logs",
        "activity",
        "labels",
        "comments",
        "attachments",
        "notifications",
        "reminders",
        "users",
        "roles",
        "search",
        "dashboard",
        "assets",
        "alert_rules",
        "intake",
        "glpi_sync",
        "jira_import",
        "organizations",
        "connectors",
    }
)

# Módulos con superficie compartida por diseño (catálogo idéntico para
# cualquier organización) — compartir NO es una fuga. ``org_role_templates``
# también recibe tests tenant-scoped para sus plantillas org-scoped (Fase 4),
# pero su clasificación de bucket es GLOBAL (tasks.md, Fase 0.3).
GLOBAL: frozenset[str] = frozenset({"menus", "org_role_templates"})

# Módulos sin superficie de lectura cross-tenant relevante para esta batería
# (auth: solo login/refresh/logout/me — sin listado ni detalle por id ajeno).
INFRA_NO_READ: frozenset[str] = frozenset({"auth"})


_APP_MODULES_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "app", "modules")
)


def _discover_app_modules() -> set[str]:
    """Return every module package name under ``app/modules`` (filesystem).

    Ignores ``__pycache__`` and ``__init__.py`` — only directories that are
    actual module packages count.
    """

    return {
        entry
        for entry in os.listdir(_APP_MODULES_DIR)
        if entry not in {"__pycache__", "__init__.py"}
        and os.path.isdir(os.path.join(_APP_MODULES_DIR, entry))
    }


def test_all_modules_are_classified() -> None:
    """Every module under ``app/modules`` MUST belong to exactly one bucket.

    A new module added to ``app/modules`` without updating the classification
    above makes this test fail, listing exactly which modules are missing —
    this forces a deliberate triage (tenant-scoped? global? infra?) instead of
    silently shipping an unaudited surface.
    """

    discovered = _discover_app_modules()
    classified = TENANT_SCOPED | GLOBAL | INFRA_NO_READ

    missing = discovered - classified
    assert not missing, f"Módulos sin clasificar en test_cross_tenant_isolation.py: {sorted(missing)}"

    stale = classified - discovered
    assert not stale, f"Módulos clasificados que ya no existen en app/modules: {sorted(stale)}"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Seed-helpers locales (tasks.md, Fase 1.3) — entidades no cubiertas por
# ``_seed_org_data``/``two_orgs`` (conftest.py:376-475). ``two_orgs`` core
# permanece intacto: estos helpers solo insertan filas adicionales sobre la
# misma sesión de test, para los módulos "pesados" de la batería.
# ---------------------------------------------------------------------------


async def _seed_second_task(session: AsyncSession, project, assignee_id: uuid.UUID):
    """A second task in ``project``, for modules that need two tasks (task_links)."""

    from app.modules.tasks.models import Task

    task = Task(
        project_id=project.id,
        title=f"{project.name} Second Task",
        status="Backlog",
        assignee_id=assignee_id,
    )
    session.add(task)
    await session.flush()
    return task


async def _seed_scrum_project(session: AsyncSession, organization):
    """A scrum-methodology project — ``two_orgs`` seeds ``kanban`` (no sprints)."""

    from app.modules.projects.models import Project
    from app.shared.enums import Methodology

    project = Project(
        organization_id=organization.id,
        name=f"{organization.name} Scrum Project",
        methodology=Methodology.scrum,
        code=f"SCR{uuid.uuid4().hex[:5].upper()}",
        task_counter=0,
    )
    session.add(project)
    await session.flush()
    return project


async def _seed_sprint(session: AsyncSession, project):
    from app.modules.sprints.models import Sprint

    sprint = Sprint(project_id=project.id, name=f"{project.name} Sprint")
    session.add(sprint)
    await session.flush()
    return sprint


async def _seed_board(session: AsyncSession, project):
    from app.modules.boards.models import Board, BoardColumn

    board = Board(project_id=project.id)
    session.add(board)
    await session.flush()
    column = BoardColumn(board_id=board.id, name="To Do", status_key="to_do", order=0)
    session.add(column)
    await session.flush()
    return board, column


async def _seed_dependency_area(session: AsyncSession, organization):
    """Seed-helper for ``app.modules.dependencies`` (organizational areas)."""

    from app.modules.dependencies.models import Dependency

    area = Dependency(organization_id=organization.id, name=f"{organization.name} Área")
    session.add(area)
    await session.flush()
    return area


async def _seed_task_dependency(session: AsyncSession, organization, blocker_task, blocked_task):
    from app.modules.task_links.models import TaskDependency

    edge = TaskDependency(
        organization_id=organization.id,
        blocker_task_id=blocker_task.id,
        blocked_task_id=blocked_task.id,
    )
    session.add(edge)
    await session.flush()
    return edge


async def _seed_checklist(session: AsyncSession, organization, task):
    from app.modules.checklists.models import TaskChecklist

    checklist = TaskChecklist(
        organization_id=organization.id, task_id=task.id, title="Checklist"
    )
    session.add(checklist)
    await session.flush()
    return checklist


async def _seed_checklist_item(session: AsyncSession, organization, checklist):
    from app.modules.checklists.models import ChecklistItem

    item = ChecklistItem(
        organization_id=organization.id, checklist_id=checklist.id, text="Ítem"
    )
    session.add(item)
    await session.flush()
    return item


async def _seed_time_log(session: AsyncSession, organization, task, user):
    from app.modules.time_logs.models import TaskTimeLog

    log = TaskTimeLog(
        organization_id=organization.id,
        task_id=task.id,
        user_id=user.id,
        work_date=date.today(),
        hours=Decimal("2.0"),
    )
    session.add(log)
    await session.flush()
    return log


async def _seed_task_history(session: AsyncSession, organization, task, actor):
    from app.modules.activity.models import TaskHistory

    row = TaskHistory(
        organization_id=organization.id,
        task_id=task.id,
        actor_id=actor.id,
        actor_type="user",
        field="status",
        old_value="Backlog",
        new_value="In Progress",
    )
    session.add(row)
    await session.flush()
    return row


async def _seed_label(session: AsyncSession, organization, project):
    from app.modules.labels.models import Label

    label = Label(
        organization_id=organization.id,
        project_id=project.id,
        name=f"{organization.name} Label",
        color="#ff0000",
    )
    session.add(label)
    await session.flush()
    return label


async def _seed_comment(session: AsyncSession, organization, task, author):
    from app.modules.comments.models import TaskComment

    comment = TaskComment(
        organization_id=organization.id,
        task_id=task.id,
        author_id=author.id,
        body="Comentario de prueba",
    )
    session.add(comment)
    await session.flush()
    return comment


async def _seed_attachment(session: AsyncSession, organization, task, uploader):
    from app.modules.attachments.models import Attachment

    attachment = Attachment(
        organization_id=organization.id,
        target_type="task",
        target_id=task.id,
        original_name="archivo.txt",
        stored_name=str(uuid.uuid4()),
        content_type="text/plain",
        size_bytes=10,
        uploaded_by=uploader.id,
    )
    session.add(attachment)
    await session.flush()
    return attachment


async def _seed_reminder(session: AsyncSession, organization, user):
    from app.modules.reminders.models import Reminder

    reminder = Reminder(
        organization_id=organization.id,
        user_id=user.id,
        remind_at=datetime.now(UTC) + timedelta(days=1),
        message="Recordatorio de prueba",
    )
    session.add(reminder)
    await session.flush()
    return reminder


# ---------------------------------------------------------------------------
# Fase 2 — Proyecto y ejecución (tasks.md, Commit 2)
# ---------------------------------------------------------------------------

# projects: el listado y el detalle-404 ya están cubiertos por
# test_multi_tenancy.py (R1); aquí se agrega solo el update-rechazado que
# faltaba para completar el contrato de la Fase 2.


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_project_from_other_org_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    response = await client.patch(
        f"/projects/{two_orgs.b.project.id}",
        json={"name": "hackeado"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_tasks_only_returns_callers_organization(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    response = await client.get(
        f"/projects/{two_orgs.a.project.id}/tasks", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert str(two_orgs.a.task.id) in ids
    assert str(two_orgs.b.task.id) not in ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_task_from_other_org_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    response = await client.get(
        f"/tasks/{two_orgs.b.task.id}", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_task_from_other_org_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    response = await client.patch(
        f"/tasks/{two_orgs.b.task.id}",
        json={"title": "hackeado"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_task_from_other_org_returns_404_and_task_survives(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    response = await client.delete(
        f"/tasks/{two_orgs.b.task.id}", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 404
    await session.refresh(two_orgs.b.task)
    assert two_orgs.b.task.is_active is True


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_sprints_only_returns_callers_organization(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    project_a = await _seed_scrum_project(session, two_orgs.a.organization)
    project_b = await _seed_scrum_project(session, two_orgs.b.organization)
    sprint_a = await _seed_sprint(session, project_a)
    sprint_b = await _seed_sprint(session, project_b)

    response = await client.get(
        f"/projects/{project_a.id}/sprints", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert str(sprint_a.id) in ids
    assert str(sprint_b.id) not in ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_sprint_from_other_org_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    sprint_b = await _seed_sprint(session, two_orgs.b.project)

    response = await client.patch(
        f"/sprints/{sprint_b.id}",
        json={"name": "hackeado"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_rename_board_column_from_other_org_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    board_b, column_b = await _seed_board(session, two_orgs.b.project)

    response = await client.patch(
        f"/boards/{board_b.id}/columns/{column_b.id}",
        json={"name": "hackeado"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_dependency_areas_only_returns_callers_organization(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    await rbac_admin(session, two_orgs.a.organization, two_orgs.a.user)
    area_a = await _seed_dependency_area(session, two_orgs.a.organization)
    area_b = await _seed_dependency_area(session, two_orgs.b.organization)

    response = await client.get(
        "/admin/dependencies", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert str(area_a.id) in ids
    assert str(area_b.id) not in ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_and_delete_dependency_area_from_other_org_return_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    await rbac_admin(session, two_orgs.a.organization, two_orgs.a.user)
    area_b = await _seed_dependency_area(session, two_orgs.b.organization)

    update_response = await client.patch(
        f"/admin/dependencies/{area_b.id}",
        json={"name": "hackeado"},
        headers=_auth(two_orgs.a.token),
    )
    delete_response = await client.delete(
        f"/admin/dependencies/{area_b.id}", headers=_auth(two_orgs.a.token)
    )

    assert update_response.status_code == 404
    assert delete_response.status_code == 404
    await session.refresh(area_b)
    assert area_b.is_active is True


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_unlink_task_dependency_from_other_org_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    second_task_b = await _seed_second_task(session, two_orgs.b.project, two_orgs.b.user.id)
    edge_b = await _seed_task_dependency(
        session, two_orgs.b.organization, two_orgs.b.task, second_task_b
    )

    response = await client.delete(
        f"/tasks/{two_orgs.a.task.id}/dependencies/{edge_b.id}",
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404
    await session.refresh(edge_b)
    assert edge_b.is_active is True


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_and_delete_checklist_from_other_org_return_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    checklist_b = await _seed_checklist(session, two_orgs.b.organization, two_orgs.b.task)

    update_response = await client.patch(
        f"/checklists/{checklist_b.id}",
        json={"title": "hackeado"},
        headers=_auth(two_orgs.a.token),
    )
    delete_response = await client.delete(
        f"/checklists/{checklist_b.id}", headers=_auth(two_orgs.a.token)
    )

    assert update_response.status_code == 404
    assert delete_response.status_code == 404
    await session.refresh(checklist_b)
    assert checklist_b.is_active is True


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_and_delete_checklist_item_from_other_org_return_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    checklist_b = await _seed_checklist(session, two_orgs.b.organization, two_orgs.b.task)
    item_b = await _seed_checklist_item(session, two_orgs.b.organization, checklist_b)

    update_response = await client.patch(
        f"/checklist-items/{item_b.id}",
        json={"text": "hackeado"},
        headers=_auth(two_orgs.a.token),
    )
    delete_response = await client.delete(
        f"/checklist-items/{item_b.id}", headers=_auth(two_orgs.a.token)
    )

    assert update_response.status_code == 404
    assert delete_response.status_code == 404
    await session.refresh(item_b)
    assert item_b.is_active is True


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_and_delete_time_log_from_other_org_return_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    log_b = await _seed_time_log(
        session, two_orgs.b.organization, two_orgs.b.task, two_orgs.b.user
    )

    update_response = await client.patch(
        f"/time-logs/{log_b.id}",
        json={"note": "hackeado"},
        headers=_auth(two_orgs.a.token),
    )
    delete_response = await client.delete(
        f"/time-logs/{log_b.id}", headers=_auth(two_orgs.a.token)
    )

    assert update_response.status_code == 404
    assert delete_response.status_code == 404
    await session.refresh(log_b)
    assert log_b.is_active is True


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_task_history_of_other_org_task_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    await _seed_task_history(
        session, two_orgs.b.organization, two_orgs.b.task, two_orgs.b.user
    )

    response = await client.get(
        f"/tasks/{two_orgs.b.task.id}/history", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_labels_only_returns_callers_organization(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    label_a = await _seed_label(session, two_orgs.a.organization, two_orgs.a.project)
    label_b = await _seed_label(session, two_orgs.b.organization, two_orgs.b.project)

    response = await client.get(
        f"/projects/{two_orgs.a.project.id}/labels", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert str(label_a.id) in ids
    assert str(label_b.id) not in ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_and_delete_label_from_other_org_return_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    label_b = await _seed_label(session, two_orgs.b.organization, two_orgs.b.project)

    update_response = await client.patch(
        f"/labels/{label_b.id}",
        json={"name": "hackeado"},
        headers=_auth(two_orgs.a.token),
    )
    delete_response = await client.delete(
        f"/labels/{label_b.id}", headers=_auth(two_orgs.a.token)
    )

    assert update_response.status_code == 404
    assert delete_response.status_code == 404
    await session.refresh(label_b)
    assert label_b.is_active is True


# ---------------------------------------------------------------------------
# Fase 3 — Colaboración (tasks.md, Commit 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_comments_only_returns_callers_organization(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    comment_a = await _seed_comment(
        session, two_orgs.a.organization, two_orgs.a.task, two_orgs.a.user
    )
    comment_b = await _seed_comment(
        session, two_orgs.b.organization, two_orgs.b.task, two_orgs.b.user
    )

    response = await client.get(
        f"/tasks/{two_orgs.a.task.id}/comments", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert str(comment_a.id) in ids
    assert str(comment_b.id) not in ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_and_delete_comment_from_other_org_return_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    comment_b = await _seed_comment(
        session, two_orgs.b.organization, two_orgs.b.task, two_orgs.b.user
    )

    update_response = await client.patch(
        f"/comments/{comment_b.id}",
        json={"body": "hackeado"},
        headers=_auth(two_orgs.a.token),
    )
    delete_response = await client.delete(
        f"/comments/{comment_b.id}", headers=_auth(two_orgs.a.token)
    )

    assert update_response.status_code == 404
    assert delete_response.status_code == 404
    await session.refresh(comment_b)
    assert comment_b.is_active is True


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_attachments_only_returns_callers_organization(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    attachment_a = await _seed_attachment(
        session, two_orgs.a.organization, two_orgs.a.task, two_orgs.a.user
    )
    attachment_b = await _seed_attachment(
        session, two_orgs.b.organization, two_orgs.b.task, two_orgs.b.user
    )

    response = await client.get(
        f"/tasks/{two_orgs.a.task.id}/attachments", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert str(attachment_a.id) in ids
    assert str(attachment_b.id) not in ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_download_attachment_from_other_org_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    attachment_b = await _seed_attachment(
        session, two_orgs.b.organization, two_orgs.b.task, two_orgs.b.user
    )

    response = await client.get(
        f"/attachments/{attachment_b.id}/download", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_notifications_only_returns_callers_organization(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    response = await client.get("/notifications", headers=_auth(two_orgs.a.token))

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert str(two_orgs.a.notification.id) in ids
    assert str(two_orgs.b.notification.id) not in ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_notification_status_from_other_org_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    response = await client.patch(
        f"/notifications/{two_orgs.b.notification.id}",
        json={"status": "read"},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_reminders_only_returns_callers_organization(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    reminder_a = await _seed_reminder(session, two_orgs.a.organization, two_orgs.a.user)
    reminder_b = await _seed_reminder(session, two_orgs.b.organization, two_orgs.b.user)

    response = await client.get("/reminders", headers=_auth(two_orgs.a.token))

    assert response.status_code == 200, response.text
    ids = {row["id"] for row in response.json()["data"]}
    assert str(reminder_a.id) in ids
    assert str(reminder_b.id) not in ids


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_update_and_delete_reminder_from_other_org_return_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    reminder_b = await _seed_reminder(session, two_orgs.b.organization, two_orgs.b.user)

    update_response = await client.patch(
        f"/reminders/{reminder_b.id}",
        json={"message": "hackeado"},
        headers=_auth(two_orgs.a.token),
    )
    delete_response = await client.delete(
        f"/reminders/{reminder_b.id}", headers=_auth(two_orgs.a.token)
    )

    assert update_response.status_code == 404
    assert delete_response.status_code == 404
    await session.refresh(reminder_b)
    assert reminder_b.is_active is True
