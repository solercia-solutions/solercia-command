"""Intake routes (change 22-intake-classifier).

``POST /intake/pull`` and every write on `/intake/rules` require
``require_role(admin, manager)`` (intake-items spec, "Ingesta manual
on-demand"; intake-rules spec, "CRUD de reglas con permisos por rol"); every
``GET`` here is open to any authenticated member, but the full mail body
(``raw_payload.body_text``) is returned only to admin/manager (C03). Responses follow the
standard ``{data[, meta]}`` envelope, same as every other module.
Triage/settings routes (Fase 5) are added by a later commit.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership, require_role
from app.modules.intake.schemas import (
    IntakeConvertRequest,
    IntakeRuleCreate,
    IntakeRuleUpdate,
    IntakeSettingsUpdate,
)
from app.modules.intake.service import IntakeService
from app.modules.organizations.models import OrganizationMember
from app.shared.enums import IntakeItemStatus, IntakeItemType, MemberRole

router = APIRouter(tags=["intake"])

# Roles allowed to read the full body of an ingested mail (C03 privacy).
_BODY_READER_ROLES = frozenset({MemberRole.admin, MemberRole.manager})


def _reads_full_body(membership: OrganizationMember) -> bool:
    return membership.role in _BODY_READER_ROLES


# Module-level singletons (ruff B008 — see connectors/router.py's identical
# rationale): every write endpoint below shares ONE dependency instance.
require_intake_pull_role = require_role(MemberRole.admin, MemberRole.manager)
require_intake_rule_write_role = require_role(MemberRole.admin, MemberRole.manager)
require_intake_settings_write_role = require_role(MemberRole.admin, MemberRole.manager)


@router.post("/intake/pull")
async def pull_intake(
    membership: OrganizationMember = Depends(require_intake_pull_role),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ingest every connected account of the organization (admin or manager
    only) — opens/closes one ``IntakeRun`` per account."""

    service = IntakeService(db)
    runs = await service.pull(membership.organization_id, actor_id=actor_id)
    return {"data": runs, "meta": {"total": len(runs)}}


@router.get("/intake/items")
async def list_intake_items(
    status_filter: IntakeItemStatus | None = Query(default=None, alias="status"),
    item_type: IntakeItemType | None = Query(default=None),
    connector_id: uuid.UUID | None = Query(default=None),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the organization's stored insumos (any authenticated member),
    including the triage view (`?status=pending`). The full mail body is
    included only for admin/manager; everyone keeps the snippet."""

    service = IntakeService(db)
    items = await service.list_items(
        membership.organization_id,
        status=status_filter,
        item_type=item_type,
        connector_id=connector_id,
        include_body=_reads_full_body(membership),
    )
    return {"data": items, "meta": {"total": len(items)}}


@router.get("/intake/items/{item_id}")
async def get_intake_item(
    item_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a single insumo. 404 if it does not exist or is not the caller's.
    The full mail body is included only for admin/manager."""

    service = IntakeService(db)
    item = await service.get_item(
        membership.organization_id, item_id, include_body=_reads_full_body(membership)
    )
    return {"data": item}


@router.get("/intake/runs")
async def list_intake_runs(
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the organization's ingestion bitácora (any authenticated member)."""

    service = IntakeService(db)
    runs = await service.list_runs(membership.organization_id)
    return {"data": runs, "meta": {"total": len(runs)}}


# ---------------------------------------------------------------------------
# intake_rules CRUD (change 22, Fase 3)
# ---------------------------------------------------------------------------


@router.post("/intake/rules", status_code=status.HTTP_201_CREATED)
async def create_intake_rule(
    payload: IntakeRuleCreate,
    membership: OrganizationMember = Depends(require_intake_rule_write_role),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a tema→respondiente rule (admin or manager only)."""

    service = IntakeService(db)
    rule = await service.create_rule(membership.organization_id, payload, actor_id=actor_id)
    return {"data": rule, "message": "Regla creada."}


@router.get("/intake/rules")
async def list_intake_rules(
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the organization's rules (any authenticated member)."""

    service = IntakeService(db)
    rules = await service.list_rules(membership.organization_id)
    return {"data": rules, "meta": {"total": len(rules)}}


@router.get("/intake/rules/{rule_id}")
async def get_intake_rule(
    rule_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a single rule. 404 if it does not exist or is not the caller's."""

    service = IntakeService(db)
    rule = await service.get_rule(membership.organization_id, rule_id)
    return {"data": rule}


@router.patch("/intake/rules/{rule_id}")
async def update_intake_rule(
    rule_id: uuid.UUID,
    payload: IntakeRuleUpdate,
    membership: OrganizationMember = Depends(require_intake_rule_write_role),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Edit a rule, including `rule_order`/`is_active` (admin or manager only)."""

    service = IntakeService(db)
    rule = await service.update_rule(
        membership.organization_id, rule_id, payload, actor_id=actor_id
    )
    return {"data": rule, "message": "Regla actualizada."}


@router.delete("/intake/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_intake_rule(
    rule_id: uuid.UUID,
    membership: OrganizationMember = Depends(require_intake_rule_write_role),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Soft-delete a rule (admin or manager only)."""

    service = IntakeService(db)
    await service.delete_rule(membership.organization_id, rule_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Manual triage + settings (change 22, Fase 5)
# ---------------------------------------------------------------------------


@router.post("/intake/items/{item_id}/convert")
async def convert_intake_item(
    item_id: uuid.UUID,
    payload: IntakeConvertRequest,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually convert a `pending` insumo into a `Task` (any authenticated
    member) — the organization's default project, `matched_rule_id` stays
    ``null`` (distinguishes manual from automatic conversion)."""

    service = IntakeService(db)
    item = await service.convert_manual(
        membership.organization_id, item_id, payload, actor_id=actor_id
    )
    return {"data": item, "message": "Insumo convertido en tarea."}


@router.get("/intake/settings")
async def get_intake_settings(
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get the organization's intake configuration (any authenticated member)."""

    service = IntakeService(db)
    settings_read = await service.get_settings(membership.organization_id)
    return {"data": settings_read}


@router.patch("/intake/settings")
async def update_intake_settings(
    payload: IntakeSettingsUpdate,
    membership: OrganizationMember = Depends(require_intake_settings_write_role),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Configure the default project's name (admin or manager only)."""

    service = IntakeService(db)
    settings_read = await service.update_settings(membership.organization_id, payload)
    return {"data": settings_read, "message": "Configuración de intake actualizada."}
