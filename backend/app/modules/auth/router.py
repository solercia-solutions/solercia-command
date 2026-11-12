"""Authentication routes."""

import httpx
from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import (
    get_current_membership,
    get_current_user,
    load_accessible_menus,
)
from app.modules.auth.oidc import client as oidc_client_module
from app.modules.auth.oidc.client import OidcTokenError
from app.modules.auth.schemas import (
    LoginRequest,
    LoginResponse,
    TokenResponse,
    UserRead,
)
from app.modules.auth.service import (
    authenticate,
    build_user_read,
    primary_organization_id,
)
from app.modules.auth.sso_service import (
    SsoDisabledError,
    SsoLoginRejectedError,
    SsoStateInvalidError,
    sso_callback,
    sso_login,
)
from app.modules.menus.schemas import MenuNode
from app.modules.organizations.models import OrganizationMember
from app.modules.users.models import User
from app.shared.exceptions import AppException
from app.shared.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

_SSO_INERT_MESSAGE = "El inicio de sesión SSO no está disponible."


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Attach the rotated refresh-token cookie to the response."""

    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate a user, set the refresh cookie and return an access token."""

    user = await authenticate(db, payload.email, payload.password)
    if user is None:
        raise AppException(
            "Credenciales inválidas.",
            code="invalid_credentials",
            status_code=401,
        )

    organization_id = await primary_organization_id(db, user)
    access_token = create_access_token(str(user.id))
    refresh_token, _ = create_refresh_token(str(user.id))
    _set_refresh_cookie(response, refresh_token)

    user_read = await build_user_read(db, user, organization_id)
    return LoginResponse(access_token=access_token, user=user_read)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Rotate the refresh cookie and issue a fresh access token."""

    cookie = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not cookie:
        raise AppException(
            "No hay una sesión activa. Inicia sesión nuevamente.",
            code="missing_refresh_token",
            status_code=401,
        )

    try:
        payload = decode_token(cookie, expected_type=REFRESH_TOKEN_TYPE)
    except Exception as exc:  # noqa: BLE001 - any JWT error maps to 401
        raise AppException(
            "Tu sesión ha expirado. Inicia sesión nuevamente.",
            code="invalid_refresh_token",
            status_code=401,
        ) from exc

    subject = payload.get("sub")
    if not subject:
        raise AppException(
            "Tu sesión no es válida. Inicia sesión nuevamente.",
            code="invalid_refresh_token",
            status_code=401,
        )

    access_token = create_access_token(str(subject))
    new_refresh_token, _ = create_refresh_token(str(subject))
    _set_refresh_cookie(response, new_refresh_token)
    return TokenResponse(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    """Clear the refresh cookie, ending the session."""

    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserRead)
async def read_current_user(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    membership: OrganizationMember = Depends(get_current_membership),
) -> UserRead:
    """Return the authenticated user including its roles."""

    return await build_user_read(db, user, membership.organization_id)


@router.get("/me/menus", response_model=list[MenuNode])
async def read_current_user_menus(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    membership: OrganizationMember = Depends(get_current_membership),
) -> list[dict]:
    """Return the nested menu tree the caller can access."""

    return await load_accessible_menus(db, user, membership.organization_id)


def _sso_inert() -> AppException:
    """404 for SSO_ENABLED=false or an unconfigured provider (sso-oidc R6).

    Both causes render IDENTICALLY on purpose — a caller (or attacker)
    probing ``/auth/sso/{provider}/login`` can never distinguish "SSO is
    off" from "this provider name is wrong", same info-minimization
    posture as the generic invalid-credentials message on local login.
    """

    return AppException(_SSO_INERT_MESSAGE, code="sso_disabled", status_code=404)


@router.get("/sso/{provider}/login")
async def sso_login_route(provider: str) -> RedirectResponse:
    """Start the SSO flow (sso-oidc R1): 302 to the IdP with
    ``state``/``nonce``/PKCE persisted in Redis. Any ``redirect_uri`` a
    caller might supply is IGNORED — the OIDC ``redirect_uri`` is always
    the provider's own fixed, env-configured value (design.md D5,
    "allowlist de 1"), never client input."""

    try:
        authorize_url = await sso_login(provider, oidc_client_module.get_http_client())
    except SsoDisabledError as exc:
        raise _sso_inert() from exc

    return RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)


@router.get("/sso/{provider}/callback")
async def sso_callback_route(
    provider: str,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Complete the SSO flow (sso-oidc R2-R5): validate state, exchange the
    code, verify the ID token, resolve/provision the user, then set the
    SAME refresh cookie local login uses and redirect to the SPA landing —
    the access token NEVER travels in this URL (sso-oidc R7); the SPA
    exchanges the cookie for one via ``POST /auth/refresh``.

    An ``error`` from the IdP (e.g. ``access_denied``) is a controlled,
    NON-exceptional outcome (sso-oidc R5): redirected to the SPA landing
    with ``?error=...`` attached, never a JWT, never a raised 4xx — the
    caller here is the user's own browser navigating back from the IdP,
    not an API client that could act on a JSON error body.
    """

    try:
        if error:
            return RedirectResponse(
                url=f"{settings.SSO_POST_LOGIN_REDIRECT}?error={error}",
                status_code=status.HTTP_302_FOUND,
            )

        _, refresh_token, _ = await sso_callback(
            db,
            provider,
            oidc_client_module.get_http_client(),
            code=code,
            state=state,
            error=error,
        )
    except SsoDisabledError as exc:
        raise _sso_inert() from exc
    except SsoStateInvalidError as exc:
        raise AppException(
            "El inicio de sesión SSO expiró o ya fue utilizado. Intenta de nuevo.",
            code="sso_state_invalid",
            status_code=400,
        ) from exc
    except OidcTokenError as exc:
        raise AppException(
            "El proveedor de identidad devolvió una respuesta inválida.",
            code="sso_id_token_invalid",
            status_code=400,
        ) from exc
    except SsoLoginRejectedError as exc:
        raise AppException(
            "No fue posible iniciar sesión con esa cuenta.",
            code="sso_login_rejected",
            status_code=403,
        ) from exc
    except httpx.HTTPError as exc:
        raise AppException(
            "No fue posible completar el inicio de sesión con el proveedor.",
            code="sso_provider_error",
            status_code=502,
        ) from exc

    redirect = RedirectResponse(
        url=settings.SSO_POST_LOGIN_REDIRECT, status_code=status.HTTP_302_FOUND
    )
    _set_refresh_cookie(redirect, refresh_token)
    return redirect
