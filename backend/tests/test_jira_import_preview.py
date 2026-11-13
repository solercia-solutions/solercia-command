"""Preview of a Jira project import: pure function, never touches the DB."""

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.adapters.jira.dtos import NormalizationReport, NormalizedJiraIssue
from app.methodology.scrum import ScrumStrategy
from tests.conftest import skip_no_db


def _issue(key: str, issue_type: str, **overrides: object) -> NormalizedJiraIssue:
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


def _report(**overrides: object) -> NormalizationReport:
    base = NormalizationReport(
        total=5,
        normalized=5,
        unmapped_types={},
        unmapped_statuses={"Esperando": 1},
        unmapped_priorities={},
        story_points_field="customfield_10032",
        sprint_field="customfield_10020",
        source="api",
    )
    return replace(base, **overrides)


def _issues() -> list[NormalizedJiraIssue]:
    start = datetime(2024, 3, 1, tzinfo=UTC)
    return [
        _issue("P-1", "epic"),
        _issue(
            "P-2",
            "story",
            status_raw="En curso",
            status_bucket="in_progress",
            sprint_name="Sprint 1",
            sprint_state="active",
            story_points=2.5,
            original_estimate_seconds=14400,
        ),
        _issue(
            "P-3",
            "subtask",
            status_raw="Hecho",
            status_bucket="done",
            sprint_name="Sprint 2",
            sprint_state="future",
            sprint_start_date=start,
        ),
        _issue("P-4", "bug", sprint_name="Sprint 1", original_estimate_seconds=1800),
        _issue("P-5", "story", status_raw="Esperando", status_bucket="todo"),
    ]


class TestBuildPreview:
    def test_counts_sprints_status_mapping_and_estimation(self) -> None:
        from app.modules.jira_import.preview import build_preview

        preview = build_preview(_issues(), _report(), strategy=ScrumStrategy())

        assert preview.total == 5
        assert preview.counts_by_type == {"epic": 1, "story": 2, "subtask": 1, "bug": 1}
        sprints = {sprint.name: sprint for sprint in preview.sprints}
        assert sprints["Sprint 1"].status == "active"
        assert sprints["Sprint 1"].issues == 2
        assert sprints["Sprint 2"].status == "draft"
        assert sprints["Sprint 2"].start_date == datetime(2024, 3, 1, tzinfo=UTC)
        mapping = {item.jira_status: item.target_status for item in preview.status_mapping}
        assert mapping == {
            "To Do": "To Do",
            "En curso": "In Progress",
            "Hecho": "Done",
            "Esperando": "To Do",
        }
        assert preview.target_statuses == ScrumStrategy().allowed_statuses()
        assert preview.estimated_hours == Decimal("4.50")
        assert preview.issues_with_estimate == 2
        assert preview.story_points == 3  # 2.5 rounded up
        assert preview.unmapped_statuses == {"Esperando": 1}

    def test_empty_project_previews_zero_everything(self) -> None:
        from app.modules.jira_import.preview import build_preview

        preview = build_preview([], _report(total=0, normalized=0), strategy=ScrumStrategy())

        assert preview.total == 0
        assert preview.counts_by_type == {}
        assert preview.sprints == []
        assert preview.estimated_hours == Decimal(0)

    @pytest.mark.asyncio(loop_scope="session")
    @skip_no_db
    async def test_preview_never_writes_to_the_database(self, session: AsyncSession) -> None:
        from app.modules.jira_import.preview import build_preview
        from app.modules.projects.models import Project
        from app.modules.sprints.models import Sprint
        from app.modules.tasks.models import Task

        async def _counts() -> tuple[int, ...]:
            counts = []
            for model in (Project, Sprint, Task):
                result = await session.execute(select(func.count()).select_from(model))
                counts.append(int(result.scalar_one()))
            return tuple(counts)

        before = await _counts()
        build_preview(_issues(), _report(), strategy=ScrumStrategy())
        assert await _counts() == before


class TestHelpers:
    def test_seconds_to_hours_divides_by_3600(self) -> None:
        from app.modules.jira_import.preview import seconds_to_hours

        assert seconds_to_hours(14400) == Decimal("4")
        assert seconds_to_hours(5400) == Decimal("1.50")
        assert seconds_to_hours(None) is None

    @pytest.mark.parametrize("key", ["PROJ", "AB1", "X2Y3"])
    def test_safe_project_keys_are_accepted(self, key: str) -> None:
        from app.modules.jira_import.preview import project_jql

        assert project_jql(key) == f'project = "{key}" ORDER BY key ASC'

    @pytest.mark.parametrize(
        "key", ['ABC" OR 1=1--', "proj", "1ABC", "A", "AB-1", "AB C", ""]
    )
    def test_unsafe_project_keys_are_rejected_with_422(self, key: str) -> None:
        from app.modules.jira_import.preview import project_jql
        from app.shared.exceptions import AppException

        with pytest.raises(AppException) as excinfo:
            project_jql(key)
        assert excinfo.value.status_code == 422
