"""Reminders and reminder-rules routes — strictly personal (solo-dueño).

All endpoints require authentication and are scoped to the caller's own
resources within their current organization. Responses are wrapped in a
``{data[, message][, meta]}`` envelope. ``POST /reminders/dispatch`` (Fase B)
is admin-only (``require_admin``), espejo de ``POST /alerts/evaluate``.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_actor_id, get_current_membership, require_admin
from app.modules.organizations.models import OrganizationMember
from app.modules.reminders.schemas import (
    ReminderCreate,
    ReminderRuleCreate,
    ReminderRuleUpdate,
    ReminderUpdate,
)
from app.modules.reminders.service import ReminderRuleService, ReminderService
from app.modules.users.models import User
from app.reminders.dispatcher import dispatch_reminders
from app.shared.enums import ReminderStatus
from app.shared.pagination import PaginationParams, build_list_meta, pagination_params

router = APIRouter(tags=["reminders"])


@router.post("/reminders", status_code=status.HTTP_201_CREATED)
async def create_reminder(
    payload: ReminderCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a manual reminder for the authenticated caller."""
    service = ReminderService(db)
    reminder = await service.create_reminder(
        membership.organization_id, membership.user_id, payload, actor_id=actor_id
    )
    return {"data": reminder, "message": "Recordatorio creado."}


@router.get("/reminders")
async def list_reminders(
    status_filter: ReminderStatus | None = Query(default=None, alias="status"),
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the caller's own reminders, most recent first (opt-in pagination)."""
    service = ReminderService(db)
    reminders, total = await service.list_reminders(
        membership.organization_id, membership.user_id, status_filter, pagination
    )
    return {
        "data": reminders,
        "message": "Recordatorios obtenidos.",
        "meta": build_list_meta(pagination, total),
    }


@router.get("/reminders/{reminder_id}")
async def get_reminder(
    reminder_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a single reminder owned by the caller. 404 if it does not exist or is not theirs."""
    service = ReminderService(db)
    reminder = await service.get_reminder(
        membership.organization_id, reminder_id, membership.user_id
    )
    return {"data": reminder}


@router.patch("/reminders/{reminder_id}")
async def update_reminder(
    reminder_id: uuid.UUID,
    payload: ReminderUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Edit remind_at/message. Only allowed while the reminder is scheduled."""
    service = ReminderService(db)
    reminder = await service.update_reminder(
        membership.organization_id,
        reminder_id,
        membership.user_id,
        payload,
        actor_id=actor_id,
    )
    return {"data": reminder, "message": "Recordatorio actualizado."}


@router.delete("/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_reminder(
    reminder_id: uuid.UUID,
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Cancel a scheduled reminder (status=cancelled). The scheduler will skip it."""
    service = ReminderService(db)
    await service.cancel_reminder(
        membership.organization_id, reminder_id, membership.user_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/reminder-rules")
async def list_reminder_rules(
    pagination: PaginationParams = Depends(pagination_params),
    membership: OrganizationMember = Depends(get_current_membership),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List the caller's own reminder rules."""
    service = ReminderRuleService(db)
    rules, total = await service.list_rules(
        membership.organization_id, membership.user_id, pagination
    )
    return {
        "data": rules,
        "message": "Reglas de recordatorio obtenidas.",
        "meta": build_list_meta(pagination, total),
    }


@router.post("/reminder-rules", status_code=status.HTTP_201_CREATED)
async def create_reminder_rule(
    payload: ReminderRuleCreate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a personal reminder rule (e.g. task_due_soon), enabled by default."""
    service = ReminderRuleService(db)
    rule = await service.create_rule(
        membership.organization_id, membership.user_id, payload, actor_id=actor_id
    )
    return {"data": rule, "message": "Regla de recordatorio creada."}


@router.patch("/reminder-rules/{rule_id}")
async def update_reminder_rule(
    rule_id: uuid.UUID,
    payload: ReminderRuleUpdate,
    membership: OrganizationMember = Depends(get_current_membership),
    actor_id: uuid.UUID | None = Depends(get_actor_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Edit lead_days/enabled of a personal reminder rule."""
    service = ReminderRuleService(db)
    rule = await service.update_rule(
        membership.organization_id,
        rule_id,
        membership.user_id,
        payload,
        actor_id=actor_id,
    )
    return {"data": rule, "message": "Regla de recordatorio actualizada."}


@router.post("/reminders/dispatch")
async def trigger_reminder_dispatch(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict:
    """Trigger the reminder dispatcher on demand (admin only). Useful for testing."""
    total = await dispatch_reminders(db)
    return {
        "data": {"created": total},
        "message": f"Disparo de recordatorios completado. {total} notificaciones nuevas creadas.",
    }
