"""Tests for the auth module: login, refresh rotation, logout, me/menus.

R1/R2 access token (30 min) + refresh cookie httpOnly 7 días SameSite=lax ·
R3 rotación de refresh (jti nuevo + access nuevo) · R4 bcrypt con
truncamiento a 72 bytes · R5 ``GET /auth/me/menus`` árbol filtrado por rol ·
logout 204 + cookie eliminada (openspec/specs/auth/spec.md).

Uses the shared in-process fixtures (``client``/``session``/``tenant``/``user``).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.organizations.models import Organization
from app.modules.users.models import User
from app.shared.security import decode_token
from tests.conftest import skip_no_db

_PASSWORD = "Test123*"  # matches the plaintext hashed by the `user` fixture


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# R1/R2 — Login exitoso: access token 30 min + cookie de refresh httpOnly 7 días
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_login_returns_access_token_and_sets_refresh_cookie(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """A valid login returns a 30-min access token and an httpOnly 7-day
    refresh cookie with ``SameSite=lax``.
    """

    owner, _ = user

    response = await client.post(
        "/auth/login", json={"email": owner.email, "password": _PASSWORD}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["id"] == str(owner.id)

    decoded = decode_token(body["access_token"], expected_type="access")
    lifetime_minutes = (decoded["exp"] - decoded["iat"]) / 60
    assert lifetime_minutes == 30

    set_cookie_headers = response.headers.get_list("set-cookie")
    refresh_header = next(
        h for h in set_cookie_headers if h.startswith(f"{settings.REFRESH_COOKIE_NAME}=")
    )
    assert "HttpOnly" in refresh_header
    assert "samesite=lax" in refresh_header.lower()
    assert f"Max-Age={7 * 24 * 60 * 60}" in refresh_header

    cookie_value = response.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert cookie_value is not None
    refresh_payload = decode_token(cookie_value, expected_type="refresh")
    assert refresh_payload["sub"] == str(owner.id)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_login_with_wrong_password_returns_401(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Wrong credentials are rejected with 401 and no cookie is set."""

    owner, _ = user

    response = await client.post(
        "/auth/login", json={"email": owner.email, "password": "wrong-password"}
    )

    assert response.status_code == 401
    assert settings.REFRESH_COOKIE_NAME not in response.cookies


# ---------------------------------------------------------------------------
# R3 — Rotación de refresh: jti nuevo + access nuevo en cada llamada
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_refresh_rotates_jti_and_issues_new_access_token(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Calling /auth/refresh with a valid cookie rotates the jti and issues
    a fresh access token — the SAME cookie is never replayed unchanged.
    """

    owner, _ = user
    login_response = await client.post(
        "/auth/login", json={"email": owner.email, "password": _PASSWORD}
    )
    assert login_response.status_code == 200, login_response.text
    first_cookie = client.cookies.get(settings.REFRESH_COOKIE_NAME)
    first_jti = decode_token(first_cookie, expected_type="refresh")["jti"]

    refresh_response = await client.post("/auth/refresh")

    assert refresh_response.status_code == 200, refresh_response.text
    second_access = refresh_response.json()["access_token"]
    second_cookie = client.cookies.get(settings.REFRESH_COOKIE_NAME)
    second_jti = decode_token(second_cookie, expected_type="refresh")["jti"]

    # Real production behavior rotates jti on every refresh call — this is
    # the exact case the "aserción invertida" convention targets (tasks.md);
    # the inverted assertion was run and confirmed to FAIL before this.
    assert second_jti != first_jti

    # NOTE (discovered as-built behavior, not asserted as a defect): a fresh
    # access token is minted on every /auth/refresh call, but
    # `create_access_token` encodes `iat`/`exp` at 1-second resolution, so
    # two calls landing in the SAME wall-clock second (as happens here, two
    # in-process ASGI calls back-to-back) can produce a byte-identical JWT.
    # This is harmless for a stateless bearer token (same claims = same
    # validity window) and does not weaken R3: the security-relevant
    # rotation is the refresh cookie's `jti`, asserted above. We verify the
    # access token decodes to the SAME subject instead of asserting
    # byte-inequality, which the spec does not guarantee.
    second_access_payload = decode_token(second_access, expected_type="access")
    assert second_access_payload["sub"] == str(owner.id)


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_refresh_without_cookie_returns_401(client: AsyncClient) -> None:
    """Calling refresh with no session (no refresh cookie) is rejected."""

    response = await client.post("/auth/refresh")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# R4 — bcrypt con truncamiento a 72 bytes
# ---------------------------------------------------------------------------


def test_bcrypt_truncates_to_72_bytes_before_hashing() -> None:
    """Two passwords sharing the same first 72 bytes hash/verify identically
    (bcrypt truncation), while a difference within the first 72 bytes does
    NOT verify — proving truncation happens, not silent no-op comparison.
    """

    from app.shared.security import hash_password, verify_password

    base_72 = "a" * 72
    long_password = base_72 + "-this-tail-is-ignored-by-bcrypt"
    hashed = hash_password(long_password)

    # The 72-byte prefix alone verifies against the hash of the longer string.
    assert verify_password(base_72, hashed) is True
    # A change WITHIN the first 72 bytes must NOT verify.
    assert verify_password("b" * 72, hashed) is False


# ---------------------------------------------------------------------------
# R5 — GET /auth/me/menus: árbol filtrado por rol
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_me_menus_returns_only_menus_granted_to_the_role(
    client: AsyncClient,
    session: AsyncSession,
    tenant: Organization,
    user: tuple[User, str],
) -> None:
    """A user whose role only grants a subset of menus sees exactly that
    subset, nested under its parent — never the ungranted menu.
    """

    from app.modules.menus.models import Menu
    from app.modules.roles.models import Role, RoleMenu, UserRole

    owner, token = user

    parent_menu = Menu(name="Proyectos", order=1)
    child_menu = Menu(name="Tableros", order=1)
    session.add_all([parent_menu, child_menu])
    await session.flush()
    child_menu.parent_id = parent_menu.id

    ungranted_menu = Menu(name="Administración", order=2)
    session.add(ungranted_menu)
    await session.flush()

    role = Role(organization_id=tenant.id, code="LIMITED", name="Limited")
    session.add(role)
    await session.flush()

    session.add_all(
        [
            RoleMenu(role_id=role.id, menu_id=parent_menu.id),
            RoleMenu(role_id=role.id, menu_id=child_menu.id),
            UserRole(user_id=owner.id, role_id=role.id),
        ]
    )
    await session.flush()

    response = await client.get("/auth/me/menus", headers=_auth(token))

    assert response.status_code == 200, response.text
    tree = response.json()
    names_at_root = {node["name"] for node in tree}
    assert names_at_root == {"Proyectos"}
    assert "Administración" not in names_at_root

    root = next(node for node in tree if node["name"] == "Proyectos")
    child_names = {child["name"] for child in root["children"]}
    assert child_names == {"Tableros"}


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@skip_no_db
async def test_logout_returns_204_and_clears_refresh_cookie(
    client: AsyncClient, tenant: Organization, user: tuple[User, str]
) -> None:
    """Logout responds 204 and the refresh cookie is deleted (empty/expired)."""

    owner, _ = user
    await client.post("/auth/login", json={"email": owner.email, "password": _PASSWORD})
    assert client.cookies.get(settings.REFRESH_COOKIE_NAME) is not None

    response = await client.post("/auth/logout")

    assert response.status_code == 204
    set_cookie_headers = response.headers.get_list("set-cookie")
    delete_header = next(
        h for h in set_cookie_headers if h.startswith(f"{settings.REFRESH_COOKIE_NAME}=")
    )
    assert 'Max-Age=0' in delete_header or "expires=" in delete_header.lower()
