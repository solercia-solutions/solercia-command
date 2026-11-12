"""Reconciliation report of an import run (JSON + Markdown, Spanish)."""

from datetime import UTC, datetime
from typing import Any

from app.modules.plans.importers.apply import ImportBundle


def build_report(
    bundle: ImportBundle,
    *,
    mode: str,
    organization: dict[str, str],
    database: str,
    existing_activities: dict[str, set[str]],
    existing_links: set[tuple[str, str, str, str]],
) -> dict[str, Any]:
    """Describe what the run reads and what it would create or update."""

    plans = []
    for parsed in bundle.plans:
        codes = [activity.code for activity in parsed.activities]
        before = existing_activities.get(parsed.plan.code)
        plans.append(
            {
                "kind": parsed.kind,
                "code": parsed.plan.code,
                "name": parsed.plan.name,
                "version": parsed.plan.version,
                "source_document": parsed.plan.source_document,
                "plan_exists": before is not None,
                "activity_count": len(codes),
                "is_mine_count": sum(activity.is_mine for activity in parsed.activities),
                "new_activities": [c for c in codes if c not in (before or set())],
                "existing_activities": [c for c in codes if c in (before or set())],
                "in_db_not_in_source": sorted((before or set()) - set(codes)),
                "activity_keys": [f"{parsed.plan.code}/{code}" for code in codes],
                "warnings": parsed.warnings,
                "facts": parsed.facts,
            }
        )
    existing_pairs = {(f, t): r for f, t, _, r in existing_links}
    links = [
        {
            "from": link.from_key,
            "to": link.to_key,
            "resolution": link.resolution,
            "source_reference": link.source_reference,
            "note": link.note,
            "status": (
                "nuevo"
                if (link.from_key, link.to_key) not in existing_pairs
                else "sin cambios"
                if existing_pairs[(link.from_key, link.to_key)] == link.resolution
                else "actualiza resolución"
            ),
        }
        for link in bundle.links
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": mode,
        "organization": organization,
        "database": database,
        "sources": [
            {
                "kind": p.kind,
                "name": p.source.name,
                "sha256": p.source.sha256,
                "bytes": p.source.size_bytes,
            }
            for p in bundle.plans
        ],
        "plans": plans,
        "links": links,
        "conflicts": [link for link in links if link["resolution"] == "conflict"],
        "review": [
            {
                "from": item.from_key,
                "source_reference": item.source_reference,
                "reason": item.reason,
            }
            for item in bundle.review
        ],
        "warnings": bundle.warnings,
    }


def render_markdown(report: dict[str, Any]) -> str:
    mode = "simulación (no escribe)" if report["mode"] == "dry-run" else "aplicación"
    org = report["organization"]
    lines = [
        "# Importación de planes institucionales",
        "",
        f"- Modo: **{mode}**",
        f"- Organización: `{org['slug']}` ({org['id']})",
        f"- Base de datos: `{report['database']}`",
        f"- Generado: {report['generated_at']}",
        "",
        "## Fuentes",
        "",
        "| Tipo | Archivo | SHA-256 | Bytes |",
        "|---|---|---|---:|",
    ]
    lines += [
        f"| {s['kind']} | {s['name']} | `{s['sha256']}` | {s['bytes']} |" for s in report["sources"]
    ]
    lines += [
        "",
        "## Planes",
        "",
        "| Plan | Versión | Actividades | Propias | Nuevas | Existentes | En base, no en fuente |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for plan in report["plans"]:
        lines.append(
            f"| {plan['code']} | {plan['version'] or '—'} | {plan['activity_count']} | "
            f"{plan['is_mine_count']} | {len(plan['new_activities'])} | "
            f"{len(plan['existing_activities'])} | "
            f"{', '.join(plan['in_db_not_in_source']) or '—'} |"
        )
    for plan in report["plans"]:
        lines += [
            "",
            f"### {plan['code']} — {plan['name']}",
            "",
            "Claves: " + ", ".join(f"`{key}`" for key in plan["activity_keys"]),
        ]
        if plan["facts"]:
            lines.append("")
            lines += [f"- {key}: {value}" for key, value in plan["facts"].items()]
        if plan["warnings"]:
            lines += ["", "Advertencias de la fuente:", ""]
            lines += [f"- {warning}" for warning in plan["warnings"]]
    lines += ["", f"## Enlaces entre actividades ({len(report['links'])})", ""]
    if report["links"]:
        lines += [
            "| Desde | Hacia | Resolución | Texto de la fuente | Estado | Nota |",
            "|---|---|---|---|---|---|",
        ]
        lines += [
            f"| {link['from']} | {link['to']} | {link['resolution']} | "
            f"{link['source_reference']} | "
            f"{link['status']} | {link['note'] or ''} |"
            for link in report["links"]
        ]
    else:
        lines.append("Sin enlaces.")
    lines += ["", f"## Conflictos registrados ({len(report['conflicts'])})", ""]
    lines += [
        f"- {c['from']} → {c['to']}: «{c['source_reference']}». {c['note']}"
        for c in report["conflicts"]
    ] or ["Ninguno."]
    lines += ["", f"## Referencias a revisión, sin enlace ({len(report['review'])})", ""]
    lines += [
        f"- {r['from']}: «{r['source_reference']}». {r['reason']}" for r in report["review"]
    ] or ["Ninguna."]
    lines += ["", "## Advertencias generales", ""]
    lines += [f"- {warning}" for warning in report["warnings"]] or ["Ninguna."]
    return "\n".join(lines) + "\n"
