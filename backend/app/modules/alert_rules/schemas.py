"""Alert rule Pydantic schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    rule_type: str
    enabled: bool
    threshold_params: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AlertRuleUpdate(BaseModel):
    enabled: bool | None = None
    threshold_params: dict | None = None
