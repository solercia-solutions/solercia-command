"""Jira project importer against the real PostgreSQL test database.

Most scenarios feed normalized issues through a fake ``JiraIssueSource``;
the anti-injection and mid-pagination failure scenarios go through the real
adapter with ``httpx.MockTransport`` (zero network).
"""

import uuid
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.adapters.jira.dtos import NormalizationReport, NormalizedJiraIssue
from app.modules.projects.models import Project
from app.modules.sprints.models import Sprint
from app.modules.tasks.models import Task
from app.shared.exceptions import AppException
from tests.conftest import TwoOrgs, skip_no_db


def _issue(key: str, issue_type: str = "story", **overrides: object) -> NormalizedJiraIssue:
    base = NormalizedJiraIssue(
        key=key,
        title=f"Issue {key}",
        description=None,
        issue_type=issue_type,
        status_raw="To Do",
        status_bucket="todo",
        priority="medium",
        assignee_raw=None,
        sprint_name=None,
        sprint_state=None,
        story_points=None,
        labels=(),
        created_at=None,
        source="api",
    )
    return replace(base, **overrides)


def _report(issues: list[NormalizedJiraIssue]) -> NormalizationReport:
    return NormalizationReport(
        total=len(issues),
        normalized=len(issues),
        unmapped_types={},
        unmapped_statuses={},
        unmapped_priorities={},
        story_points_field=None,
        sprint_field=None,
        source="api",
    )


class FakeSource:
    def __init__(self, issues: list[NormalizedJiraIssue]) -> None:
        self.issues = issues
        self.jqls: list[str] = []

    async def fetch_issues(self, jql: str):
        self.jqls.append(jql)
        return list(self.issues), _report(self.issues)


def _hierarchy() -> list[NormalizedJiraIssue]:
    return [
        _issue("PROJ-1", "epic"),
        _issue("PROJ-2", "story", parent_key="PROJ-1"),
        _issue("PROJ-3", "story", parent_key="PROJ-1"),
        _issue("PROJ-4", "subtask", parent_key="PROJ-2"),
        _issue("PROJ-5", "subtask", parent_key="PROJ-3"),
    ]


async def _import(session, org_id, issues, key="PROJ", **mapping):
    from app.modules.jira_import.importer import ImportMapping, importar_proyecto

    return await importar_proyecto(
        FakeSource(issues),
        key,
        ImportMapping(**mapping),
        organization_id=org_id,
        session=session,
    )


async def _tasks(session: AsyncSession, project_id: uuid.UUID) -> dict[str, Task]:
    result = await session.execute(select(Task).where(Task.project_id == project_id))
    return {task.external_key: task for task in result.scalars()}


async def _count(session: AsyncSession, model) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


class TestJqlInjection:
    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_rejects_project_key_that_fails_jql_safe_pattern(
        self, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        """jql_injection: a malicious key is refused before any JQL or HTTP."""

        from app.integrations.adapters.jira.adapter import JiraAdapter
        from app.modules.jira_import.importer import (
            AdapterIssueSource,
            ImportMapping,
            importar_proyecto,
        )

        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(200, json={})

        source = AdapterIssueSource(
            JiraAdapter(transport=httpx.MockTransport(handler)),
            base_url="https://acme.atlassian.net",
            email="mia@acme.com",
            api_token="SECRET",
        )
        with pytest.raises(AppException) as excinfo:
            await importar_proyecto(
                source,
                'ABC" OR 1=1--',
                ImportMapping(),
                organization_id=two_orgs.a.organization.id,
                session=session,
            )

        assert excinfo.value.status_code == 422
        assert calls == 0


class TestHierarchy:
    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_jerarquia_epic_story_subtask_dos_pasadas(
        self, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        summary = await _import(session, two_orgs.a.organization.id, _hierarchy())

        tasks = await _tasks(session, summary.project_id)
        assert tasks["PROJ-2"].parent_task_id == tasks["PROJ-1"].id
        assert tasks["PROJ-3"].parent_task_id == tasks["PROJ-1"].id
        assert tasks["PROJ-4"].parent_task_id == tasks["PROJ-2"].id
        assert tasks["PROJ-5"].parent_task_id == tasks["PROJ-3"].id
        assert tasks["PROJ-1"].parent_task_id is None
        assert sorted(t.task_number for t in tasks.values()) == [1, 2, 3, 4, 5]
        assert tasks["PROJ-1"].task_number == 1
        assert all(t.source == "jira" for t in tasks.values())
        assert summary.tasks.created == 5
        assert summary.parents_linked == 4

        project = await session.get(Project, summary.project_id)
        assert project.code == "PROJ"
        assert project.source == "jira"
        assert project.external_key == "PROJ"
        assert project.methodology.value == "scrum"

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_subtarea_huerfana_sin_padre_en_el_set(
        self, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        issues = [_issue("PROJ-1"), _issue("PROJ-2", "subtask", parent_key="PROJ-99")]

        summary = await _import(session, two_orgs.a.organization.id, issues)

        tasks = await _tasks(session, summary.project_id)
        assert tasks["PROJ-2"].parent_task_id is None
        assert summary.orphans == ["PROJ-2"]


class TestTaskNumbers:
    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_task_key_atomico_por_bloque(
        self, session: AsyncSession, two_orgs: TwoOrgs, monkeypatch
    ) -> None:
        from app.modules.tasks.repository import TaskRepository

        calls: list[int] = []
        original = TaskRepository.allocate_task_numbers

        async def spy(self, project_id, count):
            calls.append(count)
            return await original(self, project_id, count)

        monkeypatch.setattr(TaskRepository, "allocate_task_numbers", spy)
        org_id = two_orgs.a.organization.id

        summary = await _import(session, org_id, _hierarchy())
        project = await session.get(Project, summary.project_id)
        assert calls == [5]
        assert project.task_counter == 5

        again = await _import(session, org_id, _hierarchy())
        await session.refresh(project)
        assert calls == [5]  # nothing new -> no counter consumed
        assert project.task_counter == 5
        assert again.tasks.created == 0

        grown = await _import(session, org_id, [*_hierarchy(), _issue("PROJ-6")])
        await session.refresh(project)
        assert calls == [5, 1]
        assert (await _tasks(session, project.id))["PROJ-6"].task_number == 6
        assert grown.tasks.created == 1


class TestMapping:
    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_mapeo_estado_via_strategy_sin_if_methodology(
        self, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        from app.methodology.scrum import ScrumStrategy

        allowed = ScrumStrategy().allowed_statuses()
        issues = [
            _issue("PROJ-1", status_raw="Abierto", status_bucket="todo"),
            _issue("PROJ-2", status_raw="En curso", status_bucket="in_progress"),
            _issue("PROJ-3", status_raw="Cerrado", status_bucket="done"),
        ]

        summary = await _import(session, two_orgs.a.organization.id, issues)

        tasks = await _tasks(session, summary.project_id)
        assert tasks["PROJ-1"].status == allowed[0]
        assert tasks["PROJ-2"].status == "In Progress"
        assert tasks["PROJ-3"].status == allowed[-1]
        assert tasks["PROJ-3"].completed_at is not None
        assert tasks["PROJ-1"].completed_at is None
        assert all(task.board_column_id is not None for task in tasks.values())

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_status_override_wins_and_unknown_target_is_rejected(
        self, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        issues = [_issue("PROJ-1", status_raw="En revisión", status_bucket="in_progress")]

        summary = await _import(
            session,
            two_orgs.a.organization.id,
            issues,
            status_overrides={"En revisión": "In Review"},
        )
        assert (await _tasks(session, summary.project_id))["PROJ-1"].status == "In Review"

        with pytest.raises(AppException) as excinfo:
            await _import(
                session,
                two_orgs.b.organization.id,
                issues,
                status_overrides={"En revisión": "Inventado"},
            )
        assert excinfo.value.status_code == 422

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_sprint_state_future_activo_cerrado_mapea_a_draft_active_closed(
        self, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        start = datetime(2024, 3, 1, 8, tzinfo=UTC)
        end = datetime(2024, 3, 15, 17, tzinfo=UTC)
        issues = [
            _issue(
                "PROJ-1",
                sprint_name="Futuro",
                sprint_state="future",
                sprint_start_date=start,
                sprint_end_date=end,
            ),
            _issue("PROJ-2", sprint_name="Actual", sprint_state="active"),
            _issue("PROJ-3", sprint_name="Pasado", sprint_state="closed", sprint_end_date=end),
        ]

        summary = await _import(session, two_orgs.a.organization.id, issues)

        result = await session.execute(
            select(Sprint).where(Sprint.project_id == summary.project_id)
        )
        sprints = {sprint.name: sprint for sprint in result.scalars()}
        assert sprints["Futuro"].status == "draft"
        assert sprints["Futuro"].start_date == start
        assert sprints["Futuro"].end_date == end
        assert sprints["Actual"].status == "active"
        assert sprints["Pasado"].status == "closed"
        assert sprints["Pasado"].closed_at == end
        assert all(s.source == "jira" and s.external_key == s.name for s in sprints.values())
        tasks = await _tasks(session, summary.project_id)
        assert tasks["PROJ-1"].sprint_id == sprints["Futuro"].id
        assert summary.sprints.created == 3

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_estimation_conversion_seconds_a_horas_y_story_points(
        self, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        issues = [_issue("PROJ-1", original_estimate_seconds=14400, story_points=5.0)]

        summary = await _import(session, two_orgs.a.organization.id, issues)

        task = (await _tasks(session, summary.project_id))["PROJ-1"]
        assert task.estimation_hours == Decimal("4")
        assert task.estimation_points == 5

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_asignado_email_match_y_sin_match(
        self, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        member_email = two_orgs.a.user.email
        issues = [
            _issue("PROJ-1", assignee_raw="acc-1", assignee_email=member_email.upper()),
            _issue("PROJ-2", assignee_raw="acc-2", assignee_email="ajeno@otra.org"),
            # A member of ANOTHER organization never matches.
            _issue("PROJ-3", assignee_raw="acc-3", assignee_email=two_orgs.b.user.email),
        ]

        summary = await _import(session, two_orgs.a.organization.id, issues)

        tasks = await _tasks(session, summary.project_id)
        assert tasks["PROJ-1"].assignee_id == two_orgs.a.user.id
        assert tasks["PROJ-2"].assignee_id is None
        assert "Asignado en Jira: ajeno@otra.org" in (tasks["PROJ-2"].description or "")
        assert tasks["PROJ-3"].assignee_id is None
        assert summary.unassigned == ["PROJ-2", "PROJ-3"]


class TestReimport:
    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_reimportar_no_duplica_reconcilia(
        self, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        org_id = two_orgs.a.organization.id
        first = await _import(session, org_id, _hierarchy(), project_name="Nombre local")
        projects_before = await _count(session, Project)
        tasks_before = await _count(session, Task)

        changed = [
            replace(issue, title="Versión editada") if issue.key == "PROJ-2" else issue
            for issue in _hierarchy()
        ]
        second = await _import(session, org_id, changed)

        assert second.project_id == first.project_id
        assert second.project_created is False
        assert second.tasks.created == 0
        assert second.tasks.updated == 1
        assert second.tasks.unchanged == 4
        assert await _count(session, Project) == projects_before
        assert await _count(session, Task) == tasks_before
        tasks = await _tasks(session, first.project_id)
        assert tasks["PROJ-2"].title == "Versión editada"
        project = await session.get(Project, first.project_id)
        assert project.name == "Nombre local"

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_conflicto_ambiguo_se_rechaza(
        self, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        org_id = two_orgs.a.organization.id
        await _import(session, org_id, _hierarchy())
        tasks_before = await _count(session, Task)
        sprints_before = await _count(session, Sprint)

        conflicting = [
            replace(issue, issue_type="subtask") if issue.key == "PROJ-1" else issue
            for issue in _hierarchy()
        ] + [_issue("PROJ-9", sprint_name="Nuevo", sprint_state="active")]

        with pytest.raises(AppException) as excinfo:
            async with session.begin_nested():
                await _import(session, org_id, conflicting)

        assert excinfo.value.status_code == 409
        assert "PROJ-1" in excinfo.value.detail
        assert await _count(session, Task) == tasks_before
        assert await _count(session, Sprint) == sprints_before


class TestFailureMidImport:
    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_fallo_a_mitad_de_import_hace_rollback_total(
        self, session: AsyncSession, two_orgs: TwoOrgs
    ) -> None:
        """rollback_total: page 2 fails -> the error propagates, nothing persists."""

        import json
        from pathlib import Path

        from app.integrations.adapters.jira import errors
        from app.integrations.adapters.jira.adapter import JiraAdapter
        from app.modules.jira_import.importer import (
            AdapterIssueSource,
            ImportMapping,
            importar_proyecto,
        )

        fixtures = Path(__file__).parent / "fixtures" / "jira"
        fields = json.loads((fixtures / "fields.json").read_text(encoding="utf-8"))
        page1 = json.loads((fixtures / "search_page1.json").read_text(encoding="utf-8"))

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/rest/api/3/field":
                return httpx.Response(200, json=fields)
            if request.url.params.get("nextPageToken"):
                return httpx.Response(500, json={"errorMessages": ["boom"]})
            return httpx.Response(200, json=page1)

        source = AdapterIssueSource(
            JiraAdapter(transport=httpx.MockTransport(handler)),
            base_url="https://acme.atlassian.net",
            email="mia@acme.com",
            api_token="SECRET",
        )
        counts_before = [await _count(session, m) for m in (Project, Sprint, Task)]

        with pytest.raises(errors.JiraUnavailable):
            await importar_proyecto(
                source,
                "PROJ",
                ImportMapping(),
                organization_id=two_orgs.a.organization.id,
                session=session,
            )

        assert [await _count(session, m) for m in (Project, Sprint, Task)] == counts_before
