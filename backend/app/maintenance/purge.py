"""Idempotent demo-data purge use case (design.md D2/D3/D4).

``purge_demo_data`` NEVER calls ``commit()``/``rollback()`` — the caller
owns the transaction (the test's SAVEPOINT session here; ``runner.py`` in
Fase 3).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.maintenance.report import DeletionResult, PlannedDeletion, PurgeGuardError, PurgeOutcome
from app.maintenance.repository import MaintenanceRepository, ResolvedScope
from app.maintenance.scope import DemoScope


async def purge_demo_data(session: AsyncSession, scope: DemoScope | None = None) -> PurgeOutcome:
    """Resolve the scope, apply the fail-closed guards, delete leaf-to-root
    (D4). Raises :class:`PurgeGuardError` and deletes NOTHING when a demo
    user still owns a connected account."""

    scope = scope or DemoScope()
    repo = MaintenanceRepository(session)
    resolved = await repo.resolve_demo_scope(scope)

    risks = await repo.find_connected_accounts_owned_by(resolved.user_ids)
    if risks:
        raise PurgeGuardError(
            "La purga se detuvo antes de borrar cualquier fila: al menos "
            "una cuenta conectada pertenece a un usuario del alcance demo.",
            risks=risks,
        )

    inventory = await repo.count_inventory(resolved)
    planned = _build_planned(resolved)

    attachment_targets = resolved.task_ids + resolved.comment_ids
    attachments = await repo.delete_attachments_for_targets(attachment_targets)
    notifications = await repo.delete_notifications_for_tasks(resolved.task_ids)
    reminders = await repo.delete_reminders_for_tasks(resolved.task_ids)
    tasks = await repo.delete_tasks(resolved.task_ids)
    projects = await repo.delete_projects_leaf_first(resolved.project_ids)
    connectors = await repo.delete_fake_connectors(resolved.connector_ids)
    assets = await repo.delete_demo_assets(resolved.asset_ids)
    users = await repo.delete_demo_users(resolved.user_ids)
    organizations = await repo.delete_demo_organizations(resolved.organization_ids)
    deleted = (
        DeletionResult("attachments", attachments),
        DeletionResult("notifications", notifications),
        DeletionResult("reminders", reminders),
        DeletionResult("tasks", tasks),
        DeletionResult("projects", projects),
        DeletionResult("connectors", connectors),
        DeletionResult("assets", assets),
        DeletionResult("users", users),
        DeletionResult("organizations", organizations),
    )

    return PurgeOutcome(inventory=inventory, planned=planned, deleted=deleted)


def _build_planned(resolved: ResolvedScope) -> tuple[PlannedDeletion, ...]:
    """The exact ids about to be deleted, printable before ``--execute``
    touches anything (design.md D3)."""

    return (
        PlannedDeletion("organizations", resolved.organization_ids, "organización demo"),
        PlannedDeletion("users", resolved.user_ids, "usuario demo por correo"),
        PlannedDeletion("projects", resolved.project_ids, "proyecto demo y subárbol"),
        PlannedDeletion("tasks", resolved.task_ids, "tareas de proyectos demo"),
        PlannedDeletion("connectors", resolved.connector_ids, "conector 'fake'"),
        PlannedDeletion("assets", resolved.asset_ids, "activo demo por nombre"),
    )
