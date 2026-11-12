"""ORM models owned by the auth module.

``FederatedIdentity`` anchors a local :class:`~app.modules.users.models.User`
to an external OIDC identity (change 20-sso-keycloak, design.md D1). The
anchor is ``UNIQUE(issuer, subject)`` — NOT ``(provider, subject)``: ``sub``
is only unique per ``issuer`` per the OIDC spec, which is the cryptographic
anchor the callback resolves the user by; ``provider`` is purely a config
alias used to route which :class:`~app.modules.auth.oidc.config.OidcProviderConfig`
to load, it never participates in the identity anchor. After the first link,
``email`` is informative only (kept for display/debugging) — the user is
resolved by ``(issuer, subject)`` on every subsequent login.
"""

import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.shared.base_model import AuditMixin, PkMixin, SoftDeleteMixin, TimestampMixin


class FederatedIdentity(PkMixin, TimestampMixin, SoftDeleteMixin, AuditMixin, Base):
    """A local user's link to one external OIDC identity.

    ``user_id`` is indexed (frequent lookup: "this user's linked
    identities"); the anchor lookup used by the callback is the
    ``UNIQUE(issuer, subject)`` constraint below, which Postgres backs with
    its own unique index.
    """

    __tablename__ = "federated_identities"
    __table_args__ = (
        UniqueConstraint(
            "issuer", "subject", name="uq_federated_identities_issuer_subject"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Config alias (e.g. "keycloak") used to route to the provider's
    # OidcProviderConfig. Never part of the identity anchor — see module
    # docstring.
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    # Informative snapshot of the verified email at link time; NOT re-used
    # to re-resolve the user on later logins (design.md Open Questions —
    # best-effort resync is deferred).
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
