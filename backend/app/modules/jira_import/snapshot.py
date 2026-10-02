"""Raw Jira snapshot: fetch (read-only) to disk and load it back.

The snapshot is the single input of every dry-run/apply, so the database step
never needs network access nor credentials. Layout (every file ``0600``)::

    raw/manifest.json            site host, fetched_at, since, field ids
    raw/fields.json              GET /rest/api/3/field
    raw/projects.json            GET /rest/api/3/project/search (expand)
    raw/users.json               GET /rest/api/3/users/search
    raw/statuses/<KEY>.json      GET /rest/api/3/project/<KEY>/statuses
    raw/boards/<KEY>.json        GET /rest/agile/1.0/board?projectKeyOrId=<KEY>
    raw/board_config/<ID>.json   GET /rest/agile/1.0/board/<ID>/configuration
    raw/sprints/<ID>.json        GET /rest/agile/1.0/board/<ID>/sprint
    raw/issues/<KEY>.json        GET /rest/api/3/search/jql (scope JQL)
    raw/issues_context.json      parents of in-scope issues outside the window
"""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from app.modules.jira_import.client import JiraReadClient, JiraReadError

STORY_POINT_FIELD_NAMES = ("story points", "story point estimate", "puntos de historia")
SPRINT_FIELD_NAMES = ("sprint",)
START_DATE_FIELD_NAMES = ("start date", "fecha de inicio")
BASE_ISSUE_FIELDS = (
    "summary",
    "description",
    "issuetype",
    "status",
    "priority",
    "assignee",
    "reporter",
    "created",
    "updated",
    "duedate",
    "resolutiondate",
    "parent",
    "labels",
    "project",
)


def read_jira_credentials(env_file: Path | None, prefix: str) -> tuple[str, str, str]:
    """Return ``(base_url, email, api_token)``.

    ``os.environ`` wins; otherwise ONLY the three ``<prefix>_URL``/
    ``<prefix>_EMAIL``/``<prefix>_API_TOKEN`` lines of ``env_file`` are read —
    every other key of that file is skipped without being kept in memory.
    """

    wanted = {f"{prefix}_URL", f"{prefix}_EMAIL", f"{prefix}_API_TOKEN"}
    values = {key: os.environ[key] for key in wanted if os.environ.get(key)}
    if env_file is not None and len(values) < len(wanted):
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, sep, raw = line.partition("=")
            key = key.strip().removeprefix("export ").strip()
            if not sep or key not in wanted or key in values:
                continue
            values[key] = raw.strip().strip('"').strip("'")
    missing = sorted(wanted - values.keys())
    if missing:
        raise ValueError(f"Faltan credenciales de Jira: {', '.join(missing)}")
    return values[f"{prefix}_URL"], values[f"{prefix}_EMAIL"], values[f"{prefix}_API_TOKEN"]


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    os.chmod(path, 0o600)


def _read(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _field_ids(fields: list[dict[str, Any]], names: tuple[str, ...]) -> list[str]:
    return [
        str(item["id"])
        for item in fields
        if str(item.get("name", "")).strip().lower() in names and item.get("id")
    ]


def scope_jql(project_key: str, since: str) -> str:
    window = f'(created >= "{since}" OR updated >= "{since}")'
    return f'project = "{project_key}" AND {window} ORDER BY key ASC'


async def fetch_snapshot(
    client: JiraReadClient,
    raw_dir: Path,
    *,
    base_url: str,
    since: str = "2026-01-01",
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Download everything the feed needs into ``raw_dir`` (GET only)."""

    raw_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    fields = await client.get("/rest/api/3/field")
    _write(raw_dir / "fields.json", fields)
    story_fields = _field_ids(fields, STORY_POINT_FIELD_NAMES)
    sprint_fields = _field_ids(fields, SPRINT_FIELD_NAMES)
    start_fields = _field_ids(fields, START_DATE_FIELD_NAMES)

    projects = await client.paginate_values(
        "/rest/api/3/project/search",
        {"expand": "description,lead,projectKeys", "status": "live,archived"},
    )
    _write(raw_dir / "projects.json", projects)
    log(f"Proyectos visibles en el sitio: {len(projects)}")

    users = await client.paginate_list("/rest/api/3/users/search", page_size=1000)
    _write(raw_dir / "users.json", users)
    log(f"Cuentas del sitio: {len(users)}")

    issue_fields = [*BASE_ISSUE_FIELDS, *story_fields, *sprint_fields, *start_fields]
    in_scope: dict[str, int] = {}
    for project in projects:
        key = project["key"]
        try:
            issues = await client.search_jql(scope_jql(key, since), issue_fields)
        except JiraReadError as exc:
            log(f"  {key}: no se pudo consultar ({exc.status_code})")
            continue
        _write(raw_dir / "issues" / f"{key}.json", issues)
        log(f"  {key}: {len(issues)} issues desde {since}")
        if not issues:
            continue
        in_scope[key] = len(issues)
        try:
            statuses = await client.get(f"/rest/api/3/project/{key}/statuses")
        except JiraReadError:
            statuses = []
        _write(raw_dir / "statuses" / f"{key}.json", statuses)
        try:
            boards = await client.paginate_values("/rest/agile/1.0/board", {"projectKeyOrId": key})
        except JiraReadError:
            boards = []
        _write(raw_dir / "boards" / f"{key}.json", boards)
        for board in boards:
            board_id = board["id"]
            config_path = raw_dir / "board_config" / f"{board_id}.json"
            if not config_path.exists():
                try:
                    _write(
                        config_path,
                        await client.get(f"/rest/agile/1.0/board/{board_id}/configuration"),
                    )
                except JiraReadError:
                    _write(config_path, {})
            sprint_path = raw_dir / "sprints" / f"{board_id}.json"
            if board.get("type") == "scrum" and not sprint_path.exists():
                try:
                    sprints = await client.paginate_values(
                        f"/rest/agile/1.0/board/{board_id}/sprint"
                    )
                except JiraReadError:
                    sprints = []
                _write(sprint_path, sprints)

    known = {
        issue["key"] for key in in_scope for issue in _read(raw_dir / "issues" / f"{key}.json", [])
    }
    missing_parents = sorted(
        {
            parent["key"]
            for key in in_scope
            for issue in _read(raw_dir / "issues" / f"{key}.json", [])
            if (parent := (issue.get("fields") or {}).get("parent"))
            and parent.get("key") not in known
        }
    )
    context: list[dict[str, Any]] = []
    for start in range(0, len(missing_parents), 50):
        chunk = ", ".join(f'"{k}"' for k in missing_parents[start : start + 50])
        context.extend(await client.search_jql(f"key in ({chunk})", issue_fields))
    _write(raw_dir / "issues_context.json", context)
    log(f"Padres fuera de la ventana traídos como contexto: {len(context)}")

    manifest = {
        "site_host": urlsplit(base_url).netloc,
        "fetched_at": datetime.now(UTC).isoformat(),
        "since": since,
        "story_point_fields": story_fields,
        "sprint_fields": sprint_fields,
        "start_date_fields": start_fields,
        "projects_in_scope": in_scope,
        "requests_made": client.requests_made,
    }
    _write(raw_dir / "manifest.json", manifest)
    return manifest


@dataclass
class Snapshot:
    """Raw snapshot loaded back from disk (pure data, no network)."""

    manifest: dict[str, Any]
    fields: list[dict[str, Any]]
    projects: list[dict[str, Any]]
    users: list[dict[str, Any]]
    issues: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    statuses: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    boards: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    board_configs: dict[int, dict[str, Any]] = field(default_factory=dict)
    sprints: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    context_issues: list[dict[str, Any]] = field(default_factory=list)


def load_snapshot(raw_dir: Path) -> Snapshot:
    manifest = _read(raw_dir / "manifest.json")
    if manifest is None:
        raise FileNotFoundError(f"No hay snapshot en {raw_dir} (falta manifest.json)")

    def by_stem(folder: str, as_int: bool = False) -> dict:
        directory = raw_dir / folder
        if not directory.is_dir():
            return {}
        return {
            (int(path.stem) if as_int else path.stem): _read(path)
            for path in sorted(directory.glob("*.json"))
        }

    return Snapshot(
        manifest=manifest,
        fields=_read(raw_dir / "fields.json", []),
        projects=_read(raw_dir / "projects.json", []),
        users=_read(raw_dir / "users.json", []),
        issues=by_stem("issues"),
        statuses=by_stem("statuses"),
        boards=by_stem("boards"),
        board_configs=by_stem("board_config", as_int=True),
        sprints=by_stem("sprints", as_int=True),
        context_issues=_read(raw_dir / "issues_context.json", []),
    )
