"""Use case: apply (or simulate) a :class:`FeedPlan` for one organization.

Idempotency anchors:

* users        -> ``federated_identities(issuer=https://<site>, subject=accountId)``,
                  then the org's connected Jira account, then a real email
* memberships  -> ``(organization_id, user_id)``; existing roles are never touched
* projects     -> ``(organization_id, code)``
* columns      -> ``(board_id, status_key)`` (missing ones are added, none removed)
* sprints      -> ``(project_id, name)``
* tasks        -> ``(project_id, source='jira', external_key=<issue key>)``

``write=False`` (dry-run) walks the exact same path but never adds, flushes
nor mutates an ORM object, so it runs inside a ``READ ONLY`` transaction.
Transaction completion belongs to the caller (:class:`SessionJiraFeedUow`).
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import FederatedIdentity
from app.modules.boards.models import Board, BoardColumn
from app.modules.jira_import.mapper import FeedPlan, PlannedProject
from app.modules.jira_import.repository import (
    JIRA_IDENTITY_PROVIDER,
    JIRA_SOURCE,
    JiraFeedRepository,
)
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.projects.models import Project
from app.modules.roles.models import UserRole
from app.modules.sprints.models import Sprint
from app.modules.tasks.models import Task
from app.modules.users.models import User
from app.shared.enums import MemberRole, Methodology, Priority, ProjectKind, ProjectStatus

MEMBER_ROLE_CODE = "MEMBER"
_TASK_FIELDS = (
    "title",
    "description",
    "task_type",
    "priority",
    "status",
    "board_column_id",
    "assignee_id",
    "estimation_points",
    "due_date",
    "start_date",
    "completed_at",
    "sprint_id",
    "order",
)
_SPRINT_FIELDS = ("goal", "status", "start_date", "end_date", "closed_at", "completed_points")


@dataclass
class Counter:
    created: int = 0
    updated: int = 0
    unchanged: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "creados": self.created,
            "actualizados": self.updated,
            "sin_cambios": self.unchanged,
        }


@dataclass
class ApplyResult:
    users: Counter = field(default_factory=Counter)
    identities: Counter = field(default_factory=Counter)
    memberships: Counter = field(default_factory=Counter)
    user_roles: Counter = field(default_factory=Counter)
    projects: Counter = field(default_factory=Counter)
    columns: Counter = field(default_factory=Counter)
    sprints: Counter = field(default_factory=Counter)
    tasks: Counter = field(default_factory=Counter)
    parents_linked: int = 0
    per_project: dict[str, dict[str, Any]] = field(default_factory=dict)
    warnings: dict[str, int] = field(default_factory=dict)

    def warn(self, code: str) -> None:
        self.warnings[code] = self.warnings.get(code, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "usuarios": self.users.as_dict(),
            "identidades_jira": self.identities.as_dict(),
            "membresias": self.memberships.as_dict(),
            "roles_member": self.user_roles.as_dict(),
            "proyectos": self.projects.as_dict(),
            "columnas": self.columns.as_dict(),
            "sprints": self.sprints.as_dict(),
            "tareas": self.tasks.as_dict(),
            "padres_enlazados": self.parents_linked,
            "por_proyecto": self.per_project,
            "advertencias_aplicacion": self.warnings,
        }


def _differs(current: Any, desired: Any) -> bool:
    return current != desired


class JiraFeedApplier:
    """Walks a plan against the database; ``write`` decides if it persists."""

    def __init__(
        self, repo: JiraFeedRepository, organization: Organization, *, write: bool
    ) -> None:
        self.repo = repo
        self.org = organization
        self.write = write
        self.result = ApplyResult()
        self.account_to_user: dict[str, uuid.UUID] = {}

    async def run(self, plan: FeedPlan) -> ApplyResult:
        await self._users(plan)
        task_ids: dict[str, uuid.UUID] = {}
        pending_parents: list[tuple[Task | None, str, str, uuid.UUID | None]] = []
        for project in plan.projects:
            await self._project(project, task_ids, pending_parents)
        for task, _key, parent_key, current_parent in pending_parents:
            parent_id = task_ids.get(parent_key)
            if parent_id is None:
                self.result.warn("padre_no_encontrado")
                continue
            if current_parent != parent_id:
                self.result.parents_linked += 1
                if self.write and task is not None:
                    task.parent_task_id = parent_id
        if self.write:
            await self.repo.flush()
        return self.result

    # ------------------------------------------------------------------ users

    async def _users(self, plan: FeedPlan) -> None:
        issuer = f"https://{plan.site_host}"
        identities = await self.repo.identities_by_subject(issuer)
        links = await self.repo.jira_account_links(self.org.id)
        by_email = await self.repo.users_by_emails([u.email for u in plan.users])
        memberships = await self.repo.memberships(self.org.id)
        with_role = await self.repo.users_with_org_role(self.org.id)
        member_role = await self.repo.role_by_code(self.org.id, MEMBER_ROLE_CODE)
        if member_role is None:
            self.result.warn("rol_member_inexistente")

        for planned in plan.users:
            user_id = identities.get(planned.account_id) or links.get(planned.account_id)
            if user_id is None and planned.email in by_email:
                user_id = by_email[planned.email].id
            if user_id is None:
                self.result.users.created += 1
                user = User(
                    email=planned.email,
                    primer_nombre=planned.primer_nombre,
                    segundo_nombre=planned.segundo_nombre,
                    primer_apellido=planned.primer_apellido,
                    segundo_apellido=planned.segundo_apellido,
                    hashed_password=None,
                    is_active=planned.active,
                )
                if self.write:
                    user = await self.repo.add_user(user)
                    user_id = user.id
                else:
                    user_id = uuid.uuid4()
            else:
                self.result.users.unchanged += 1
            self.account_to_user[planned.account_id] = user_id

            if planned.account_id in identities:
                self.result.identities.unchanged += 1
            else:
                self.result.identities.created += 1
                if self.write:
                    await self.repo.add_identity(
                        FederatedIdentity(
                            user_id=user_id,
                            provider=JIRA_IDENTITY_PROVIDER,
                            issuer=issuer,
                            subject=planned.account_id,
                            email=None if planned.email_is_placeholder else planned.email,
                        )
                    )

            if user_id in memberships:
                self.result.memberships.unchanged += 1
            else:
                self.result.memberships.created += 1
                if self.write:
                    await self.repo.add_membership(
                        OrganizationMember(
                            organization_id=self.org.id, user_id=user_id, role=MemberRole.member
                        )
                    )
            if user_id in with_role or member_role is None:
                self.result.user_roles.unchanged += 1
            else:
                self.result.user_roles.created += 1
                with_role.add(user_id)
                if self.write:
                    await self.repo.add_user_role(UserRole(user_id=user_id, role_id=member_role.id))
        if self.write:
            await self.repo.flush()

    # ------------------------------------------------------------------ projects

    async def _project(
        self,
        planned: PlannedProject,
        task_ids: dict[str, uuid.UUID],
        pending_parents: list,
    ) -> None:
        stats: dict[str, Any] = {"nombre": planned.name, "metodologia": planned.methodology}
        project = await self.repo.project_by_code(self.org.id, planned.code)
        is_new = project is None
        if project is None:
            self.result.projects.created += 1
            project = Project(
                organization_id=self.org.id,
                name=planned.name,
                description=planned.description,
                methodology=Methodology(planned.methodology),
                status=ProjectStatus.active,
                code=planned.code,
                task_counter=0,
                project_kind=ProjectKind.proyecto,
                lead_user_id=self.account_to_user.get(planned.lead_account_id or ""),
            )
            if self.write:
                project = await self.repo.add_project(project)
            else:
                project.id = uuid.uuid4()
        else:
            self.result.projects.unchanged += 1
            if project.methodology.value != planned.methodology:
                self.result.warn("metodologia_existente_conservada")
            stats["metodologia"] = project.methodology.value
        stats["proyecto_nuevo"] = is_new

        column_ids = await self._columns(project, planned, is_new)
        sprint_ids = await self._sprints(project, planned, is_new)
        await self._tasks(
            project, planned, is_new, column_ids, sprint_ids, task_ids, pending_parents, stats
        )
        self.result.per_project[planned.key] = stats

    async def _columns(
        self, project: Project, planned: PlannedProject, is_new: bool
    ) -> dict[str, uuid.UUID]:
        board, existing = (None, []) if is_new else await self.repo.board_with_columns(project.id)
        if board is None:
            board = Board(project_id=project.id)
            if self.write:
                board = await self.repo.add_board(board)
            else:
                board.id = uuid.uuid4()
        by_key = {column.status_key: column for column in existing}
        ids: dict[str, uuid.UUID] = {}
        next_order = max((c.order for c in existing), default=-1) + 1
        for planned_column in planned.columns:
            column = by_key.get(planned_column.status_key)
            if column is not None:
                self.result.columns.unchanged += 1
                ids[planned_column.status_key] = column.id
                continue
            self.result.columns.created += 1
            column = BoardColumn(
                board_id=board.id,
                name=planned_column.name,
                status_key=planned_column.status_key,
                order=next_order,
            )
            next_order += 1
            if self.write:
                column = await self.repo.add_column(column)
            else:
                column.id = uuid.uuid4()
            ids[planned_column.status_key] = column.id
            by_key[column.status_key] = column
        done_key = planned.done_status
        if (
            existing
            and done_key in by_key
            and by_key[done_key].order != max(c.order for c in by_key.values())
        ):
            # Command treats the last column as "done": keep it last.
            self.result.warn("columna_finalizada_reubicada_al_final")
            if self.write:
                by_key[done_key].order = next_order
        return ids

    async def _sprints(
        self, project: Project, planned: PlannedProject, is_new: bool
    ) -> dict[int, uuid.UUID]:
        existing = {} if is_new else await self.repo.sprints_by_name(project.id)
        ids: dict[int, uuid.UUID] = {}
        for planned_sprint in planned.sprints:
            desired = {name: getattr(planned_sprint, name) for name in _SPRINT_FIELDS}
            sprint = existing.get(planned_sprint.name)
            if sprint is None:
                self.result.sprints.created += 1
                sprint = Sprint(project_id=project.id, name=planned_sprint.name, **desired)
                if self.write:
                    sprint = await self.repo.add_sprint(sprint)
                else:
                    sprint.id = uuid.uuid4()
            elif any(_differs(getattr(sprint, k), v) for k, v in desired.items()):
                self.result.sprints.updated += 1
                if self.write:
                    for name, value in desired.items():
                        setattr(sprint, name, value)
            else:
                self.result.sprints.unchanged += 1
            ids[planned_sprint.jira_id] = sprint.id
        return ids

    async def _tasks(
        self,
        project: Project,
        planned: PlannedProject,
        is_new: bool,
        column_ids: dict[str, uuid.UUID],
        sprint_ids: dict[int, uuid.UUID],
        task_ids: dict[str, uuid.UUID],
        pending_parents: list,
        stats: dict[str, Any],
    ) -> None:
        existing = {} if is_new else await self.repo.jira_tasks(self.org.id, project.id)
        used_numbers = set() if is_new else await self.repo.used_task_numbers(project.id)
        counter = Counter()
        by_status: dict[str, int] = {}
        max_number = project.task_counter or 0
        new_tasks: list[tuple[Task, Any]] = []
        for planned_task in planned.tasks:
            by_status[planned_task.status] = by_status.get(planned_task.status, 0) + 1
            desired = {
                "title": planned_task.title,
                "description": planned_task.description,
                "task_type": planned_task.task_type,
                "priority": Priority(planned_task.priority),
                "status": planned_task.status,
                "board_column_id": column_ids.get(planned_task.status),
                "assignee_id": self.account_to_user.get(planned_task.assignee_account_id or ""),
                "estimation_points": planned_task.estimation_points,
                "due_date": planned_task.due_date,
                "start_date": planned_task.start_date,
                "completed_at": planned_task.completed_at,
                "sprint_id": sprint_ids.get(planned_task.sprint_jira_id or -1),
                "order": planned_task.number,
            }
            task = existing.get(planned_task.key)
            if task is None:
                counter.created += 1
                number = planned_task.number if planned_task.number not in used_numbers else None
                if number is None:
                    self.result.warn("numero_de_tarea_ocupado")
                else:
                    used_numbers.add(number)
                    max_number = max(max_number, number)
                task = Task(
                    project_id=project.id,
                    source=JIRA_SOURCE,
                    external_key=planned_task.key,
                    task_number=number,
                    risk_flag=False,
                    created_by=self.account_to_user.get(planned_task.reporter_account_id or ""),
                    **desired,
                )
                if planned_task.created_at is not None:
                    task.created_at = planned_task.created_at
                if planned_task.updated_at is not None:
                    task.updated_at = planned_task.updated_at
                task.id = uuid.uuid4()
                new_tasks.append((task, planned_task))
                if self.write:
                    await self.repo.add_task(task)
            else:
                if task.task_number:
                    max_number = max(max_number, task.task_number)
                changed = [k for k, v in desired.items() if _differs(getattr(task, k), v)]
                if changed:
                    counter.updated += 1
                    if self.write:
                        for name in changed:
                            setattr(task, name, desired[name])
                        if planned_task.updated_at is not None:
                            task.updated_at = planned_task.updated_at
                else:
                    counter.unchanged += 1
            task_ids[planned_task.key] = task.id
            if planned_task.parent_key:
                pending_parents.append(
                    (task, planned_task.key, planned_task.parent_key, task.parent_task_id)
                )

        # Tasks whose Jira number was taken get the next free numbers.
        for task, _planned in new_tasks:
            if task.task_number is None:
                max_number += 1
                task.task_number = max_number
        if self.write and max_number != (project.task_counter or 0):
            project.task_counter = max_number
        if self.write:
            await self.repo.flush()

        self.result.tasks.created += counter.created
        self.result.tasks.updated += counter.updated
        self.result.tasks.unchanged += counter.unchanged
        stats["tareas"] = counter.as_dict()
        stats["tareas_por_estado"] = by_status
        stats["sprints"] = len(planned.sprints)
        stats["columnas"] = [c.status_key for c in planned.columns]


class SessionJiraFeedUow:
    """Explicit unit of work: one session, one repository, one commit."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = JiraFeedRepository(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


async def run_feed(
    uow: SessionJiraFeedUow, organization: Organization, plan: FeedPlan, *, write: bool
) -> ApplyResult:
    """Apply (``write=True``, commits once) or simulate (rolls back) the plan."""

    try:
        result = await JiraFeedApplier(uow.repo, organization, write=write).run(plan)
    except Exception:
        await uow.rollback()
        raise
    if write:
        await uow.commit()
    else:
        await uow.rollback()
    return result
