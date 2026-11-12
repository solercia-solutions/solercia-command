"""CLI delgada: importa planes institucionales desde sus documentos fuente (45b).

Ejecución en el host, desde ``backend/``::

    .venv/bin/python -m scripts.import_plans --organization-slug sdmujer \\
        --pspi PSPI.docx --ptr PTR.docx --pai PAI.xlsx \\
        --report /ruta/informe --database-url postgresql+asyncpg://...

Por defecto es una SIMULACIÓN: abre una transacción ``READ ONLY``, consulta lo
que ya existe y escribe el informe (JSON + Markdown); no modifica la base.
Solo ``--apply`` escribe, en UNA transacción, a través de la costura de
upserts del repositorio de planes: repetir la corrida no crea filas.

Códigos de salida:

=====  ==========================================================
Código  Significado
=====  ==========================================================
0      Éxito (simulación o aplicación)
1      Error de uso (argumentos, archivo inexistente)
2      Fuente con estructura no reconocida — no se tocó la base
3      La organización no existe o está inactiva — no se escribió nada
4      Excepción inesperada — transacción revertida
=====  ==========================================================
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
from app.modules.organizations.repository import OrganizationRepository
from app.modules.plans.importers.apply import (
    SessionPlanImportUow,
    apply_bundle,
    build_bundle,
)
from app.modules.plans.importers.common import ParsedPlan, SourceFormatError
from app.modules.plans.importers.pai import DEFAULT_POLICIES, parse_pai
from app.modules.plans.importers.pspi import parse_pspi
from app.modules.plans.importers.ptr import parse_ptr
from app.modules.plans.importers.report import build_report, render_markdown
from app.modules.plans.repository import PlansRepository

EXIT_OK = 0
EXIT_USAGE_ERROR = 1
EXIT_SOURCE_ERROR = 2
EXIT_ORGANIZATION_NOT_FOUND = 3
EXIT_UNEXPECTED_ERROR = 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.import_plans",
        description="Importa PSPI/PTR (DOCX) y PAI (XLSX). Simulación por defecto.",
    )
    parser.add_argument("--organization-slug", required=True, help="Organización destino.")
    parser.add_argument("--pspi", type=Path, help="DOCX del Plan de Seguridad y Privacidad.")
    parser.add_argument("--ptr", type=Path, help="DOCX del Plan de Tratamiento de Riesgos.")
    parser.add_argument("--pai", type=Path, help="XLSX del Plan de Acción Institucional.")
    parser.add_argument(
        "--pai-policies",
        default=",".join(DEFAULT_POLICIES),
        help="Políticas MIPG del PAI a importar, separadas por coma (por defecto 11,12).",
    )
    parser.add_argument("--period-year", type=int, default=2026)
    parser.add_argument(
        "--report",
        type=Path,
        required=True,
        help="Ruta base del informe; se escriben <ruta>.json y <ruta>.md.",
    )
    parser.add_argument("--database-url", default=settings.DATABASE_URL)
    parser.add_argument(
        "--apply", action="store_true", help="Escribe en la base (una transacción)."
    )
    return parser


def describe_database(url: str) -> str:
    parsed = make_url(url)
    return f"{parsed.host}:{parsed.port or 5432}/{parsed.database}"


def parse_sources(args: argparse.Namespace) -> list[ParsedPlan]:
    plans: list[ParsedPlan] = []
    if args.pspi:
        plans.append(parse_pspi(args.pspi, period_year=args.period_year))
    if args.ptr:
        plans.append(parse_ptr(args.ptr, period_year=args.period_year))
    if args.pai:
        policies = tuple(p.strip() for p in args.pai_policies.split(",") if p.strip())
        plans.append(parse_pai(args.pai, period_year=args.period_year, policies=policies))
    return plans


def write_report(base: Path, report: dict) -> tuple[Path, Path]:
    base = base.with_suffix("") if base.suffix in {".json", ".md"} else base
    json_path, md_path = base.with_name(base.name + ".json"), base.with_name(base.name + ".md")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


async def run(args: argparse.Namespace) -> int:
    sources = [path for path in (args.pspi, args.ptr, args.pai) if path]
    if not sources:
        print("Indica al menos una fuente: --pspi, --ptr o --pai.", file=sys.stderr)
        return EXIT_USAGE_ERROR
    missing = [str(path) for path in sources if not path.is_file()]
    if missing:
        print(f"No existe la fuente: {', '.join(missing)}", file=sys.stderr)
        return EXIT_USAGE_ERROR
    try:
        bundle = build_bundle(parse_sources(args))
    except (SourceFormatError, ValueError) as exc:
        print(f"Fuente no válida: {exc}", file=sys.stderr)
        return EXIT_SOURCE_ERROR

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
            organization = await OrganizationRepository(session).get_by_slug(args.organization_slug)
            if organization is None or not organization.is_active:
                await session.rollback()
                print(
                    f"La organización «{args.organization_slug}» no existe o está inactiva; "
                    "no se escribió nada.",
                    file=sys.stderr,
                )
                return EXIT_ORGANIZATION_NOT_FOUND
            existing, links = await PlansRepository(session).import_snapshot(
                organization.id, [parsed.plan.code for parsed in bundle.plans]
            )
            report = build_report(
                bundle,
                mode=mode,
                organization={"slug": organization.slug, "id": str(organization.id)},
                database=database,
                existing_activities=existing,
                existing_links=links,
            )
            if args.apply:
                written = await apply_bundle(SessionPlanImportUow(session), organization.id, bundle)
                print(
                    f"Aplicado: {written} actividades en {len(bundle.plans)} planes, "
                    "una transacción."
                )
            else:
                await session.rollback()
    except Exception as exc:  # noqa: BLE001 — typed exit code, transaction already rolled back
        print(f"Error inesperado; no se aplicaron cambios: {exc!r}", file=sys.stderr)
        return EXIT_UNEXPECTED_ERROR
    finally:
        await engine.dispose()

    json_path, md_path = write_report(args.report, report)
    for plan in report["plans"]:
        print(
            f"{plan['code']}: {plan['activity_count']} actividades "
            f"({len(plan['new_activities'])} nuevas)"
        )
    print(
        f"Enlaces: {len(report['links'])} · conflictos: {len(report['conflicts'])} · "
        f"a revisión: {len(report['review'])}"
    )
    print(f"Informe: {json_path} · {md_path}")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(run(build_parser().parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
