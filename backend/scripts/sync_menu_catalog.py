"""CLI delgada: sincroniza el catálogo de menús (``seed_catalog``) con una base existente.

Ejecución en el host, desde ``backend/``::

    .venv/bin/python -m scripts.sync_menu_catalog \\
        --database-url postgresql+asyncpg://...

El arranque (``db_init``) solo siembra la organización por defecto y el
bootstrap (O5) solo cubre organizaciones nuevas: una entrada agregada después al
catálogo —como «Planes» (45c)— no llega a las organizaciones ya creadas. Esta
CLI cierra esa brecha.

Por defecto es una SIMULACIÓN: abre una transacción ``READ ONLY`` y lista lo que
insertaría. Solo ``--apply`` escribe, en UNA transacción, y únicamente INSERTA:

- los menús globales del catálogo que falten (por nombre, como ``db_init``);
- los permisos ``role_menus`` que falten, por organización activa y por rol del
  catálogo que exista en ella.

Nunca actualiza ni borra filas existentes: un menú ya presente conserva su
ícono, ruta y orden; un menú desactivado no se reactiva ni recibe permisos; un
rol que falta en una organización no se crea (se informa). Repetir la corrida
no inserta nada.

Códigos de salida:

=====  ==========================================================
Código  Significado
=====  ==========================================================
0      Éxito (simulación o aplicación)
1      Error de uso (argumentos)
4      Excepción inesperada — transacción revertida
=====  ==========================================================
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.db_init  # noqa: F401  (registers every ORM model)
from app.modules.menus.models import Menu
from app.modules.organizations.models import Organization
from app.modules.roles.models import Role, RoleMenu
from app.modules.roles.seed_catalog import MENU_SEED, ROLE_MENU_SEED

EXIT_OK = 0
EXIT_USAGE_ERROR = 1
EXIT_UNEXPECTED_ERROR = 4


@dataclass
class SyncResult:
    """What the sync found missing (dry-run) or inserted (apply)."""

    missing_menus: list[str] = field(default_factory=list)
    # (organization slug, role code, menu name)
    missing_grants: list[tuple[str, str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.sync_menu_catalog",
        description=(
            "Inserta los menús y permisos por rol que falten según el catálogo. "
            "Simulación por defecto; nunca actualiza ni borra."
        ),
    )
    parser.add_argument(
        "--database-url",
        required=True,
        help="URL async de SQLAlchemy de la base destino (obligatoria).",
    )
    parser.add_argument(
        "--apply", action="store_true", help="Inserta lo faltante (una transacción)."
    )
    return parser


def describe_database(url: str) -> str:
    parsed = make_url(url)
    return f"{parsed.host}:{parsed.port or 5432}/{parsed.database}"


async def sync_catalog(session: AsyncSession, *, apply: bool) -> SyncResult:
    """Compute (and with ``apply`` insert) the missing menus and grants.

    Does NOT commit: the caller owns the transaction. Never updates or deletes.
    """

    result = SyncResult()

    existing = {
        menu.name: menu
        for menu in (
            await session.execute(select(Menu).where(Menu.name.in_([r[0] for r in MENU_SEED])))
        ).scalars()
    }
    # Menu ids by name; ``None`` = missing in dry-run (no id to grant yet).
    menu_ids: dict[str, object | None] = {}
    inactive: set[str] = set()
    for name, icon, path, parent_name, order in MENU_SEED:
        menu = existing.get(name)
        if menu is not None:
            menu_ids[name] = menu.id
            if not menu.is_active or menu.deleted_at is not None:
                inactive.add(name)
                result.notes.append(f"Menú «{name}» desactivado: no se toca ni se otorga.")
            continue
        result.missing_menus.append(name)
        if not apply:
            menu_ids[name] = None
            continue
        parent_id = menu_ids.get(parent_name) if parent_name else None
        new_menu = Menu(name=name, icon=icon, path=path, parent_id=parent_id, order=order)
        session.add(new_menu)
        await session.flush()  # assign new_menu.id for children and grants
        menu_ids[name] = new_menu.id

    organizations = (
        (
            await session.execute(
                select(Organization)
                .where(Organization.is_active.is_(True), Organization.deleted_at.is_(None))
                .order_by(Organization.slug)
            )
        )
        .scalars()
        .all()
    )

    for organization in organizations:
        roles = {
            role.code: role
            for role in (
                await session.execute(
                    select(Role).where(
                        Role.organization_id == organization.id,
                        Role.code.in_(list(ROLE_MENU_SEED)),
                        Role.deleted_at.is_(None),
                    )
                )
            ).scalars()
        }
        for role_code, spec in ROLE_MENU_SEED.items():
            role = roles.get(role_code)
            if role is None:
                result.notes.append(
                    f"{organization.slug}: sin rol {role_code}; no se crea ni se otorga."
                )
                continue
            granted_menu_ids = set(
                (
                    await session.execute(
                        select(RoleMenu.menu_id).where(RoleMenu.role_id == role.id)
                    )
                ).scalars()
            )
            names = [row[0] for row in MENU_SEED] if spec == "*" else list(spec)
            for name in names:
                if name in inactive:
                    continue
                menu_id = menu_ids.get(name)
                if menu_id is not None and menu_id in granted_menu_ids:
                    continue
                result.missing_grants.append((organization.slug, role_code, name))
                if apply and menu_id is not None:
                    session.add(RoleMenu(role_id=role.id, menu_id=menu_id))
    if apply:
        await session.flush()
    return result


async def run(args: argparse.Namespace) -> int:
    print(f"Base de datos destino: {describe_database(args.database_url)}")
    print(f"Modo: {'APLICAR (solo inserta)' if args.apply else 'simulación (solo lectura)'}")

    engine = create_async_engine(args.database_url, future=True)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as session:
            if not args.apply:
                await session.execute(text("SET TRANSACTION READ ONLY"))
            result = await sync_catalog(session, apply=args.apply)
            if args.apply:
                await session.commit()
            else:
                await session.rollback()
    except Exception as exc:  # noqa: BLE001 — typed exit code, transaction rolled back
        print(f"Error inesperado; no se aplicaron cambios: {exc!r}", file=sys.stderr)
        return EXIT_UNEXPECTED_ERROR
    finally:
        await engine.dispose()

    verb = "Insertados" if args.apply else "Se insertarían"
    print(f"{verb} {len(result.missing_menus)} menús globales:")
    for name in result.missing_menus:
        print(f"  + menú «{name}»")
    print(f"{verb} {len(result.missing_grants)} permisos por rol:")
    for slug, role_code, name in result.missing_grants:
        print(f"  + {slug} · {role_code} → «{name}»")
    for note in result.notes:
        print(f"  ! {note}")
    if not result.missing_menus and not result.missing_grants:
        print("Sin cambios: el catálogo ya está sincronizado.")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:  # argparse exits 2 on usage errors
        return EXIT_USAGE_ERROR if exc.code else EXIT_OK
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
