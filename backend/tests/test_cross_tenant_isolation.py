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
from datetime import date
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
