"""Confirm/persist of the checklist plan (T05f): classify, then apply atomically.

Transaction ownership (agents/rules/solercia-persistence.md): the adapter
(:class:`SqlChecklistImportStore`) only flushes; :func:`apply_checklist_plan`
owns completion through :class:`ChecklistImportUow` and commits ONCE or rolls
back everything. Every read and write is scoped to one organization.

Re-run semantics (docs/plans/command-institutional-plans-2026.md):

* existing anchor, same business fields -> ``unchanged`` (no write);
* existing anchor, different fields -> ``changed``: reported, and written only
  with ``update_existing=True`` — a revised file never silently overwrites
  later work done in Command;
* anchor of a soft-deleted task -> ``inactive``: never resurrected nor
  duplicated;
* anchor living in another project than the mapping says -> ``project_mismatch``:
  never moved automatically.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.boards.models import Board, BoardColumn
from app.modules.organizations.models import OrganizationMember
from app.modules.projects.models import Project
from app.modules.tasks.models import Task
from app.modules.users.models import User
from app.shared.enums import Priority

from .checklist_import import CHECKLIST_SOURCE, ChecklistPlan, TaskDraft, body_of

Outcome = Literal["create", "unchanged", "changed", "inactive", "project_mismatch"]


@dataclass(frozen=True)
class AnchorState:
    task_id: uuid.UUID
    project_id: uuid.UUID
    project_code: str
    is_active: bool
    title: str
    description: str | None
    status: str
    priority: str
    due_date: datetime | None


@dataclass(frozen=True)
class ProjectTarget:
    project_id: uuid.UUID
    code: str
    #: active ``status_key`` -> ``board_column_id`` of the project's active board.
    columns: dict[str, uuid.UUID]


class ChecklistImportStore(Protocol):
    async def find_anchors(
        self, organization_id: uuid.UUID, source: str, keys: list[str]
    ) -> dict[str, AnchorState]: ...

    async def project_targets(
        self, organization_id: uuid.UUID, codes: list[str]
    ) -> dict[str, ProjectTarget]: ...

    async def find_member(self, organization_id: uuid.UUID, email: str) -> uuid.UUID | None: ...

    async def create_task(self, task: Task) -> Task: ...

    async def update_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID, values: dict[str, object]
    ) -> None: ...


class ChecklistImportUow(Protocol):
    store: ChecklistImportStore

    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class SqlChecklistImportStore:
    """SQLAlchemy adapter bound to the caller's session. Never commits."""

    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    async def find_anchors(
        self, organization_id: uuid.UUID, source: str, keys: list[str]
    ) -> dict[str, AnchorState]:
        """Anchors of ``keys`` in the organization, INCLUDING soft-deleted tasks.

        If more than one row holds a key (only possible across projects or
        after soft deletes) the active one wins, then the oldest.
        """

        if not keys:
            return {}
        result = await self.db.execute(
            select(Task, Project.code)
            .join(Project, Project.id == Task.project_id)
            .where(
                Project.organization_id == organization_id,
                Task.source == source,
                Task.external_key.in_(keys),
            )
            .order_by(Task.is_active.desc(), Task.created_at.asc(), Task.id.asc())
        )
        anchors: dict[str, AnchorState] = {}
        for task, project_code in result.all():
            if task.external_key in anchors:
                continue
            anchors[task.external_key] = AnchorState(
                task_id=task.id,
                project_id=task.project_id,
                project_code=project_code,
                is_active=bool(task.is_active),
                title=task.title,
                description=task.description,
                status=task.status,
                priority=getattr(task.priority, "value", task.priority),
                due_date=task.due_date,
            )
        return anchors

    async def project_targets(
        self, organization_id: uuid.UUID, codes: list[str]
    ) -> dict[str, ProjectTarget]:
        result = await self.db.execute(
            select(Project.id, Project.code, BoardColumn.status_key, BoardColumn.id)
            .select_from(Project)
            .outerjoin(Board, (Board.project_id == Project.id) & Board.is_active.is_(True))
            .outerjoin(
                BoardColumn,
                (BoardColumn.board_id == Board.id) & BoardColumn.is_active.is_(True),
            )
            .where(
                Project.organization_id == organization_id,
                Project.code.in_(codes),
                Project.is_active.is_(True),
            )
        )
        targets: dict[str, ProjectTarget] = {}
        for project_id, code, status_key, column_id in result.all():
            target = targets.setdefault(code, ProjectTarget(project_id, code, {}))
            if status_key is not None:
                target.columns[status_key] = column_id
        return targets

    async def find_member(self, organization_id: uuid.UUID, email: str) -> uuid.UUID | None:
        return await self.db.scalar(
            select(User.id)
            .join(OrganizationMember, OrganizationMember.user_id == User.id)
            .where(
                OrganizationMember.organization_id == organization_id,
                User.email == email,
                User.is_active.is_(True),
            )
        )

    async def create_task(self, task: Task) -> Task:
        """Allocate the project sequence in this transaction, then flush."""

        task.task_number = (
            await self.db.execute(
                text(
                    "UPDATE projects SET task_counter = task_counter + 1 "
                    "WHERE id = :project_id RETURNING task_counter"
                ),
                {"project_id": str(task.project_id)},
            )
        ).scalar_one()
        self.db.add(task)
        await self.db.flush()
        return task

    async def update_task(
        self, organization_id: uuid.UUID, task_id: uuid.UUID, values: dict[str, object]
    ) -> None:
        task = await self.db.scalar(
            select(Task)
            .join(Project, Project.id == Task.project_id)
            .where(Task.id == task_id, Project.organization_id == organization_id)
        )
        if task is None:
            raise LookupError("La tarea anclada ya no existe en la organización.")
        for name, value in values.items():
            setattr(task, name, value)
        await self.db.flush()


class SessionChecklistImportUow:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.store: ChecklistImportStore = SqlChecklistImportStore(session)

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self) -> None:
        await self.session.rollback()


@dataclass(frozen=True)
class Classified:
    draft: TaskDraft
    outcome: Outcome
    anchor: AnchorState | None
    differences: tuple[str, ...] = ()


def _differences(draft: TaskDraft, anchor: AnchorState) -> tuple[str, ...]:
    diffs = []
    if anchor.title != draft.title:
        diffs.append("title")
    if body_of(anchor.description) != draft.body:
        diffs.append("description")
    if anchor.status != draft.status_key:
        diffs.append("status")
    if anchor.priority != draft.priority:
        diffs.append("priority")
    if anchor.due_date != draft.due_date:
        diffs.append("due_date")
    return tuple(diffs)


def classify(
    plan: ChecklistPlan,
    anchors: dict[str, AnchorState],
    targets: dict[str, ProjectTarget],
) -> list[Classified]:
    """Pure: decide what applying ``plan`` would do against ``anchors``."""

    result = []
    for draft in plan.drafts:
        anchor = anchors.get(draft.external_key)
        if anchor is None:
            result.append(Classified(draft, "create", None))
        elif not anchor.is_active:
            result.append(Classified(draft, "inactive", anchor))
        elif anchor.project_code != draft.project_code:
            result.append(Classified(draft, "project_mismatch", anchor))
        else:
            diffs = _differences(draft, anchor)
            result.append(Classified(draft, "changed" if diffs else "unchanged", anchor, diffs))
    return result


class ChecklistTargetError(ValueError):
    """The organization lacks a project or board column the plan needs."""


def require_targets(plan: ChecklistPlan, targets: dict[str, ProjectTarget]) -> list[str]:
    """Return every missing project/column; empty when the plan is placeable."""

    missing = []
    for code in sorted({draft.project_code for draft in plan.drafts}):
        if code not in targets:
            missing.append(f"Falta el proyecto activo {code}.")
    for draft in plan.drafts:
        target = targets.get(draft.project_code)
        if target is not None and draft.status_key not in target.columns:
            missing.append(
                f"{draft.source_id}: el tablero de {draft.project_code} no tiene la columna "
                f"«{draft.status_key}»."
            )
    return missing


@dataclass
class ApplyResult:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    changed_not_applied: list[str] = field(default_factory=list)
    inactive: list[str] = field(default_factory=list)
    project_mismatch: list[str] = field(default_factory=list)


async def apply_checklist_plan(
    uow: ChecklistImportUow,
    organization_id: uuid.UUID,
    plan: ChecklistPlan,
    *,
    actor_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None,
    update_existing: bool = False,
) -> ApplyResult:
    """Write the plan in ONE transaction; any failure rolls everything back."""

    try:
        store = uow.store
        keys = [draft.external_key for draft in plan.drafts]
        if len(set(keys)) != len(keys):
            raise ValueError("La planificación repite una clave de negocio; no se aplica.")
        targets = await store.project_targets(
            organization_id, sorted({draft.project_code for draft in plan.drafts})
        )
        missing = require_targets(plan, targets)
        if missing:
            raise ChecklistTargetError(" ".join(missing))
        anchors = await store.find_anchors(organization_id, CHECKLIST_SOURCE, keys)
        result = ApplyResult()
        for item in classify(plan, anchors, targets):
            draft = item.draft
            target = targets[draft.project_code]
            if item.outcome == "create":
                await store.create_task(
                    Task(
                        id=uuid.uuid4(),
                        project_id=target.project_id,
                        title=draft.title,
                        description=draft.description,
                        task_type="task",
                        status=draft.status_key,
                        board_column_id=target.columns[draft.status_key],
                        priority=Priority(draft.priority),
                        assignee_id=assignee_id,
                        due_date=draft.due_date,
                        order=draft.row,
                        source=CHECKLIST_SOURCE,
                        external_key=draft.external_key,
                        created_by=actor_id,
                        updated_by=actor_id,
                    )
                )
                result.created.append(draft.source_id)
            elif item.outcome == "unchanged":
                result.unchanged.append(draft.source_id)
            elif item.outcome == "changed" and update_existing:
                await store.update_task(
                    organization_id,
                    item.anchor.task_id,  # type: ignore[union-attr]
                    {
                        "title": draft.title,
                        "description": draft.description,
                        "status": draft.status_key,
                        "board_column_id": target.columns[draft.status_key],
                        "priority": Priority(draft.priority),
                        "due_date": draft.due_date,
                        "updated_by": actor_id,
                    },
                )
                result.updated.append(draft.source_id)
            elif item.outcome == "changed":
                result.changed_not_applied.append(draft.source_id)
            elif item.outcome == "inactive":
                result.inactive.append(draft.source_id)
            else:
                result.project_mismatch.append(draft.source_id)
        await uow.commit()
        return result
    except BaseException:
        await uow.rollback()
        raise
