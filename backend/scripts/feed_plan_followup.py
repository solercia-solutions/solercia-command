"""CLI: alimenta el seguimiento de los planes ya cargados (reportes por periodo y
enlaces tarea↔actividad) desde fuentes reales, con cita literal de cada dato.

Ejecución en el host, desde ``backend/``::

    .venv/bin/python -m scripts.feed_plan_followup --organization-slug sdmujer \\
        --checklist CHECKLIST_TAREAS.csv --pai PAI-CORREGIDO.xlsx \\
        --cruce REPORTE_CRUCE_PLAN_SEGURIDAD_2026-08-14.md \\
        --monthly "Reporte Seguimiento ... Enero.docx" ... \\
        --report /ruta/informe-seguimiento --database-url postgresql+asyncpg://...

Simulación por defecto (transacción ``READ ONLY``). ``--apply`` escribe en UNA
transacción por la costura idempotente del 45a y exige ``--expect-database``
igual al destino. Requiere que las tareas del checklist ya estén importadas
(``scripts.import_sdm_tasks``); lo que no resuelve va al informe de revisión.

Códigos de salida: 0 éxito · 1 uso · 2 fuente no válida · 3 organización
inexistente/inactiva · 4 error inesperado (revertido).
"""

import argparse
import asyncio
import json
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
from app.modules.plans.importers.common import SourceFormatError, SourceInfo
from app.modules.plans.importers.followup import (
    FollowupBundle,
    checklist_link_candidates,
    monthly_report_review,
    parse_cruce_report,
    parse_pai_followup,
)
from app.modules.plans.importers.followup_apply import (
    ResolvedFollowup,
    SessionFollowupUow,
    apply_followup,
    resolve_followup,
)
from app.modules.plans.importers.pai import DEFAULT_POLICIES
from app.modules.task_import.checklist_apply import SqlChecklistImportStore
from app.modules.task_import.checklist_import import DEFAULT_NAMESPACE
from app.modules.task_import.checklist_parser import parse_checklist
from app.modules.task_import.contracts import ChecklistProfile, ParseLimits, SourceSnapshot

EXIT_OK = 0
EXIT_USAGE_ERROR = 1
EXIT_SOURCE_ERROR = 2
EXIT_ORGANIZATION_NOT_FOUND = 3
EXIT_UNEXPECTED_ERROR = 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.feed_plan_followup",
        description="Reportes por periodo y enlaces tarea↔actividad. Simulación por defecto.",
    )
    parser.add_argument("--organization-slug", required=True)
    parser.add_argument("--checklist", type=Path, help="Checklist CSV/XLSX (enlaces declarados).")
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--pai", type=Path, help="XLSX del PAI con el seguimiento diligenciado.")
    parser.add_argument("--pai-policies", default=",".join(DEFAULT_POLICIES))
    parser.add_argument("--cruce", type=Path, help="Reporte de cruce PSPI vs. checklist (.md).")
    parser.add_argument("--monthly", type=Path, nargs="*", default=[], help="Reportes mensuales.")
    parser.add_argument("--period-year", type=int, default=2026)
    parser.add_argument("--actor-email", help="Autor de la carga (miembro activo).")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--database-url", default=settings.DATABASE_URL)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expect-database", help="Obligatorio con --apply: host:puerto/base.")
    return parser


def describe_database(url: str) -> str:
    parsed = make_url(url)
    return f"{parsed.host}:{parsed.port or 5432}/{parsed.database}"


def checklist_rows(path: Path) -> list[tuple[str, int, dict[str, str]]]:
    preview = parse_checklist(
        SourceSnapshot(path.name, path.read_bytes(), provenance="cli"),
        ChecklistProfile(),
        ParseLimits(),
    )
    if not preview.complete:
        raise SourceFormatError("El checklist no se pudo leer completo.")
    headings = [str(cell.value) for cell in preview.headers]
    rows = []
    for row in preview.rows:
        values = {
            h: "" if c.value is None else str(c.value)
            for h, c in zip(headings, row.cells, strict=False)
        }
        if values.get("ID"):
            rows.append((values["ID"], row.number, values))
    return rows


def build_bundle(args: argparse.Namespace) -> FollowupBundle:
    bundle = FollowupBundle()
    if args.pai:
        policies = tuple(p.strip() for p in args.pai_policies.split(",") if p.strip())
        reports, review = parse_pai_followup(
            args.pai, period_year=args.period_year, policies=policies
        )
        bundle.sources.append(SourceInfo.of(args.pai))
        bundle.reports += reports
        bundle.review += review
    if args.checklist:
        links, review = checklist_link_candidates(
            checklist_rows(args.checklist),
            source_name=args.checklist.name,
            period_year=args.period_year,
        )
        bundle.sources.append(SourceInfo.of(args.checklist))
        bundle.links += links
        bundle.review += review
    if args.cruce:
        links, review = parse_cruce_report(args.cruce, period_year=args.period_year)
        bundle.sources.append(SourceInfo.of(args.cruce))
        bundle.links += links
        bundle.review += review
    for path in args.monthly:
        bundle.sources.append(SourceInfo.of(path))
    bundle.review += monthly_report_review(args.monthly)
    return bundle


def build_report(
    bundle: FollowupBundle,
    resolved: ResolvedFollowup,
    *,
    mode: str,
    database: str,
    organization: dict[str, str],
    written: dict[str, int] | None,
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": mode,
        "database": database,
        "organization": organization,
        "sources": [
            {"name": s.name, "sha256": s.sha256, "bytes": s.size_bytes} for s in bundle.sources
        ],
        "counts": {
            "reports": dict(Counter(r.status for r in resolved.reports)),
            "links": dict(Counter(link.status for link in resolved.links)),
            "links_by_role": dict(Counter(link.candidate.role for link in resolved.links)),
            "links_by_plan": dict(
                Counter(link.activity_key.split("/")[0] for link in resolved.links)
            ),
            "review": dict(Counter(item.origin for item in resolved.review)),
        },
        "reports": [
            {
                "activity": r.draft.activity_key,
                "period": r.draft.period,
                "reported_progress": str(r.draft.reported_progress)
                if r.draft.reported_progress is not None
                else None,
                "raw_progress": r.draft.raw_progress,
                "progress_basis": r.draft.progress_basis,
                "is_met": r.draft.is_met,
                "met_on_time": r.draft.met_on_time,
                "evidence_refs": r.draft.evidence_refs,
                "qualitative_summary": r.draft.qualitative_summary,
                "source": r.draft.source_ref,
                "status": r.status,
            }
            for r in resolved.reports
        ],
        "links": [
            {
                "task": link.candidate.source_id,
                "activity": link.activity_key,
                "role": link.candidate.role,
                "resolution": link.candidate.resolution,
                "source": link.candidate.source_ref,
                "quote": link.candidate.quote,
                "status": link.status,
            }
            for link in resolved.links
        ],
        "review": [
            {"origin": r.origin, "subject": r.subject, "reason": r.reason, "quote": r.quote}
            for r in resolved.review
        ],
        "written": written,
    }


def render_markdown(report: dict[str, Any]) -> str:
    mode = "simulación (no escribe)" if report["mode"] == "dry-run" else "aplicación"
    lines = [
        "# Seguimiento de planes: reportes por periodo y enlaces tarea↔actividad",
        "",
        f"- Modo: **{mode}**",
        f"- Base de datos: `{report['database']}`",
        f"- Organización: `{report['organization']['slug']}`",
        f"- Generado: {report['generated_at']}",
        "",
        "## Fuentes",
        "",
        "| Archivo | SHA-256 | Bytes |",
        "|---|---|---:|",
    ]
    lines += [f"| {s['name']} | `{s['sha256']}` | {s['bytes']} |" for s in report["sources"]]
    lines += [
        "",
        "## Conteos",
        "",
        "```json",
        json.dumps(report["counts"], ensure_ascii=False, indent=2),
        "```",
    ]
    if report["written"]:
        lines += ["", f"Escrito: {json.dumps(report['written'], ensure_ascii=False)}"]
    lines += ["", f"## Reportes por actividad y periodo ({len(report['reports'])})", ""]
    for r in report["reports"]:
        lines += [
            f"### {r['activity']} · periodo {r['period']} · {r['status']}",
            "",
            f"- Avance reportado: {r['reported_progress'] or '—'} "
            f"(valor de la fuente «{r['raw_progress'] or '—'}», {r['progress_basis']})",
            f"- ¿Se cumplió?: {r['is_met']} · ¿En la fecha programada?: {r['met_on_time']}",
            f"- Evidencias: {'; '.join(r['evidence_refs'] or []) or '—'}",
            f"- Fuente: {r['source']}",
            f"- Cita: «{(r['qualitative_summary'] or '')[:400]}»",
            "",
        ]
    lines += [f"## Enlaces tarea↔actividad ({len(report['links'])})", ""]
    lines += [
        "| Tarea | Actividad | Rol | Resolución | Estado | Fuente |",
        "|---|---|---|---|---|---|",
    ]
    lines += [
        f"| {lk['task']} | {lk['activity']} | {lk['role']} | {lk['resolution']} | {lk['status']} | "
        f"{lk['source']} |"
        for lk in report["links"]
    ]
    lines += ["", f"## A revisión, sin aplicar ({len(report['review'])})", ""]
    lines += [
        f"- [{r['origin']}] {r['subject']}: {r['reason']}"
        + (f" «{r['quote']}»" if r["quote"] else "")
        for r in report["review"]
    ] or ["Ninguna."]
    return "\n".join(lines) + "\n"


async def run(args: argparse.Namespace) -> int:
    inputs = [p for p in (args.checklist, args.pai, args.cruce, *args.monthly) if p]
    if not inputs:
        print("Indica al menos una fuente.", file=sys.stderr)
        return EXIT_USAGE_ERROR
    missing_files = [str(p) for p in inputs if not p.is_file()]
    if missing_files:
        print(f"No existe la fuente: {', '.join(missing_files)}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    database = describe_database(args.database_url)
    print(f"Base de datos destino: {database}")
    if args.apply and args.expect_database != database:
        print(
            f"Con --apply, --expect-database debe ser exactamente {database}; no se escribió nada.",
            file=sys.stderr,
        )
        return EXIT_USAGE_ERROR
    try:
        bundle = build_bundle(args)
    except (SourceFormatError, ValueError, OSError) as exc:
        print(f"Fuente no válida: {exc}", file=sys.stderr)
        return EXIT_SOURCE_ERROR
    print(f"Modo: {'APLICAR (escribe)' if args.apply else 'simulación (solo lectura)'}")

    year = args.period_year
    plan_codes = [f"PSPI-{year}", f"PTR-{year}", f"PAI-{year}"]
    engine = create_async_engine(args.database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    written = None
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
            actor_id = None
            if args.actor_email:
                actor_id = await SqlChecklistImportStore(session).find_member(
                    organization.id, args.actor_email
                )
                if actor_id is None:
                    await session.rollback()
                    print(f"{args.actor_email} no es miembro activo.", file=sys.stderr)
                    return EXIT_USAGE_ERROR
            uow = SessionFollowupUow(session)
            resolved = await resolve_followup(
                uow, organization.id, bundle, plan_codes=plan_codes, namespace=args.namespace
            )
            if args.apply:
                written = await apply_followup(uow, resolved, actor_id=actor_id)
                print("Aplicado en una transacción: " + json.dumps(written))
            else:
                await session.rollback()
    except Exception as exc:  # noqa: BLE001 — typed exit code, transaction rolled back
        print(f"Error inesperado; no se aplicaron cambios: {exc!r}", file=sys.stderr)
        return EXIT_UNEXPECTED_ERROR
    finally:
        await engine.dispose()

    report = build_report(
        bundle,
        resolved,
        mode="apply" if args.apply else "dry-run",
        database=database,
        organization=org_info,
        written=written,
    )
    base = args.report
    json_path = base.with_name(base.name + ".json")
    md_path = base.with_name(base.name + ".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print("Conteos: " + json.dumps(report["counts"], ensure_ascii=False))
    print(f"Informe: {json_path} · {md_path}")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
