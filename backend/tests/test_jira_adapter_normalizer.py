"""RED tests for the Jira adapter's normalizer (change 18-adapter-jira,
specs/jira-import/spec.md). Pure functions over fixture dicts — zero I/O,
zero HTTP (design.md "TDD estricto contra fixtures").
"""

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "jira"


def _load_fixture(name: str) -> dict:
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _mappings():
    from app.integrations.adapters.jira.mappings import build_mappings

    return build_mappings(None)


class TestNormalizeApiIssue:
    def test_known_type_status_priority_map_exactly_no_report(self) -> None:
        """PROJ-44 (search_page2.json) has a fully-known type/status/priority
        — normalizing it reports NOTHING unmapped."""

        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        raw_issue = _load_fixture("search_page2.json")["issues"][0]

        issue, flags = normalize_api_issue(
            raw_issue,
            mappings=_mappings(),
            story_points_field="customfield_10032",
            sprint_field="customfield_10020",
        )

        assert issue.key == "PROJ-44"
        assert issue.issue_type == "bug"
        assert issue.status_bucket == "done"
        assert issue.priority == "medium"
        assert issue.story_points == 3.0
        assert issue.labels == ("billing",)
        assert flags.type_raw is None
        assert flags.status_raw is None
        assert flags.priority_raw is None

    def test_unknown_type_falls_back_to_task_and_is_flagged(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        raw_issue = {
            "key": "PROJ-99",
            "fields": {
                "summary": "Investigar una idea nueva",
                "description": None,
                "issuetype": {"name": "Design Spike", "subtask": False},
                "status": {"name": "To Do", "statusCategory": {"key": "new"}},
                "priority": {"name": "Medium"},
                "assignee": None,
                "labels": [],
                "created": None,
            },
        }

        issue, flags = normalize_api_issue(
            raw_issue, mappings=_mappings(), story_points_field=None, sprint_field=None
        )

        assert issue.issue_type == "task"
        assert flags.type_raw == "Design Spike"

    def test_unknown_status_resolves_via_status_category(self) -> None:
        """PROJ-43's status 'Esperando aprobacion' has no exact-name
        mapping — resolved via `statusCategory.key=indeterminate`."""

        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        raw_issue = _load_fixture("search_page1.json")["issues"][1]

        issue, flags = normalize_api_issue(
            raw_issue,
            mappings=_mappings(),
            story_points_field="customfield_10032",
            sprint_field="customfield_10020",
        )

        assert issue.status_bucket == "in_progress"
        assert flags.status_raw == "Esperando aprobacion"

    def test_unknown_priority_falls_back_to_medium_and_is_flagged(self) -> None:
        """PROJ-43's priority 'Blocker' is not in the default Jira Cloud
        priority scheme."""

        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        raw_issue = _load_fixture("search_page1.json")["issues"][1]

        issue, flags = normalize_api_issue(
            raw_issue,
            mappings=_mappings(),
            story_points_field="customfield_10032",
            sprint_field="customfield_10020",
        )

        assert issue.priority == "medium"
        assert flags.priority_raw == "Blocker"

    def test_subtask_flag_is_supported_regardless_of_type_name(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        raw_issue = _load_fixture("search_page1.json")["issues"][1]

        issue, _ = normalize_api_issue(
            raw_issue,
            mappings=_mappings(),
            story_points_field="customfield_10032",
            sprint_field="customfield_10020",
        )

        assert issue.issue_type == "subtask"

    def test_assignee_and_labels_are_preserved_raw(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        raw_issue = _load_fixture("search_page1.json")["issues"][0]

        issue, _ = normalize_api_issue(
            raw_issue,
            mappings=_mappings(),
            story_points_field="customfield_10032",
            sprint_field="customfield_10020",
        )

        assert issue.assignee_raw == "5b10a2844c20165700ede21g"
        assert issue.labels == ("backend", "auth")

    def test_unassigned_issue_has_none_assignee(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        raw_issue = _load_fixture("search_page1.json")["issues"][1]

        issue, _ = normalize_api_issue(
            raw_issue,
            mappings=_mappings(),
            story_points_field="customfield_10032",
            sprint_field="customfield_10020",
        )

        assert issue.assignee_raw is None

    def test_adf_description_converts_to_plain_text(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        raw_issue = _load_fixture("search_page1.json")["issues"][0]

        issue, _ = normalize_api_issue(
            raw_issue,
            mappings=_mappings(),
            story_points_field="customfield_10032",
            sprint_field="customfield_10020",
        )

        assert issue.description == "Falta soportar el flujo SSO en el login."

    def test_missing_description_is_none(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        raw_issue = _load_fixture("search_page1.json")["issues"][1]

        issue, _ = normalize_api_issue(
            raw_issue,
            mappings=_mappings(),
            story_points_field="customfield_10032",
            sprint_field="customfield_10020",
        )

        assert issue.description is None

    def test_sprint_object_form_carries_name_and_state(self) -> None:
        """PROJ-43's sprint customfield is the richer JSON-object form
        (`{id, name, state}`), not a plain string."""

        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        raw_issue = _load_fixture("search_page1.json")["issues"][1]

        issue, _ = normalize_api_issue(
            raw_issue,
            mappings=_mappings(),
            story_points_field="customfield_10032",
            sprint_field="customfield_10020",
        )

        assert issue.sprint_name == "Sprint 4"
        assert issue.sprint_state == "active"

    def test_story_points_field_absent_is_none_not_a_crash(self) -> None:
        """No `story_points_field` resolved (custom field ausente) ->
        `story_points=None`, never raises."""

        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        raw_issue = _load_fixture("search_page1.json")["issues"][0]

        issue, _ = normalize_api_issue(
            raw_issue, mappings=_mappings(), story_points_field=None, sprint_field=None
        )

        assert issue.story_points is None
        assert issue.sprint_name is None

    def test_created_at_parses_the_jira_timestamp(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        raw_issue = _load_fixture("search_page1.json")["issues"][0]

        issue, _ = normalize_api_issue(
            raw_issue,
            mappings=_mappings(),
            story_points_field="customfield_10032",
            sprint_field="customfield_10020",
        )

        assert issue.created_at == datetime(2024, 1, 15, 10, 30, tzinfo=UTC)

    def test_source_is_tagged_api(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        raw_issue = _load_fixture("search_page2.json")["issues"][0]

        issue, _ = normalize_api_issue(
            raw_issue, mappings=_mappings(), story_points_field=None, sprint_field=None
        )

        assert issue.source == "api"


class TestNormalizeFileRow:
    def test_source_is_tagged_file(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_file_row

        row = {
            "Issue key": "PROJ-42",
            "Summary": "Implementar el inicio de sesion con SSO",
            "Issue Type": "Story",
            "Status": "In Progress",
            "Priority": "High",
            "Assignee": "5b10a2844c20165700ede21g",
            "Labels": ["backend", "auth"],
            "Sprint": ["Sprint 3"],
            "Story Points": "5",
            "Created": "2024-01-15T10:30:00.000+0000",
            "Description": "Falta soportar el flujo SSO en el login.",
        }

        issue, _ = normalize_file_row(row, mappings=_mappings())

        assert issue.source == "file"
        assert issue.labels == ("backend", "auth")
        assert issue.story_points == 5.0

    def test_row_marked_as_sub_task_type_maps_to_subtask(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_file_row

        row = {
            "Issue key": "PROJ-50",
            "Summary": "Ajuste menor",
            "Issue Type": "Sub-task",
            "Status": "To Do",
            "Priority": "Low",
            "Assignee": None,
            "Labels": [],
            "Sprint": [],
            "Story Points": None,
            "Created": None,
            "Description": None,
        }

        issue, _ = normalize_file_row(row, mappings=_mappings())

        assert issue.issue_type == "subtask"


class TestNormalizeBatchConvergence:
    def test_same_issue_via_api_and_file_normalizes_equivalently(self) -> None:
        """specs/jira-import/spec.md 'Convergencia entre vías': PROJ-42 via
        the API fixture (search_page1.json) and via the equivalent CSV row
        (export.csv) produce an equivalent `NormalizedJiraIssue` — every
        field EXCEPT `source`, which is the one field meant to tell the two
        vias apart."""

        from app.integrations.adapters.jira.normalizer import (
            normalize_api_issue,
            normalize_file_row,
        )

        raw_api_issue = _load_fixture("search_page1.json")["issues"][0]
        file_row = {
            "Issue key": "PROJ-42",
            "Summary": "Implementar el inicio de sesion con SSO",
            "Issue Type": "Story",
            "Status": "In Progress",
            "Priority": "High",
            "Assignee": "5b10a2844c20165700ede21g",
            "Labels": ["backend", "auth"],
            "Sprint": ["Sprint 3"],
            "Story Points": "5",
            "Created": "2024-01-15T10:30:00.000+0000",
            "Description": "Falta soportar el flujo SSO en el login.",
        }

        api_issue, _ = normalize_api_issue(
            raw_api_issue,
            mappings=_mappings(),
            story_points_field="customfield_10032",
            sprint_field="customfield_10020",
        )
        file_issue, _ = normalize_file_row(file_row, mappings=_mappings())

        # A file export carries no assignee email (the API vía does): the
        # import-only `assignee_email` is the other field allowed to differ.
        assert dataclasses.replace(api_issue, source="", assignee_email=None) == (
            dataclasses.replace(file_issue, source="")
        )
        assert api_issue.source == "api"
        assert file_issue.source == "file"

    def test_normalize_api_batch_builds_the_full_report(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_api_batch

        raw_issues = _load_fixture("search_page1.json")["issues"]

        issues, report = normalize_api_batch(
            raw_issues,
            mappings=_mappings(),
            story_points_field="customfield_10032",
            sprint_field="customfield_10020",
        )

        assert report.total == 2
        assert report.normalized == 2
        assert report.unmapped_statuses == {"Esperando aprobacion": 1}
        assert report.unmapped_priorities == {"Blocker": 1}
        assert report.story_points_field == "customfield_10032"
        assert report.source == "api"
        assert len(issues) == 2

    def test_normalize_file_batch_builds_the_full_report(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_file_batch

        rows = [
            {
                "Issue key": "PROJ-42",
                "Summary": "Implementar el inicio de sesion con SSO",
                "Issue Type": "Story",
                "Status": "In Progress",
                "Priority": "High",
                "Assignee": "5b10a2844c20165700ede21g",
                "Labels": ["backend", "auth"],
                "Sprint": ["Sprint 3"],
                "Story Points": "5",
                "Created": "2024-01-15T10:30:00.000+0000",
                "Description": "Falta soportar el flujo SSO en el login.",
            }
        ]

        issues, report = normalize_file_batch(rows, mappings=_mappings())

        assert report.total == 1
        assert report.normalized == 1
        assert report.unmapped_types == {}
        assert report.source == "file"
        assert report.story_points_field is None
        assert len(issues) == 1


class TestNormalizeBatchIsolation:
    """A malformed item (non-``Mapping`` ``assignee``) is isolated into
    ``report.skipped_malformed`` instead of aborting the whole batch."""

    def test_a_malformed_api_issue_is_skipped_and_reported(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_api_batch

        raw_issues = [
            {"key": "PROJ-1", "fields": {"summary": "A", "assignee": None}},
            {"key": "PROJ-2", "fields": {"summary": "B", "assignee": "not-a-mapping"}},
            {"key": "PROJ-3", "fields": {"summary": "C", "assignee": {"accountId": "x"}}},
        ]

        issues, report = normalize_api_batch(
            raw_issues, mappings=_mappings(), story_points_field=None, sprint_field=None
        )

        assert [issue.key for issue in issues] == ["PROJ-1", "PROJ-3"]
        assert report.total == 3
        assert report.normalized == 2
        assert len(report.skipped_malformed) == 1
        assert report.skipped_malformed[0]["index"] == 1
        assert report.skipped_malformed[0]["key"] == "PROJ-2"


class TestImportFieldsExtraction:
    def _raw(self, **fields: object) -> dict:
        base: dict[str, object] = {
            "summary": "Historia con estimación",
            "issuetype": {"name": "Story", "subtask": False},
            "status": {"name": "To Do", "statusCategory": {"key": "new"}},
            "priority": {"name": "Medium"},
        }
        base.update(fields)
        return {"key": "PROJ-7", "fields": base}

    def test_estimate_seconds_assignee_email_and_parent_key_are_extracted(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        raw_issue = self._raw(
            timeoriginalestimate=14400,
            assignee={"accountId": "acc-1", "emailAddress": "mia@acme.com"},
            parent={"key": "PROJ-1"},
        )

        issue, _flags = normalize_api_issue(
            raw_issue, mappings=_mappings(), story_points_field=None, sprint_field=None
        )

        assert issue.original_estimate_seconds == 14400
        assert issue.assignee_email == "mia@acme.com"
        assert issue.parent_key == "PROJ-1"
        # The raw assignee keeps its accountId priority (unchanged contract).
        assert issue.assignee_raw == "acc-1"

    def test_missing_estimate_assignee_email_and_parent_key_are_none(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        issue, _flags = normalize_api_issue(
            self._raw(), mappings=_mappings(), story_points_field=None, sprint_field=None
        )

        assert issue.original_estimate_seconds is None
        assert issue.assignee_email is None
        assert issue.parent_key is None

    def test_sprint_object_dates_are_extracted(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_api_issue

        raw_issue = self._raw(
            customfield_10020=[
                {
                    "id": 9,
                    "name": "Sprint 5",
                    "state": "future",
                    "startDate": "2024-03-01T08:00:00.000Z",
                    "endDate": "2024-03-15T17:00:00.000Z",
                }
            ]
        )

        issue, _flags = normalize_api_issue(
            raw_issue,
            mappings=_mappings(),
            story_points_field=None,
            sprint_field="customfield_10020",
        )

        assert issue.sprint_name == "Sprint 5"
        assert issue.sprint_state == "future"
        assert issue.sprint_start_date == datetime(2024, 3, 1, 8, 0, tzinfo=UTC)
        assert issue.sprint_end_date == datetime(2024, 3, 15, 17, 0, tzinfo=UTC)

    def test_file_row_estimate_is_read_and_bad_values_fall_back_to_none(self) -> None:
        from app.integrations.adapters.jira.normalizer import normalize_file_row

        row = {
            "Issue key": "PROJ-8",
            "Summary": "Fila del export",
            "Issue Type": "Story",
            "Status": "To Do",
            "Priority": "Medium",
            "Original Estimate": "7200",
            "Parent id": "PROJ-1",
        }

        issue, _flags = normalize_file_row(row, mappings=_mappings())
        assert issue.original_estimate_seconds == 7200
        assert issue.parent_key == "PROJ-1"

        broken, _flags = normalize_file_row(
            {**row, "Original Estimate": "dos horas"}, mappings=_mappings()
        )
        assert broken.original_estimate_seconds is None
