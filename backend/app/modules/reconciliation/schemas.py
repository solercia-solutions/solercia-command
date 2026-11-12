"""Request/response models of ``/intake/proposals`` (C05)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import Priority


class IntakeProposalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_key: str
    conversation_id: str | None
    subject: str
    item_ids: list[str]
    message_count: int
    last_message_at: datetime
    thread_state: str
    relation: str | None
    task_id: uuid.UUID | None
    confidence: float | None
    result: dict | None
    candidates: list[dict]
    provider: str | None
    model: str | None
    prompt_version: str | None
    classification_error: str | None
    status: str
    created_task_id: uuid.UUID | None
    decided_by: uuid.UUID | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProposalAccept(BaseModel):
    """``task_id`` overrides the proposed task (same organization only).
    ``status`` is applied ONLY when sent: accepting never moves a task by
    itself."""

    task_id: uuid.UUID | None = None
    status: str | None = Field(default=None, min_length=1, max_length=60)
    note: str | None = Field(default=None, max_length=2000)


class ProposalCreateTask(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    priority: Priority = Priority.medium
    assignee_id: uuid.UUID | None = None
