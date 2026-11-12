"""RED tests for ``IntakeService.pull`` idempotency and connector-without-
account-mapping (change 22-intake-classifier, tasks.md T2.6).

The idempotency scenarios use TWO INDEPENDENT ``AsyncSession`` instances
bound to the shared ``engine`` fixture (never the SAVEPOINT-scoped
``session``/``client`` combo) — this is the ONLY way to prove
``IntakeService.pull``'s explicit ``db.commit()`` calls survive as REAL,
durable writes instead of merely looking committed because they share one
uncommitted outer SAVEPOINT transaction with the assertions (design.md
lección savepoint, ratified for change 22's write flows: ingesta idempotente,
conversión a tarea, sink).
"""

import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.integrations import crypto
from app.integrations.dtos import ExternalPerson, Ticket
from app.integrations.ports import Capability, CredentialKind
from app.modules.connectors.models import ConnectedAccount, ConnectionCredentials, Connector
from app.modules.intake.models import IntakeItem
from app.modules.intake.service import IntakeService
from app.modules.organizations.models import Organization, OrganizationMember
from app.modules.users.models import User
from app.shared.enums import AccountStatus, ConnectorStatus, IntakeRunStatus, MemberRole
from app.shared.security import hash_password
from tests.conftest import skip_no_db


async def _seed_committed_org_with_fake_connector(
    db: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Persist (REAL commit) an organization + owner + a `fake`-provider
    connector/account/credentials. Returns ``(organization_id, connector_id)``."""

    organization = Organization(
        name="Intake Idempotency Org", slug=f"intake-idem-{uuid.uuid4().hex[:12]}"
    )
    db.add(organization)
    await db.flush()

    owner = User(
        email=f"intake-owner-{uuid.uuid4().hex[:12]}@example.com",
        primer_nombre="Intake",
        primer_apellido="Owner",
        hashed_password=hash_password("Test123*"),
    )
    db.add(owner)
    await db.flush()

    db.add(
        OrganizationMember(
            organization_id=organization.id, user_id=owner.id, role=MemberRole.admin
        )
    )
    await db.flush()

    connector = Connector(
        organization_id=organization.id,
        provider="fake",
        credential_kind=CredentialKind.oauth,
        status=ConnectorStatus.active,
    )
    db.add(connector)
    await db.flush()

    account = ConnectedAccount(
        organization_id=organization.id,
        connector_id=connector.id,
        user_id=owner.id,
        external_account_id="fake-account-idempotency",
        status=AccountStatus.active,
    )
    db.add(account)
    await db.flush()

    credentials = ConnectionCredentials(
        organization_id=organization.id,
        connected_account_id=account.id,
        access_token_enc=crypto.encrypt("fake-access-token"),
        refresh_token_enc=crypto.encrypt("fake-refresh-token"),
        token_type="Bearer",
        scopes=["mail"],
    )
    db.add(credentials)
    await db.commit()

    return organization.id, connector.id


async def _cleanup_org(db: AsyncSession, organization_id: uuid.UUID) -> None:
    await db.execute(delete(Organization).where(Organization.id == organization_id))
    await db.commit()


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_repull_does_not_duplicate_items_across_two_independent_sessions(
    engine: AsyncEngine,
) -> None:
    """T2.6: re-pull del mismo insumo aumenta `items_duplicated`, nunca crea
    una segunda fila — verificado con sesiones REALMENTE independientes."""

    session_a = AsyncSession(engine, expire_on_commit=False)
    organization_id, _connector_id = await _seed_committed_org_with_fake_connector(session_a)

    try:
        service_a = IntakeService(session_a)
        first_runs = await service_a.pull(organization_id)
        await session_a.close()

        # Independent session B: proves the FIRST pull's writes are REALLY
        # committed (not merely visible within session_a's own transaction).
        session_b = AsyncSession(engine, expire_on_commit=False)
        try:
            result = await session_b.execute(
                select(IntakeItem).where(IntakeItem.organization_id == organization_id)
            )
            items_after_first_pull = result.scalars().all()
            assert len(items_after_first_pull) == 5  # fake adapter: 5 capabilities

            assert len(first_runs) == 1
            assert first_runs[0].status == IntakeRunStatus.completed
            assert first_runs[0].items_new == 5
            assert first_runs[0].items_duplicated == 0
        finally:
            await session_b.close()

        # Independent session C: repeat the pull from a THIRD fresh session.
        session_c = AsyncSession(engine, expire_on_commit=False)
        try:
            service_c = IntakeService(session_c)
            second_runs = await service_c.pull(organization_id)
        finally:
            await session_c.close()

        # Independent session D: prove NO duplicate rows were created and the
        # second IntakeRun genuinely recorded every item as a duplicate.
        session_d = AsyncSession(engine, expire_on_commit=False)
        try:
            result = await session_d.execute(
                select(IntakeItem).where(IntakeItem.organization_id == organization_id)
            )
            items_after_second_pull = result.scalars().all()
            assert len(items_after_second_pull) == 5  # still 5 — no duplicate rows

            assert len(second_runs) == 1
            assert second_runs[0].items_new == 0
            assert second_runs[0].items_duplicated == 5
        finally:
            await session_d.close()
    finally:
        # ALWAYS clean up, even if an assertion above failed mid-test — a
        # fresh session guarantees the delete never inherits a broken
        # transaction state from an earlier DB-level error.
        cleanup_session = AsyncSession(engine, expire_on_commit=False)
        try:
            await _cleanup_org(cleanup_session, organization_id)
        finally:
            await cleanup_session.close()


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_repull_of_already_converted_item_does_not_reset_its_status(
    engine: AsyncEngine,
) -> None:
    """T2.6: re-pull de un ítem YA `converted` no lo reclasifica ni lo
    revierte a `pending` — la idempotencia respeta el estado ya asignado."""

    session_a = AsyncSession(engine, expire_on_commit=False)
    organization_id, _connector_id = await _seed_committed_org_with_fake_connector(session_a)

    try:
        service_a = IntakeService(session_a)
        await service_a.pull(organization_id)

        # Manually mark one item as already converted (simulates Fase 4's
        # classify_and_convert, not yet wired in this Lote).
        result = await session_a.execute(
            select(IntakeItem).where(IntakeItem.organization_id == organization_id).limit(1)
        )
        converted_item = result.scalars().first()
        assert converted_item is not None
        converted_item.status = "converted"
        await session_a.commit()
        converted_external_id = converted_item.external_id
        await session_a.close()

        session_b = AsyncSession(engine, expire_on_commit=False)
        try:
            service_b = IntakeService(session_b)
            await service_b.pull(organization_id)
        finally:
            await session_b.close()

        session_c = AsyncSession(engine, expire_on_commit=False)
        try:
            result = await session_c.execute(
                select(IntakeItem).where(
                    IntakeItem.organization_id == organization_id,
                    IntakeItem.external_id == converted_external_id,
                )
            )
            rows = result.scalars().all()
            assert len(rows) == 1  # still exactly one row for this external_id
            assert rows[0].status == "converted"  # NOT reset to pending
        finally:
            await session_c.close()
    finally:
        cleanup_session = AsyncSession(engine, expire_on_commit=False)
        try:
            await _cleanup_org(cleanup_session, organization_id)
        finally:
            await cleanup_session.close()


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_pull_ingests_ticket_connector_without_individual_account(
    session: AsyncSession, tenant: Organization, user, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T2.6: un conector `api_token` (ej. GLPI) se ingesta sin error y el
    `IntakeItem` resultante queda con `connected_account_id=None` — no es
    una cuenta personal, es una credencial de servicio."""

    from app.integrations import registry as integrations_registry

    class _StubTicketPort:
        async def list_tickets(self, ctx: object, *, since: object = None, limit: int = 50):
            return [
                Ticket(
                    external_id="stub-ticket-1",
                    key="STUB-1",
                    summary="Caso de prueba",
                    status="1",
                    priority=None,
                    requester="solicitante@stub.test",
                    created_at=datetime.now(UTC),
                    assignees=(
                        ExternalPerson(
                            external_id="p1", display_name=None, email=None, document=None
                        ),
                    ),
                )
            ][:limit]

    class _StubTicketAdapter:
        provider = "stub-ticket"
        capabilities = frozenset({Capability.tickets})
        credential_kind = CredentialKind.api_token
        credential_kinds = frozenset({CredentialKind.api_token})
        oauth = None
        api_token = None

        def __init__(self) -> None:
            self._port = _StubTicketPort()

        def port_for(self, capability: Capability) -> object | None:
            return self._port if capability == Capability.tickets else None

    monkeypatch.setitem(
        integrations_registry._ADAPTERS, "stub-ticket", _StubTicketAdapter()
    )

    owner, _token = user
    connector = Connector(
        organization_id=tenant.id,
        provider="stub-ticket",
        credential_kind=CredentialKind.api_token,
        status=ConnectorStatus.active,
    )
    session.add(connector)
    await session.flush()

    account = ConnectedAccount(
        organization_id=tenant.id,
        connector_id=connector.id,
        user_id=owner.id,
        external_account_id="stub-ticket-service-account",
        status=AccountStatus.active,
    )
    session.add(account)
    await session.flush()

    credentials = ConnectionCredentials(
        organization_id=tenant.id,
        connected_account_id=account.id,
        access_token_enc=crypto.encrypt(json.dumps({"api_token": "x"})),
        token_type="stub-ticket",
    )
    session.add(credentials)
    await session.flush()

    service = IntakeService(session)
    runs = await service.pull(tenant.id)

    assert len(runs) == 1
    assert runs[0].status == IntakeRunStatus.completed
    assert runs[0].items_new == 1

    result = await session.execute(
        select(IntakeItem).where(
            IntakeItem.organization_id == tenant.id, IntakeItem.external_id == "stub-ticket-1"
        )
    )
    item = result.scalar_one()
    assert item.item_type == "ticket"
    assert item.connected_account_id is None
