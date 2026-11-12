"""CLI: alimenta una organización con los proyectos, issues, sprints y usuarios de Jira.

Ejecución en el host, desde ``backend/``::

    # 1) Descarga (solo lectura en Jira) a un snapshot local
    .venv/bin/python -m scripts.import_jira --fetch --snapshot /ruta/raw \\
        --env-file /ruta/.env --env-prefix JIRA_IDARTES

    # 2) Simulación (por defecto): transacción READ ONLY, no modifica la base
    .venv/bin/python -m scripts.import_jira --from-snapshot /ruta/raw \\
        --organization-slug idartes --database-url postgresql+asyncpg://... \\
        --report /ruta/informe

    # 3) Aplicación: misma corrida con --apply (una transacción, idempotente)

Las credenciales se leen de variables de entorno ``<PREFIJO>_URL``,
``<PREFIJO>_EMAIL`` y ``<PREFIJO>_API_TOKEN`` o, en su defecto, solo esas tres
claves del archivo ``--env-file``; nunca se imprimen ni se escriben.

Códigos de salida: 0 éxito · 1 uso · 2 snapshot o Jira no disponibles ·
3 organización inexistente o inactiva · 4 error inesperado (sin cambios).
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.db_init  # noqa: F401  (registers every ORM model)
from app.config import settings
from app.modules.jira_import.apply import SessionJiraFeedUow, run_feed
from app.modules.jira_import.client import JiraReadClient, JiraReadError
from app.modules.jira_import.mapper import build_feed_plan
from app.modules.jira_import.report import build_report, render_markdown
from app.modules.jira_import.snapshot import fetch_snapshot, load_snapshot, read_jira_credentials

EXIT_OK = 0
EXIT_USAGE_ERROR = 1
EXIT_SOURCE_ERROR = 2
EXIT_ORGANIZATION_NOT_FOUND = 3
EXIT_UNEXPECTED_ERROR = 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.import_jira",
        description="Alimentación Jira → organización. Simulación por defecto.",
    )
    parser.add_argument("--fetch", action="store_true", help="Descarga Jira al snapshot y termina.")
    parser.add_argument("--snapshot", type=Path, help="Directorio destino de --fetch.")
    parser.add_argument("--env-file", type=Path, help="Archivo .env con las credenciales de Jira.")
    parser.add_argument("--env-prefix", default="JIRA_IDARTES", help="Prefijo de las claves.")
    parser.add_argument("--since", default="2026-01-01", help="Inicio de la ventana (AAAA-MM-DD).")
    parser.add_argument("--from-snapshot", type=Path, help="Snapshot a simular o aplicar.")
    parser.add_argument("--organization-slug", help="Organización destino.")
    parser.add_argument("--database-url", default=settings.DATABASE_URL)
    parser.add_argument("--report", type=Path, help="Ruta base del informe (.json y .md).")
    parser.add_argument(
        "--apply", action="store_true", help="Escribe en la base (una transacción)."
    )
    return parser


def describe_database(url: str) -> str:
    parsed = make_url(url)
    return f"{parsed.host}:{parsed.port or 5432}/{parsed.database}"


def write_report(base: Path, report: dict) -> tuple[Path, Path]:
    base = base.with_suffix("") if base.suffix in {".json", ".md"} else base
    json_path, md_path = base.with_name(base.name + ".json"), base.with_name(base.name + ".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), "utf-8")
    md_path.write_text(render_markdown(report), "utf-8")
    return json_path, md_path


async def run_fetch(args: argparse.Namespace) -> int:
    if args.snapshot is None:
        print("--fetch requiere --snapshot.", file=sys.stderr)
        return EXIT_USAGE_ERROR
    try:
        base_url, email, token = read_jira_credentials(args.env_file, args.env_prefix)
        async with JiraReadClient(base_url, email, token) as client:
            manifest = await fetch_snapshot(
                client, args.snapshot, base_url=base_url, since=args.since
            )
    except (ValueError, OSError, JiraReadError) as exc:
        print(f"No fue posible descargar Jira: {exc}", file=sys.stderr)
        return EXIT_SOURCE_ERROR
    scope = manifest["projects_in_scope"]
    print(f"Snapshot: {args.snapshot} · {len(scope)} proyectos · {sum(scope.values())} issues")
    return EXIT_OK


async def run_feed_command(args: argparse.Namespace) -> int:
    if args.from_snapshot is None or not args.organization_slug or args.report is None:
        print("Indica --from-snapshot, --organization-slug y --report.", file=sys.stderr)
        return EXIT_USAGE_ERROR
    try:
        snapshot = load_snapshot(args.from_snapshot)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Snapshot no válido: {exc}", file=sys.stderr)
        return EXIT_SOURCE_ERROR
    plan = build_feed_plan(snapshot)

    database = describe_database(args.database_url)
    mode = "apply" if args.apply else "dry-run"
    print(f"Base de datos destino: {database}")
    print(f"Modo: {'APLICAR (escribe)' if args.apply else 'simulación (solo lectura)'}")

    engine = create_async_engine(args.database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as session:
            if not args.apply:
                await session.execute(text("SET TRANSACTION READ ONLY"))
            uow = SessionJiraFeedUow(session)
            organization = await uow.repo.get_organization_by_slug(args.organization_slug)
            if organization is None or not organization.is_active:
                await session.rollback()
                print(
                    f"La organización «{args.organization_slug}» no existe o está inactiva; "
                    "no se escribió nada.",
                    file=sys.stderr,
                )
                return EXIT_ORGANIZATION_NOT_FOUND
            org_info = {"slug": organization.slug, "id": str(organization.id)}
            result = await run_feed(uow, organization, plan, write=args.apply)
    except Exception as exc:  # noqa: BLE001 — typed exit code, transaction rolled back
        print(f"Error inesperado; no se aplicaron cambios: {exc!r}", file=sys.stderr)
        return EXIT_UNEXPECTED_ERROR
    finally:
        await engine.dispose()

    report = build_report(
        snapshot, plan, result, mode=mode, database=database, organization=org_info
    )
    json_path, md_path = write_report(args.report, report)
    for label, key in (
        ("Usuarios", "users"),
        ("Proyectos", "projects"),
        ("Sprints", "sprints"),
        ("Tareas", "tasks"),
    ):
        counter = getattr(result, key)
        print(
            f"{label}: {counter.created} nuevos · {counter.updated} actualizados · "
            f"{counter.unchanged} sin cambios"
        )
    print(f"Informe: {json_path} · {md_path}")
    return EXIT_OK


async def run(args: argparse.Namespace) -> int:
    return await (run_fetch(args) if args.fetch else run_feed_command(args))


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
