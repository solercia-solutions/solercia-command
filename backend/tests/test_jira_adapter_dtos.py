"""RED tests for the Jira adapter's DTOs (change 18-adapter-jira,
specs/jira-import/spec.md). ``NormalizedJiraIssue``/``NormalizationReport``
are frozen dataclasses — a pure snapshot of a normalized issue, never
mutated after construction (same discipline as ``app/integrations/dtos.py``
Ticket/OAuthTokens, design.md "Interfaces / Contracts").
"""

import dataclasses
from datetime import UTC, datetime

import pytest


def _issue(**overrides: object):
    from app.integrations.adapters.jira.dtos import NormalizedJiraIssue

    defaults: dict[str, object] = {
        "key": "PROJ-42",
        "title": "Implementar el inicio de sesion con SSO",
        "description": "Falta soportar el flujo SSO en el login.",
        "issue_type": "story",
        "status_raw": "In Progress",
        "status_bucket": "in_progress",
        "priority": "high",
        "assignee_raw": "5b10a2844c20165700ede21g",
        "sprint_name": "Sprint 3",
        "sprint_state": None,
        "story_points": 5.0,
        "labels": ("backend", "auth"),
        "created_at": datetime(2024, 1, 15, 10, 30, tzinfo=UTC),
        "source": "api",
    }
    defaults.update(overrides)
    return NormalizedJiraIssue(**defaults)  # type: ignore[arg-type]


class TestNormalizedJiraIssue:
    def test_carries_every_field_from_a_real_issue(self) -> None:
        """A fully-populated issue keeps every field reachable — this is
        the DTO the API and file vias both converge on (design.md
        'Interfaces / Contracts')."""

        issue = _issue()

        assert issue.key == "PROJ-42"
        assert issue.issue_type == "story"
        assert issue.status_bucket == "in_progress"
        assert issue.priority == "high"
        assert issue.assignee_raw == "5b10a2844c20165700ede21g"
        assert issue.sprint_name == "Sprint 3"
        assert issue.story_points == 5.0
        assert issue.labels == ("backend", "auth")
        assert issue.source == "api"

    def test_is_frozen_and_never_mutated_after_construction(self) -> None:
        """A port response is a pure snapshot — never mutated in place
        (mirrors ``Ticket``/``OAuthTokens``, ``app/integrations/dtos.py``)."""

        issue = _issue()

        with pytest.raises(dataclasses.FrozenInstanceError):
            issue.title = "Otro titulo"  # type: ignore[misc]

    def test_optional_fields_accept_none_for_an_unassigned_issue(self) -> None:
        """An issue with no assignee/sprint/story points/description/created
        date still constructs — every optional field is genuinely optional."""

        issue = _issue(
            description=None,
            assignee_raw=None,
            sprint_name=None,
            sprint_state=None,
            story_points=None,
            created_at=None,
            labels=(),
        )

        assert issue.description is None
        assert issue.assignee_raw is None
        assert issue.labels == ()


class TestNormalizationReport:
    def test_carries_totals_and_unmapped_counters(self) -> None:
        from app.integrations.adapters.jira.dtos import NormalizationReport

        report = NormalizationReport(
            total=3,
            normalized=3,
            unmapped_types={"Design Spike": 1},
            unmapped_statuses={},
            unmapped_priorities={"Blocker": 1},
            story_points_field="customfield_10032",
            sprint_field="customfield_10020",
            source="api",
        )

        assert report.total == 3
        assert report.normalized == 3
        assert report.unmapped_types == {"Design Spike": 1}
        assert report.unmapped_priorities == {"Blocker": 1}
        assert report.story_points_field == "customfield_10032"
        assert report.source == "api"

    def test_is_frozen(self) -> None:
        from app.integrations.adapters.jira.dtos import NormalizationReport

        report = NormalizationReport(
            total=0,
            normalized=0,
            unmapped_types={},
            unmapped_statuses={},
            unmapped_priorities={},
            story_points_field=None,
            sprint_field=None,
            source="file",
        )

        with pytest.raises(dataclasses.FrozenInstanceError):
            report.total = 5  # type: ignore[misc]

    def test_custom_field_absent_reports_none_not_a_crash(self) -> None:
        """A Jira instance that renamed/removed the story points custom
        field resolves to ``None`` in the report — never raises
        (specs/jira-import/spec.md 'Resolución configurable de custom
        fields')."""

        from app.integrations.adapters.jira.dtos import NormalizationReport

        report = NormalizationReport(
            total=1,
            normalized=1,
            unmapped_types={},
            unmapped_statuses={},
            unmapped_priorities={},
            story_points_field=None,
            sprint_field=None,
            source="api",
        )

        assert report.story_points_field is None
        assert report.sprint_field is None
