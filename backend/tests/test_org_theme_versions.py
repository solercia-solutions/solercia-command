"""Tests for the per-organization theme version history (PostgreSQL).

Contract:
- ``PUT /organizations/me/theme[?source_version_id=<id>]`` — body is still the
  ThemeFile. Stores it AND records a version in one transaction; ``data`` is
  the theme (unchanged contract) and ``meta.version`` describes the new
  version. When the organization already had a theme and no history, that
  previous theme is recorded first with ``initial_capture = true``.
- ``GET /organizations/me/theme/versions[?before=<cursor>]`` — 20 per page,
  newest first; ``data.next`` is the cursor of the next page or ``null``.
- ``GET /organizations/me/theme/versions/{id}`` — metadata + ThemeFile; 404
  for an unknown id AND for a version of another organization.
- ``DELETE /organizations/me/theme`` resets the theme and keeps the history.

Every route is RBAC ``ADMIN`` only and scoped to the caller's organization.
The history is insert-only: no route updates or deletes a recorded version.
"""

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import OrgData, TwoOrgs, skip_no_db

_THEME_URL = "/organizations/me/theme"
_VERSIONS_URL = "/organizations/me/theme/versions"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _theme(label: str) -> dict:
    """Minimal ThemeFile-shaped payload; the API stores it opaquely."""

    return {
        "meta": {"tenant": label, "logo": {"url": "", "altText": label, "width": 120}},
        "primitives": {"color": {"brand": {"600": "#7C3AED"}}},
        "modes": {
            "light": {"semantic": {"color": {"primary": "#7C3AED"}}},
            "dark": {"semantic": {"color": {"primary": "#8B5CF6"}}},
        },
    }


async def _admins(session: AsyncSession, two_orgs: TwoOrgs, rbac_admin) -> None:
    """Grant RBAC ADMIN to both owners and release the fixtures' SAVEPOINT.

    A rejected apply rolls its transaction back; committing here keeps the
    seeded rows (the outer transaction is still rolled back at teardown).
    """

    await rbac_admin(session, two_orgs.a.organization, two_orgs.a.user)
    await rbac_admin(session, two_orgs.b.organization, two_orgs.b.user)
    await session.commit()


async def _apply(
    client: AsyncClient, org: OrgData, label: str, *, source_version_id=None
) -> dict:
    params = {} if source_version_id is None else {"source_version_id": source_version_id}
    response = await client.put(
        _THEME_URL, json=_theme(label), params=params, headers=_auth(org.token)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _versions(client: AsyncClient, org: OrgData, **params) -> dict:
    response = await client.get(_VERSIONS_URL, params=params, headers=_auth(org.token))
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _stored_rows(session: AsyncSession, organization_id) -> list[tuple]:
    """Raw rows of the history table (Core select: no identity-map caching)."""

    from app.modules.organizations.models import OrganizationThemeVersion

    table = OrganizationThemeVersion.__table__
    result = await session.execute(
        select(table).where(table.c.organization_id == organization_id).order_by(table.c.id)
    )
    return [tuple(row) for row in result.all()]


# ---------------------------------------------------------------------------
# PUT — guarda el tema y registra la versión
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_theme_records_a_version_and_returns_its_metadata(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """PUT keeps ``data`` = theme and adds the new version under ``meta.version``."""

    await _admins(session, two_orgs, rbac_admin)

    body = await _apply(client, two_orgs.a, "v1")

    assert body["data"] == _theme("v1")
    assert body["message"] == "Tema de la organización actualizado."
    version = body["meta"]["version"]
    assert set(version) == {
        "id", "user_name", "user_id", "applied_at", "initial_capture", "source_version_id",
    }
    assert isinstance(version["id"], int)
    assert version["user_id"] == str(two_orgs.a.user.id)
    assert version["user_name"] == "Owner ORGA"
    assert version["initial_capture"] is False
    assert version["source_version_id"] is None
    applied_at = datetime.fromisoformat(version["applied_at"])
    assert applied_at.utcoffset() == timedelta(0)

    page = await _versions(client, two_orgs.a)
    assert page == {"versions": [version], "next": None}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_theme_captures_the_previous_theme_once(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """A theme stored before the history existed becomes the initial capture."""

    two_orgs.a.organization.theme = _theme("legacy")
    await session.flush()
    await _admins(session, two_orgs, rbac_admin)

    first = await _apply(client, two_orgs.a, "v1")
    await _apply(client, two_orgs.a, "v2")

    page = await _versions(client, two_orgs.a)
    assert [v["initial_capture"] for v in page["versions"]] == [False, False, True]
    capture = page["versions"][-1]
    assert capture["id"] < first["meta"]["version"]["id"]
    assert (capture["user_id"], capture["user_name"]) == (None, None)
    assert capture["source_version_id"] is None

    detail = await client.get(
        f"{_VERSIONS_URL}/{capture['id']}", headers=_auth(two_orgs.a.token)
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["theme"] == _theme("legacy")


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_theme_from_a_restored_version_records_its_source(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """Restoring = applying an old ThemeFile with ``source_version_id``."""

    await _admins(session, two_orgs, rbac_admin)
    first = (await _apply(client, two_orgs.a, "v1"))["meta"]["version"]
    await _apply(client, two_orgs.a, "v2")

    restored = await _apply(client, two_orgs.a, "v1", source_version_id=first["id"])

    assert restored["meta"]["version"]["source_version_id"] == first["id"]
    assert restored["meta"]["version"]["id"] > first["id"]
    current = await client.get(_THEME_URL, headers=_auth(two_orgs.a.token))
    assert current.json()["data"] == _theme("v1")
    page = await _versions(client, two_orgs.a)
    assert [v["source_version_id"] for v in page["versions"]] == [first["id"], None, None]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_theme_rejects_a_source_version_of_another_org(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """A foreign or unknown source version gets the same 422 and writes nothing."""

    await _admins(session, two_orgs, rbac_admin)
    foreign = (await _apply(client, two_orgs.b, "b1"))["meta"]["version"]

    bodies = []
    for source_version_id in (foreign["id"], foreign["id"] + 1000):
        response = await client.put(
            _THEME_URL,
            json=_theme("a1"),
            params={"source_version_id": source_version_id},
            headers=_auth(two_orgs.a.token),
        )
        assert response.status_code == 422, response.text
        bodies.append(response.json())

    assert bodies[0] == bodies[1]
    assert bodies[0]["code"] == "theme_source_version_invalid"
    current = await client.get(_THEME_URL, headers=_auth(two_orgs.a.token))
    assert current.json()["data"] is None
    assert await _versions(client, two_orgs.a) == {"versions": [], "next": None}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_theme_rejects_an_invalid_source_version_id(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """``source_version_id`` must be a positive integer (422 by validation)."""

    await _admins(session, two_orgs, rbac_admin)

    for bad in ("abc", "0", "-1"):
        response = await client.put(
            _THEME_URL,
            json=_theme("a1"),
            params={"source_version_id": bad},
            headers=_auth(two_orgs.a.token),
        )
        assert response.status_code == 422, response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_put_theme_rejected_for_member_records_nothing(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin, make_member
) -> None:
    """A plain member gets 403 and no version is recorded."""

    from app.shared.enums import MemberRole

    _, member_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )
    await _admins(session, two_orgs, rbac_admin)

    response = await client.put(
        _THEME_URL, json=_theme("v1"), headers=_auth(member_token)
    )

    assert response.status_code == 403, response.text
    assert await _stored_rows(session, two_orgs.a.organization.id) == []


# ---------------------------------------------------------------------------
# GET /versions — 20 por página, más nuevas primero, por cursor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_versions_pages_newest_first_by_cursor(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """45 versions → pages of 20, 20 and 5; ``next`` chains them without gaps."""

    await _admins(session, two_orgs, rbac_admin)
    applied = [
        (await _apply(client, two_orgs.a, f"v{index}"))["meta"]["version"]["id"]
        for index in range(45)
    ]
    newest_first = list(reversed(applied))
    assert newest_first == sorted(applied, reverse=True)

    first = await _versions(client, two_orgs.a)
    second = await _versions(client, two_orgs.a, before=first["next"])
    third = await _versions(client, two_orgs.a, before=second["next"])

    assert [v["id"] for v in first["versions"]] == newest_first[:20]
    assert first["next"] == newest_first[19]
    assert [v["id"] for v in second["versions"]] == newest_first[20:40]
    assert second["next"] == newest_first[39]
    assert [v["id"] for v in third["versions"]] == newest_first[40:]
    assert third["next"] is None
    assert "theme" not in first["versions"][0]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_versions_is_empty_without_history(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """No applied theme yet → an empty page, not an error."""

    await _admins(session, two_orgs, rbac_admin)

    assert await _versions(client, two_orgs.a) == {"versions": [], "next": None}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_versions_rejects_an_invalid_cursor(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """``before`` must be a positive integer (422 by validation)."""

    await _admins(session, two_orgs, rbac_admin)

    for bad in ("abc", "0", "-5"):
        response = await client.get(
            _VERSIONS_URL, params={"before": bad}, headers=_auth(two_orgs.a.token)
        )
        assert response.status_code == 422, response.text


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_list_versions_requires_admin(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, make_member
) -> None:
    """No token → 401; a plain member → 403."""

    from app.shared.enums import MemberRole

    _, member_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )

    assert (await client.get(_VERSIONS_URL)).status_code == 401
    response = await client.get(_VERSIONS_URL, headers=_auth(member_token))
    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# GET /versions/{id} — metadatos + tema
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_version_returns_metadata_and_theme(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """The detail is the listed metadata plus the stored ThemeFile."""

    await _admins(session, two_orgs, rbac_admin)
    version = (await _apply(client, two_orgs.a, "v1"))["meta"]["version"]
    await _apply(client, two_orgs.a, "v2")

    response = await client.get(
        f"{_VERSIONS_URL}/{version['id']}", headers=_auth(two_orgs.a.token)
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {**version, "theme": _theme("v1")}


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_version_of_another_org_returns_404(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """A foreign version and an unknown id are indistinguishable (same 404)."""

    await _admins(session, two_orgs, rbac_admin)
    foreign = (await _apply(client, two_orgs.b, "b1"))["meta"]["version"]

    bodies = []
    for version_id in (foreign["id"], foreign["id"] + 1000):
        response = await client.get(
            f"{_VERSIONS_URL}/{version_id}", headers=_auth(two_orgs.a.token)
        )
        assert response.status_code == 404, response.text
        bodies.append(response.json())

    assert bodies[0] == bodies[1]
    assert bodies[0]["code"] == "theme_version_not_found"


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_get_version_requires_admin(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin, make_member
) -> None:
    """No token → 401; a plain member → 403, even for an existing version."""

    from app.shared.enums import MemberRole

    _, member_token = await make_member(
        session, two_orgs.a.organization, MemberRole.member
    )
    await _admins(session, two_orgs, rbac_admin)
    version = (await _apply(client, two_orgs.a, "v1"))["meta"]["version"]
    url = f"{_VERSIONS_URL}/{version['id']}"

    assert (await client.get(url)).status_code == 401
    response = await client.get(url, headers=_auth(member_token))
    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# Aislamiento entre organizaciones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_versions_are_isolated_between_orgs(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """Each organization lists only its own versions."""

    await _admins(session, two_orgs, rbac_admin)
    a_ids = [
        (await _apply(client, two_orgs.a, f"a{i}"))["meta"]["version"]["id"]
        for i in range(2)
    ]
    b_ids = [(await _apply(client, two_orgs.b, "b0"))["meta"]["version"]["id"]]

    page_a = await _versions(client, two_orgs.a)
    page_b = await _versions(client, two_orgs.b)

    assert sorted(v["id"] for v in page_a["versions"]) == sorted(a_ids)
    assert [v["id"] for v in page_b["versions"]] == b_ids
    assert page_b["versions"][0]["user_name"] == "Owner ORGB"


# ---------------------------------------------------------------------------
# DELETE — restablece el tema; el historial se conserva
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_theme_keeps_the_history(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """Resetting clears the current theme only; versions stay restorable."""

    await _admins(session, two_orgs, rbac_admin)
    version = (await _apply(client, two_orgs.a, "v1"))["meta"]["version"]

    response = await client.delete(_THEME_URL, headers=_auth(two_orgs.a.token))

    assert response.status_code == 200, response.text
    assert response.json()["data"] is None
    current = await client.get(_THEME_URL, headers=_auth(two_orgs.a.token))
    assert current.json()["data"] is None
    assert await _versions(client, two_orgs.a) == {"versions": [version], "next": None}

    await _apply(client, two_orgs.a, "v2")
    page = await _versions(client, two_orgs.a)
    assert [v["initial_capture"] for v in page["versions"]] == [False, False]


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_delete_theme_captures_a_theme_without_history(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """Resetting a theme that predates the history records it before clearing."""

    two_orgs.a.organization.theme = _theme("legacy")
    await session.flush()
    await _admins(session, two_orgs, rbac_admin)

    response = await client.delete(_THEME_URL, headers=_auth(two_orgs.a.token))

    assert response.status_code == 200, response.text
    page = await _versions(client, two_orgs.a)
    assert [v["initial_capture"] for v in page["versions"]] == [True]
    detail = await client.get(
        f"{_VERSIONS_URL}/{page['versions'][0]['id']}", headers=_auth(two_orgs.a.token)
    )
    assert detail.json()["data"]["theme"] == _theme("legacy")


# ---------------------------------------------------------------------------
# Solo inserción
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_history_is_insert_only(
    client: AsyncClient, session: AsyncSession, two_orgs: TwoOrgs, rbac_admin
) -> None:
    """Applies, restores and resets only ever ADD rows; stored rows never change."""

    two_orgs.a.organization.theme = _theme("legacy")
    await session.flush()
    await _admins(session, two_orgs, rbac_admin)
    org_id = two_orgs.a.organization.id

    first = (await _apply(client, two_orgs.a, "v1"))["meta"]["version"]
    snapshot = await _stored_rows(session, org_id)
    assert len(snapshot) == 2

    await _apply(client, two_orgs.a, "v2")
    await _apply(client, two_orgs.a, "v1", source_version_id=first["id"])
    await client.delete(_THEME_URL, headers=_auth(two_orgs.a.token))
    await _apply(client, two_orgs.a, "v3")

    rows = await _stored_rows(session, org_id)
    assert len(rows) == 5
    assert rows[: len(snapshot)] == snapshot


def test_history_routes_expose_no_write_methods() -> None:
    """The history has no PUT/PATCH/DELETE/POST route at all."""

    from app.main import app

    methods: set[str] = set()
    for route in app.routes:
        if "/organizations/me/theme/versions" in getattr(route, "path", ""):
            methods |= route.methods
    assert methods == {"GET"}


# ---------------------------------------------------------------------------
# Adaptador PostgreSQL: integridad que no depende del caso de uso
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_database_rejects_a_source_version_of_another_org(
    session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """The composite FK ties ``source_version_id`` to the SAME organization."""

    from app.modules.organizations.theme_repository import OrganizationThemeRepository

    repository = OrganizationThemeRepository(session)
    # Ids read up front: the rollback below expires every loaded instance.
    org_a, org_b = two_orgs.a.organization.id, two_orgs.b.organization.id
    foreign = await repository.add_version(
        org_b, _theme("b1"), user_id=None, user_name=None
    )
    await session.commit()

    with pytest.raises(IntegrityError):
        await repository.add_version(
            org_a,
            _theme("a1"),
            user_id=None,
            user_name=None,
            source_version_id=foreign.id,
        )
    await session.rollback()

    assert await _stored_rows(session, org_a) == []


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_database_allows_one_initial_capture_per_org(
    session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """The partial unique index forbids a second initial capture per organization."""

    from app.modules.organizations.theme_repository import OrganizationThemeRepository

    repository = OrganizationThemeRepository(session)
    # Ids read up front: the rollback below expires every loaded instance.
    org_a, org_b = two_orgs.a.organization.id, two_orgs.b.organization.id
    for organization_id in (org_a, org_b):
        await repository.add_version(
            organization_id, _theme("legacy"), user_id=None, user_name=None,
            initial_capture=True,
        )
    await session.commit()

    with pytest.raises(IntegrityError):
        await repository.add_version(
            org_a, _theme("other"), user_id=None, user_name=None,
            initial_capture=True,
        )
    await session.rollback()

    assert len(await _stored_rows(session, org_a)) == 1


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_repository_reads_are_scoped_to_the_organization(
    session: AsyncSession, two_orgs: TwoOrgs
) -> None:
    """``find_version``/``list_versions``/``has_versions`` never cross tenants."""

    from app.modules.organizations.theme_repository import OrganizationThemeRepository

    repository = OrganizationThemeRepository(session)
    org_a, org_b = two_orgs.a.organization.id, two_orgs.b.organization.id
    foreign = await repository.add_version(
        org_b, _theme("b1"), user_id=two_orgs.b.user.id, user_name="Owner ORGB"
    )

    assert await repository.find_version(org_a, foreign.id) is None
    assert await repository.list_versions(org_a, before=None, limit=20) == []
    assert await repository.has_versions(org_a) is False
    found = await repository.find_version(org_b, foreign.id)
    assert found == foreign
    assert found.applied_at.utcoffset() == timedelta(0)
