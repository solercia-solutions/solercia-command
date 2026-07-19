"""``Connector``, ``ConnectedAccount`` and ``ConnectionCredentials`` ORM
models (change 14-integration-ports, design.md "Tablas").

``Connector`` is the org-scoped provider configuration
(``UNIQUE(organization_id, provider)``). ``ConnectedAccount`` is a user's
account under a connector — unicidad por ``external_account_id`` dentro del
conector, NUNCA por ``(user_id, provider)`` (decisión ratificada #1, un
usuario puede conectar varias cuentas del mismo proveedor).
``ConnectionCredentials`` vive en tabla AISLADA, 1:1 con la cuenta
(decisión ratificada #4): los tokens cifrados (Fernet) nunca conviven con
los campos que la API expone directamente sobre ``ConnectedAccount``.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import (
    AuditMixin,
    PkMixin,
    SoftDeleteMixin,
    TenantMixin,
    TimestampMixin,
)
from app.shared.enums import AccountStatus, ConnectorStatus


class Connector(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    """A provider configuration owned by an organization."""

    __tablename__ = "connectors"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "provider", name="uq_connectors_organization_provider"
        ),
    )

    # Free-text provider key (e.g. "microsoft365", "google", "glpi"),
    # deliberately NOT a PG enum — providers extend in changes 15-19 without
    # an enum migration (design.md "Provider como String(50), no enum PG").
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    scopes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ConnectorStatus] = mapped_column(
        SAEnum(ConnectorStatus, name="connector_status", native_enum=False, length=20),
        default=ConnectorStatus.active,
        nullable=False,
        index=True,
    )


class ConnectedAccount(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, TenantMixin, Base):
    """A single user's connected account under a ``Connector``."""

    __tablename__ = "connected_accounts"
    __table_args__ = (
        UniqueConstraint(
            "connector_id",
            "external_account_id",
            name="uq_connected_accounts_connector_external",
        ),
    )

    connector_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_account_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[AccountStatus] = mapped_column(
        SAEnum(AccountStatus, name="account_status", native_enum=False, length=20),
        default=AccountStatus.active,
        nullable=False,
        index=True,
    )


class ConnectionCredentials(PkMixin, TimestampMixin, TenantMixin, Base):
    """Encrypted OAuth tokens for a ``ConnectedAccount`` (1:1, isolated table).

    No ``SoftDeleteMixin``: credentials are hard-scoped to the lifetime of
    their ``ConnectedAccount`` (``ondelete="CASCADE"``); disconnecting an
    account soft-deletes BOTH rows explicitly from the service layer.
    """

    __tablename__ = "connection_credentials"
    __table_args__ = (
        UniqueConstraint(
            "connected_account_id", name="uq_connection_credentials_connected_account"
        ),
    )

    connected_account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("connected_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    token_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    scopes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
