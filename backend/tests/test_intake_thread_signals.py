"""C03 — thread signals on ingested mail (``conversation_id``,
``internet_message_id``, ``direction``) and the refresh of already-stored
items, so a re-ingested window backfills them without touching triage state.

Also covers the privacy narrowing of ``GET /intake/items``: the full mail
body (``raw_payload.body_text``) is visible only to admin/manager.
"""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.db_init  # noqa: F401  (registers every mapper before building rows)
from app.integrations.dtos import MailMessage
from app.integrations.ports import Capability, CredentialKind
from app.modules.connectors.models import Connector
from app.modules.intake.models import IntakeItem
from app.modules.intake.repository import IntakeItemRepository
from app.modules.intake.service import _dto_to_item
from app.shared.enums import ConnectorStatus, IntakeItemStatus, IntakeItemType, MemberRole
from tests.conftest import TwoOrgs, skip_no_db

_WHEN = datetime(2026, 9, 1, 13, 0, tzinfo=UTC)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _message(**overrides: object) -> MailMessage:
    values: dict[str, object] = {
        "external_id": "msg-1",
        "subject": "Solicitud de soporte",
        "sender": "persona@entidad.example.gov.co",
        "recipients": ("mesa@entidad.example.gov.co",),
        "received_at": _WHEN,
        "snippet": "Buenas tardes",
        "body_text": "Buenas tardes, cuerpo completo del correo.",
    }
    values.update(overrides)
    return MailMessage(**values)  # type: ignore[arg-type]


def _connector(organization_id: uuid.UUID) -> Connector:
    return Connector(
        id=uuid.uuid4(),
        organization_id=organization_id,
        provider="solercia_connect",
        credential_kind=CredentialKind.oauth,
        status=ConnectorStatus.active,
    )


def _item(message: MailMessage, organization_id: uuid.UUID, connector: Connector) -> IntakeItem:
    return _dto_to_item(
        message,
        capability=Capability.mail,
        organization_id=organization_id,
        connector=connector,
        connected_account_id=None,
        source_provider=connector.provider,
    )


async def _seed_connector(session: AsyncSession, organization_id: uuid.UUID) -> Connector:
    connector = _connector(organization_id)
    session.add(connector)
    await session.flush()
    return connector


def test_mail_dto_signals_land_in_their_columns_and_raw_payload() -> None:
    organization_id = uuid.uuid4()
    message = _message(
        conversation_id="CONV-1",
        internet_message_id="<abc@entidad>",
        direction="outbound",
        cc=("copia@entidad",),
        has_attachments=True,
    )

    item = _item(message, organization_id, _connector(organization_id))

    assert item.conversation_id == "CONV-1"
    assert item.internet_message_id == "<abc@entidad>"
    assert item.direction == "outbound"
    assert item.raw_payload["cc"] == ["copia@entidad"]
    assert item.raw_payload["has_attachments"] is True


def test_non_mail_items_carry_no_thread_signals() -> None:
    from app.integrations.dtos import CalendarEvent

    organization_id = uuid.uuid4()
    event = CalendarEvent(
        external_id="evt-1",
        title="Comité",
        starts_at=_WHEN,
        ends_at=_WHEN,
        organizer="org@entidad",
        attendees=(),
        location=None,
    )

    item = _dto_to_item(
        event,
        capability=Capability.calendar,
        organization_id=organization_id,
        connector=_connector(organization_id),
        connected_account_id=None,
        source_provider="solercia_connect",
    )

    assert item.conversation_id is None
    assert item.direction is None
    assert item.internet_message_id is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reingest_refreshes_signals_without_touching_triage_state(
    session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    organization_id = two_orgs.a.organization.id
    connector = await _seed_connector(session, organization_id)
    repository = IntakeItemRepository(session)

    legacy, created = await repository.upsert_item(_item(_message(), organization_id, connector))
    assert created is True
    assert legacy.conversation_id is None
    legacy.status = IntakeItemStatus.ignored
    legacy.classified_at = _WHEN
    await session.flush()

    refreshed, created = await repository.upsert_item(
        _item(
            _message(
                conversation_id="CONV-9",
                internet_message_id="<m9@entidad>",
                direction="inbound",
                cc=("copia@entidad",),
            ),
            organization_id,
            connector,
        )
    )

    assert created is False
    assert refreshed.id == legacy.id
    assert refreshed.conversation_id == "CONV-9"
    assert refreshed.internet_message_id == "<m9@entidad>"
    assert refreshed.direction == "inbound"
    assert refreshed.raw_payload["conversation_id"] == "CONV-9"
    assert refreshed.raw_payload["cc"] == ["copia@entidad"]
    # Triage state and classification are never rewritten by a re-ingest.
    assert refreshed.status == IntakeItemStatus.ignored
    assert refreshed.classified_at == _WHEN
    assert refreshed.created_task_id is None


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_reingest_without_signals_never_erases_known_ones(
    session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    organization_id = two_orgs.a.organization.id
    connector = await _seed_connector(session, organization_id)
    repository = IntakeItemRepository(session)

    await repository.upsert_item(
        _item(
            _message(conversation_id="CONV-1", direction="outbound", internet_message_id="<a@b>"),
            organization_id,
            connector,
        )
    )
    kept, created = await repository.upsert_item(_item(_message(), organization_id, connector))

    assert created is False
    assert kept.conversation_id == "CONV-1"
    assert kept.direction == "outbound"
    assert kept.internet_message_id == "<a@b>"
    assert kept.raw_payload["conversation_id"] == "CONV-1"


async def _seed_stored_mail(session: AsyncSession, organization_id: uuid.UUID) -> IntakeItem:
    connector = await _seed_connector(session, organization_id)
    item, _created = await IntakeItemRepository(session).upsert_item(
        _item(_message(conversation_id="CONV-API", direction="inbound"), organization_id, connector)
    )
    return item


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_sees_thread_signals_but_not_the_full_body(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    item = await _seed_stored_mail(session, two_orgs.a.organization.id)
    _member, member_token = await make_member(session, two_orgs.a.organization, MemberRole.member)

    listed = await client.get("/intake/items", headers=_auth(member_token))
    detail = await client.get(f"/intake/items/{item.id}", headers=_auth(member_token))

    assert listed.status_code == 200, listed.text
    (row,) = listed.json()["data"]
    assert row["conversation_id"] == "CONV-API"
    assert row["direction"] == "inbound"
    assert "body_text" not in row["raw_payload"]
    assert row["snippet"] == "Buenas tardes"
    assert detail.status_code == 200, detail.text
    assert "body_text" not in detail.json()["data"]["raw_payload"]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_admin_and_manager_keep_the_full_body(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    item = await _seed_stored_mail(session, two_orgs.a.organization.id)
    _manager, manager_token = await make_member(
        session, two_orgs.a.organization, MemberRole.manager
    )

    admin_list = await client.get("/intake/items", headers=_auth(two_orgs.a.token))
    manager_detail = await client.get(f"/intake/items/{item.id}", headers=_auth(manager_token))

    (row,) = admin_list.json()["data"]
    assert row["raw_payload"]["body_text"] == "Buenas tardes, cuerpo completo del correo."
    assert manager_detail.status_code == 200, manager_detail.text
    assert manager_detail.json()["data"]["raw_payload"]["body_text"].startswith("Buenas")


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_stored_payload_keeps_item_type_email(
    session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    item = await _seed_stored_mail(session, two_orgs.a.organization.id)

    assert item.item_type == IntakeItemType.email
    assert item.raw_payload["direction"] == "inbound"
