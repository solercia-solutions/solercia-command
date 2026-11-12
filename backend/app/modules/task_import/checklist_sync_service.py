"""Reusable checklist sync (C01): load the CSV/XLSX plan, classify it and, in
apply mode, write it — shared by ``scripts.import_sdm_tasks`` and the
scheduled ``daily_sync`` job.

Transaction ownership (agents/rules/solercia-persistence.md): this use case
owns completion through :class:`ChecklistSyncUow`. A dry run marks the
transaction read-only and always rolls back; an apply delegates to
:func:`apply_checklist_plan`, which commits ONCE or rolls back everything.
Every read is scoped to the organization resolved from its slug.
"""

import json
import os
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.repository import OrganizationRepository

from .checklist_apply import (
    ChecklistImportStore,
    ChecklistTargetError,
    Classified,
    SessionChecklistImportUow,
    apply_checklist_plan,
    classify,
    require_targets,
)
from .checklist_import import (
    CHECKLIST_SOURCE,
    DEFAULT_NAMESPACE,
    ChecklistPlan,
    build_checklist_plan,
    work_folders_from_names,
)
from .checklist_parser import parse_checklist
from .contracts import ChecklistProfile, ParseLimits, SourceSnapshot

SyncMode = Literal["dry-run", "apply"]


class ChecklistSourceError(ValueError):
    """The checklist file could not be read or parsed completely."""


class ChecklistOrganizationError(LookupError):
    """The organization slug does not exist or is inactive."""

    def __init__(self, slug: str) -> None:
        super().__init__(slug)
        self.slug = slug


class ChecklistMemberError(LookupError):
    """An explicit actor/assignee email is not an active member."""

    def __init__(self, email: str) -> None:
        super().__init__(email)
        self.email = email


class OrganizationRef(Protocol):
    id: uuid.UUID
    slug: str
    is_active: bool


class ChecklistSyncUow(Protocol):
    store: ChecklistImportStore

    async def find_organization(self, slug: str) -> OrganizationRef | None: ...
    async def begin_read_only(self) -> None: ...
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...


class SessionChecklistSyncUow(SessionChecklistImportUow):
    """SQLAlchemy unit of work bound to the caller's session."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self._organizations = OrganizationRepository(session)

    async def find_organization(self, slug: str) -> OrganizationRef | None:
        return await self._organizations.get_by_slug(slug)

    async def begin_read_only(self) -> None:
        await self.session.execute(text("SET TRANSACTION READ ONLY"))


@dataclass(frozen=True)
class ChecklistSyncOptions:
    namespace: str = DEFAULT_NAMESPACE
    actor_email: str | None = None
    assignee_email: str | None = None
    update_existing: bool = False
    apply: bool = False


@dataclass(frozen=True)
class ChecklistSyncConfig:
    """Scheduled-sync configuration; ``None`` from settings means disabled."""

    path: Path
    organization_slug: str
    tareas_root: Path | None = None
    actor_email: str | None = None
    update_existing: bool = True

    @classmethod
    def from_settings(cls, settings: Any) -> "ChecklistSyncConfig | None":
        path = (settings.CHECKLIST_SYNC_PATH or "").strip()
        slug = (settings.CHECKLIST_SYNC_ORG_SLUG or "").strip()
        if not path or not slug:
            return None
        root = (settings.CHECKLIST_SYNC_TAREAS_ROOT or "").strip()
        actor = (settings.CHECKLIST_SYNC_ACTOR_EMAIL or "").strip()
        return cls(
            path=Path(path),
            organization_slug=slug,
            tareas_root=Path(root) if root else None,
            actor_email=actor or None,
            update_existing=bool(settings.CHECKLIST_SYNC_UPDATE_EXISTING),
        )

    def options(self) -> ChecklistSyncOptions:
        return ChecklistSyncOptions(
            actor_email=self.actor_email, update_existing=self.update_existing, apply=True
        )


@dataclass(frozen=True)
class ChecklistSyncResult:
    mode: SyncMode
    organization: dict[str, str]
    plan: ChecklistPlan
    items: list[Classified]
    missing: list[str]
    applied: dict[str, list[str]] | None = None
    counts: dict[str, Any] = field(default_factory=dict)

    def report(self, *, database: str) -> dict[str, Any]:
        return build_report(
            self.plan,
            self.items,
            mode=self.mode,
            database=database,
            organization=self.organization,
            missing=self.missing,
            applied=self.applied,
        )


def load_checklist_plan(
    checklist: Path, *, namespace: str = DEFAULT_NAMESPACE, tareas_root: Path | None = None
) -> ChecklistPlan:
    """Parse ``checklist`` into a plan. ``tareas_root`` is only LISTED."""

    try:
        data = checklist.read_bytes()
        preview = parse_checklist(
            SourceSnapshot(checklist.name, data, provenance="cli"),
            ChecklistProfile(),
            ParseLimits(),
        )
        if not preview.complete:
            codes = ", ".join(sorted({issue.code for issue in preview.issues}))
            raise ChecklistSourceError(f"El checklist no se pudo leer completo ({codes}).")
        folders = None
        if tareas_root is not None:
            names = [entry.name for entry in os.scandir(tareas_root) if entry.is_dir()]
            folders = work_folders_from_names(names)
    except ChecklistSourceError:
        raise
    except (ValueError, OSError) as exc:
        raise ChecklistSourceError(str(exc)) from exc
    return build_checklist_plan(
        preview, source_name=checklist.name, namespace=namespace, work_folders=folders
    )


def _counts(
    plan: ChecklistPlan, items: list[Classified], applied: dict[str, list[str]] | None
) -> dict[str, Any]:
    return {
        "planned": len(plan.drafts),
        "skipped": len(plan.skipped),
        "review": len(plan.review),
        "outcomes": dict(Counter(item.outcome for item in items)),
        "applied": {key: len(value) for key, value in applied.items()} if applied else None,
    }


async def run_checklist_sync(
    uow: ChecklistSyncUow,
    organization_slug: str,
    plan: ChecklistPlan,
    options: ChecklistSyncOptions,
) -> ChecklistSyncResult:
    """Classify ``plan`` for the organization; write it only with ``apply``."""

    try:
        if not options.apply:
            await uow.begin_read_only()
        organization = await uow.find_organization(organization_slug)
        if organization is None or not organization.is_active:
            raise ChecklistOrganizationError(organization_slug)
        store = uow.store
        people: dict[str, uuid.UUID | None] = {}
        for name in ("assignee_email", "actor_email"):
            email = getattr(options, name)
            if email:
                people[name] = await store.find_member(organization.id, email)
                if people[name] is None:
                    raise ChecklistMemberError(email)
        codes = sorted({draft.project_code for draft in plan.drafts})
        targets = await store.project_targets(organization.id, codes)
        missing = require_targets(plan, targets)
        anchors = await store.find_anchors(
            organization.id, CHECKLIST_SOURCE, [draft.external_key for draft in plan.drafts]
        )
        items = classify(plan, anchors, targets)
        applied = None
        if options.apply:
            if missing:
                raise ChecklistTargetError(" ".join(missing))
            result = await apply_checklist_plan(
                uow,
                organization.id,
                plan,
                actor_id=people.get("actor_email"),
                assignee_id=people.get("assignee_email"),
                update_existing=options.update_existing,
            )
            applied = dict(vars(result))
        else:
            await uow.rollback()
    except BaseException:
        await uow.rollback()
        raise
    return ChecklistSyncResult(
        mode="apply" if options.apply else "dry-run",
        organization={"slug": organization.slug, "id": str(organization.id)},
        plan=plan,
        items=items,
        missing=missing,
        applied=applied,
        counts=_counts(plan, items, applied),
    )


async def sync_checklist_from_config(
    session: AsyncSession, config: ChecklistSyncConfig
) -> ChecklistSyncResult:
    """Apply the configured checklist (scheduled job entry point)."""

    plan = load_checklist_plan(config.path, tareas_root=config.tareas_root)
    return await run_checklist_sync(
        SessionChecklistSyncUow(session), config.organization_slug, plan, config.options()
    )


def build_report(
    plan: ChecklistPlan,
    items: list[Any],
    *,
    mode: str,
    database: str,
    organization: dict[str, str],
    missing: list[str],
    applied: dict[str, list[str]] | None,
) -> dict[str, Any]:
    by_project_status = Counter((i.draft.project_code, i.draft.status_key) for i in items)
    projects: dict[str, dict[str, int]] = {}
    for (project, status), count in sorted(by_project_status.items()):
        projects.setdefault(project, {})[status] = count
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": mode,
        "database": database,
        "organization": organization,
        "source": {
            "name": plan.source_name,
            "sha256": plan.sha256,
            "identity": f"({organization['slug']}, {CHECKLIST_SOURCE}, {plan.namespace}:<ID>)",
        },
        "counts": {
            "rows_read": plan.rows_read,
            "drafts": len(plan.drafts),
            "skipped": len(plan.skipped),
            "outcomes": dict(Counter(i.outcome for i in items)),
            "by_project": {k: sum(v.values()) for k, v in projects.items()},
            "by_project_status": projects,
            "null_due_date": sum(1 for d in plan.drafts if d.due_date is None),
            "with_work_folder": sum(1 for d in plan.drafts if d.work_folder),
            "review_by_kind": dict(Counter(n.kind for n in plan.review)),
            "default_categories": dict(
                Counter(d.category for d in plan.drafts if d.project_basis == "default")
            ),
            "completed_without_completed_at": sum(
                1 for d in plan.drafts if d.source_status == "COMPLETADA"
            ),
        },
        "missing_targets": missing,
        "tasks": [
            {
                "id": i.draft.source_id,
                "external_key": i.draft.external_key,
                "row": i.draft.row,
                "lines": [i.draft.line_start, i.draft.line_end],
                "project": i.draft.project_code,
                "project_basis": i.draft.project_basis,
                "source_status": i.draft.source_status,
                "status": i.draft.status_key,
                "priority": i.draft.priority,
                "due_date": i.draft.due_date.isoformat() if i.draft.due_date else None,
                "due_raw": i.draft.due_raw,
                "outcome": i.outcome,
                "differences": list(i.differences),
                "title": i.draft.title,
            }
            for i in items
        ],
        "null_due_dates": [
            {"id": d.source_id, "raw": d.due_raw} for d in plan.drafts if d.due_date is None
        ],
        "review": [
            {"kind": n.kind, "id": n.source_id, "row": n.row, "detail": n.detail}
            for n in plan.review
        ],
        "skipped": [
            {"kind": n.kind, "id": n.source_id, "row": n.row, "detail": n.detail}
            for n in plan.skipped
        ],
        "applied": applied,
    }


def render_markdown(report: dict[str, Any]) -> str:
    c = report["counts"]
    mode = "simulación (no escribe)" if report["mode"] == "dry-run" else "aplicación"
    lines = [
        "# Importación del checklist de tareas",
        "",
        f"- Modo: **{mode}**",
        f"- Base de datos: `{report['database']}`",
        f"- Organización: `{report['organization']['slug']}`",
        f"- Fuente: `{report['source']['name']}` · SHA-256 `{report['source']['sha256']}`",
        f"- Identidad de negocio: `{report['source']['identity']}`",
        f"- Generado: {report['generated_at']}",
        "",
        "## Conteos",
        "",
        f"- Filas leídas: {c['rows_read']} · tareas planificadas: {c['drafts']} · "
        f"omitidas: {c['skipped']}",
        f"- Resultado por fila: {json.dumps(c['outcomes'], ensure_ascii=False)}",
        f"- Sin fecha límite: {c['null_due_date']} · con carpeta de trabajo: "
        f"{c['with_work_folder']}",
        "",
        "| Proyecto | Estado (columna) | Tareas |",
        "|---|---|---:|",
    ]
    for project, statuses in report["counts"]["by_project_status"].items():
        for status, count in statuses.items():
            lines.append(f"| {project} | {status} | {count} |")
    if report["missing_targets"]:
        lines += ["", "## Destino incompleto (bloquea la aplicación)", ""]
        lines += [f"- {m}" for m in report["missing_targets"]]
    if report["applied"]:
        lines += ["", "## Aplicado", ""]
        lines += [f"- {k}: {len(v)}" for k, v in report["applied"].items()]
    lines += [
        "",
        f"Revisión por tipo: {json.dumps(c['review_by_kind'], ensure_ascii=False)}",
        "",
        "Las tareas COMPLETADA quedan sin `completed_at` (la fuente no trae fecha de cierre): "
        f"{c['completed_without_completed_at']}.",
        "",
        "## Categorías sin regla explícita → GENERALES",
        "",
    ]
    lines += [f"- {k or '—'}: {v}" for k, v in sorted(c["default_categories"].items())] or [
        "Ninguna."
    ]
    lines += ["", f"## A revisión ({len(report['review'])})", ""]
    lines += [
        f"- {r['id']} (registro {r['row']}) · {r['kind']}: {r['detail']}" for r in report["review"]
    ] or ["Ninguna."]
    lines += ["", f"## Omitidas ({len(report['skipped'])})", ""]
    lines += [f"- {r['id']} (registro {r['row']}): {r['detail']}" for r in report["skipped"]] or [
        "Ninguna."
    ]
    lines += ["", f"## Tareas sin fecha límite ({len(report['null_due_dates'])})", ""]
    lines += [f"- {r['id']}: «{r['raw'] or '—'}»" for r in report["null_due_dates"]] or ["Ninguna."]
    changed = [t for t in report["tasks"] if t["outcome"] not in ("create", "unchanged")]
    lines += ["", f"## Con diferencias o bloqueadas ({len(changed)})", ""]
    lines += [
        f"- {t['id']} · {t['outcome']} · {', '.join(t['differences']) or '—'}" for t in changed
    ] or ["Ninguna."]
    return "\n".join(lines) + "\n"
