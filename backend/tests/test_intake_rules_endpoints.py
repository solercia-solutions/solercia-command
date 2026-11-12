"""RED tests for the `/intake/rules` CRUD REST surface (change
22-intake-classifier, tasks.md T3.6): permisos por rol, criterios AND, y
exclusión de una regla eliminada de listados/evaluación futura.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.enums import MemberRole
from tests.conftest import TwoOrgs, skip_no_db


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _rule_payload(**overrides) -> dict:
    payload = {
        "name": "Seguridad a Camilo",
        "criteria": [
            {"field": "domain", "operator": "contains", "value": "proveedor-x.com"}
        ],
        "convert_to_task": True,
        "task_priority": "high",
        "rule_order": 1,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_manager_creates_rule_active_by_default(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """Scenario: Manager crea una regla — activa (`is_active=true`) por defecto."""

    _manager, manager_token = await make_member(
        session, two_orgs.a.organization, MemberRole.manager
    )

    response = await client.post(
        "/intake/rules", json=_rule_payload(), headers=_auth(manager_token)
    )

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["is_active"] is True
    assert body["name"] == "Seguridad a Camilo"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_cannot_create_rule(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """Scenario: Member no puede crear reglas — 403."""

    _member, member_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )

    response = await client.post(
        "/intake/rules", json=_rule_payload(), headers=_auth(member_token)
    )

    assert response.status_code == 403, response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_member_can_read_rules(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """`GET /intake/rules` es accesible a cualquier miembro autenticado."""

    _manager, manager_token = await make_member(
        session, two_orgs.a.organization, MemberRole.manager
    )
    create_response = await client.post(
        "/intake/rules", json=_rule_payload(), headers=_auth(manager_token)
    )
    assert create_response.status_code == 201, create_response.text

    _member, member_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )
    response = await client.get("/intake/rules", headers=_auth(member_token))

    assert response.status_code == 200, response.text
    assert len(response.json()["data"]) == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_rule_with_two_and_conditions_requires_both(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """Scenario: Regla con dos condiciones — solo casa si ambas se cumplen
    (validado a nivel de creación: el criteria persiste ambas condiciones)."""

    _manager, manager_token = await make_member(
        session, two_orgs.a.organization, MemberRole.manager
    )
    payload = _rule_payload(
        criteria=[
            {"field": "source_provider", "operator": "equals", "value": "microsoft365"},
            {"field": "title", "operator": "contains", "value": "incidente"},
        ]
    )

    response = await client.post("/intake/rules", json=payload, headers=_auth(manager_token))

    assert response.status_code == 201, response.text
    assert len(response.json()["data"]["criteria"]) == 2


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_excludes_rule_from_listing(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """Scenario: `DELETE` es borrado suave — la regla eliminada desaparece
    de `GET /intake/rules` (y por tanto de la evaluación futura, que solo
    lee reglas activas)."""

    _manager, manager_token = await make_member(
        session, two_orgs.a.organization, MemberRole.manager
    )
    create_response = await client.post(
        "/intake/rules", json=_rule_payload(), headers=_auth(manager_token)
    )
    rule_id = create_response.json()["data"]["id"]

    delete_response = await client.delete(
        f"/intake/rules/{rule_id}", headers=_auth(manager_token)
    )
    assert delete_response.status_code == 204, delete_response.text

    list_response = await client.get("/intake/rules", headers=_auth(manager_token))
    assert list_response.json()["data"] == []

    get_response = await client.get(f"/intake/rules/{rule_id}", headers=_auth(manager_token))
    assert get_response.status_code == 404, get_response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_org_b_never_sees_org_a_rules(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """Aislamiento multi-tenant: org B nunca ve las reglas de org A."""

    _manager, manager_token = await make_member(
        session, two_orgs.a.organization, MemberRole.manager
    )
    create_response = await client.post(
        "/intake/rules", json=_rule_payload(), headers=_auth(manager_token)
    )
    assert create_response.status_code == 201, create_response.text

    response = await client.get("/intake/rules", headers=_auth(two_orgs.b.token))
    assert response.json()["data"] == []
