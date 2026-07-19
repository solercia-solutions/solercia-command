"""Pydantic schemas for the intake module (change 22-intake-classifier)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import IntakeItemStatus, IntakeItemType, IntakeRunStatus, Priority


class IntakeItemRead(BaseModel):
    """An ``IntakeItem`` as returned by the API — includes ``raw_payload``
    for triage (the original insumo, preserved for trazabilidad/
    reclasificación futura, design.md "Almacenamiento de insumos")."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_provider: str
    connector_id: uuid.UUID
    connected_account_id: uuid.UUID | None = None
    item_type: IntakeItemType
    external_id: str
    title: str
    snippet: str | None = None
    origin_actor: str
    occurred_at: datetime
    raw_payload: dict
    status: IntakeItemStatus
    matched_rule_id: uuid.UUID | None = None
    created_task_id: uuid.UUID | None = None
    classified_at: datetime | None = None
    created_at: datetime


class IntakeRunRead(BaseModel):
    """An ``IntakeRun`` (bitácora de un ``POST /intake/pull`` por cuenta)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connector_id: uuid.UUID
    connected_account_id: uuid.UUID | None = None
    items_fetched: int
    items_new: int
    items_duplicated: int
    items_converted: int
    status: IntakeRunStatus
    started_at: datetime
    finished_at: datetime | None = None
    created_at: datetime


class IntakeRuleCriterion(BaseModel):
    """One AND-combined condition of an ``IntakeRule.criteria`` list
    (design.md Interfaces/Contracts)."""

    field: str = Field(
        description="origin_actor|domain|title|snippet|source_provider|connector_id"
    )
    operator: str = Field(description="equals|contains|in")
    value: str | list[str]


class IntakeRuleCreate(BaseModel):
    """Payload to create an ``IntakeRule`` (change 22, Fase 3)."""

    name: str = Field(min_length=1, max_length=160)
    criteria: list[IntakeRuleCriterion] = Field(min_length=1)
    convert_to_task: bool = True
    target_project_id: uuid.UUID | None = None
    task_priority: Priority = Priority.medium
    assignee_id: uuid.UUID | None = None
    rule_order: int = Field(ge=0)


class IntakeRuleUpdate(BaseModel):
    """Partial payload to edit an ``IntakeRule``. Every field is optional."""

    name: str | None = Field(default=None, min_length=1, max_length=160)
    criteria: list[IntakeRuleCriterion] | None = Field(default=None, min_length=1)
    convert_to_task: bool | None = None
    target_project_id: uuid.UUID | None = None
    task_priority: Priority | None = None
    assignee_id: uuid.UUID | None = None
    rule_order: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class IntakeRuleRead(BaseModel):
    """An ``IntakeRule`` as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    criteria: list[dict]
    convert_to_task: bool
    target_project_id: uuid.UUID | None = None
    task_priority: Priority
    assignee_id: uuid.UUID | None = None
    rule_order: int
    is_active: bool
    created_at: datetime


class IntakeConvertRequest(BaseModel):
    """Payload for ``POST /intake/items/{id}/convert`` (manual triage,
    change 22, Fase 5)."""

    priority: Priority = Priority.medium
    assignee_id: uuid.UUID | None = None


class IntakeSettingsRead(BaseModel):
    """Per-organization intake configuration."""

    model_config = ConfigDict(from_attributes=True)

    default_project_id: uuid.UUID | None = None
    default_project_name: str | None = None


class IntakeSettingsUpdate(BaseModel):
    """Payload for ``PATCH /intake/settings`` (change 22, Fase 5)."""

    default_project_name: str = Field(min_length=1, max_length=160)
