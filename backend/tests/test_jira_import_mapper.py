"""Pure mapping tests for the Jira organization feed (synthetic fixtures)."""

from datetime import UTC, datetime

from pydantic import EmailStr, TypeAdapter

from app.modules.jira_import.adf import adf_to_markdown
from app.modules.jira_import.mapper import (
    PLACEHOLDER_DOMAIN,
    build_feed_plan,
    placeholder_email,
    split_display_name,
)
from tests.jira_feed_fixtures import make_snapshot


def _plan():
    plan = build_feed_plan(make_snapshot())
    return plan, {p.key: p for p in plan.projects}


def test_scope_excludes_projects_without_issues_in_window():
    plan, projects = _plan()
    assert sorted(projects) == ["ALFA", "BETA"]
    assert plan.excluded_projects == {"VIEJO": 0}


def test_methodology_scrum_when_issues_use_sprints_even_on_simple_board():
    _, projects = _plan()
    assert projects["ALFA"].methodology == "scrum"
    assert projects["BETA"].methodology == "kanban"
    assert projects["BETA"].sprints == []


def test_columns_follow_board_with_unmapped_status_and_done_last():
    plan, projects = _plan()
    alfa = projects["ALFA"]
    assert [c.status_key for c in alfa.columns] == ["Por hacer", "En curso", "Bloqueado", "Listo"]
    assert alfa.done_status == "Listo"
    assert plan.warnings["estado_fuera_del_tablero_jira"] == 1


def test_columns_without_board_come_from_statuses_by_category():
    _, projects = _plan()
    assert [c.status_key for c in projects["BETA"].columns] == [
        "Tareas por hacer",
        "En curso",
        "Finalizada",
    ]


def test_task_mapping_types_priority_points_and_sprint():
    plan, projects = _plan()
    tasks = {t.key: t for t in projects["ALFA"].tasks}
    assert tasks["ALFA-1"].task_type == "epic"
    assert tasks["ALFA-2"].task_type == "story"
    assert tasks["ALFA-2"].estimation_points == 1  # 0.5 rounded up
    assert tasks["ALFA-2"].description == "Hola"
    assert tasks["ALFA-2"].parent_key == "ALFA-1"
    assert tasks["ALFA-3"].task_type == "subtask"
    assert tasks["ALFA-3"].priority == "critical"
    assert tasks["ALFA-3"].sprint_jira_id == 12  # last sprint of the issue
    assert tasks["ALFA-3"].status == "Bloqueado"
    assert tasks["ALFA-5"].task_type == "bug"
    assert tasks["ALFA-5"].number == 5
    assert plan.warnings["puntos_redondeados_hacia_arriba"] == 1


def test_long_summary_is_truncated_and_kept_in_description():
    _, projects = _plan()
    task = next(t for t in projects["ALFA"].tasks if t.key == "ALFA-5")
    assert len(task.title) == 200 and task.title.endswith("…")
    assert task.description.startswith("**Título completo en Jira:** " + "x" * 250)


def test_completed_at_only_in_done_column_and_real_dates():
    plan, projects = _plan()
    alfa = {t.key: t for t in projects["ALFA"].tasks}
    assert alfa["ALFA-2"].completed_at == datetime(2026, 2, 15, 17, 0, tzinfo=UTC)
    assert alfa["ALFA-1"].completed_at is None
    beta = {t.key: t for t in projects["BETA"].tasks}
    assert beta["BETA-7"].completed_at == beta["BETA-7"].updated_at
    assert plan.warnings["finalizada_sin_fecha_de_resolucion"] == 1
    assert alfa["ALFA-5"].due_date.isoformat() == "2026-04-30T00:00:00-05:00"


def test_kanban_drops_story_points_and_reports_unmapped_values():
    plan, projects = _plan()
    beta = {t.key: t for t in projects["BETA"].tasks}
    assert beta["BETA-7"].estimation_points is None
    assert beta["BETA-8"].task_type == "task"
    assert beta["BETA-8"].priority == "medium"
    assert plan.warnings["puntos_descartados_por_metodologia"] == 1
    assert plan.warnings["tipo_no_homologado"] == 1
    assert plan.warnings["prioridad_no_homologada"] == 1


def test_context_parent_is_imported_and_flagged():
    _, projects = _plan()
    context = [t for t in projects["ALFA"].tasks if t.context]
    assert [t.key for t in context] == ["ALFA-0"]
    assert context[0].status == "Listo"


def test_sprints_with_real_states_and_completed_points():
    _, projects = _plan()
    sprints = {s.jira_id: s for s in projects["ALFA"].sprints}
    assert sprints[11].status == "closed"
    assert sprints[11].closed_at == datetime(2026, 2, 16, 15, 0, tzinfo=UTC)
    assert sprints[11].completed_points == 1
    assert sprints[12].status == "active"
    assert sprints[12].closed_at is None


def test_only_human_accounts_and_non_human_assignee_dropped():
    plan, projects = _plan()
    assert sorted(u.account_id for u in plan.users) == ["557058:abc-def", "acc-ana", "acc-luis"]
    task = next(t for t in projects["ALFA"].tasks if t.key == "ALFA-5")
    assert task.assignee_account_id is None
    assert plan.warnings["responsable_no_humano_omitido"] == 1


def test_emails_real_or_reserved_placeholder_valid_for_emailstr():
    plan, _ = _plan()
    users = {u.account_id: u for u in plan.users}
    assert users["acc-ana"].email == "ana@ejemplo.gov.co"
    assert not users["acc-ana"].email_is_placeholder
    carla = users["557058:abc-def"]
    assert carla.email_is_placeholder
    assert carla.email == f"jira-557058-abc-def@{PLACEHOLDER_DOMAIN}"
    TypeAdapter(EmailStr).validate_python(placeholder_email("557058:abc-def"))


def test_split_display_name_variants():
    assert split_display_name("Ana María Pérez Gómez") == ("Ana", "María", "Pérez", "Gómez")
    assert split_display_name("Carla Ruiz") == ("Carla", None, "Ruiz", None)
    assert split_display_name("Juan Pérez Gómez") == ("Juan", None, "Pérez", "Gómez")
    assert split_display_name("luis.rojas") == ("Luis", None, "Rojas", None)
    assert split_display_name("Prince") == ("Prince", None, "-", None)


def test_adf_to_markdown_common_nodes():
    doc = {
        "type": "doc",
        "content": [
            {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "T"}]},
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [
                                    {"type": "text", "text": "uno", "marks": [{"type": "strong"}]}
                                ],
                            }
                        ],
                    }
                ],
            },
            {"type": "codeBlock", "content": [{"type": "text", "text": "x = 1"}]},
        ],
    }
    assert adf_to_markdown(doc) == "## T\n\n- **uno**\n\n```\nx = 1\n```"
    assert adf_to_markdown(None) is None
    assert adf_to_markdown("  texto ") == "texto"
