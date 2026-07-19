"""RED tests for the `on_tokens_refreshed` sink (change 22-intake-classifier,
delta specs/connectors/spec.md, tasks.md T6.3): token vencido se refresca y
persiste antes de leer; refresco fallido no persiste credenciales corruptas
y el `IntakeRun` cierra `error`; token vigente no dispara refresco.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import crypto
from app.integrations.adapters.fake import FakeAdapter
from app.integrations.dtos import OAuthTokens
from app.integrations.ports import CredentialKind
from app.modules.connectors.models import ConnectedAccount, ConnectionCredentials, Connector
from app.shared.enums import AccountStatus, ConnectorStatus
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class _FlakyRefreshFakeAdapter(FakeAdapter):
    """Same canned read data as ``FakeAdapter``, but ``refresh`` always
    fails — simulates a provider-revoked ``refresh_token``."""

    async def refresh(self, refresh_token: str) -> OAuthTokens:
        raise RuntimeError("refresh_token revocado por el proveedor")


async def _seed_fake_account(
    session: AsyncSession,
    organization_id: uuid.UUID,
    owner_id: uuid.UUID,
    *,
    expires_at: datetime | None,
    access_token_plain: str = "stale-access-token",
    refresh_token_plain: str | None = "stale-refresh-token",
) -> ConnectedAccount:
    connector = Connector(
        organization_id=organization_id,
        provider="fake",
        credential_kind=CredentialKind.oauth,
        status=ConnectorStatus.active,
    )
    session.add(connector)
    await session.flush()

    account = ConnectedAccount(
        organization_id=organization_id,
        connector_id=connector.id,
        user_id=owner_id,
        external_account_id="fake-account-sink",
        status=AccountStatus.active,
    )
    session.add(account)
    await session.flush()

    session.add(
        ConnectionCredentials(
            organization_id=organization_id,
            connected_account_id=account.id,
            access_token_enc=crypto.encrypt(access_token_plain),
            refresh_token_enc=(
                crypto.encrypt(refresh_token_plain) if refresh_token_plain else None
            ),
            expires_at=expires_at,
            token_type="Bearer",
            scopes=["mail"],
        )
    )
    await session.flush()
    return account


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_expired_token_refreshes_and_persists_before_reading(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Token vencido se refresca y persiste antes de leer — las
    nuevas credenciales cifradas quedan persistidas y la lectura procede."""

    expired_at = datetime.now(UTC) - timedelta(hours=1)
    account = await _seed_fake_account(
        session,
        two_orgs.a.organization.id,
        two_orgs.a.user.id,
        expires_at=expired_at,
        refresh_token_plain="stale-refresh-token",
    )

    response = await client.post("/intake/pull", headers=_auth(two_orgs.a.token))

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body[0]["status"] == "completed"
    assert body[0]["items_fetched"] == 5  # read proceeded with the NEW token

    # The plaintext refreshed token never appears in the response.
    assert "fake-access-refreshed-stale-refresh-token" not in response.text

    result = await session.execute(
        select(ConnectionCredentials).where(
            ConnectionCredentials.connected_account_id == account.id
        )
    )
    credentials = result.scalar_one()
    # Never stored as plaintext — the ciphertext column is NEVER the raw
    # refreshed token string itself.
    assert "fake-access-refreshed-stale-refresh-token" not in credentials.access_token_enc
    assert crypto.decrypt(credentials.access_token_enc) == (
        "fake-access-refreshed-stale-refresh-token"
    )
    # FakeAdapter.refresh always returns expires_at=None.
    assert credentials.expires_at is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_failed_refresh_does_not_persist_corrupted_credentials(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Refresco fallido no persiste credenciales corruptas — las
    credenciales existentes NO se sobrescriben y el `IntakeRun` cierra
    `status=error`."""

    from app.integrations import registry as integrations_registry

    monkeypatch.setitem(integrations_registry._ADAPTERS, "fake", _FlakyRefreshFakeAdapter())

    expired_at = datetime.now(UTC) - timedelta(hours=1)
    account = await _seed_fake_account(
        session,
        two_orgs.a.organization.id,
        two_orgs.a.user.id,
        expires_at=expired_at,
    )
    original_access_token_enc = crypto.encrypt("stale-access-token")

    response = await client.post("/intake/pull", headers=_auth(two_orgs.a.token))

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body[0]["status"] == "error"

    result = await session.execute(
        select(ConnectionCredentials).where(
            ConnectionCredentials.connected_account_id == account.id
        )
    )
    credentials = result.scalar_one()
    # Different ciphertext is expected (Fernet is non-deterministic), but the
    # DECRYPTED plaintext must be UNCHANGED — the credentials were untouched.
    assert crypto.decrypt(credentials.access_token_enc) == crypto.decrypt(
        original_access_token_enc
    )
    assert credentials.expires_at is not None  # still the ORIGINAL expiry, not cleared


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_valid_token_never_triggers_refresh(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """Scenario: Token vigente no dispara refresco — `ConnectionCredentials`
    permanece exactamente igual tras el pull."""

    valid_until = datetime.now(UTC) + timedelta(hours=1)
    account = await _seed_fake_account(
        session,
        two_orgs.a.organization.id,
        two_orgs.a.user.id,
        expires_at=valid_until,
        access_token_plain="still-valid-access-token",
    )

    result_before = await session.execute(
        select(ConnectionCredentials).where(
            ConnectionCredentials.connected_account_id == account.id
        )
    )
    access_token_enc_before = result_before.scalar_one().access_token_enc

    response = await client.post("/intake/pull", headers=_auth(two_orgs.a.token))

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body[0]["status"] == "completed"
    assert body[0]["items_fetched"] == 5

    result_after = await session.execute(
        select(ConnectionCredentials).where(
            ConnectionCredentials.connected_account_id == account.id
        )
    )
    credentials_after = result_after.scalar_one()
    assert credentials_after.access_token_enc == access_token_enc_before
    assert credentials_after.expires_at == valid_until
