"""JSON + Markdown report of a Jira feed run (dry-run or apply)."""

from collections import Counter
from typing import Any

from app.modules.jira_import.apply import ApplyResult
from app.modules.jira_import.mapper import FeedPlan
from app.modules.jira_import.snapshot import Snapshot


def build_report(
    snapshot: Snapshot,
    plan: FeedPlan,
    result: ApplyResult,
    *,
    mode: str,
    database: str,
    organization: dict[str, str],
) -> dict[str, Any]:
    account_types = Counter(str(u.get("accountType")) for u in snapshot.users)
    projects = []
    for project in plan.projects:
        projects.append(
            {
                "clave": project.key,
                "codigo": project.code,
                "nombre": project.name,
                "categoria": project.category,
                "metodologia": project.methodology,
                "tableros_jira": project.board_types,
                "issues_en_ventana": sum(1 for t in project.tasks if not t.context),
                "padres_de_contexto": sum(1 for t in project.tasks if t.context),
                "sprints": len(project.sprints),
                "columnas": [c.status_key for c in project.columns],
                "aplicacion": result.per_project.get(project.key, {}),
            }
        )
    return {
        "modo": mode,
        "base_de_datos": database,
        "organizacion": organization,
        "sitio_jira": plan.site_host,
        "snapshot_tomado": snapshot.manifest.get("fetched_at"),
        "ventana_desde": plan.since,
        "proyectos_visibles": len(snapshot.projects),
        "proyectos_en_alcance": projects,
        "proyectos_sin_actividad_en_ventana": sorted(plan.excluded_projects),
        "usuarios": {
            "cuentas_del_sitio": len(snapshot.users),
            "por_tipo_de_cuenta": dict(account_types),
            "humanas_importadas": len(plan.users),
            "activas": sum(1 for u in plan.users if u.active),
            "inactivas": sum(1 for u in plan.users if not u.active),
            "con_correo_real": sum(1 for u in plan.users if not u.email_is_placeholder),
            "con_correo_marcador": sum(1 for u in plan.users if u.email_is_placeholder),
        },
        "totales": {
            "tareas": sum(len(p.tasks) for p in plan.projects),
            "sprints": sum(len(p.sprints) for p in plan.projects),
        },
        "advertencias_mapeo": plan.warnings,
        "muestras_advertencias": plan.warning_samples,
        "resultado": result.as_dict(),
    }


def render_markdown(report: dict[str, Any]) -> str:
    users = report["usuarios"]
    result = report["resultado"]
    lines = [
        f"# Alimentación Jira → {report['organizacion'].get('slug')}",
        "",
        f"- Modo: **{report['modo']}** · Base: `{report['base_de_datos']}`",
        f"- Sitio: `{report['sitio_jira']}` · snapshot: {report['snapshot_tomado']}",
        f"- Ventana: issues creados o actualizados desde {report['ventana_desde']}",
        f"- Proyectos visibles: {report['proyectos_visibles']} · en alcance: "
        f"{len(report['proyectos_en_alcance'])} · sin actividad: "
        f"{', '.join(report['proyectos_sin_actividad_en_ventana']) or '—'}",
        "",
        "## Proyectos",
        "",
        "| Clave | Nombre | Categoría | Metodología | Issues | Contexto | Sprints | Columnas |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- |",
    ]
    for p in report["proyectos_en_alcance"]:
        lines.append(
            f"| {p['clave']} | {p['nombre']} | {p['categoria'] or '—'} | {p['metodologia']} | "
            f"{p['issues_en_ventana']} | {p['padres_de_contexto']} | {p['sprints']} | "
            f"{' → '.join(p['columnas'])} |"
        )
    lines += [
        "",
        f"Totales: {report['totales']['tareas']} tareas · {report['totales']['sprints']} sprints.",
        "",
        "## Tareas por estado",
        "",
    ]
    for p in report["proyectos_en_alcance"]:
        by_status = p["aplicacion"].get("tareas_por_estado", {})
        lines.append(f"- **{p['clave']}**: " + ", ".join(f"{k}: {v}" for k, v in by_status.items()))
    lines += [
        "",
        "## Usuarios",
        "",
        f"- Cuentas del sitio: {users['cuentas_del_sitio']} ({users['por_tipo_de_cuenta']})",
        f"- Humanas importadas: {users['humanas_importadas']} (activas {users['activas']}, "
        f"inactivas {users['inactivas']})",
        f"- Con correo real: {users['con_correo_real']} · "
        "con marcador reservado (`example.org`, sin buzón): "
        f"{users['con_correo_marcador']}",
        "",
        "## Resultado",
        "",
        "| Entidad | Creados | Actualizados | Sin cambios |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label, key in (
        ("Usuarios", "usuarios"),
        ("Identidades Jira", "identidades_jira"),
        ("Membresías", "membresias"),
        ("Rol MEMBER", "roles_member"),
        ("Proyectos", "proyectos"),
        ("Columnas", "columnas"),
        ("Sprints", "sprints"),
        ("Tareas", "tareas"),
    ):
        c = result[key]
        lines.append(f"| {label} | {c['creados']} | {c['actualizados']} | {c['sin_cambios']} |")
    lines += ["", f"Padres enlazados: {result['padres_enlazados']}", "", "## Advertencias", ""]
    warnings = {**report["advertencias_mapeo"], **result["advertencias_aplicacion"]}
    if not warnings:
        lines.append("- Ninguna.")
    for code, count in sorted(warnings.items()):
        lines.append(f"- `{code}`: {count}")
    return "\n".join(lines) + "\n"
