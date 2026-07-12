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
    # Audit trail (R4/R5): who created/last-updated the row. NULL for rows
    # written before the audit migration or outside a request context.
    created_by: uuid.UUID | None = None
    updated_by: uuid.UUID | None = None


class AlertRuleUpdate(BaseModel):
    enabled: bool | None = None
    threshold_params: dict | None = None
