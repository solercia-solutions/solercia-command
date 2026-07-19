"""Pydantic schemas for the connectors module (change 14-integration-ports)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import ConnectorStatus


class ConnectorCreate(BaseModel):
    """Payload to create a connector (provider configuration)."""

    provider: str = Field(min_length=1, max_length=50)
    scopes: list[str] | None = None
    status: ConnectorStatus = ConnectorStatus.active


class ConnectorUpdate(BaseModel):
    """Partial payload to edit a connector."""

    provider: str | None = Field(default=None, min_length=1, max_length=50)
    scopes: list[str] | None = None
    status: ConnectorStatus | None = None


class ConnectorRead(BaseModel):
    """A connector as returned by the API.

    Never exposes tokens — a connector has none: OAuth tokens live isolated
    in ``ConnectionCredentials``, a separate table this schema never touches.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    scopes: list[str] | None = None
    status: ConnectorStatus
    created_at: datetime
    updated_at: datetime
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None
