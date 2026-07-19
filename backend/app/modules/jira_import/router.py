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

from app.database import get_db
from app.dependencies import require_role
from app.modules.jira_import.schemas import JiraImportRequest
from app.modules.jira_import.service import JiraImportService
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import MemberRole

router = APIRouter(tags=["jira-import"])

# Module-level singleton (ruff B008, same precedent as
# `connectors/router.py`'s `require_connector_write_role`).
require_jira_import_role = require_role(MemberRole.admin, MemberRole.manager)


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
    service = JiraImportService(db)
    result = await service.import_via_file(
        membership.organization_id, connector_id, file.filename or "", content
    )
    return {"data": result, "meta": {"total": result.report.total}}
