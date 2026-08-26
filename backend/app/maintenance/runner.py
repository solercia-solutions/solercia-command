"""Owns the ONE maintenance transaction (design.md D2).

Runs purge -> bootstrap -> invariants on the SAME ``session``; commits ONLY
when ``execute`` and every invariant passes — every other outcome (dry-run,
a failing invariant) ends in ``rollback()``, the identical code path either
way.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.maintenance.bootstrap import bootstrap_sdmujer
from app.maintenance.invariants import collect_invariants
from app.maintenance.purge import purge_demo_data
from app.maintenance.report import MaintenanceReport
from app.maintenance.repository import MaintenanceRepository
from app.maintenance.scope import DemoScope


async def run_maintenance(
    session: AsyncSession, *, execute: bool, scope: DemoScope | None = None
) -> MaintenanceReport:
    """Purge the demo scope, bootstrap SDMUJER, verify I1-I8 — commit only
    when ``execute`` and every invariant passed (D2)."""

    scope = scope or DemoScope()
    repo = MaintenanceRepository(session)

    purge_outcome = await purge_demo_data(session, scope)

    organization_id = await repo.find_organization_id_by_name(
        scope.protected_organization_names[0]
    )
    actor_id = await repo.find_user_id_by_email(scope.protected_admin_email)
    bootstrap_messages: tuple[str, ...]
    if organization_id is None or actor_id is None:
        # Protected org/admin missing is itself an I1/I2 failure — bootstrap
        # has nothing to attach to, so it is skipped rather than raising.
        bootstrap_messages = (
            "bootstrap omitido: falta la organización o el admin protegidos",
        )
    else:
        bootstrap_messages = await bootstrap_sdmujer(
            session, organization_id=organization_id, actor_id=actor_id
        )

    invariants = await collect_invariants(session)

    if execute and all(result.passed for result in invariants):
        await session.commit()
    else:
        await session.rollback()

    return MaintenanceReport(
        mode="execute" if execute else "dry-run",
        inventory=purge_outcome.inventory,
        planned=purge_outcome.planned,
        deleted=purge_outcome.deleted,
        bootstrap=bootstrap_messages,
        invariants=invariants,
        orphans_swept=purge_outcome.orphans_swept,
    )
