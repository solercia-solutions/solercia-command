"""AlertRule ORM model — configurable alert rule per organization."""
from sqlalchemy import JSON, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    AuditMixin,
    PkMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)


class AlertRule(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    __tablename__ = "alert_rules"

    rule_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # e.g. {"days_before": 3} or {"max_active_tasks": 8} or {"inactive_days": 3}
    threshold_params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
