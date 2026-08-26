"""CLI delgada: purga datos demo y bootstrapea la jerarquía SDMUJER
(design.md D7).

Ejecución en el host, SIEMPRE con ``-m`` desde ``backend/`` — así
``sys.path[0]`` es el cwd y ``import app.*``/``scripts.*`` resuelven sin
parchear ``sys.path``::

    cd backend && .venv/bin/python -m scripts.purge_demo_data \\
        --database-url postgresql+asyncpg://app:app@127.0.0.1:5434/solercia

Por defecto corre en modo ``dry-run`` (sin ``--execute``): ejecuta el MISMO
código de ``run_maintenance`` (purga + bootstrap + invariantes) y termina en
``rollback`` — nada cambia en la base. ``--execute`` exige ``--backup-file``,
verificado (existe y > 0 bytes) ANTES de tocar la base. La CLI construye su
propio engine (nunca el ``engine`` de módulo de ``app.database``, que
apuntaría al DNS interno de Docker) y lo libera con ``dispose()``.

Códigos de salida (D7):

=====  ==============================================================
Código  Significado
=====  ==============================================================
0      Éxito (dry-run o execute) con todas las invariantes en PASS
1      Error de uso: ``--execute`` sin ``--backup-file`` o vacío
2      Guarda de seguridad activada — no se escribió nada
3      Alguna invariante en FAIL — transacción revertida
4      Excepción inesperada — transacción revertida
=====  ==============================================================
"""

import argparse
import asyncio
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Pulls in every ORM model so relationship() string references (e.g. User ->
# Role) resolve before the first session query; same pattern as
# tests/conftest.py:66-68 (Corrección 1, Fase 5).
import app.db_init  # noqa: F401
from app.config import settings
from app.maintenance.report import MaintenanceReport, PurgeGuardError
from app.maintenance.repository import MaintenanceRepository
from app.maintenance.runner import run_maintenance
from app.maintenance.scope import DemoScope

EXIT_OK = 0
EXIT_USAGE_ERROR = 1
EXIT_GUARD_TRIPPED = 2
EXIT_INVARIANT_FAILED = 3
EXIT_UNEXPECTED_ERROR = 4

_URL_PASSWORD = re.compile(r"://([^:/@]+):([^@]+)@")


class BackupVerificationError(Exception):
    """``--execute`` sin ``--backup-file``, o con una ruta inexistente o de
    0 bytes (spec.md "Respaldo obligatorio y verificado antes de cualquier
    borrado")."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.purge_demo_data",
        description="Purga datos demo y bootstrapea SDMUJER/SEGURIDAD/PANDORA (destructivo).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Modo por defecto (sin --execute); explícito solo para documentación.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Aplica el borrado y el bootstrap; exige --backup-file.",
    )
    parser.add_argument(
        "--backup-file",
        default=None,
        help="Ruta del volcado pg_dump previo — obligatoria con --execute.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="URL asyncpg del host (el DATABASE_URL por defecto apunta a postgres:5432, "
        "solo resoluble dentro de Docker).",
    )
    parser.add_argument(
        "--purge-upload-files",
        action="store_true",
        help="Apagado por defecto. Borra SOLO los ficheros de UPLOAD_DIR referenciados por "
        "los attachments efectivamente borrados, después del commit.",
    )
    return parser


def verify_backup_file(path: str | None) -> None:
    """Existe y pesa más de 0 bytes — nunca valida el CONTENIDO del volcado."""

    if not path:
        raise BackupVerificationError("--execute requiere --backup-file <ruta>.")
    backup_path = Path(path)
    if not backup_path.is_file():
        raise BackupVerificationError(f"El respaldo no existe: {backup_path}")
    if backup_path.stat().st_size == 0:
        raise BackupVerificationError(f"El respaldo está vacío (0 bytes): {backup_path}")


def redact_database_url(url: str) -> str:
    """``app:supersecreto@host`` -> ``app:***@host`` — nunca se imprime la
    contraseña real (design.md D8)."""

    return _URL_PASSWORD.sub(r"://\1:***@", url)


def is_within_upload_dir(upload_dir: Path, stored_name: str) -> Path | None:
    """``resolve()`` + ``is_relative_to(UPLOAD_DIR)`` — una ruta que escapa
    del directorio de subidas se rechaza, nunca se borra (design.md Threat
    Matrix, "Borrado en sistema de ficheros")."""

    resolved_root = upload_dir.resolve()
    candidate = (upload_dir / stored_name).resolve()
    if not candidate.is_relative_to(resolved_root):
        return None
    return candidate


def delete_referenced_files(upload_dir: Path, stored_names: Sequence[str]) -> tuple[int, int]:
    """Borra ÚNICAMENTE ``stored_names`` dentro de ``upload_dir``. Una ruta
    fuera del directorio, o un fichero ya ausente, cuenta como advertencia,
    nunca como error. Retorna ``(borrados, advertencias)``."""

    deleted = 0
    warnings = 0
    for stored_name in stored_names:
        candidate = is_within_upload_dir(upload_dir, stored_name)
        if candidate is None:
            warnings += 1
            continue
        try:
            candidate.unlink()
            deleted += 1
        except FileNotFoundError:
            warnings += 1
    return deleted, warnings


def format_report(report: MaintenanceReport, *, database_url: str, backup_file: str | None) -> str:
    lines = [
        f"Modo: {report.mode}",
        f"Base de datos: {redact_database_url(database_url)}",
    ]
    if backup_file:
        lines.append(f"Respaldo: {backup_file}")

    lines += ["", "ALCANCE PLANEADO"]
    for planned in report.planned:
        lines.append(f"  {planned.table}: {len(planned.ids)} fila(s) — {planned.reason}")

    lines += ["", "INVENTARIO"]
    for row in report.inventory:
        lines.append(f"  {row.table}: antes={row.before} después={row.after}")

    lines += ["", "BORRADOS"]
    for deletion in report.deleted:
        lines.append(f"  {deletion.table}: {deletion.deleted}")

    lines += ["", "BOOTSTRAP"]
    for message in report.bootstrap:
        lines.append(f"  {message}")

    lines += ["", "INVARIANTES"]
    for invariant in report.invariants:
        status = "PASS" if invariant.passed else "FAIL"
        lines.append(f"  [{status}] {invariant.key} — {invariant.description} ({invariant.detail})")

    return "\n".join(lines)


async def _run(args: argparse.Namespace, *, database_url: str) -> int:
    engine = create_async_engine(database_url, echo=False, future=True)
    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
    )
    try:
        async with session_factory() as session:
            stored_names: tuple[str, ...] = ()
            if args.execute and args.purge_upload_files:
                repo = MaintenanceRepository(session)
                resolved = await repo.resolve_demo_scope(DemoScope())
                stored_names = await repo.find_attachment_stored_names(
                    resolved.task_ids + resolved.comment_ids
                )
            report = await run_maintenance(session, execute=args.execute)
    except PurgeGuardError as error:
        print(f"GUARDA DE SEGURIDAD: {error}", file=sys.stderr)
        for risk in error.risks:
            owner = f"{risk.provider} ({risk.display_name}) de {risk.owner_email}"
            print(f"  - {owner}", file=sys.stderr)
        return EXIT_GUARD_TRIPPED
    except Exception as error:  # noqa: BLE001 - se traduce a código 4, nunca silencioso
        print(f"ERROR INESPERADO: {error}", file=sys.stderr)
        return EXIT_UNEXPECTED_ERROR
    finally:
        await engine.dispose()

    print(format_report(report, database_url=database_url, backup_file=args.backup_file))

    if not report.ok:
        return EXIT_INVARIANT_FAILED

    if args.execute and args.purge_upload_files:
        deleted, warnings = delete_referenced_files(Path(settings.UPLOAD_DIR), stored_names)
        print(f"Ficheros borrados: {deleted}; advertencias: {warnings}")

    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database_url = args.database_url or settings.DATABASE_URL

    if args.execute:
        try:
            verify_backup_file(args.backup_file)
        except BackupVerificationError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return EXIT_USAGE_ERROR

    return asyncio.run(_run(args, database_url=database_url))


if __name__ == "__main__":
    sys.exit(main())
