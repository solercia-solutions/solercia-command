"""Tests for ``app.modules.auth.sso_service`` (change 20-sso-keycloak, T12).

Covers the state store (Redis, TTL 300s, single-use — via ``fakeredis``,
same ``patched_redis`` fixture as the connectors OAuth state store) and
``resolve_or_provision_user``'s R4 resolution order: existing
``(issuer, subject)`` link · link by verified email · reject without
auto-provision · auto-provision without password/roles · reject an
unverified email (R3). Pure DB-level unit tests — no HTTP, no OidcClient.
"""

import uuid

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.auth.models import FederatedIdentity
from app.modules.auth.oidc.config import OidcProviderConfig
from app.modules.auth.sso_service import (
    SsoDisabledError,
    SsoLoginRejectedError,
    pop_state,
    put_state,
    require_provider_config,
    resolve_or_provision_user,
)
from app.modules.users.models import User
from tests.conftest import skip_no_db

_ISSUER = "https://idp.test/realms/demo"


def _claims(
    *, sub: str = "user-sub-1", email: str = "person@example.com", email_verified: bool = True
) -> dict:
    return {
        "iss": _ISSUER,
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
    }


# ---------------------------------------------------------------------------
# State store — Redis, TTL 300s, single-use
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_put_state_persists_payload_with_a_300s_ttl(patched_redis) -> None:
    await put_state("state-1", {"nonce": "n1", "code_verifier": "v1", "provider": "keycloak"})

    ttl = await patched_redis.ttl("sso:state:state-1")

    assert 0 < ttl <= 300


@pytest.mark.asyncio
async def test_pop_state_returns_the_payload_and_is_single_use(patched_redis) -> None:
    await put_state("state-2", {"nonce": "n2", "code_verifier": "v2", "provider": "keycloak"})

    first = await pop_state("state-2")
    second = await pop_state("state-2")

    assert first == {"nonce": "n2", "code_verifier": "v2", "provider": "keycloak"}
    assert second is None


@pytest.mark.asyncio
async def test_pop_state_returns_none_for_an_unknown_state(patched_redis) -> None:
    result = await pop_state("never-issued-state")

    assert result is None


# ---------------------------------------------------------------------------
# require_provider_config — R6
# ---------------------------------------------------------------------------


def test_require_provider_config_raises_when_sso_disabled(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "SSO_ENABLED", False)

    with pytest.raises(SsoDisabledError):
        require_provider_config("keycloak")


def test_require_provider_config_raises_when_provider_unconfigured(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "SSO_ENABLED", True)
    for suffix in ("ISSUER", "CLIENT_ID", "CLIENT_SECRET", "REDIRECT_URI"):
        monkeypatch.delenv(f"OIDC_KEYCLOAK_{suffix}", raising=False)

    with pytest.raises(SsoDisabledError):
        require_provider_config("keycloak")


def test_require_provider_config_returns_config_when_fully_configured(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "SSO_ENABLED", True)
    monkeypatch.setenv("OIDC_KEYCLOAK_ISSUER", _ISSUER)
    monkeypatch.setenv("OIDC_KEYCLOAK_CLIENT_ID", "solercia")
    monkeypatch.setenv("OIDC_KEYCLOAK_CLIENT_SECRET", "shh")
    monkeypatch.setenv("OIDC_KEYCLOAK_REDIRECT_URI", "http://localhost:4200/auth/callback")

    config = require_provider_config("keycloak")

    assert config == OidcProviderConfig(
        provider="keycloak",
        issuer=_ISSUER,
        client_id="solercia",
        client_secret="shh",
        redirect_uri="http://localhost:4200/auth/callback",
    )


# ---------------------------------------------------------------------------
# resolve_or_provision_user — R4 order + R3
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_resolve_reuses_an_existing_issuer_subject_link(session: AsyncSession) -> None:
    """(a) Enlace idempotente por sub — no duplica la identidad, autentica
    al mismo usuario local."""

    existing_user = User(
        email="linked@example.com",
        primer_nombre="Linked",
        primer_apellido="User",
        hashed_password="x",
    )
    session.add(existing_user)
    await session.flush()
    session.add(
        FederatedIdentity(
            user_id=existing_user.id,
            provider="keycloak",
            issuer=_ISSUER,
            subject="user-sub-1",
            email="linked@example.com",
        )
    )
    await session.flush()

    resolved = await resolve_or_provision_user(
        session, "keycloak", _claims(sub="user-sub-1", email="linked@example.com")
    )

    assert resolved.id == existing_user.id

    count_result = await session.execute(
        select(FederatedIdentity).where(FederatedIdentity.subject == "user-sub-1")
    )
    assert len(count_result.scalars().all()) == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_resolve_links_an_existing_user_by_verified_email(session: AsyncSession) -> None:
    """(b) Callback feliz — enlace de usuario existente: crea el registro
    en FederatedIdentity y resuelve ese usuario."""

    existing_user = User(
        email="matcher@example.com",
        primer_nombre="Matcher",
        primer_apellido="User",
        hashed_password="x",
    )
    session.add(existing_user)
    await session.flush()

    resolved = await resolve_or_provision_user(
        session,
        "keycloak",
        _claims(sub="fresh-sub", email="matcher@example.com", email_verified=True),
    )

    assert resolved.id == existing_user.id

    link_result = await session.execute(
        select(FederatedIdentity).where(FederatedIdentity.subject == "fresh-sub")
    )
    link = link_result.scalar_one()
    assert link.user_id == existing_user.id
    assert link.issuer == _ISSUER


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_resolve_rejects_unverified_email_without_creating_anything(
    session: AsyncSession,
) -> None:
    """R3 — correo no verificado: rechaza sin crear ni enlazar ninguna cuenta."""

    with pytest.raises(SsoLoginRejectedError):
        await resolve_or_provision_user(
            session,
            "keycloak",
            _claims(sub="unverified-sub", email="nobody@example.com", email_verified=False),
        )

    user_result = await session.execute(
        select(User).where(User.email == "nobody@example.com")
    )
    assert user_result.scalar_one_or_none() is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_resolve_rejects_no_match_when_auto_provision_disabled(
    session: AsyncSession, monkeypatch
) -> None:
    """(c) Usuario no existente, auto-provisión desactivada — rechaza y no
    crea ningún usuario."""

    from app.config import settings

    monkeypatch.setattr(settings, "SSO_AUTO_PROVISION", False)

    with pytest.raises(SsoLoginRejectedError):
        await resolve_or_provision_user(
            session, "keycloak", _claims(sub="no-match-sub", email="unknown@example.com")
        )

    user_result = await session.execute(
        select(User).where(User.email == "unknown@example.com")
    )
    assert user_result.scalar_one_or_none() is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_resolve_auto_provisions_a_user_without_password_or_roles(
    session: AsyncSession, monkeypatch
) -> None:
    """(d) Usuario no existente, auto-provisión activada — crea el usuario
    local (sin hashed_password), lo enlaza y lo autentica sin ningún rol."""

    from app.config import settings

    monkeypatch.setattr(settings, "SSO_AUTO_PROVISION", True)

    resolved = await resolve_or_provision_user(
        session,
        "keycloak",
        _claims(sub="brand-new-sub", email=f"new-{uuid.uuid4().hex[:8]}@example.com"),
    )

    assert resolved.hashed_password is None

    from app.modules.roles.models import UserRole

    roles_result = await session.execute(
        select(UserRole).where(UserRole.user_id == resolved.id)
    )
    assert roles_result.scalars().all() == []

    link_result = await session.execute(
        select(FederatedIdentity).where(FederatedIdentity.subject == "brand-new-sub")
    )
    link = link_result.scalar_one()
    assert link.user_id == resolved.id


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_resolve_commits_so_a_new_request_session_sees_the_provisioned_user(
    engine: AsyncEngine, monkeypatch
) -> None:
    """Regresión: ``resolve_or_provision_user`` DEBE confirmar (commit) sus
    escrituras — ``get_db()`` (app/database.py) abre una sesión nueva por
    request sin auto-commit, así que un flush sin commit se pierde al
    cerrarse la sesión. Usa sesiones ligadas DIRECTAMENTE al engine real
    (evitando el fixture ``session``, que envuelve en un SAVEPOINT y hace
    visible el flush sin necesitar commit, enmascarando este defecto)."""

    from app.config import settings

    monkeypatch.setattr(settings, "SSO_AUTO_PROVISION", True)

    subject = f"regression-sub-{uuid.uuid4().hex[:8]}"
    email = f"regression-{uuid.uuid4().hex[:8]}@example.com"

    request_session = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        resolved = await resolve_or_provision_user(
            request_session, "keycloak", _claims(sub=subject, email=email)
        )
        provisioned_user_id = resolved.id
    finally:
        await request_session.close()

    fresh_session = AsyncSession(bind=engine, expire_on_commit=False)
    try:
        user_result = await fresh_session.execute(
            select(User).where(User.id == provisioned_user_id)
        )
        assert user_result.scalar_one_or_none() is not None

        link_result = await fresh_session.execute(
            select(FederatedIdentity).where(FederatedIdentity.subject == subject)
        )
        link = link_result.scalar_one_or_none()
        assert link is not None
        assert link.user_id == provisioned_user_id
    finally:
        await fresh_session.execute(
            delete(FederatedIdentity).where(FederatedIdentity.subject == subject)
        )
        await fresh_session.execute(delete(User).where(User.id == provisioned_user_id))
        await fresh_session.commit()
        await fresh_session.close()
