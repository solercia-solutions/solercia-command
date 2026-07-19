"""RED tests for the glpi_sync REST surface (change 17-adapter-glpi,
specs/user-homologation/spec.md, UH-R3/UH-R4/UH-R5/UH-R6/UH-R7).

Registers a MINIMAL stub adapter under provider "glpi" for the duration of
each test (``monkeypatch.setitem`` on the registry's internal dict, same
convention ``patched_redis`` uses for ``app.shared.redis.get_redis_client``)
so ``run_sync`` is exercised end-to-end WITHOUT any real GLPI HTTP call —
the wire protocol itself is already proven by ``test_adapter_glpi.py``
(Lote 4-6); this suite's concern is the sync ORCHESTRATION + queue + REST.
"""

import json
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import crypto
from app.integrations.dtos import ExternalPerson, Ticket
from app.integrations.ports import Capability, CredentialKind
from app.modules.connectors.models import ConnectedAccount, ConnectionCredentials, Connector
from app.modules.glpi_sync.models import GlpiUnmatchedAssignee, GlpiUserLink
from app.shared.enums import AccountStatus, ConnectorStatus, MemberRole
from tests.conftest import TwoOrgs, skip_no_db

_ALLOWED_BASE_URL = "http://localhost:8080/glpi/apirest.php"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


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
        self.calls = 0

    async def list_tickets(self, ctx: object, *, since: object = None, limit: int = 50):
        self.calls += 1
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


def _install_glpi_stub(monkeypatch: pytest.MonkeyPatch, tickets: list[Ticket]) -> _StubGlpiAdapter:
    from app.integrations import registry as integrations_registry

    stub = _StubGlpiAdapter(tickets)
    monkeypatch.setitem(integrations_registry._ADAPTERS, "glpi", stub)
    return stub


async def _create_glpi_connector(
    session: AsyncSession,
    organization_id: uuid.UUID,
    owner_id: uuid.UUID,
    *,
    app_token: str = "app-token-x",
    user_token: str = "user-token-y",
) -> Connector:
    connector = Connector(
        organization_id=organization_id,
        provider="glpi",
        credential_kind=CredentialKind.api_token,
        status=ConnectorStatus.active,
        settings={"base_url": _ALLOWED_BASE_URL, "document_field": "registration_number"},
    )
    session.add(connector)
    await session.flush()

    account = ConnectedAccount(
        organization_id=organization_id,
        connector_id=connector.id,
        user_id=owner_id,
        external_account_id="glpi-service-account",
        status=AccountStatus.active,
    )
    session.add(account)
    await session.flush()

    credentials = ConnectionCredentials(
        organization_id=organization_id,
        connected_account_id=account.id,
        access_token_enc=crypto.encrypt(
            json.dumps({"app_token": app_token, "user_token": user_token})
        ),
        token_type="glpi",
    )
    session.add(credentials)
    await session.flush()
    return connector


# ---------------------------------------------------------------------------
# UH-R6 — Sincronización manual on-demand + UH-R3/UH-R4 (link/cola)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_run_creates_link_for_match_and_queue_entry_for_unmatched(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, monkeypatch
) -> None:
    """Scenario: Admin dispara la sincronización — determinísticos se
    homologan, el resto puebla la cola."""

    connector = await _create_glpi_connector(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    matched_person = _person(
        "55", display_name="Owner ORGA", email=two_orgs.a.user.email
    )
    unmatched_person = _person("77", display_name="Nadie Desconocido")
    tickets = [
        _ticket("301", assignees=(matched_person,)),
        _ticket("302", assignees=(unmatched_person,)),
    ]
    _install_glpi_stub(monkeypatch, tickets)

    response = await client.post(
        "/glpi-sync/run",
        json={"connector_id": str(connector.id)},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["tickets_processed"] == 2
    assert body["links_created"] == 1
    assert body["queue_updated"] == 1

    link_result = await session.execute(
        select(GlpiUserLink).where(GlpiUserLink.glpi_user_id == "55")
    )
    link = link_result.scalar_one()
    assert link.user_id == two_orgs.a.user.id
    assert link.match_method.value == "email"

    header_result = await session.execute(
        select(GlpiUnmatchedAssignee).where(GlpiUnmatchedAssignee.glpi_user_id == "77")
    )
    header = header_result.scalar_one()
    assert header.status.value == "pending"
    assert len(header.cases) == 1
    assert header.cases[0].glpi_ticket_id == "302"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_second_case_of_same_unmatched_person_appends_without_duplicating_header(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, monkeypatch
) -> None:
    """Scenario: Segundo caso sin homologar de la misma persona."""

    connector = await _create_glpi_connector(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    same_unmatched_person = _person("88", display_name="Persona Repetida")
    tickets = [
        _ticket("401", assignees=(same_unmatched_person,)),
        _ticket("402", assignees=(same_unmatched_person,)),
    ]
    _install_glpi_stub(monkeypatch, tickets)

    response = await client.post(
        "/glpi-sync/run",
        json={"connector_id": str(connector.id)},
        headers=_auth(two_orgs.a.token),
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["queue_updated"] == 2

    header_result = await session.execute(
        select(GlpiUnmatchedAssignee).where(GlpiUnmatchedAssignee.glpi_user_id == "88")
    )
    headers = header_result.scalars().all()
    assert len(headers) == 1
    assert {case.glpi_ticket_id for case in headers[0].cases} == {"401", "402"}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_run_on_foreign_or_nonexistent_connector_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, monkeypatch
) -> None:
    """Scenario: Sincronización sobre conector ajeno."""

    connector = await _create_glpi_connector(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    _install_glpi_stub(monkeypatch, [])

    foreign_response = await client.post(
        "/glpi-sync/run",
        json={"connector_id": str(connector.id)},
        headers=_auth(two_orgs.b.token),
    )
    assert foreign_response.status_code == 404

    nonexistent_response = await client.post(
        "/glpi-sync/run",
        json={"connector_id": str(uuid.uuid4())},
        headers=_auth(two_orgs.a.token),
    )
    assert nonexistent_response.status_code == 404


# ---------------------------------------------------------------------------
# UH-R5 — Resolución manual de la cola
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_resolve_creates_link_and_removes_entry_from_active_queue(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, monkeypatch
) -> None:
    """Scenario: Resolver una entrada crea el mapeo y drena la cola."""

    connector = await _create_glpi_connector(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    unmatched_person = _person("99", display_name="Otra Persona")
    _install_glpi_stub(monkeypatch, [_ticket("501", assignees=(unmatched_person,))])

    await client.post(
        "/glpi-sync/run",
        json={"connector_id": str(connector.id)},
        headers=_auth(two_orgs.a.token),
    )
    queue_response = await client.get("/glpi-sync/unmatched", headers=_auth(two_orgs.a.token))
    header_id = queue_response.json()["data"][0]["id"]

    resolve_response = await client.post(
        f"/glpi-sync/unmatched/{header_id}/resolve",
        json={"user_id": str(two_orgs.a.user.id)},
        headers=_auth(two_orgs.a.token),
    )

    assert resolve_response.status_code == 201, resolve_response.text
    assert resolve_response.json()["data"]["match_method"] == "manual"

    active_queue = await client.get("/glpi-sync/unmatched", headers=_auth(two_orgs.a.token))
    assert active_queue.json()["meta"]["total"] == 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_future_sync_of_resolved_person_resolves_direct_via_link(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, monkeypatch
) -> None:
    """Scenario: Sincronización futura homologa directo tras resolver."""

    connector = await _create_glpi_connector(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    unmatched_person = _person("111", display_name="Persona A Resolver")
    _install_glpi_stub(monkeypatch, [_ticket("601", assignees=(unmatched_person,))])
    await client.post(
        "/glpi-sync/run",
        json={"connector_id": str(connector.id)},
        headers=_auth(two_orgs.a.token),
    )
    header_id = (
        (await client.get("/glpi-sync/unmatched", headers=_auth(two_orgs.a.token)))
        .json()["data"][0]["id"]
    )
    await client.post(
        f"/glpi-sync/unmatched/{header_id}/resolve",
        json={"user_id": str(two_orgs.a.user.id)},
        headers=_auth(two_orgs.a.token),
    )

    # A LATER sync brings a NEW case for the SAME glpi_user_id.
    _install_glpi_stub(monkeypatch, [_ticket("602", assignees=(unmatched_person,))])
    second_run = await client.post(
        "/glpi-sync/run",
        json={"connector_id": str(connector.id)},
        headers=_auth(two_orgs.a.token),
    )

    assert second_run.json()["data"]["links_created"] == 0
    assert second_run.json()["data"]["queue_updated"] == 0
    queue_after = await client.get("/glpi-sync/unmatched", headers=_auth(two_orgs.a.token))
    assert queue_after.json()["meta"]["total"] == 0


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_ignore_removes_entry_without_creating_link(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, monkeypatch
) -> None:
    """Scenario: Ignorar una entrada sin crear mapeo."""

    connector = await _create_glpi_connector(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    unmatched_person = _person("122", display_name="Ignorada Persona")
    _install_glpi_stub(monkeypatch, [_ticket("701", assignees=(unmatched_person,))])
    await client.post(
        "/glpi-sync/run",
        json={"connector_id": str(connector.id)},
        headers=_auth(two_orgs.a.token),
    )
    header_id = (
        (await client.get("/glpi-sync/unmatched", headers=_auth(two_orgs.a.token)))
        .json()["data"][0]["id"]
    )

    ignore_response = await client.post(
        f"/glpi-sync/unmatched/{header_id}/ignore", headers=_auth(two_orgs.a.token)
    )

    assert ignore_response.status_code == 200
    active_queue = await client.get("/glpi-sync/unmatched", headers=_auth(two_orgs.a.token))
    assert active_queue.json()["meta"]["total"] == 0
    link_result = await session.execute(
        select(GlpiUserLink).where(GlpiUserLink.glpi_user_id == "122")
    )
    assert link_result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# UH-R3 — Mapeos confirmados: listar y revocar
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_links_returns_org_scoped_links(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, monkeypatch
) -> None:
    connector = await _create_glpi_connector(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    matched_person = _person("55", display_name="Owner ORGA", email=two_orgs.a.user.email)
    _install_glpi_stub(monkeypatch, [_ticket("801", assignees=(matched_person,))])
    await client.post(
        "/glpi-sync/run",
        json={"connector_id": str(connector.id)},
        headers=_auth(two_orgs.a.token),
    )

    response = await client.get("/glpi-sync/links", headers=_auth(two_orgs.a.token))

    assert response.status_code == 200
    assert response.json()["meta"]["total"] == 1
    assert response.json()["data"][0]["glpi_user_id"] == "55"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_link_revokes_it_and_next_sync_recascades(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, monkeypatch
) -> None:
    """Scenario: Admin revoca un mapeo."""

    connector = await _create_glpi_connector(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    matched_person = _person("55", display_name="Owner ORGA", email=two_orgs.a.user.email)
    _install_glpi_stub(monkeypatch, [_ticket("901", assignees=(matched_person,))])
    await client.post(
        "/glpi-sync/run",
        json={"connector_id": str(connector.id)},
        headers=_auth(two_orgs.a.token),
    )
    link_id = (
        (await client.get("/glpi-sync/links", headers=_auth(two_orgs.a.token)))
        .json()["data"][0]["id"]
    )

    delete_response = await client.delete(
        f"/glpi-sync/links/{link_id}", headers=_auth(two_orgs.a.token)
    )
    assert delete_response.status_code == 204

    links_after = await client.get("/glpi-sync/links", headers=_auth(two_orgs.a.token))
    assert links_after.json()["meta"]["total"] == 0

    # A subsequent sync re-runs the cascade for this person (auto-matches
    # again via email since nothing else changed) instead of silently
    # staying unlinked.
    _install_glpi_stub(monkeypatch, [_ticket("902", assignees=(matched_person,))])
    rerun = await client.post(
        "/glpi-sync/run",
        json={"connector_id": str(connector.id)},
        headers=_auth(two_orgs.a.token),
    )
    assert rerun.json()["data"]["links_created"] == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_nonexistent_or_foreign_link_returns_404(
    client: AsyncClient, two_orgs: TwoOrgs
) -> None:
    response = await client.delete(
        f"/glpi-sync/links/{uuid.uuid4()}", headers=_auth(two_orgs.a.token)
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# RBAC + UH-R7 — Aislamiento multi-tenant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_and_viewer_get_403_on_every_endpoint(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member, monkeypatch
) -> None:
    connector = await _create_glpi_connector(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    _install_glpi_stub(monkeypatch, [])
    _, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)
    _, viewer_token = await make_member(session, two_orgs.a.organization, MemberRole.viewer)

    for token in (member_token, viewer_token):
        assert (
            await client.post(
                "/glpi-sync/run",
                json={"connector_id": str(connector.id)},
                headers=_auth(token),
            )
        ).status_code == 403
        assert (
            await client.get("/glpi-sync/unmatched", headers=_auth(token))
        ).status_code == 403
        assert (
            await client.post(
                f"/glpi-sync/unmatched/{uuid.uuid4()}/resolve",
                json={"user_id": str(uuid.uuid4())},
                headers=_auth(token),
            )
        ).status_code == 403
        assert (
            await client.post(
                f"/glpi-sync/unmatched/{uuid.uuid4()}/ignore", headers=_auth(token)
            )
        ).status_code == 403
        assert (
            await client.get("/glpi-sync/links", headers=_auth(token))
        ).status_code == 403
        assert (
            await client.delete(
                f"/glpi-sync/links/{uuid.uuid4()}", headers=_auth(token)
            )
        ).status_code == 403


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_org_b_cannot_see_or_resolve_org_a_queue_or_links(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, monkeypatch
) -> None:
    """Scenario: Cola de otra organización no es accesible."""

    connector = await _create_glpi_connector(
        session, two_orgs.a.organization.id, two_orgs.a.user.id
    )
    matched_person = _person("55", display_name="Owner ORGA", email=two_orgs.a.user.email)
    unmatched_person = _person("66", display_name="Sin Match ORGA")
    _install_glpi_stub(
        monkeypatch,
        [
            _ticket("1001", assignees=(matched_person,)),
            _ticket("1002", assignees=(unmatched_person,)),
        ],
    )
    await client.post(
        "/glpi-sync/run",
        json={"connector_id": str(connector.id)},
        headers=_auth(two_orgs.a.token),
    )

    # Org B's own queue/links stay empty — org A's rows never leak across.
    assert (
        await client.get("/glpi-sync/unmatched", headers=_auth(two_orgs.b.token))
    ).json()["meta"]["total"] == 0
    assert (
        await client.get("/glpi-sync/links", headers=_auth(two_orgs.b.token))
    ).json()["meta"]["total"] == 0

    header_id = (
        (await client.get("/glpi-sync/unmatched", headers=_auth(two_orgs.a.token)))
        .json()["data"][0]["id"]
    )
    link_id = (
        (await client.get("/glpi-sync/links", headers=_auth(two_orgs.a.token)))
        .json()["data"][0]["id"]
    )

    assert (
        await client.post(
            f"/glpi-sync/unmatched/{header_id}/resolve",
            json={"user_id": str(two_orgs.b.user.id)},
            headers=_auth(two_orgs.b.token),
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/glpi-sync/unmatched/{header_id}/ignore", headers=_auth(two_orgs.b.token)
        )
    ).status_code == 404
    assert (
        await client.delete(f"/glpi-sync/links/{link_id}", headers=_auth(two_orgs.b.token))
    ).status_code == 404
