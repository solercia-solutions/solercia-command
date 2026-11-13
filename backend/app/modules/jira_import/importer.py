"""Use case: import ONE Jira project into the organization (idempotent).

``importar_proyecto`` fetches every issue of the project FIRST (read-only
toward Jira), then writes inside the caller's single transaction:

1. project  -> anchored ``(organization, 'jira', <project key>)``; created
   as a new ``scrum`` project (board seeded by ``ProjectService``) or reused.
2. sprints  -> anchored ``(project, 'jira', <sprint name>)``.
3. tasks    -> anchored ``(project, 'jira', <issue key>)``; pass 1 upserts
   every task without parent and reserves the new task numbers with ONE
   ``UPDATE ... RETURNING``; pass 2 links ``parent_task_id`` by Jira key.

It never commits nor rolls back: :class:`JiraImportService` owns completion,
so any failure leaves nothing behind. Re-importing reconciles anchored rows
instead of duplicating them; an anchored task whose hierarchy level changed
(epic <-> subtask) is an ambiguous conflict and aborts the whole import.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.adapters.jira.adapter import JiraAdapter
from app.integrations.adapters.jira.dtos import NormalizationReport, NormalizedJiraIssue
from app.methodology.factory import get_strategy
from app.modules.jira_import.mapper import TITLE_MAX
from app.modules.jira_import.preview import (
    project_jql,
    require_project_key,
    resolve_status,
    seconds_to_hours,
    sprint_status,
    story_points_to_int,
    suggested_code,
    validate_overrides,
)
from app.modules.jira_import.repository import JIRA_SOURCE, JiraImportRepository
from app.modules.projects.models import Project
from app.modules.projects.schemas import ProjectCreate
from app.modules.projects.service import ProjectService
from app.modules.sprints.models import Sprint
from app.modules.tasks.models import Task
from app.modules.tasks.repository import TaskRepository
from app.shared.enums import Methodology, Priority
from app.shared.exceptions import AppException

DEFAULT_METHODOLOGY = Methodology.scrum
_LEVEL = {"epic": 0, "subtask": 2}
_DEFAULT_LEVEL = 1


class JiraIssueSource(Protocol):
    """Provider port: every normalized issue matching a JQL (read-only)."""

    async def fetch_issues(
        self, jql: str
    ) -> tuple[list[NormalizedJiraIssue], NormalizationReport]: ...


class AdapterIssueSource:
    """:class:`JiraIssueSource` over the registered Jira adapter and the
    connector's decrypted credentials (never logged nor returned)."""

    def __init__(
        self,
        adapter: JiraAdapter,
        *,
        base_url: str,
        email: str,
        api_token: str,
        jira_settings: Mapping[str, Any] | None = None,
    ) -> None:
        self._adapter = adapter
        self._base_url = base_url
        self._email = email
        self._api_token = api_token
        self._jira_settings = dict(jira_settings or {})

    async def fetch_issues(
        self, jql: str
    ) -> tuple[list[NormalizedJiraIssue], NormalizationReport]:
        return await self._adapter.import_issues(
            base_url=self._base_url,
            email=self._email,
            api_token=self._api_token,
            jql=jql,
            jira_settings=self._jira_settings,
            whole_project=True,
        )


@dataclass(frozen=True)
class ImportMapping:
    """User choices for the import (prefilled from the preview)."""

    project_name: str | None = None
    project_code: str | None = None
    status_overrides: Mapping[str, str] = field(default_factory=dict)


@dataclass
class EntityCounts:
    created: int = 0
    updated: int = 0
    unchanged: int = 0


@dataclass
class ImportSummary:
    project_id: uuid.UUID
    project_code: str | None
    project_name: str
    project_created: bool
    tasks: EntityCounts = field(default_factory=EntityCounts)
    sprints: EntityCounts = field(default_factory=EntityCounts)
    parents_linked: int = 0
    orphans: list[str] = field(default_factory=list)
    unassigned: list[str] = field(default_factory=list)
    unmapped_types: dict[str, int] = field(default_factory=dict)
    unmapped_statuses: dict[str, int] = field(default_factory=dict)
    unmapped_priorities: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def _level(task_type: str) -> int:
    return _LEVEL.get(task_type, _DEFAULT_LEVEL)


def _issue_number(key: str) -> int:
    _prefix, _sep, number = key.rpartition("-")
    return int(number) if number.isdigit() else 0


def _title(issue: NormalizedJiraIssue) -> str:
    title = (issue.title or issue.key).strip() or issue.key
    return title if len(title) <= TITLE_MAX else title[: TITLE_MAX - 1].rstrip() + "…"


def _priority(value: str) -> Priority:
    try:
        return Priority(value)
    except ValueError:
        return Priority.medium


def _description(issue: NormalizedJiraIssue, *, unassigned_note: str | None) -> str | None:
    parts: list[str] = []
    title = (issue.title or "").strip()
    if len(title) > TITLE_MAX:
        parts.append(f"Título completo en Jira: {title}")
    if issue.description:
        parts.append(issue.description)
    if unassigned_note:
        parts.append(unassigned_note)
    return "\n\n".join(parts) or None


class JiraProjectImporter:
    """Writes one Jira project into the caller's session (never commits)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = JiraImportRepository(session)
        self.tasks_repo = TaskRepository(session)

    async def importar_proyecto(
        self,
        source: JiraIssueSource,
        jira_project_key: str,
        mapping: ImportMapping,
        *,
        organization_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> ImportSummary:
        """Import (or reconcile) ``jira_project_key`` for the organization."""

        jql = project_jql(require_project_key(jira_project_key))
        issues, report = await source.fetch_issues(jql)
        issues = sorted(issues, key=lambda issue: (_issue_number(issue.key), issue.key))

        project, created = await self._project(
            organization_id, jira_project_key, mapping, actor_id=actor_id
        )
        _board, columns = await self.repo.board_with_columns(project.id)
        allowed = [column.status_key for column in columns] or get_strategy(
            project.methodology
        ).allowed_statuses()
        validate_overrides(mapping.status_overrides, allowed)
        column_ids = {column.status_key: column.id for column in columns}

        summary = ImportSummary(
            project_id=project.id,
            project_code=project.code,
            project_name=project.name,
            project_created=created,
            unmapped_types=dict(report.unmapped_types),
            unmapped_statuses=dict(report.unmapped_statuses),
            unmapped_priorities=dict(report.unmapped_priorities),
            errors=[str(item.get("key") or item.get("index")) for item in report.skipped_malformed],
        )
        sprint_ids = await self._sprints(project, issues, summary, actor_id=actor_id)
        await self._tasks(
            organization_id,
            project,
            issues,
            allowed=allowed,
            column_ids=column_ids,
            sprint_ids=sprint_ids,
            overrides=mapping.status_overrides,
            summary=summary,
            actor_id=actor_id,
        )
        return summary

    # ------------------------------------------------------------------ project

    async def _project(
        self,
        organization_id: uuid.UUID,
        jira_project_key: str,
        mapping: ImportMapping,
        *,
        actor_id: uuid.UUID | None,
    ) -> tuple[Project, bool]:
        existing = await self.repo.project_by_anchor(organization_id, jira_project_key)
        if existing is not None:
            if not existing.is_active:
                raise AppException(
                    "El proyecto que se importó antes desde este proyecto de Jira fue "
                    "eliminado. Restáuralo antes de volver a importarlo.",
                    code="jira_import_project_deleted",
                    status_code=409,
                )
            return existing, False

        try:
            data = ProjectCreate(
                name=(mapping.project_name or jira_project_key).strip() or jira_project_key,
                methodology=DEFAULT_METHODOLOGY,
                code=(mapping.project_code or suggested_code(jira_project_key)).strip().upper(),
                description=f"Importado desde el proyecto {jira_project_key} de Jira.",
            )
        except ValidationError as exc:
            message = str(exc.errors()[0].get("msg", "")).removeprefix("Value error, ")
            raise AppException(
                message or "El nombre o el código del proyecto no son válidos.",
                code="jira_import_project_invalid",
                status_code=422,
            ) from exc
        project = await ProjectService(self.session)._create_project_unit(
            organization_id, data, actor_id=actor_id
        )
        project.source = JIRA_SOURCE
        project.external_key = jira_project_key
        await self.repo.flush()
        return project, True

    # ------------------------------------------------------------------ sprints

    async def _sprints(
        self,
        project: Project,
        issues: Sequence[NormalizedJiraIssue],
        summary: ImportSummary,
        *,
        actor_id: uuid.UUID | None,
    ) -> dict[str, uuid.UUID]:
        wanted: dict[str, dict[str, Any]] = {}
        for issue in issues:
            if not issue.sprint_name:
                continue
            seen = wanted.setdefault(issue.sprint_name, {})
            seen["state"] = issue.sprint_state or seen.get("state")
            seen["start_date"] = issue.sprint_start_date or seen.get("start_date")
            seen["end_date"] = issue.sprint_end_date or seen.get("end_date")
        existing = await self.repo.jira_sprints(project.id)
        ids: dict[str, uuid.UUID] = {}
        for name, raw in wanted.items():
            status = sprint_status(raw["state"])
            desired: dict[str, Any] = {"status": status}
            if raw["start_date"] is not None:
                desired["start_date"] = raw["start_date"]
            if raw["end_date"] is not None:
                desired["end_date"] = raw["end_date"]
            if status == "closed":
                desired["closed_at"] = raw["end_date"]
            sprint = existing.get(name)
            if sprint is None:
                sprint = await self.repo.add_sprint(
                    Sprint(
                        project_id=project.id,
                        name=name[:160],
                        source=JIRA_SOURCE,
                        external_key=name,
                        created_by=actor_id,
                        updated_by=actor_id,
                        **desired,
                    )
                )
                summary.sprints.created += 1
            elif any(getattr(sprint, k) != v for k, v in desired.items()):
                for key, value in desired.items():
                    setattr(sprint, key, value)
                sprint.updated_by = actor_id
                summary.sprints.updated += 1
            else:
                summary.sprints.unchanged += 1
            ids[name] = sprint.id
        return ids

    # ------------------------------------------------------------------ tasks

    async def _tasks(
        self,
        organization_id: uuid.UUID,
        project: Project,
        issues: Sequence[NormalizedJiraIssue],
        *,
        allowed: Sequence[str],
        column_ids: Mapping[str, uuid.UUID],
        sprint_ids: Mapping[str, uuid.UUID],
        overrides: Mapping[str, str],
        summary: ImportSummary,
        actor_id: uuid.UUID | None,
    ) -> None:
        existing = await self.repo.jira_tasks(organization_id, project.id)
        for issue in issues:
            current = existing.get(issue.key)
            if current is not None and _level(current.task_type) != _level(issue.issue_type):
                raise AppException(
                    f"La tarea {issue.key} ya se importó como «{current.task_type}» y ahora "
                    f"llega como «{issue.issue_type}». Revísala en Jira antes de reimportar.",
                    code="jira_import_conflict",
                    status_code=409,
                )

        emails = [issue.assignee_email for issue in issues if issue.assignee_email]
        members = await self.repo.member_user_ids_by_email(organization_id, emails)
        done_status = allowed[-1]
        now = datetime.now(UTC)

        new_tasks: list[Task] = []
        by_key: dict[str, Task] = dict(existing)
        for issue in issues:
            status = resolve_status(issue, allowed, overrides)
            assignee_id = members.get((issue.assignee_email or "").lower())
            original_assignee = issue.assignee_email or issue.assignee_raw
            note = None
            if assignee_id is None and original_assignee:
                summary.unassigned.append(issue.key)
                note = (
                    f"Asignado en Jira: {original_assignee} (no coincide con ningún "
                    "miembro de la organización)."
                )
            desired: dict[str, Any] = {
                "title": _title(issue),
                "task_type": issue.issue_type,
                "priority": _priority(issue.priority),
                "status": status,
                "board_column_id": column_ids.get(status),
                "estimation_points": story_points_to_int(issue.story_points),
                "estimation_hours": seconds_to_hours(issue.original_estimate_seconds),
                "sprint_id": sprint_ids.get(issue.sprint_name or ""),
            }
            task = existing.get(issue.key)
            if task is None:
                task = Task(
                    project_id=project.id,
                    source=JIRA_SOURCE,
                    external_key=issue.key,
                    description=_description(issue, unassigned_note=note),
                    assignee_id=assignee_id,
                    completed_at=now if status == done_status else None,
                    risk_flag=False,
                    order=_issue_number(issue.key),
                    created_by=actor_id,
                    updated_by=actor_id,
                    **desired,
                )
                if issue.created_at is not None:
                    task.created_at = issue.created_at
                new_tasks.append(task)
                summary.tasks.created += 1
            else:
                if assignee_id is not None:
                    desired["assignee_id"] = assignee_id
                if status == done_status:
                    desired["completed_at"] = task.completed_at or now
                else:
                    desired["completed_at"] = None
                changed = [k for k, v in desired.items() if getattr(task, k) != v]
                if changed:
                    for key in changed:
                        setattr(task, key, desired[key])
                    task.updated_by = actor_id
                    summary.tasks.updated += 1
                else:
                    summary.tasks.unchanged += 1
            by_key[issue.key] = task

        if new_tasks:
            last = await self.tasks_repo.allocate_task_numbers(project.id, len(new_tasks))
            first = last - len(new_tasks) + 1
            for offset, task in enumerate(new_tasks):
                task.task_number = first + offset
                await self.repo.add_task(task)
        await self.repo.flush()

        # Pass 2: link the hierarchy by Jira key, now that every id exists.
        for issue in issues:
            if not issue.parent_key:
                continue
            task = by_key[issue.key]
            parent = by_key.get(issue.parent_key)
            if parent is None:
                summary.orphans.append(issue.key)
                continue
            if task.parent_task_id != parent.id:
                task.parent_task_id = parent.id
                summary.parents_linked += 1
        await self.repo.flush()


async def importar_proyecto(
    source: JiraIssueSource,
    jira_project_key: str,
    mapping: ImportMapping,
    *,
    organization_id: uuid.UUID,
    session: AsyncSession,
    actor_id: uuid.UUID | None = None,
) -> ImportSummary:
    """Reusable seam: import one project inside ``session`` (no commit)."""

    return await JiraProjectImporter(session).importar_proyecto(
        source, jira_project_key, mapping, organization_id=organization_id, actor_id=actor_id
    )
