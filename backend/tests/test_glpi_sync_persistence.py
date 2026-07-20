"""Persistence-regression net for the GLPI connector's FIVE write flows
(change 17-adapter-glpi).

Every test here uses TWO INDEPENDENT ``AsyncSession`` instances bound to the
shared ``engine`` fixture (NEVER the SAVEPOINT-scoped ``session``/``client``
combo): session A seeds COMMITTED data and invokes the service; a brand-new
session B then proves the service's own ``db.commit()`` produced a REAL,
durable write — not one that merely *looks* committed because it shares the
test's uncommitted outer SAVEPOINT transaction (same lesson ratified in
``test_intake_items_service.py`` for change 22).

Covered write flows (the repositories only ``flush``; the ``commit`` lives
in the service — exactly what this regression net protects):

1. ``GlpiSyncService.run_sync``                       (glpi_sync/service.py)
2. ``GlpiSyncService.resolve_unmatched_entry``        (glpi_sync/service.py)
3. ``GlpiSyncService.ignore_unmatched_entry``         (glpi_sync/service.py)
4. ``GlpiSyncService.revoke_link``                    (glpi_sync/service.py)
5. ``ConnectorService.register_api_token_credentials`` (connectors/service.py)

Cleanup ALWAYS runs on a FRESH session: a failed assertion leaves session
A/B's transaction aborted, so the final ``DELETE`` must never inherit that
broken state.
"""

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.integrations import crypto
from app.integrations.dtos import AccountRef, ExternalPerson, Ticket
from app.integrations.ports import ApiTokenHandshake, Capability, CredentialKind
from app.modules.connectors.models import ConnectedAccount, ConnectionCredentials, Connector
from app.modules.connectors.service import ConnectorService
from app.modules.glpi_sync.models import (
    GlpiUnmatchedAssignee,
    GlpiUnmatchedCase,
    GlpiUserLink,
)
from app.modules.glpi_sync.service import GlpiSyncService
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.users.models import User
from app.shared.enums import (
    AccountStatus,
    ConnectorStatus,
    MatchMethod,
    MemberRole,
    UnmatchedStatus,
)
from app.shared.security import hash_password
from tests.conftest import skip_no_db

_ALLOWED_BASE_URL = "http://localhost:8080/glpi/apirest.php"

# Provider name for the flow-5 fake adapter — DISTINCT from the module-level
# "fake-api-token" adapter that `test_connectors_api_token.py` registers
# globally at import time, so this suite never depends on (or contaminates)
# that registration; it is installed per-test via `monkeypatch.setitem`.
_FAKE_PROVIDER = "fake-api-token-persistencia"


# ---------------------------------------------------------------------------
# Stubs (adapted from tests/test_glpi_sync.py / test_connectors_api_token.py)
# ---------------------------------------------------------------------------


def _person(
    external_id: str, *, display_name: str | None = None, email: str | None = None
) -> ExternalPerson:
    return ExternalPerson(
        external_id=external_id, display_name=display_name, email=email, document=None
    )


def _ticket(external_id: str, *, assignees: tuple[ExternalPerson, ...] = ()) -> Ticket:
    return Ticket(
        external_id=external_id,
        key=f"GLPI-{external_id}",
        summary=f"Caso {external_id}",
        status="1",
        priority=None,
        requester=None,
        created_at=datetime.now(UTC),
        assignees=assignees,
    )


class _StubGlpiTicketPort:
    def __init__(self, tickets: list[Ticket]) -> None:
        self._tickets = tickets

    async def list_tickets(self, ctx: object, *, since: object = None, limit: int = 50):
        return self._tickets


class _StubGlpiAdapter:
    provider = "glpi"
    capabilities = frozenset({Capability.tickets})
    credential_kind = CredentialKind.api_token
    oauth = None
    api_token = None

    def __init__(self, tickets: list[Ticket]) -> None:
        self.port = _StubGlpiTicketPort(tickets)

    def port_for(self, capability: Capability) -> object | None:
        return self.port if capability == Capability.tickets else None


def _install_glpi_stub(monkeypatch: pytest.MonkeyPatch, tickets: list[Ticket]) -> None:
    from app.integrations import registry as integrations_registry

    monkeypatch.setitem(integrations_registry._ADAPTERS, "glpi", _StubGlpiAdapter(tickets))


class _FakeApiTokenHandshake:
    """Validates without any real HTTP call — mirrors GLPI's
    ``initSession``+``killSession`` validation shape."""

    async def connect(self, raw: Mapping[str, str]) -> AccountRef:
        return AccountRef(
            external_account_id="svc-red-persistencia",
            display_name="Cuenta de servicio api_token",
        )


class _FakeApiTokenAdapter:
    provider = _FAKE_PROVIDER
    capabilities: frozenset = frozenset()
    credential_kind = CredentialKind.api_token
    oauth = None

    def __init__(self) -> None:
        self.api_token: ApiTokenHandshake | None = _FakeApiTokenHandshake()

    def port_for(self, capability: object) -> object | None:
        return None


def _install_api_token_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.integrations import registry as integrations_registry

    monkeypatch.setitem(
        integrations_registry._ADAPTERS, _FAKE_PROVIDER, _FakeApiTokenAdapter()
    )


# ---------------------------------------------------------------------------
# Seed / cleanup helpers — session A commits for REAL; cleanup on a FRESH one
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Scenario:
    organization_id: uuid.UUID
    owner_id: uuid.UUID
    owner_email: str
    connector_id: uuid.UUID


async def _seed_committed_glpi_scenario(
    session_a: AsyncSession,
    *,
    provider: str = "glpi",
    with_account: bool = True,
) -> _Scenario:
    """Persist (REAL commit) an organization + owner admin + an ``api_token``
    connector; optionally its service account + encrypted credentials."""

    organization = Organization(
        name="GLPI Persistencia Org", slug=f"glpi-persist-{uuid.uuid4().hex[:12]}"
    )
    session_a.add(organization)
    await session_a.flush()

    owner_email = f"glpi-owner-{uuid.uuid4().hex[:12]}@example.com"
    owner = User(
        email=owner_email,
        primer_nombre="Glpi",
        primer_apellido="Owner",
        hashed_password=hash_password("Test123*"),
    )
    session_a.add(owner)
    await session_a.flush()

    session_a.add(
        OrganizationMember(
            organization_id=organization.id, user_id=owner.id, role=MemberRole.admin
        )
    )
    await session_a.flush()

    connector = Connector(
        organization_id=organization.id,
        provider=provider,
        credential_kind=CredentialKind.api_token,
        status=ConnectorStatus.active,
        settings={"base_url": _ALLOWED_BASE_URL, "document_field": "registration_number"}
        if provider == "glpi"
        else None,
    )
    session_a.add(connector)
    await session_a.flush()

    if with_account:
        account = ConnectedAccount(
            organization_id=organization.id,
            connector_id=connector.id,
            user_id=owner.id,
            external_account_id="glpi-service-account",
            status=AccountStatus.active,
        )
        session_a.add(account)
        await session_a.flush()

        session_a.add(
            ConnectionCredentials(
                organization_id=organization.id,
                connected_account_id=account.id,
                access_token_enc=crypto.encrypt(
                    json.dumps({"app_token": "app-token-x", "user_token": "user-token-y"})
                ),
                token_type="glpi",
            )
        )

    await session_a.commit()
    return _Scenario(
        organization_id=organization.id,
        owner_id=owner.id,
        owner_email=owner_email,
        connector_id=connector.id,
    )


async def _get_membership(
    db: AsyncSession, organization_id: uuid.UUID, user_id: uuid.UUID
) -> OrganizationMember:
    result = await db.execute(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
    )
    return result.scalar_one()


async def _cleanup_org(
    cleanup_session: AsyncSession, organization_id: uuid.UUID, owner_id: uuid.UUID
) -> None:
    """Delete in FK-safe order on a FRESH session.

    Organization FIRST: its ``ON DELETE CASCADE`` chains remove the members,
    the connector and — via ``connector_id`` CASCADE — accounts, credentials,
    ``glpi_user_links`` and the unmatched queue (header + cases). The owner
    ``User`` goes SECOND: only after the cascade nothing references it any
    more (``glpi_user_links.user_id`` rows died with the connector; audit
    columns are ``ON DELETE SET NULL``).
    """

    await cleanup_session.execute(
        delete(Organization).where(Organization.id == organization_id)
    )
    await cleanup_session.execute(delete(User).where(User.id == owner_id))
    await cleanup_session.commit()


def _fresh_session(engine: AsyncEngine) -> AsyncSession:
    return AsyncSession(engine, expire_on_commit=False)


async def _cleanup_scenario(engine: AsyncEngine, scenario: _Scenario) -> None:
    """Run :func:`_cleanup_org` on a FRESH session — never on one whose
    transaction a failed assertion or DB error may have left aborted."""

    cleanup_session = _fresh_session(engine)
    try:
        await _cleanup_org(
            cleanup_session, scenario.organization_id, scenario.owner_id
        )
    finally:
        await cleanup_session.close()


# ---------------------------------------------------------------------------
# 1. run_sync — link + cola quedan COMMITEADOS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_run_sync_commits_link_and_queue_across_independent_sessions(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flujo 1: ``run_sync`` persiste (commit REAL) el ``GlpiUserLink`` del
    asignado homologado por correo Y el header+caso de la cola del asignado
    sin homologar — verificado desde una sesión B independiente."""

    session_a = _fresh_session(engine)
    scenario: _Scenario | None = None

    try:
        scenario = await _seed_committed_glpi_scenario(session_a)
        membership = await _get_membership(
            session_a, scenario.organization_id, scenario.owner_id
        )
        matched_person = _person(
            "55", display_name="Owner Homologado", email=scenario.owner_email
        )
        unmatched_person = _person("77", display_name="Nadie Desconocido")
        _install_glpi_stub(
            monkeypatch, [_ticket("301", assignees=(matched_person, unmatched_person))]
        )

        service = GlpiSyncService(session_a)
        result = await service.run_sync(
            scenario.organization_id, scenario.connector_id, membership
        )
        await session_a.close()

        assert result.tickets_processed == 1
        assert result.links_created == 1
        assert result.queue_updated == 1

        session_b = _fresh_session(engine)
        try:
            link = (
                await session_b.execute(
                    select(GlpiUserLink).where(
                        GlpiUserLink.connector_id == scenario.connector_id
                    )
                )
            ).scalar_one()
            assert link.glpi_user_id == "55"
            assert link.user_id == scenario.owner_id
            assert link.match_method == MatchMethod.email
            assert link.is_active is True

            header = (
                await session_b.execute(
                    select(GlpiUnmatchedAssignee).where(
                        GlpiUnmatchedAssignee.connector_id == scenario.connector_id
                    )
                )
            ).scalar_one()
            assert header.glpi_user_id == "77"
            assert header.status == UnmatchedStatus.pending

            cases = (
                (
                    await session_b.execute(
                        select(GlpiUnmatchedCase).where(
                            GlpiUnmatchedCase.unmatched_assignee_id == header.id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert [case.glpi_ticket_id for case in cases] == ["301"]
        finally:
            await session_b.close()
    finally:
        # Idempotent double-close: guarantees the NullPool connection goes
        # back even if the seed, a fixture commit or the service raised
        # before the happy path's own `close()` ran.
        await session_a.close()
        if scenario is not None:
            await _cleanup_scenario(engine, scenario)


# ---------------------------------------------------------------------------
# 2. resolve_unmatched_entry — link manual + header resolved COMMITEADOS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_resolve_unmatched_entry_commits_manual_link_and_resolved_header(
    engine: AsyncEngine,
) -> None:
    """Flujo 2: resolver una entrada pendiente crea el link ``manual`` Y
    voltea el header a ``resolved`` con ``resolved_user_id``/``resolved_at``
    — ambos durables desde una sesión B independiente."""

    session_a = _fresh_session(engine)
    scenario: _Scenario | None = None

    try:
        scenario = await _seed_committed_glpi_scenario(session_a)
        header = GlpiUnmatchedAssignee(
            organization_id=scenario.organization_id,
            connector_id=scenario.connector_id,
            glpi_user_id="900",
            glpi_username="Persona Pendiente",
            status=UnmatchedStatus.pending,
        )
        session_a.add(header)
        await session_a.commit()
        header_id = header.id

        membership = await _get_membership(
            session_a, scenario.organization_id, scenario.owner_id
        )
        service = GlpiSyncService(session_a)
        link_read = await service.resolve_unmatched_entry(
            scenario.organization_id, header_id, scenario.owner_id, membership
        )
        await session_a.close()

        assert link_read.match_method == MatchMethod.manual

        session_b = _fresh_session(engine)
        try:
            link = (
                await session_b.execute(
                    select(GlpiUserLink).where(
                        GlpiUserLink.connector_id == scenario.connector_id,
                        GlpiUserLink.glpi_user_id == "900",
                    )
                )
            ).scalar_one()
            assert link.user_id == scenario.owner_id
            assert link.match_method == MatchMethod.manual
            assert link.is_active is True

            persisted_header = (
                await session_b.execute(
                    select(GlpiUnmatchedAssignee).where(
                        GlpiUnmatchedAssignee.id == header_id
                    )
                )
            ).scalar_one()
            assert persisted_header.status == UnmatchedStatus.resolved
            assert persisted_header.resolved_user_id == scenario.owner_id
            assert persisted_header.resolved_at is not None
        finally:
            await session_b.close()
    finally:
        # Idempotent double-close: guarantees the NullPool connection goes
        # back even if the seed, a fixture commit or the service raised
        # before the happy path's own `close()` ran.
        await session_a.close()
        if scenario is not None:
            await _cleanup_scenario(engine, scenario)


# ---------------------------------------------------------------------------
# 3. ignore_unmatched_entry — header ignored COMMITEADO, sin link
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_ignore_unmatched_entry_commits_ignored_header_without_link(
    engine: AsyncEngine,
) -> None:
    """Flujo 3: ignorar una entrada pendiente la retira (``ignored``) SIN
    crear ningún link — el commit directo de ``ignore_unmatched_entry``
    (service.py, sin try/except) debe ser durable en una sesión B."""

    session_a = _fresh_session(engine)
    scenario: _Scenario | None = None

    try:
        scenario = await _seed_committed_glpi_scenario(session_a)
        header = GlpiUnmatchedAssignee(
            organization_id=scenario.organization_id,
            connector_id=scenario.connector_id,
            glpi_user_id="901",
            glpi_username="Persona Ignorada",
            status=UnmatchedStatus.pending,
        )
        session_a.add(header)
        await session_a.commit()
        header_id = header.id

        membership = await _get_membership(
            session_a, scenario.organization_id, scenario.owner_id
        )
        service = GlpiSyncService(session_a)
        await service.ignore_unmatched_entry(
            scenario.organization_id, header_id, membership
        )
        await session_a.close()

        session_b = _fresh_session(engine)
        try:
            persisted_header = (
                await session_b.execute(
                    select(GlpiUnmatchedAssignee).where(
                        GlpiUnmatchedAssignee.id == header_id
                    )
                )
            ).scalar_one()
            assert persisted_header.status == UnmatchedStatus.ignored
            assert persisted_header.resolved_user_id is None
            assert persisted_header.resolved_at is None

            links = (
                (
                    await session_b.execute(
                        select(GlpiUserLink).where(
                            GlpiUserLink.connector_id == scenario.connector_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert links == []
        finally:
            await session_b.close()
    finally:
        # Idempotent double-close: guarantees the NullPool connection goes
        # back even if the seed, a fixture commit or the service raised
        # before the happy path's own `close()` ran.
        await session_a.close()
        if scenario is not None:
            await _cleanup_scenario(engine, scenario)


# ---------------------------------------------------------------------------
# 4. revoke_link — soft-delete COMMITEADO
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_revoke_link_commits_soft_delete_across_independent_sessions(
    engine: AsyncEngine,
) -> None:
    """Flujo 4: revocar un link activo lo deja ``is_active=False`` con
    ``deleted_at`` no nulo — verificado en sesión B consultando por ``id``
    SIN filtro ``is_active`` (la fila sigue existiendo, soft-delete)."""

    session_a = _fresh_session(engine)
    scenario: _Scenario | None = None

    try:
        scenario = await _seed_committed_glpi_scenario(session_a)
        link = GlpiUserLink(
            organization_id=scenario.organization_id,
            connector_id=scenario.connector_id,
            glpi_user_id="66",
            user_id=scenario.owner_id,
            match_method=MatchMethod.email,
        )
        session_a.add(link)
        await session_a.commit()
        link_id = link.id

        membership = await _get_membership(
            session_a, scenario.organization_id, scenario.owner_id
        )
        service = GlpiSyncService(session_a)
        await service.revoke_link(scenario.organization_id, link_id, membership)
        await session_a.close()

        session_b = _fresh_session(engine)
        try:
            persisted_link = (
                await session_b.execute(
                    select(GlpiUserLink).where(GlpiUserLink.id == link_id)
                )
            ).scalar_one()
            assert persisted_link.is_active is False
            assert persisted_link.deleted_at is not None
        finally:
            await session_b.close()
    finally:
        # Idempotent double-close: guarantees the NullPool connection goes
        # back even if the seed, a fixture commit or the service raised
        # before the happy path's own `close()` ran.
        await session_a.close()
        if scenario is not None:
            await _cleanup_scenario(engine, scenario)


# ---------------------------------------------------------------------------
# 5. register_api_token_credentials — cuenta + credenciales cifradas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_register_api_token_credentials_commits_account_and_encrypted_secret(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flujo 5: el registro directo de credenciales ``api_token`` persiste
    (commit REAL) el ``ConnectedAccount`` + ``ConnectionCredentials`` — el
    secreto NUNCA queda en claro en ``access_token_enc`` y descifra al JSON
    original con el MISMO helper de crypto que usa el service."""

    session_a = _fresh_session(engine)
    scenario: _Scenario | None = None
    _install_api_token_stub(monkeypatch)
    raw = {"app_token": "APP-1", "user_token": "USER-1"}

    try:
        scenario = await _seed_committed_glpi_scenario(
            session_a, provider=_FAKE_PROVIDER, with_account=False
        )
        membership = await _get_membership(
            session_a, scenario.organization_id, scenario.owner_id
        )
        service = ConnectorService(session_a)
        account_read = await service.register_api_token_credentials(
            scenario.organization_id, scenario.connector_id, raw, membership
        )
        await session_a.close()

        assert account_read.external_account_id == "svc-red-persistencia"

        session_b = _fresh_session(engine)
        try:
            account = (
                await session_b.execute(
                    select(ConnectedAccount).where(
                        ConnectedAccount.connector_id == scenario.connector_id
                    )
                )
            ).scalar_one()
            assert account.external_account_id == "svc-red-persistencia"
            assert account.user_id == scenario.owner_id

            credentials = (
                await session_b.execute(
                    select(ConnectionCredentials).where(
                        ConnectionCredentials.connected_account_id == account.id
                    )
                )
            ).scalar_one()
            assert "APP-1" not in credentials.access_token_enc
            assert "USER-1" not in credentials.access_token_enc
            assert json.loads(crypto.decrypt(credentials.access_token_enc)) == raw
            assert credentials.refresh_token_enc is None
        finally:
            await session_b.close()
    finally:
        # Idempotent double-close: guarantees the NullPool connection goes
        # back even if the seed, a fixture commit or the service raised
        # before the happy path's own `close()` ran.
        await session_a.close()
        if scenario is not None:
            await _cleanup_scenario(engine, scenario)
