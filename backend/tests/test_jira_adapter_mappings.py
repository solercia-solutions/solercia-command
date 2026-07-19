"""RED tests for the Jira adapter's homologation tables (change
18-adapter-jira, specs/jira-import/spec.md "Homologación de tipo/estado/
prioridad con fallback y reporte"). Pure functions — no I/O, no fixtures.
"""


class TestBuildMappings:
    def test_no_overrides_returns_the_jira_cloud_defaults(self) -> None:
        from app.integrations.adapters.jira.mappings import build_mappings

        mappings = build_mappings(None)

        assert mappings.type_map["story"] == "story"
        assert mappings.status_map["done"] == "done"
        assert mappings.priority_map["highest"] == "critical"

    def test_overrides_merge_on_top_of_defaults_never_dropping_them(self) -> None:
        """`settings.jira.{status_map,type_map,priority_map}` overrides ADD
        to/replace default entries — a default never disappears just
        because the connector configured an override for something else."""

        from app.integrations.adapters.jira.mappings import build_mappings

        jira_settings = {
            "type_map": {"design spike": "task"},
            "status_map": {"esperando aprobacion": "in_progress"},
            "priority_map": {"blocker": "critical"},
        }

        mappings = build_mappings(jira_settings)

        assert mappings.type_map["design spike"] == "task"
        assert mappings.type_map["story"] == "story"  # default preserved
        assert mappings.status_map["esperando aprobacion"] == "in_progress"
        assert mappings.status_map["done"] == "done"  # default preserved
        assert mappings.priority_map["blocker"] == "critical"
        assert mappings.priority_map["highest"] == "critical"  # default preserved

    def test_override_replaces_a_default_entry(self) -> None:
        from app.integrations.adapters.jira.mappings import build_mappings

        mappings = build_mappings({"priority_map": {"high": "critical"}})

        assert mappings.priority_map["high"] == "critical"


class TestResolveType:
    def test_known_type_name_maps_exactly(self) -> None:
        from app.integrations.adapters.jira.mappings import build_mappings, resolve_type

        mappings = build_mappings(None)

        issue_type, mapped = resolve_type("Story", is_subtask=False, mappings=mappings)

        assert issue_type == "story"
        assert mapped is True

    def test_subtask_flag_wins_over_the_type_name(self) -> None:
        """`issuetype.subtask=True` decides `subtask` regardless of the
        display name Jira gave that type (e.g. 'Sub-task', 'Sub-tarea')."""

        from app.integrations.adapters.jira.mappings import build_mappings, resolve_type

        mappings = build_mappings(None)

        issue_type, mapped = resolve_type("Sub-tarea", is_subtask=True, mappings=mappings)

        assert issue_type == "subtask"
        assert mapped is True

    def test_unknown_type_falls_back_to_task_and_is_reported_unmapped(self) -> None:
        from app.integrations.adapters.jira.mappings import build_mappings, resolve_type

        mappings = build_mappings(None)

        issue_type, mapped = resolve_type("Design Spike", is_subtask=False, mappings=mappings)

        assert issue_type == "task"
        assert mapped is False


class TestResolveStatus:
    def test_known_status_name_maps_exactly_without_needing_the_category(self) -> None:
        from app.integrations.adapters.jira.mappings import build_mappings, resolve_status

        mappings = build_mappings(None)

        bucket, mapped = resolve_status("Done", status_category_key=None, mappings=mappings)

        assert bucket == "done"
        assert mapped is True

    def test_unknown_status_falls_back_to_the_status_category_bucket(self) -> None:
        from app.integrations.adapters.jira.mappings import build_mappings, resolve_status

        mappings = build_mappings(None)

        bucket, mapped = resolve_status(
            "Esperando aprobacion", status_category_key="indeterminate", mappings=mappings
        )

        assert bucket == "in_progress"
        assert mapped is False

    def test_unknown_status_without_any_category_defaults_to_todo(self) -> None:
        """A file-vía row never carries `statusCategory` — the safest
        fallback bucket is `todo` (specs/jira-import/spec.md, "un valor
        sin mapeo conocido DEBE usar un fallback seguro")."""

        from app.integrations.adapters.jira.mappings import build_mappings, resolve_status

        mappings = build_mappings(None)

        bucket, mapped = resolve_status(
            "Custom Workflow State", status_category_key=None, mappings=mappings
        )

        assert bucket == "todo"
        assert mapped is False


class TestResolvePriority:
    def test_known_priority_maps_exactly(self) -> None:
        from app.integrations.adapters.jira.mappings import build_mappings, resolve_priority

        mappings = build_mappings(None)

        priority, mapped = resolve_priority("Lowest", mappings=mappings)

        assert priority == "low"
        assert mapped is True

    def test_unknown_priority_falls_back_to_medium_and_is_reported(self) -> None:
        from app.integrations.adapters.jira.mappings import build_mappings, resolve_priority

        mappings = build_mappings(None)

        priority, mapped = resolve_priority("Blocker", mappings=mappings)

        assert priority == "medium"
        assert mapped is False
