"""jira_import routes: solo-lectura, dispara un import vía API o archivo
(change 18-adapter-jira, specs/jira-import/spec.md "Superficie REST de
import solo-lectura, con permisos y multi-tenant"). RBAC
``require_role(admin, manager)`` — same shape as ``connectors``'/
``glpi_sync``'s write endpoints. Responses follow the standard
``{data[, message][, meta]}`` envelope.
"""

import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings as default_settings
from app.database import get_db
from app.dependencies import require_role
from app.modules.jira_import.schemas import (
    JiraImportProjectRequest,
    JiraImportRequest,
    JiraPreviewRequest,
)
from app.modules.jira_import.service import JiraImportService
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import MemberRole
from app.shared.exceptions import AppException

router = APIRouter(tags=["jira-import"])

# Module-level singleton (ruff B008, same precedent as
# `connectors/router.py`'s `require_connector_write_role`).
require_jira_import_role = require_role(MemberRole.admin, MemberRole.manager)

_FILE_TOO_LARGE_MESSAGE = "El archivo excede el tamaño máximo permitido de 10 MB."


@router.post("/connectors/{connector_id}/jira/import", status_code=status.HTTP_200_OK)
async def import_via_api(
    connector_id: uuid.UUID,
    payload: JiraImportRequest,
    membership: OrganizationMember = Depends(require_jira_import_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger a Jira import via the API vía (admin or manager only). 404
    if the connector does not exist, belongs to another organization, or
    is not a ``jira`` connector."""

    service = JiraImportService(db)
    result = await service.import_via_api(membership.organization_id, connector_id, payload)
    return {"data": result, "meta": {"total": result.report.total}}


@router.post("/connectors/{connector_id}/jira/import-file", status_code=status.HTTP_200_OK)
async def import_via_file(
    connector_id: uuid.UUID,
    file: UploadFile = File(...),
    membership: OrganizationMember = Depends(require_jira_import_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger a Jira import via an uploaded CSV/XLSX (admin or manager
    only). Same response contract as :func:`import_via_api`."""

    content = await file.read()
    if len(content) > default_settings.JIRA_FILE_MAX_BYTES:
        # Rejected BEFORE the parser ever runs (413, never a partial parse).
        raise AppException(
            _FILE_TOO_LARGE_MESSAGE, code="jira_file_upload_too_large", status_code=413
        )
    service = JiraImportService(db)
    result = await service.import_via_file(
        membership.organization_id, connector_id, file.filename or "", content
    )
    return {"data": result, "meta": {"total": result.report.total}}


@router.get("/connectors/{connector_id}/jira/projects", status_code=status.HTTP_200_OK)
async def list_jira_projects(
    connector_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_jira_import_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the Jira projects the connector's account can browse (admin or
    manager only). Read-only; each project says whether it was already
    imported. 404 if the connector is not a ``jira`` connector of the
    caller's organization."""

    service = JiraImportService(db)
    projects = await service.list_projects(membership.organization_id, connector_id)
    return {"data": projects, "meta": {"total": len(projects)}}


@router.post("/connectors/{connector_id}/jira/preview", status_code=status.HTTP_200_OK)
async def preview_jira_project(
    connector_id: uuid.UUID,
    payload: JiraPreviewRequest,
    membership: OrganizationMember = Depends(require_jira_import_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Preview the import of one Jira project (admin or manager only):
    counts per type, sprints and the proposed status mapping. Persists
    nothing. 422 if the project key is not a valid Jira key."""

    service = JiraImportService(db)
    preview = await service.preview(membership.organization_id, connector_id, payload.project_key)
    return {"data": preview}


@router.post("/connectors/{connector_id}/jira/import-project", status_code=status.HTTP_200_OK)
async def import_jira_project(
    connector_id: uuid.UUID,
    payload: JiraImportProjectRequest,
    membership: OrganizationMember = Depends(require_jira_import_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Import one Jira project into the organization (admin or manager
    only), in one transaction. Re-importing the same project reconciles
    the anchored project, sprints and tasks instead of duplicating them."""

    service = JiraImportService(db)
    summary = await service.import_project(
        membership.organization_id, connector_id, payload, actor_id=membership.user_id
    )
    message = (
        "El proyecto de Jira se importó correctamente."
        if summary.project_created
        else "El proyecto de Jira se actualizó con los cambios de Jira."
    )
    return {"data": summary, "message": message}
