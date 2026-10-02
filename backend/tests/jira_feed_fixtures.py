"""Synthetic Jira snapshot for the organization-feed tests (no real data).

Two projects:

* ``ALFA`` — team-managed (``simple`` board) whose issues use sprints, with a
  status the board does not show and a context parent outside the window.
* ``BETA`` — no board, no sprints (kanban), with story points that kanban
  must drop.

Plus ``VIEJO`` with no issues in the window (excluded).
"""

from typing import Any

from app.modules.jira_import.snapshot import Snapshot

SP_FIELD = "customfield_90016"
SPRINT_FIELD = "customfield_90020"
START_FIELD = "customfield_90015"


def _status(sid: str, name: str, category: str) -> dict[str, Any]:
    return {"id": sid, "name": name, "statusCategory": {"key": category}}


TODO = _status("1", "Tareas por hacer", "new")
DOING = _status("2", "En curso", "indeterminate")
BLOCKED = _status("4", "Bloqueado", "indeterminate")
DONE = _status("3", "Finalizada", "done")


def issue(
    key: str,
    *,
    summary: str = "Resumen",
    type_name: str = "Historia",
    subtask: bool = False,
    status: dict[str, Any] = TODO,
    priority: str = "Medium",
    assignee: str | None = "acc-ana",
    reporter: str | None = "acc-luis",
    parent: str | None = None,
    points: float | None = None,
    sprints: list[dict[str, Any]] | None = None,
    resolved: str | None = None,
    due: str | None = None,
    description: Any = None,
) -> dict[str, Any]:
    return {
        "id": key.replace("-", "") + "0",
        "key": key,
        "fields": {
            "summary": summary,
            "description": description,
            "issuetype": {"name": type_name, "subtask": subtask},
            "status": status,
            "priority": {"name": priority},
            "assignee": {"accountId": assignee} if assignee else None,
            "reporter": {"accountId": reporter} if reporter else None,
            "created": "2026-02-01T09:00:00.000-0500",
            "updated": "2026-03-01T10:30:00.000-0500",
            "duedate": due,
            "resolutiondate": resolved,
            "parent": {"key": parent} if parent else None,
            "labels": [],
            SP_FIELD: points,
            SPRINT_FIELD: sprints,
            START_FIELD: None,
        },
    }


SPRINT_1 = {
    "id": 11,
    "name": "ALFA Sprint 1",
    "state": "closed",
    "startDate": "2026-02-02T13:00:00.000Z",
    "endDate": "2026-02-16T13:00:00.000Z",
    "completeDate": "2026-02-16T15:00:00.000Z",
    "goal": "Primer incremento",
}
SPRINT_2 = {
    "id": 12,
    "name": "ALFA Sprint 2",
    "state": "active",
    "startDate": "2026-02-17T13:00:00.000Z",
    "endDate": "2026-03-03T13:00:00.000Z",
}


def make_snapshot() -> Snapshot:
    alfa_issues = [
        issue("ALFA-1", type_name="Epic", status=DOING, parent="ALFA-0"),
        issue(
            "ALFA-2",
            status=DONE,
            points=0.5,
            sprints=[SPRINT_1],
            resolved="2026-02-15T12:00:00.000-0500",
            parent="ALFA-1",
            description={
                "type": "doc",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Hola"}]}],
            },
        ),
        issue(
            "ALFA-3",
            type_name="Subtarea",
            subtask=True,
            status=BLOCKED,
            parent="ALFA-2",
            sprints=[SPRINT_1, SPRINT_2],
            points=3,
            priority="Highest",
        ),
        issue(
            "ALFA-5",
            summary="x" * 250,
            type_name="Error",
            status=TODO,
            assignee="app-bot",
            due="2026-04-30",
        ),
    ]
    beta_issues = [
        issue("BETA-7", type_name="Tarea", status=DONE, points=5, resolved=None, assignee=None),
        issue("BETA-8", type_name="Desconocido", status=DOING, priority="Rarísima"),
    ]
    return Snapshot(
        manifest={
            "site_host": "ejemplo.atlassian.net",
            "fetched_at": "2026-10-01T00:00:00+00:00",
            "since": "2026-01-01",
            "story_point_fields": [SP_FIELD],
            "sprint_fields": [SPRINT_FIELD],
            "start_date_fields": [START_FIELD],
        },
        fields=[],
        projects=[
            {"key": "ALFA", "name": "Proyecto Alfa", "lead": {"accountId": "acc-ana"}},
            {"key": "BETA", "name": "Proyecto Beta", "description": "Descripción beta"},
            {"key": "VIEJO", "name": "Proyecto viejo"},
        ],
        users=[
            {
                "accountId": "acc-ana",
                "accountType": "atlassian",
                "active": True,
                "displayName": "Ana María Pérez Gómez",
                "emailAddress": "ana@ejemplo.gov.co",
            },
            {
                "accountId": "acc-luis",
                "accountType": "atlassian",
                "active": False,
                "displayName": "luis.rojas",
            },
            {
                "accountId": "557058:abc-def",
                "accountType": "atlassian",
                "active": True,
                "displayName": "Carla Ruiz",
            },
            {
                "accountId": "app-bot",
                "accountType": "app",
                "active": True,
                "displayName": "Automation",
            },
        ],
        issues={"ALFA": alfa_issues, "BETA": beta_issues, "VIEJO": []},
        statuses={
            "ALFA": [{"statuses": [TODO, DOING, BLOCKED, DONE]}],
            "BETA": [{"statuses": [DONE, DOING, TODO]}],
        },
        boards={"ALFA": [{"id": 501, "type": "simple"}], "BETA": []},
        board_configs={
            501: {
                "columnConfig": {
                    "columns": [
                        {"name": "Listo", "statuses": [{"id": "3"}]},
                        {"name": "Por hacer", "statuses": [{"id": "1"}]},
                        {"name": "En curso", "statuses": [{"id": "2"}]},
                        {"name": "Backlog", "statuses": []},
                    ]
                }
            }
        },
        sprints={},
        context_issues=[
            issue("ALFA-0", type_name="Epic", status=DONE, resolved="2025-11-01T08:00:00.000-0500")
        ],
    )
