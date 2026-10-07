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
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db_init  # noqa: F401  (registers every ORM model)
from app.config import settings
from app.modules.task_import.checklist_apply import ChecklistTargetError
from app.modules.task_import.checklist_import import DEFAULT_NAMESPACE, ChecklistPlan
from app.modules.task_import.checklist_sync_service import (
    ChecklistMemberError,
    ChecklistOrganizationError,
    ChecklistSourceError,
    ChecklistSyncOptions,
    SessionChecklistSyncUow,
    build_report,
    load_checklist_plan,
    render_markdown,
    run_checklist_sync,
)

__all__ = ["build_report", "render_markdown"]

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
    return load_checklist_plan(
        args.checklist, namespace=args.namespace, tareas_root=args.tareas_root
    )


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
    except ChecklistSourceError as exc:
        print(f"Fuente no válida: {exc}", file=sys.stderr)
        return EXIT_SOURCE_ERROR
    print(f"Modo: {'APLICAR (escribe)' if args.apply else 'simulación (solo lectura)'}")

    options = ChecklistSyncOptions(
        namespace=args.namespace,
        actor_email=args.actor_email,
        assignee_email=args.assignee_email,
        update_existing=args.update_existing,
        apply=args.apply,
    )
    engine = create_async_engine(args.database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as session:
            result = await run_checklist_sync(
                SessionChecklistSyncUow(session), args.organization_slug, plan, options
            )
        if result.applied is not None:
            print(
                "Aplicado en una transacción: "
                + json.dumps({k: len(v) for k, v in result.applied.items()}, ensure_ascii=False)
            )
    except ChecklistOrganizationError:
        print(
            f"La organización «{args.organization_slug}» no existe o está inactiva; "
            "no se escribió nada.",
            file=sys.stderr,
        )
        return EXIT_ORGANIZATION_NOT_FOUND
    except ChecklistMemberError as exc:
        print(f"{exc.email} no es miembro activo de la organización.", file=sys.stderr)
        return EXIT_USAGE_ERROR
    except ChecklistTargetError as exc:
        print(f"Destino incompleto; no se escribió nada: {exc}", file=sys.stderr)
        return EXIT_TARGET_INCOMPLETE
    except Exception as exc:  # noqa: BLE001 — typed exit code, transaction rolled back
        print(f"Error inesperado; no se aplicaron cambios: {exc!r}", file=sys.stderr)
        return EXIT_UNEXPECTED_ERROR
    finally:
        await engine.dispose()

    report = result.report(database=database)
    json_path, md_path = write_report(args.report, report)
    print(
        f"Planificadas: {len(plan.drafts)} · omitidas: {len(plan.skipped)} · "
        f"a revisión: {len(plan.review)}"
    )
    print("Resultado por fila: " + json.dumps(report["counts"]["outcomes"], ensure_ascii=False))
    print("Por proyecto: " + json.dumps(report["counts"]["by_project"], ensure_ascii=False))
    if result.missing:
        print("Destino incompleto: " + " | ".join(result.missing))
    print(f"Informe: {json_path} · {md_path}")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
