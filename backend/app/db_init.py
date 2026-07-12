"""Database bootstrap: schema creation and default seed data.

Importing this module pulls in every ORM model so ``Base.metadata`` is fully
populated before ``create_all`` runs (also used by Alembic's env).
"""

import logging
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, Base, engine

# Import ALL models so they register on the shared metadata.
from app.email.models import EmailOutbox  # noqa: F401
from app.methodology.factory import get_strategy
from app.modules.activity.models import TaskHistory  # noqa: F401
from app.modules.alert_rules.models import AlertRule  # noqa: F401
from app.modules.assets.models import Asset, AssetLicense, AssetTask  # noqa: F401
from app.modules.attachments.models import Attachment  # noqa: F401
from app.modules.boards.models import Board, BoardColumn  # noqa: F401
from app.modules.checklists.models import ChecklistItem, TaskChecklist  # noqa: F401
from app.modules.comments.models import TaskComment  # noqa: F401
from app.modules.dependencies.models import Dependency  # noqa: F401
from app.modules.labels.models import Label, TaskLabel  # noqa: F401
from app.modules.menus.models import Menu  # noqa: F401
from app.modules.notifications.models import Notification  # noqa: F401
from app.modules.organizations.models import (  # noqa: F401
    Organization,
    OrganizationMember,
)
from app.modules.projects.models import Project  # noqa: F401
from app.modules.reminders.models import Reminder, ReminderRule  # noqa: F401
from app.modules.roles.models import (  # noqa: F401
    Role,
    RoleMenu,
    UserRole,
)
from app.modules.sprints.models import Sprint  # noqa: F401
from app.modules.task_links.models import TaskDependency  # noqa: F401
from app.modules.tasks.models import Task  # noqa: F401
from app.modules.time_logs.models import TaskTimeLog  # noqa: F401
from app.modules.users.models import User  # noqa: F401
from app.shared.enums import MemberRole, Methodology, Priority, ProjectStatus
from app.shared.security import hash_password

logger = logging.getLogger("solercia.db_init")

# Demo credentials shared by every seeded member account.
_DEMO_PASSWORD = "Demo123*"
# (email, primer_nombre, primer_apellido, dependency_name, role_codes)
_DEMO_MEMBERS: list[tuple[str, str, str, str, list[str]]] = [
    ("ana@solercia.com", "Ana", "Torres", "Tecnología", ["MEMBER", "MANAGER"]),
    ("carlos@solercia.com", "Carlos", "Ruiz", "Operaciones", ["MEMBER"]),
    ("diana@solercia.com", "Diana", "Páez", "Tecnología", ["MEMBER"]),
]

# --- RBAC seed -----------------------------------------------------------
# Org-scoped areas ("dependencias").
_DEPENDENCY_SEED: list[tuple[str, str]] = [
    ("Dirección", "DIR"),
    ("Tecnología", "TEC"),
    ("Operaciones", "OPS"),
]

# RBAC roles: (code, display name).
_ROLE_SEED: list[tuple[str, str]] = [
    ("ADMIN", "Administrador"),
    ("MANAGER", "Líder"),
    ("MEMBER", "Colaborador"),
]

# App-level activities (menus): (name, icon, path, parent_name, order).
# Parents appear before their children so the parent id is available.
_MENU_SEED: list[tuple[str, str, str | None, str | None, int]] = [
    ("Proyectos", "folder-kanban", "/projects", None, 0),
    ("Vista de jefe", "bar-chart-3", "/executive", None, 1),
    ("Rendimiento", "trending-up", "/performance", None, 2),
    ("Administración", "settings", None, None, 3),
    ("Usuarios", "users", "/admin/users", "Administración", 0),
    ("Roles", "shield", "/admin/roles", "Administración", 1),
    ("Actividades", "list", "/admin/menus", "Administración", 2),
    ("Dependencias", "building-2", "/admin/dependencies", "Administración", 3),
]

# Menu grants per role. "*" grants every menu.
_ROLE_MENU_SEED: dict[str, str | list[str]] = {
    "ADMIN": "*",
    "MANAGER": ["Proyectos", "Vista de jefe", "Rendimiento"],
    "MEMBER": ["Proyectos"],
}

# Projects created only when the organization has none yet, so the board and
# the executive view are populated out of the box.
_DEMO_PROJECTS: list[tuple[str, str, Methodology]] = [
    ("Plataforma Web", "Desarrollo del nuevo portal de clientes.", Methodology.scrum),
    ("Soporte Técnico", "Atención y operación continua de incidencias.", Methodology.kanban),
    ("Mejoras Internas", "Iniciativas de mejora del equipo interno.", Methodology.planner),
]

_DEMO_TASK_TITLES: list[str] = [
    "Configurar el entorno de despliegue",
    "Diseñar la pantalla de inicio de sesión",
    "Corregir el error en el listado de usuarios",
    "Documentar la API de proyectos",
    "Implementar los filtros del tablero",
    "Optimizar las consultas del dashboard",
    "Revisar la accesibilidad de los formularios",
    "Preparar los datos de demostración",
    "Integrar la autenticación con el frontend",
    "Definir la política de respaldos",
    "Pulir los estilos del tablero",
    "Planear la próxima iteración",
]


def _derive_backfill_code(name: str) -> str:
    """Generate a code from a project name (same logic as ProjectService)."""

    clean = re.sub(r"[^a-zA-Z0-9 ]", "", name).upper()
    words = clean.split()
    if not words:
        return "PRJ"
    code = "".join(w[0] for w in words if w) if len(words) >= 2 else words[0][:6]
    if len(code) < 2:
        code = (words[0] + code)[:4]
    return code[:10]


async def _backfill_project_codes(session: AsyncSession) -> None:
    """Assign ``code`` to every project that still has ``code IS NULL``.

    Idempotent: rows that already have a code are left unchanged.
    """

    result = await session.execute(
        select(Project).where(Project.code.is_(None), Project.is_active.is_(True))
    )
    projects_without_code = list(result.scalars().all())
    if not projects_without_code:
        return

    # Track codes already assigned *in this session* to avoid clashes.
    # Existing non-null codes are loaded to avoid collisions.
    existing_result = await session.execute(
        select(Project.organization_id, Project.code).where(Project.code.isnot(None))
    )
    # {organization_id: {code, ...}}
    used: dict = {}
    for org_id, code in existing_result.all():
        used.setdefault(org_id, set()).add(code)

    for project in projects_without_code:
        base = _derive_backfill_code(project.name)
        candidate = base
        suffix = 2
        org_codes = used.setdefault(project.organization_id, set())
        while candidate in org_codes:
            candidate = f"{base[:8]}{suffix}"
            suffix += 1
        project.code = candidate
        org_codes.add(candidate)

    logger.info(
        "Backfilled project codes for %d project(s).", len(projects_without_code)
    )


async def _backfill_task_numbers(session: AsyncSession) -> None:
    """Assign ``task_number`` to every task that still has ``task_number IS NULL``.

    Tasks are numbered sequentially per project in ``created_at`` order.
    After numbering, the project's ``task_counter`` is updated to the highest
    number assigned so new task allocations continue from the correct value.
    Idempotent: tasks that already have a task_number are skipped.
    """

    # Collect all projects that have unnumbered tasks.
    project_result = await session.execute(
        select(Task.project_id)
        .where(Task.task_number.is_(None), Task.is_active.is_(True))
        .distinct()
    )
    project_ids = [row[0] for row in project_result.all()]
    if not project_ids:
        return

    for project_id in project_ids:
        # Load all unnumbered tasks ordered by creation time.
        tasks_result = await session.execute(
            select(Task)
            .where(
                Task.project_id == project_id,
                Task.task_number.is_(None),
                Task.is_active.is_(True),
            )
            .order_by(Task.created_at.asc())
        )
        unnumbered = list(tasks_result.scalars().all())
        if not unnumbered:
            continue

        # Find the current highest task_number for this project (already assigned rows).
        max_result = await session.execute(
            select(func.max(Task.task_number)).where(
                Task.project_id == project_id,
                Task.task_number.isnot(None),
            )
        )
        current_max = max_result.scalar_one() or 0

        next_number = current_max + 1
        for task in unnumbered:
            task.task_number = next_number
            next_number += 1

        # Update the project counter to match the highest assigned number.
        await session.execute(
            text(
                "UPDATE projects SET task_counter = :counter WHERE id = :pid "
                "AND task_counter < :counter"
            ),
            {"counter": next_number - 1, "pid": str(project_id)},
        )

    logger.info(
        "Backfilled task numbers for tasks in %d project(s).", len(project_ids)
    )


_DEFAULT_ALERT_RULES: list[tuple[str, bool, dict]] = [
    ("task_overdue", True, {}),
    ("task_at_risk", True, {"days_before": 3, "inactive_days": 3}),
    ("sprint_at_risk", True, {}),
    ("workload_imbalance", True, {"max_active_tasks": 8}),
    ("blocked_task", True, {"blocked_days": 3}),
    ("license_expiring", True, {"lead_days": [30, 7, 1]}),
    ("license_expired", True, {}),
]


async def _ensure_alert_rules(session: AsyncSession, organization: Organization) -> None:
    """Create default alert rules for the organization when they do not exist."""
    for rule_type, enabled, threshold_params in _DEFAULT_ALERT_RULES:
        existing = await session.execute(
            select(AlertRule).where(
                AlertRule.organization_id == organization.id,
                AlertRule.rule_type == rule_type,
            )
        )
        if existing.scalar_one_or_none() is None:
            session.add(
                AlertRule(
                    organization_id=organization.id,
                    rule_type=rule_type,
                    enabled=enabled,
                    threshold_params=threshold_params,
                )
            )


async def init_db() -> None:
    """Create all tables if they do not yet exist."""

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database schema ensured.")


async def seed_default() -> None:
    """Seed the org, RBAC catalog (dependencies/roles/menus), users and demo.

    Every step is independently idempotent. The RBAC catalog, the admin and the
    demo members (with their roles) are ensured on every startup; the demo
    projects/sprints/tasks are seeded only while no task exists yet.
    """

    async with AsyncSessionLocal() as session:
        organization = await _ensure_organization(session)

        dependencies = await _ensure_dependencies(session, organization)
        roles = await _ensure_roles(session, organization)
        menus = await _ensure_menus(session)
        await _ensure_role_menus(session, roles, menus)

        admin = await _ensure_admin(session, organization, dependencies)
        await _ensure_user_role(session, admin, roles["ADMIN"])

        members = await _ensure_demo_members(
            session, organization, dependencies, roles
        )

        await _ensure_alert_rules(session, organization)

        task_count = await session.execute(select(func.count()).select_from(Task))
        if (task_count.scalar_one() or 0) == 0:
            await _seed_demo_workitems(session, organization, members, admin)

        # Backfill project codes and task numbers for any rows that pre-date
        # these fields (idempotent — rows with values already set are skipped).
        await _backfill_project_codes(session)
        await _backfill_task_numbers(session)

        await session.commit()
        logger.info(
            "Seed completed (organization, RBAC, users and demo data ensured)."
        )


async def _ensure_dependencies(
    session: AsyncSession, organization: Organization
) -> dict[str, Dependency]:
    """Return the org's seed dependencies keyed by name, creating any missing."""

    result: dict[str, Dependency] = {}
    for name, code in _DEPENDENCY_SEED:
        existing = await session.execute(
            select(Dependency).where(
                Dependency.organization_id == organization.id,
                Dependency.name == name,
            )
        )
        dependency = existing.scalar_one_or_none()
        if dependency is None:
            dependency = Dependency(
                organization_id=organization.id, name=name, code=code
            )
            session.add(dependency)
            await session.flush()  # assign dependency.id
        result[name] = dependency
    return result


async def _ensure_roles(
    session: AsyncSession, organization: Organization
) -> dict[str, Role]:
    """Return the org's seed roles keyed by code, creating any missing."""

    result: dict[str, Role] = {}
    for code, name in _ROLE_SEED:
        existing = await session.execute(
            select(Role).where(
                Role.organization_id == organization.id,
                Role.code == code,
            )
        )
        role = existing.scalar_one_or_none()
        if role is None:
            role = Role(
                organization_id=organization.id, code=code, name=name
            )
            session.add(role)
            await session.flush()  # assign role.id
        result[code] = role
    return result


async def _ensure_menus(session: AsyncSession) -> dict[str, Menu]:
    """Return the seed menus keyed by name, creating any missing.

    Menus are global. Seed order lists parents before children so each child's
    ``parent_id`` resolves from the already-created parent.
    """

    result: dict[str, Menu] = {}
    for name, icon, path, parent_name, order in _MENU_SEED:
        parent_id = result[parent_name].id if parent_name else None
        existing = await session.execute(
            select(Menu).where(Menu.name == name)
        )
        menu = existing.scalar_one_or_none()
        if menu is None:
            menu = Menu(
                name=name,
                icon=icon,
                path=path,
                parent_id=parent_id,
                order=order,
            )
            session.add(menu)
            await session.flush()  # assign menu.id
        result[name] = menu
    return result


async def _ensure_role_menus(
    session: AsyncSession,
    roles: dict[str, Role],
    menus: dict[str, Menu],
) -> None:
    """Grant each role its seed menus, idempotently."""

    for code, spec in _ROLE_MENU_SEED.items():
        role = roles[code]
        target = (
            list(menus.values())
            if spec == "*"
            else [menus[name] for name in spec]
        )
        for menu in target:
            existing = await session.execute(
                select(RoleMenu).where(
                    RoleMenu.role_id == role.id,
                    RoleMenu.menu_id == menu.id,
                )
            )
            if existing.scalar_one_or_none() is None:
                session.add(RoleMenu(role_id=role.id, menu_id=menu.id))


async def _ensure_user_role(
    session: AsyncSession, user: User, role: Role
) -> None:
    """Attach ``role`` to ``user`` when not already assigned."""

    existing = await session.execute(
        select(UserRole).where(
            UserRole.user_id == user.id,
            UserRole.role_id == role.id,
        )
    )
    if existing.scalar_one_or_none() is None:
        session.add(UserRole(user_id=user.id, role_id=role.id))


async def _ensure_organization(session: AsyncSession) -> Organization:
    """Return the default organization, creating it when absent."""

    result = await session.execute(
        select(Organization).where(Organization.slug == "solercia")
    )
    organization = result.scalar_one_or_none()
    if organization is None:
        organization = Organization(name="Solercia", slug="solercia")
        session.add(organization)
        await session.flush()  # assign organization.id
    return organization


async def _ensure_admin(
    session: AsyncSession,
    organization: Organization,
    dependencies: dict[str, Dependency],
) -> User:
    """Return the admin user with membership, creating both when absent."""

    result = await session.execute(
        select(User).where(User.email == "admin@solercia.com")
    )
    admin = result.scalar_one_or_none()
    if admin is None:
        admin = User(
            email="admin@solercia.com",
            primer_nombre="Admin",
            primer_apellido="Solercia",
            dependency_id=dependencies["Dirección"].id,
            hashed_password=hash_password("Admin123*"),
        )
        session.add(admin)
        await session.flush()  # assign admin.id

    await _ensure_membership(session, organization, admin, MemberRole.admin)
    return admin


async def _ensure_membership(
    session: AsyncSession,
    organization: Organization,
    user: User,
    role: MemberRole,
) -> None:
    """Attach the user to the organization with ``role`` if not already a member."""

    result = await session.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization.id,
            OrganizationMember.user_id == user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        session.add(
            OrganizationMember(
                organization_id=organization.id,
                user_id=user.id,
                role=role,
            )
        )


async def _seed_demo_workitems(
    session: AsyncSession,
    organization: Organization,
    members: list[User],
    admin: User,
) -> None:
    """Seed demo projects (if needed), demo tasks and the demo Scrum sprint.

    Members and the admin already exist (ensured by :func:`seed_default`); this
    only creates the work-item demo data so the board, executive view, burndown
    and performance views are populated out of the box.
    """

    assignees = members + [admin]

    projects = await _ensure_demo_projects(session, organization)
    if not projects:
        return

    await _seed_demo_tasks(session, projects, assignees)
    await _seed_scrum_sprint(session, projects, assignees)
    logger.info("Seeded demo projects, tasks and sprint.")


async def _ensure_demo_members(
    session: AsyncSession,
    organization: Organization,
    dependencies: dict[str, Dependency],
    roles: dict[str, Role],
) -> list[User]:
    """Create demo users with split names, membership, dependency and roles."""

    members: list[User] = []
    for email, primer_nombre, primer_apellido, dep_name, role_codes in (
        _DEMO_MEMBERS
    ):
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                primer_nombre=primer_nombre,
                primer_apellido=primer_apellido,
                dependency_id=dependencies[dep_name].id,
                hashed_password=hash_password(_DEMO_PASSWORD),
            )
            session.add(user)
            await session.flush()  # assign user.id
        await _ensure_membership(session, organization, user, MemberRole.member)
        for code in role_codes:
            await _ensure_user_role(session, user, roles[code])
        members.append(user)
    return members


async def _ensure_demo_projects(
    session: AsyncSession, organization: Organization
) -> list[Project]:
    """Return the organization's projects, creating demo ones when none exist."""

    result = await session.execute(
        select(Project).where(
            Project.organization_id == organization.id,
            Project.is_active.is_(True),
        )
    )
    projects = list(result.scalars().all())
    if projects:
        return projects

    for name, description, methodology in _DEMO_PROJECTS:
        session.add(
            Project(
                name=name,
                description=description,
                methodology=methodology,
                status=ProjectStatus.active,
                organization_id=organization.id,
            )
        )
    await session.flush()  # assign project ids

    result = await session.execute(
        select(Project).where(
            Project.organization_id == organization.id,
            Project.is_active.is_(True),
        )
    )
    return list(result.scalars().all())


def _status_index_for_round(round_index: int, status_count: int) -> int:
    """Map a seeding round to a status index, clamped to the project's columns."""

    if round_index == 0:
        return 0
    if round_index == 1:
        return min(1, status_count - 1)
    if round_index == 2:
        return min(2, status_count - 1)
    return status_count - 1  # final/done column


async def _seed_demo_tasks(
    session: AsyncSession,
    projects: Sequence[Project],
    assignees: list[User],
) -> None:
    """Create ~12 demo tasks spread across projects, statuses and assignees.

    Statuses and estimation respect each project's methodology Strategy, so the
    seed never produces data the API would reject. A couple of tasks are made
    overdue and a couple are flagged at risk to populate the executive view.
    """

    now = datetime.now(UTC)
    priorities = [Priority.high, Priority.medium, Priority.critical, Priority.low]
    max_tasks = 12
    rounds = 4

    overdue_budget = 2
    risk_budget = 2
    total = 0
    title_index = 0

    for round_index in range(rounds):
        for project_index, project in enumerate(projects):
            if total >= max_tasks:
                break

            strategy = get_strategy(project.methodology)
            statuses = strategy.allowed_statuses() or ["todo", "doing", "done"]
            status_count = len(statuses)
            idx = _status_index_for_round(round_index, status_count)
            status = statuses[idx]
            is_last = idx == status_count - 1

            mode = strategy.estimation_mode
            points = None
            hours = None
            if mode in ("points", "both"):
                points = (round_index + 1) * 3 + project_index
            if mode in ("hours", "both"):
                hours = Decimal(str((round_index + 1) * 4 + project_index))

            due_date = None
            risk_flag = False
            risk_reason = None
            # Tasks sitting in the done column carry a completion timestamp so
            # the performance view has data for closed work.
            completed_at = now - timedelta(days=7) if is_last else None

            if round_index == 0:
                due_date = now + timedelta(days=5 + project_index)
                if risk_budget > 0 and project_index < 2 and not is_last:
                    risk_flag = True
                    risk_reason = "Bloqueada por una dependencia externa pendiente."
                    risk_budget -= 1
            elif round_index == 1:
                if overdue_budget > 0 and not is_last:
                    due_date = now - timedelta(days=2 + project_index)
                    overdue_budget -= 1
                else:
                    due_date = now + timedelta(days=10)
            elif round_index == 3 and is_last:
                due_date = now - timedelta(days=8)  # completed in the past

            assignee = assignees[total % len(assignees)]
            priority = priorities[total % len(priorities)]
            title = (
                _DEMO_TASK_TITLES[title_index]
                if title_index < len(_DEMO_TASK_TITLES)
                else f"Tarea de demostración {total + 1}"
            )
            title_index += 1

            session.add(
                Task(
                    project_id=project.id,
                    title=title,
                    description="Tarea de demostración generada automáticamente.",
                    task_type="task",
                    status=status,
                    priority=priority,
                    assignee_id=assignee.id,
                    estimation_points=points,
                    estimation_hours=hours,
                    due_date=due_date,
                    completed_at=completed_at,
                    order=total,
                    risk_flag=risk_flag,
                    risk_reason=risk_reason,
                )
            )
            total += 1


# (title, points, status, assignee_index, due_offset_days, completed_offset_days)
# completed_offset is ``None`` for tasks still open. A task is "on time" when its
# completion day is on/before its due day; entries where completed > due are late.
# Assignee indices map to [member0, member1, member2, admin].
_SPRINT_TASK_SPECS: list[tuple[str, int, str, int, int, int | None]] = [
    ("Modelar el esquema de la base de datos", 5, "Done", 3, -6, -7),
    ("Implementar el inicio de sesión con JWT", 8, "Done", 1, -5, -4),  # late
    ("Crear el tablero del proyecto", 3, "Done", 2, -3, -5),
    ("Construir el backlog del proyecto", 5, "Done", 0, -4, -2),  # late
    ("Agregar el gráfico burndown", 2, "Done", 1, -1, -4),
    ("Diseñar la vista de rendimiento", 3, "In Progress", 2, 3, None),
    ("Documentar los endpoints del sprint", 8, "To Do", 0, 5, None),
    ("Pulir la interfaz del sprint", 5, "In Review", 3, 6, None),
]


async def _seed_scrum_sprint(
    session: AsyncSession,
    projects: Sequence[Project],
    assignees: list[User],
) -> None:
    """Seed a populated Scrum sprint for the demo so the burndown and the
    performance views have realistic data.

    Creates "Sprint 1" (today-8 .. today+6, active) on the Scrum project and a
    handful of estimated tasks: several already completed across the past days
    (a couple finished after their due date) plus a few still open. The generic
    demo tasks of the Scrum project stay in the backlog (``sprint_id`` null) so
    the "assign backlog to sprint" flow is demoable. Idempotent: it does nothing
    when the project already has a sprint.
    """

    scrum_project = next(
        (p for p in projects if p.methodology == Methodology.scrum), None
    )
    if scrum_project is None:
        return

    existing = await session.execute(
        select(func.count())
        .select_from(Sprint)
        .where(Sprint.project_id == scrum_project.id)
    )
    if (existing.scalar_one() or 0) > 0:
        return

    now = datetime.now(UTC)
    sprint = Sprint(
        project_id=scrum_project.id,
        name="Sprint 1",
        goal="Entregar el flujo principal del tablero y el backlog.",
        start_date=now - timedelta(days=8),
        end_date=now + timedelta(days=6),
        status="active",
    )
    session.add(sprint)
    await session.flush()  # assign sprint.id

    priorities = [Priority.high, Priority.medium, Priority.critical, Priority.low]
    for order, spec in enumerate(_SPRINT_TASK_SPECS):
        title, points, status, assignee_index, due_off, done_off = spec
        assignee = assignees[assignee_index % len(assignees)]
        completed_at = (
            now + timedelta(days=done_off) if done_off is not None else None
        )
        session.add(
            Task(
                project_id=scrum_project.id,
                sprint_id=sprint.id,
                title=title,
                description="Tarea del Sprint 1 generada automáticamente.",
                task_type="task",
                status=status,
                priority=priorities[order % len(priorities)],
                assignee_id=assignee.id,
                estimation_points=points,
                due_date=now + timedelta(days=due_off),
                completed_at=completed_at,
                order=order,
            )
        )
