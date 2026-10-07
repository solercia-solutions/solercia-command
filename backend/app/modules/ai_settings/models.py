"""``ai_provider_settings`` (C04): the AI provider an organization chose —
ONE row per tenant (``UNIQUE(organization_id)``), edited in place, no
history. The API key is stored only as a Fernet token
(``INTEGRATIONS_FERNET_KEY``) plus its last four characters for display;
it is never returned. Presets live in code (``app.ai.presets``), so
``preset`` is validated by the service, not by a CHECK. Mirrored by
migration 0031 so ``create_all`` (tests) and ``alembic check`` agree.
"""

from sqlalchemy import Boolean, CheckConstraint, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import AuditMixin, PkMixin, TenantMixin, TimestampMixin

REASONING_EFFORTS = ("none", "low", "medium", "high")


class AiProviderSettings(PkMixin, TimestampMixin, TenantMixin, AuditMixin, Base):
    __tablename__ = "ai_provider_settings"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_ai_provider_settings_organization"),
        CheckConstraint(
            "reasoning_effort IS NULL OR reasoning_effort IN ('none', 'low', 'medium', 'high')",
            name="ck_ai_provider_settings_reasoning_effort",
        ),
    )

    preset: Mapped[str] = mapped_column(String(32), nullable=False)
    #: ``NULL`` = the preset's own URL.
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    chat_model: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    timeout_seconds: Mapped[float] = mapped_column(
        Float, nullable=False, default=60.0, server_default="60"
    )
    max_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1024, server_default="1024"
    )
    temperature: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    #: ``"none"`` disables thinking on reasoning models; ``NULL`` omits it.
    reasoning_effort: Mapped[str | None] = mapped_column(
        String(16), nullable=True, default="none", server_default="none"
    )
    #: Optional provider options, today only ``{"num_ctx": int}``.
    options: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
