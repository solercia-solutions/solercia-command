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

``credential_kind``/``settings`` (change 17-adapter-glpi, delta spec
connectors/spec.md, "Tipo de credencial del conector") son delta columns
added by migración `0017`: el 17 es DUEÑO de ambas — 18/19 solo las
consumen (con su propio namespace dentro de ``settings``), nunca agregan
columna nueva.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.integrations.ports import CredentialKind
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
    # Fixed at creation, never changed afterwards without recreating the
    # connector (specs/connectors/spec.md, change 17-adapter-glpi). Defaults
    # to `oauth` so every connector created before this column existed (14's
    # microsoft365/google) keeps behaving exactly as before.
    credential_kind: Mapped[CredentialKind] = mapped_column(
        SAEnum(CredentialKind, name="connector_credential_kind", native_enum=False, length=20),
        default=CredentialKind.oauth,
        nullable=False,
    )
    # Non-secret, provider-specific configuration (e.g. GLPI's `base_url`/
    # `document_field`) — NEVER a token/credential; those stay isolated in
    # `ConnectionCredentials`, encrypted.
    settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


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

    No ``SoftDeleteMixin`` — there are no ``is_active``/``deleted_at``
    columns to flip here. Disconnecting a ``ConnectedAccount``
    (``ConnectedAccountRepository.soft_delete_account``) soft-deletes the
    ACCOUNT row (audit trail survives) but PURGES this table's row via a
    hard delete: token material is removed immediately on disconnect rather
    than retained "soft-deleted" — the more conservative choice for a
    secret. ``ondelete="CASCADE"`` on the FK is the backstop for the case
    the account itself is ever hard-deleted directly.
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
