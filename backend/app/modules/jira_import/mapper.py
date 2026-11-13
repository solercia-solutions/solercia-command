"""Pure mapping: raw Jira snapshot -> an organization feed plan.

No database, no network: every decision of the Jira -> Command homologation
lives here so it can be tested with synthetic fixtures.

Decisions (documented in odd/tasks/plans-and-org-restructure.md, task J1):

* Scope: every Jira project with at least one issue created or updated since
  ``manifest.since``; parents of those issues outside the window are imported
  too (flagged ``context``) so the hierarchy is not broken.
* Methodology: ``scrum`` when the project has a Jira ``scrum`` board OR any
  in-scope issue references a sprint (team-managed boards are ``simple`` but
  may use sprints); otherwise ``kanban``.
* Columns: the Jira board columns (statuses mapped to them), then any project
  status that issues use but the board does not show, then the done-category
  columns last — Command treats the LAST column as "done".
* Users: only human accounts (``accountType == "atlassian"``). Jira hides
  most emails, so a placeholder under the IANA-reserved ``example.org`` (null MX, no
  mailbox) is used — ``.invalid`` would fail ``EmailStr`` in ``UserRead``; those
  accounts get no password (local login rejected) and are linked to the Jira
  ``accountId`` through ``federated_identities``.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.integrations.adapters.jira.mappings import (
    build_mappings,
    resolve_priority,
    resolve_type,
)
from app.modules.jira_import.adf import adf_to_markdown
from app.modules.jira_import.snapshot import Snapshot

BOGOTA = timezone(timedelta(hours=-5))
TITLE_MAX = 200
PROJECT_NAME_MAX = 160
COLUMN_KEY_MAX = 60
SPRINT_NAME_MAX = 160
PLACEHOLDER_DOMAIN = "idartes.jira.example.org"
_CODE_RE = re.compile(r"^[A-Z0-9]{2,10}$")
_TZ_NO_COLON = re.compile(r"([+-]\d{2})(\d{2})$")
_SPANISH_TYPES = {
    "historia": "story",
    "tarea": "task",
    "error": "bug",
    "subtarea": "subtask",
    "épica": "epic",
    "epica": "epic",
}
_CATEGORY_ORDER = {"new": 0, "indeterminate": 1, "done": 2}
# Jira sprint state -> Command sprint status (shared with the project import).
SPRINT_STATUS_BY_JIRA_STATE = {"future": "draft", "active": "active", "closed": "closed"}
_SPRINT_STATE = SPRINT_STATUS_BY_JIRA_STATE


@dataclass
class PlannedUser:
    account_id: str
    display_name: str
    active: bool
    email: str
    email_is_placeholder: bool
    primer_nombre: str
    segundo_nombre: str | None
    primer_apellido: str
    segundo_apellido: str | None


@dataclass
class PlannedColumn:
    name: str
    status_key: str
    category: str


@dataclass
class PlannedSprint:
    jira_id: int
    name: str
    goal: str | None
    status: str
    start_date: datetime | None
    end_date: datetime | None
    closed_at: datetime | None
    completed_points: int = 0


@dataclass
class PlannedTask:
    key: str
    number: int
    title: str
    description: str | None
    task_type: str
    priority: str
    status: str
    created_at: datetime | None
    updated_at: datetime | None
    due_date: datetime | None
    start_date: datetime | None
    completed_at: datetime | None
    estimation_points: int | None
    assignee_account_id: str | None
    reporter_account_id: str | None
    sprint_jira_id: int | None
    parent_key: str | None
    context: bool = False


@dataclass
class PlannedProject:
    key: str
    code: str
    name: str
    description: str | None
    category: str | None
    methodology: str
    lead_account_id: str | None
    board_types: list[str]
    columns: list[PlannedColumn]
    sprints: list[PlannedSprint] = field(default_factory=list)
    tasks: list[PlannedTask] = field(default_factory=list)

    @property
    def done_status(self) -> str | None:
        return self.columns[-1].status_key if self.columns else None


@dataclass
class FeedPlan:
    site_host: str
    since: str
    users: list[PlannedUser]
    projects: list[PlannedProject]
    excluded_projects: dict[str, int]
    warnings: dict[str, int] = field(default_factory=dict)
    warning_samples: dict[str, list[str]] = field(default_factory=dict)

    def warn(self, code: str, sample: str | None = None) -> None:
        self.warnings[code] = self.warnings.get(code, 0) + 1
        if sample is not None:
            samples = self.warning_samples.setdefault(code, [])
            if len(samples) < 10 and sample not in samples:
                samples.append(sample)


# --------------------------------------------------------------------------- helpers


def parse_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(_TZ_NO_COLON.sub(r"\1:\2", value.replace("Z", "+00:00")))
    except ValueError:
        return None


def parse_date(value: Any) -> datetime | None:
    """A Jira ``YYYY-MM-DD`` date -> midnight in Bogotá (aware)."""

    if not value or not isinstance(value, str):
        return None
    try:
        day = datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        return None
    return day.replace(tzinfo=BOGOTA)


def split_display_name(display_name: str) -> tuple[str, str | None, str, str | None]:
    """Split a display name into the four Colombian name parts.

    1 token -> (nombre, -, "-", -); 2 -> nombre apellido; 3 -> nombre
    apellido1 apellido2; 4+ -> nombre1 nombre2 apellido1 apellido2 (any extra
    tokens stay in the second surname).
    """

    tokens = display_name.split()
    if len(tokens) == 1 and re.search(r"[._]", tokens[0]):
        # "nombre.apellido" style usernames.
        tokens = [part.capitalize() for part in re.split(r"[._]+", tokens[0]) if part]
    if not tokens:
        return "Usuario", None, "Jira", None
    if len(tokens) == 1:
        return tokens[0][:120], None, "-", None
    if len(tokens) == 2:
        return tokens[0][:120], None, tokens[1][:120], None
    if len(tokens) == 3:
        return tokens[0][:120], None, tokens[1][:120], tokens[2][:120]
    return (
        tokens[0][:120],
        tokens[1][:120],
        tokens[2][:120],
        " ".join(tokens[3:])[:120],
    )


def placeholder_email(account_id: str) -> str:
    local = re.sub(r"[^A-Za-z0-9._-]", "-", account_id).strip("-.") or "cuenta"
    return f"jira-{local}@{PLACEHOLDER_DOMAIN}".lower()


def _unique(name: str, taken: set[str], limit: int) -> str:
    base = name.strip()[:limit] or "Sin nombre"
    candidate, counter = base, 2
    while candidate.lower() in taken:
        suffix = f" ({counter})"
        candidate = f"{base[: limit - len(suffix)]}{suffix}"
        counter += 1
    taken.add(candidate.lower())
    return candidate


def _story_points(fields: dict[str, Any], field_ids: list[str]) -> float | None:
    for field_id in field_ids:
        value = fields.get(field_id)
        if isinstance(value, int | float):
            return float(value)
    return None


def _sprint_refs(fields: dict[str, Any], field_ids: list[str]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for field_id in field_ids:
        value = fields.get(field_id)
        if isinstance(value, list):
            refs.extend(item for item in value if isinstance(item, dict) and "id" in item)
    return refs


# --------------------------------------------------------------------------- users


def plan_users(snapshot: Snapshot, plan: FeedPlan) -> list[PlannedUser]:
    users: list[PlannedUser] = []
    for raw in snapshot.users:
        if raw.get("accountType") != "atlassian":
            continue
        account_id = str(raw["accountId"])
        display = str(raw.get("displayName") or "").strip() or account_id
        email = str(raw.get("emailAddress") or "").strip().lower()
        primer, segundo, apellido1, apellido2 = split_display_name(display)
        if apellido1 == "-":
            plan.warn("usuario_nombre_de_un_solo_token", display)
        users.append(
            PlannedUser(
                account_id=account_id,
                display_name=display,
                active=bool(raw.get("active")),
                email=email or placeholder_email(account_id),
                email_is_placeholder=not email,
                primer_nombre=primer,
                segundo_nombre=segundo,
                primer_apellido=apellido1,
                segundo_apellido=apellido2,
            )
        )
    return users


# --------------------------------------------------------------------------- columns


def _status_index(statuses_payload: list[dict[str, Any]]) -> dict[str, tuple[str, str]]:
    index: dict[str, tuple[str, str]] = {}
    for issue_type in statuses_payload or []:
        for status in issue_type.get("statuses") or []:
            category = ((status.get("statusCategory") or {}).get("key")) or "indeterminate"
            index[str(status["id"])] = (str(status.get("name") or status["id"]), category)
    return index


def plan_columns(
    key: str,
    snapshot: Snapshot,
    issues: list[dict[str, Any]],
    plan: FeedPlan,
) -> tuple[list[PlannedColumn], dict[str, str]]:
    """Return the ordered columns and ``{jira status id: status_key}``."""

    statuses = _status_index(snapshot.statuses.get(key) or [])
    for issue in issues:
        status = issue["fields"].get("status") or {}
        statuses.setdefault(
            str(status.get("id")),
            (
                str(status.get("name") or "Sin estado"),
                (status.get("statusCategory") or {}).get("key") or "indeterminate",
            ),
        )

    raw_columns: list[tuple[str, list[str], str]] = []
    boards = snapshot.boards.get(key) or []
    config = snapshot.board_configs.get(boards[0]["id"], {}) if boards else {}
    for column in (config.get("columnConfig") or {}).get("columns") or []:
        ids = [str(s["id"]) for s in column.get("statuses") or [] if s.get("id") is not None]
        if not ids:
            continue
        categories = {statuses.get(i, ("", "indeterminate"))[1] for i in ids}
        category = (
            "done"
            if categories == {"done"}
            else min(categories - {"done"} or {"indeterminate"}, key=_CATEGORY_ORDER.get)
        )
        raw_columns.append((str(column.get("name") or ids[0]), ids, category))

    mapped = {status_id for _, ids, _ in raw_columns for status_id in ids}
    used = {str((i["fields"].get("status") or {}).get("id")) for i in issues}
    extras = sorted(
        (sid for sid in used if sid not in mapped),
        key=lambda sid: (_CATEGORY_ORDER.get(statuses[sid][1], 1), statuses[sid][0]),
    )
    if not raw_columns:
        extras = sorted(
            set(statuses) | used,
            key=lambda sid: (_CATEGORY_ORDER.get(statuses[sid][1], 1), statuses[sid][0]),
        )
    elif extras:
        for sid in extras:
            plan.warn("estado_fuera_del_tablero_jira", f"{key}: {statuses[sid][0]}")
    raw_columns.extend((statuses[sid][0], [sid], statuses[sid][1]) for sid in extras)

    ordered = [c for c in raw_columns if c[2] != "done"] + [
        c for c in raw_columns if c[2] == "done"
    ]
    if not any(c[2] == "done" for c in ordered):
        plan.warn("proyecto_sin_columna_finalizada", key)

    taken: set[str] = set()
    columns: list[PlannedColumn] = []
    status_to_key: dict[str, str] = {}
    for name, ids, category in ordered:
        status_key = _unique(name, taken, COLUMN_KEY_MAX)
        columns.append(PlannedColumn(name=status_key, status_key=status_key, category=category))
        for status_id in ids:
            status_to_key[status_id] = status_key
    return columns, status_to_key


# --------------------------------------------------------------------------- sprints


def _planned_sprint(raw: dict[str, Any], name: str) -> PlannedSprint:
    state = str(raw.get("state") or "future").lower()
    return PlannedSprint(
        jira_id=int(raw["id"]),
        name=name,
        goal=(str(raw.get("goal")).strip() or None) if raw.get("goal") else None,
        status=_SPRINT_STATE.get(state, "draft"),
        start_date=parse_datetime(raw.get("startDate")),
        end_date=parse_datetime(raw.get("endDate")),
        closed_at=parse_datetime(raw.get("completeDate")) if state == "closed" else None,
    )


def plan_sprints(
    key: str, snapshot: Snapshot, issues: list[dict[str, Any]], sprint_fields: list[str]
) -> list[PlannedSprint]:
    since = parse_date(snapshot.manifest.get("since")) or datetime(2026, 1, 1, tzinfo=BOGOTA)
    candidates: dict[int, dict[str, Any]] = {}
    referenced: set[int] = set()
    for issue in issues:
        for ref in _sprint_refs(issue["fields"], sprint_fields):
            candidates.setdefault(int(ref["id"]), ref)
            referenced.add(int(ref["id"]))
    for board in snapshot.boards.get(key) or []:
        for raw in snapshot.sprints.get(int(board["id"])) or []:
            sprint_id = int(raw["id"])
            end = parse_datetime(raw.get("endDate")) or parse_datetime(raw.get("completeDate"))
            recent = raw.get("state") in ("active", "future") or (end is not None and end >= since)
            if sprint_id in referenced or recent:
                candidates[sprint_id] = {**candidates.get(sprint_id, {}), **raw}

    def sort_key(raw: dict[str, Any]) -> tuple:
        start = parse_datetime(raw.get("startDate"))
        return (start is None, start or since, int(raw["id"]))

    taken: set[str] = set()
    return [
        _planned_sprint(
            raw, _unique(str(raw.get("name") or f"Sprint {raw['id']}"), taken, SPRINT_NAME_MAX)
        )
        for raw in sorted(candidates.values(), key=sort_key)
    ]


# --------------------------------------------------------------------------- tasks


def plan_task(
    issue: dict[str, Any],
    project: PlannedProject,
    status_to_key: dict[str, str],
    snapshot: Snapshot,
    plan: FeedPlan,
    *,
    context: bool,
) -> PlannedTask:
    fields = issue["fields"]
    key = str(issue["key"])
    mappings = build_mappings({"type_map": _SPANISH_TYPES})

    summary = str(fields.get("summary") or key).strip()
    description = adf_to_markdown(fields.get("description"))
    title = summary
    if len(summary) > TITLE_MAX:
        title = summary[: TITLE_MAX - 1].rstrip() + "…"
        description = f"**Título completo en Jira:** {summary}\n\n{description or ''}".strip()
        plan.warn("titulo_recortado_a_200", key)

    issue_type = fields.get("issuetype") or {}
    task_type, type_ok = resolve_type(
        str(issue_type.get("name") or ""),
        is_subtask=bool(issue_type.get("subtask")),
        mappings=mappings,
    )
    if not type_ok:
        plan.warn("tipo_no_homologado", f"{key}: {issue_type.get('name')}")
    priority, priority_ok = resolve_priority(
        str((fields.get("priority") or {}).get("name") or "Medium"), mappings=mappings
    )
    if not priority_ok:
        plan.warn("prioridad_no_homologada", f"{key}: {(fields.get('priority') or {}).get('name')}")

    status = fields.get("status") or {}
    status_key = status_to_key.get(str(status.get("id")))
    if status_key is None:
        category = (status.get("statusCategory") or {}).get("key") or "new"
        fallback = next((c for c in project.columns if c.category == category), project.columns[0])
        status_key = fallback.status_key
        plan.warn("estado_por_categoria", f"{key}: {status.get('name')}")

    resolved = parse_datetime(fields.get("resolutiondate"))
    updated = parse_datetime(fields.get("updated"))
    completed_at = None
    if status_key == project.done_status:
        completed_at = resolved or updated
        if resolved is None:
            plan.warn("finalizada_sin_fecha_de_resolucion", key)

    points_raw = _story_points(fields, snapshot.manifest.get("story_point_fields") or [])
    points: int | None = None
    if points_raw is not None:
        if project.methodology != "scrum":
            plan.warn("puntos_descartados_por_metodologia", key)
        else:
            points = int(math.ceil(points_raw))
            if points != points_raw:
                plan.warn("puntos_redondeados_hacia_arriba", f"{key}: {points_raw}")

    sprint_refs = _sprint_refs(fields, snapshot.manifest.get("sprint_fields") or [])
    sprint_id = (
        int(sprint_refs[-1]["id"]) if sprint_refs and project.methodology == "scrum" else None
    )

    start_fields = snapshot.manifest.get("start_date_fields") or []
    start = next((parse_date(fields.get(f)) for f in start_fields if fields.get(f)), None)

    return PlannedTask(
        key=key,
        number=int(key.rsplit("-", 1)[1]),
        title=title,
        description=description,
        task_type=task_type,
        priority=priority,
        status=status_key,
        created_at=parse_datetime(fields.get("created")),
        updated_at=updated,
        due_date=parse_date(fields.get("duedate")),
        start_date=start,
        completed_at=completed_at,
        estimation_points=points,
        assignee_account_id=(fields.get("assignee") or {}).get("accountId"),
        reporter_account_id=(fields.get("reporter") or {}).get("accountId"),
        sprint_jira_id=sprint_id,
        parent_key=(fields.get("parent") or {}).get("key"),
        context=context,
    )


# --------------------------------------------------------------------------- plan


def build_feed_plan(snapshot: Snapshot) -> FeedPlan:
    manifest = snapshot.manifest
    plan = FeedPlan(
        site_host=str(manifest.get("site_host") or ""),
        since=str(manifest.get("since") or ""),
        users=[],
        projects=[],
        excluded_projects={},
    )
    plan.users = plan_users(snapshot, plan)
    sprint_fields = manifest.get("sprint_fields") or []
    context_by_project: dict[str, list[dict[str, Any]]] = {}
    for issue in snapshot.context_issues:
        context_by_project.setdefault(issue["key"].rsplit("-", 1)[0], []).append(issue)

    for raw in sorted(snapshot.projects, key=lambda p: p["key"]):
        key = str(raw["key"])
        issues = snapshot.issues.get(key) or []
        if not issues:
            plan.excluded_projects[key] = 0
            continue
        context = context_by_project.get(key, [])
        code = key if _CODE_RE.match(key) else re.sub(r"[^A-Z0-9]", "", key.upper())[:10]
        if code != key:
            plan.warn("codigo_de_proyecto_ajustado", f"{key} -> {code}")
        boards = snapshot.boards.get(key) or []
        board_types = [str(b.get("type")) for b in boards]
        uses_sprints = any(_sprint_refs(i["fields"], sprint_fields) for i in issues)
        methodology = "scrum" if "scrum" in board_types or uses_sprints else "kanban"
        description = raw.get("description")
        project = PlannedProject(
            key=key,
            code=code,
            name=str(raw.get("name") or key)[:PROJECT_NAME_MAX],
            description=str(description).strip() or None if description else None,
            category=(raw.get("projectCategory") or {}).get("name"),
            methodology=methodology,
            lead_account_id=(raw.get("lead") or {}).get("accountId"),
            board_types=board_types,
            columns=[],
        )
        project.columns, status_to_key = plan_columns(key, snapshot, issues + context, plan)
        if methodology == "scrum":
            project.sprints = plan_sprints(key, snapshot, issues, sprint_fields)
        project.tasks = [
            plan_task(i, project, status_to_key, snapshot, plan, context=False) for i in issues
        ] + [plan_task(i, project, status_to_key, snapshot, plan, context=True) for i in context]

        by_sprint: dict[int, int] = {}
        for task in project.tasks:
            if task.sprint_jira_id is not None and task.status == project.done_status:
                by_sprint[task.sprint_jira_id] = by_sprint.get(task.sprint_jira_id, 0) + (
                    task.estimation_points or 0
                )
        for sprint in project.sprints:
            if sprint.status == "closed":
                sprint.completed_points = by_sprint.get(sprint.jira_id, 0)
        plan.projects.append(project)

    human_ids = {u.account_id for u in plan.users}
    for project in plan.projects:
        for task in project.tasks:
            if task.assignee_account_id and task.assignee_account_id not in human_ids:
                plan.warn("responsable_no_humano_omitido", task.key)
                task.assignee_account_id = None
            if task.reporter_account_id and task.reporter_account_id not in human_ids:
                plan.warn("informador_no_humano_omitido", task.key)
                task.reporter_account_id = None
    return plan
