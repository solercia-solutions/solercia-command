"""CLI: importa el checklist personal de tareas (CSV/XLSX) a una organización.

Ejecución en el host, desde ``backend/``::

    .venv/bin/python -m scripts.import_sdm_tasks --organization-slug sdmujer \\
        --checklist /ruta/CHECKLIST_TAREAS.csv --report /ruta/informe-tareas \\
        --database-url postgresql+asyncpg://app:app@127.0.0.1:5434/solercia

Por defecto es una SIMULACIÓN: abre una transacción ``READ ONLY``, clasifica
cada fila (crear / sin cambios / con diferencias / inactiva / en otro proyecto)
y escribe el informe (JSON + Markdown). Solo ``--apply`` escribe, en UNA
transacción, y exige ``--expect-database host:puerto/base`` idéntico al destino
para evitar aplicar sobre la base equivocada. Repetir la corrida no duplica: la
identidad es ``(organización, checklist_xlsx, <espacio>:<ID>)``.

Códigos de salida: 0 éxito · 1 uso · 2 fuente no válida · 3 organización
inexistente/inactiva · 4 error inesperado (revertido) · 5 destino incompleto
(proyecto o columna faltante; no se escribió nada).
"""

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db_init  # noqa: F401  (registers every ORM model)
from app.config import settings
from app.modules.organizations.repository import OrganizationRepository
from app.modules.task_import.checklist_apply import (
    ChecklistTargetError,
    SessionChecklistImportUow,
    SqlChecklistImportStore,
    apply_checklist_plan,
    classify,
    require_targets,
)
from app.modules.task_import.checklist_import import (
    CHECKLIST_SOURCE,
    DEFAULT_NAMESPACE,
    ChecklistPlan,
    build_checklist_plan,
    work_folders_from_names,
)
from app.modules.task_import.checklist_parser import parse_checklist
from app.modules.task_import.contracts import ChecklistProfile, ParseLimits, SourceSnapshot

EXIT_OK = 0
EXIT_USAGE_ERROR = 1
EXIT_SOURCE_ERROR = 2
EXIT_ORGANIZATION_NOT_FOUND = 3
EXIT_UNEXPECTED_ERROR = 4
EXIT_TARGET_INCOMPLETE = 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.import_sdm_tasks",
        description="Importa el checklist de tareas. Simulación por defecto.",
    )
    parser.add_argument("--organization-slug", required=True)
    parser.add_argument("--checklist", type=Path, required=True, help="CSV o XLSX del checklist.")
    parser.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        help="Espacio de la clave de negocio (por defecto CHECKLIST_TAREAS).",
    )
    parser.add_argument(
        "--tareas-root",
        type=Path,
        help="Carpeta TAREAS original: solo se LISTAN nombres de carpetas T-NN (no se leen).",
    )
    parser.add_argument("--assignee-email", help="Responsable explícito (miembro activo).")
    parser.add_argument("--actor-email", help="Autor de la importación (miembro activo).")
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Con --apply, sobrescribe las tareas ancladas cuyos campos difieren.",
    )
    parser.add_argument("--report", type=Path, required=True, help="Ruta base del informe.")
    parser.add_argument("--database-url", default=settings.DATABASE_URL)
    parser.add_argument("--apply", action="store_true", help="Escribe en una transacción.")
    parser.add_argument(
        "--expect-database",
        help="Obligatorio con --apply: host:puerto/base que debe coincidir con el destino.",
    )
    return parser


def describe_database(url: str) -> str:
    parsed = make_url(url)
    return f"{parsed.host}:{parsed.port or 5432}/{parsed.database}"


def load_plan(args: argparse.Namespace) -> ChecklistPlan:
    data = args.checklist.read_bytes()
    preview = parse_checklist(
        SourceSnapshot(args.checklist.name, data, provenance="cli"),
        ChecklistProfile(),
        ParseLimits(),
    )
    if not preview.complete:
        codes = ", ".join(sorted({issue.code for issue in preview.issues}))
        raise ValueError(f"El checklist no se pudo leer completo ({codes}).")
    folders = None
    if args.tareas_root is not None:
        names = [entry.name for entry in os.scandir(args.tareas_root) if entry.is_dir()]
        folders = work_folders_from_names(names)
    return build_checklist_plan(
        preview, source_name=args.checklist.name, namespace=args.namespace, work_folders=folders
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


def write_report(base: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    json_path = base.with_name(base.name + ".json")
    md_path = base.with_name(base.name + ".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


async def run(args: argparse.Namespace) -> int:
    if not args.checklist.is_file():
        print(f"No existe el checklist: {args.checklist}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    database = describe_database(args.database_url)
    print(f"Base de datos destino: {database}")
    if args.apply and args.expect_database != database:
        print(
            "Con --apply, --expect-database debe ser exactamente el destino "
            f"({database}); no se escribió nada.",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR
    try:
        plan = load_plan(args)
    except (ValueError, OSError) as exc:
        print(f"Fuente no válida: {exc}", file=sys.stderr)
        return EXIT_SOURCE_ERROR
    print(f"Modo: {'APLICAR (escribe)' if args.apply else 'simulación (solo lectura)'}")

    engine = create_async_engine(args.database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    applied = None
    try:
        async with factory() as session:
            if not args.apply:
                await session.execute(text("SET TRANSACTION READ ONLY"))
            organization = await OrganizationRepository(session).get_by_slug(args.organization_slug)
            if organization is None or not organization.is_active:
                await session.rollback()
                print(
                    f"La organización «{args.organization_slug}» no existe o está inactiva; "
                    "no se escribió nada.",
                    file=sys.stderr,
                )
                return EXIT_ORGANIZATION_NOT_FOUND
            org_info = {"slug": organization.slug, "id": str(organization.id)}
            store = SqlChecklistImportStore(session)
            people: dict[str, Any] = {}
            for flag in ("assignee_email", "actor_email"):
                email = getattr(args, flag)
                if email:
                    people[flag] = await store.find_member(organization.id, email)
                    if people[flag] is None:
                        await session.rollback()
                        print(f"{email} no es miembro activo de la organización.", file=sys.stderr)
                        return EXIT_USAGE_ERROR
            codes = sorted({d.project_code for d in plan.drafts})
            targets = await store.project_targets(organization.id, codes)
            missing = require_targets(plan, targets)
            anchors = await store.find_anchors(
                organization.id, CHECKLIST_SOURCE, [d.external_key for d in plan.drafts]
            )
            items = classify(plan, anchors, targets)
            if args.apply:
                if missing:
                    raise ChecklistTargetError(" ".join(missing))
                result = await apply_checklist_plan(
                    SessionChecklistImportUow(session),
                    organization.id,
                    plan,
                    actor_id=people.get("actor_email"),
                    assignee_id=people.get("assignee_email"),
                    update_existing=args.update_existing,
                )
                applied = dict(vars(result))
                print(
                    "Aplicado en una transacción: "
                    + json.dumps({k: len(v) for k, v in applied.items()}, ensure_ascii=False)
                )
            else:
                await session.rollback()
    except ChecklistTargetError as exc:
        print(f"Destino incompleto; no se escribió nada: {exc}", file=sys.stderr)
        return EXIT_TARGET_INCOMPLETE
    except Exception as exc:  # noqa: BLE001 — typed exit code, transaction rolled back
        print(f"Error inesperado; no se aplicaron cambios: {exc!r}", file=sys.stderr)
        return EXIT_UNEXPECTED_ERROR
    finally:
        await engine.dispose()

    report = build_report(
        plan,
        items,
        mode="apply" if args.apply else "dry-run",
        database=database,
        organization=org_info,
        missing=missing,
        applied=applied,
    )
    json_path, md_path = write_report(args.report, report)
    print(
        f"Planificadas: {len(plan.drafts)} · omitidas: {len(plan.skipped)} · "
        f"a revisión: {len(plan.review)}"
    )
    print("Resultado por fila: " + json.dumps(report["counts"]["outcomes"], ensure_ascii=False))
    print("Por proyecto: " + json.dumps(report["counts"]["by_project"], ensure_ascii=False))
    if missing:
        print("Destino incompleto: " + " | ".join(missing))
    print(f"Informe: {json_path} · {md_path}")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
