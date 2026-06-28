"""Authentication routes."""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import (
    get_current_membership,
    get_current_user,
    load_accessible_menus,
)
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
