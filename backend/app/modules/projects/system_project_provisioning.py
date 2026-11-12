"""Ensure Generales within a transaction owned and completed by the caller."""
from uuid import UUID

from app.modules.projects.system_project import GENERALES
from app.modules.projects.system_project_ports import ProjectSnapshot, SystemProjectPort
from app.shared.exceptions import AppException


class SystemProjectConflict(AppException):
    def __init__(self) -> None:
        super().__init__(
            'El proyecto reservado Generales tiene una configuración incompatible.',
            code='system_project_conflict', status_code=409,
        )


class InvalidSystemOrganization(AppException):
    def __init__(self) -> None:
        super().__init__(
            'La organización no está disponible.',
            code='system_project_organization_unavailable', status_code=404,
        )


async def ensure_generales(
    port: SystemProjectPort, *, organization_id: UUID, actor_id: UUID,
    parent_id: UUID | None,
) -> ProjectSnapshot:
    """Caller authenticates/authorizes actor, tenant and explicit parent placement.

    Parent must already be validated for the tenant and hierarchy rules; None
    explicitly requests root placement on creation only. Reuse never reparents.
    The organization lock coordinates cooperative callers only. The caller must
    roll back the whole transaction on failure (including failed flushes).
    """
    if not await port.lock_organization(organization_id):
        raise InvalidSystemOrganization()
    project = await port.find_reserved(organization_id)
    if project is None:
        return await port.create_generales(organization_id, actor_id, parent_id)
    if (
        project.organization_id != organization_id
        or project.code != GENERALES.code
        or project.is_system is not True
        or project.methodology != GENERALES.methodology
        or project.status != 'active'
        or project.is_active is not True
        or project.deleted_at is not None
    ):
        raise SystemProjectConflict()
    board = await port.read_board(organization_id, project.id)
    if (
        board is None or board.is_active is not True or board.deleted_at is not None
        or len(board.columns) != len(GENERALES.statuses)
    ):
        raise SystemProjectConflict()
    for index, (column, status) in enumerate(zip(board.columns, GENERALES.statuses)):
        if (
            column.name != status or column.status_key != status
            or column.order != index or column.is_active is not True
            or column.deleted_at is not None
        ):
            raise SystemProjectConflict()
    return project
