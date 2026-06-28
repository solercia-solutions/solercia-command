"""Password hashing and JWT helpers.

Bcrypt is used directly (no passlib) to keep the dependency surface small and
avoid the passlib/bcrypt version-detection warnings.

Two token families are issued:

* ``access`` — short-lived bearer token sent in the ``Authorization`` header.
* ``refresh`` — longer-lived token carried in an httpOnly cookie, rotated on
  every refresh and tagged with a ``jti`` so it can be reasoned about.

Both carry a ``type`` claim that is validated on decode so a refresh token can
never be replayed as an access token (and vice versa).
"""

import datetime as dt
import uuid

import bcrypt
import jwt

from app.config import settings

# Bcrypt operates on at most 72 bytes; longer secrets are truncated to stay
# within that boundary instead of raising at runtime.
_BCRYPT_MAX_BYTES = 72

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def _to_bcrypt_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    """Hash a plain-text password and return the encoded bcrypt digest."""

    hashed = bcrypt.hashpw(_to_bcrypt_bytes(password), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Return True when the plain-text password matches the bcrypt digest."""

    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """Create a signed access JWT whose subject is the user identifier."""

    minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(subject),
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + dt.timedelta(minutes=minutes),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def create_refresh_token(
    subject: str, expires_days: int | None = None
) -> tuple[str, str]:
    """Create a signed refresh JWT.

    Returns ``(token, jti)`` so callers may persist/track the identifier if
    they choose to. The token carries ``type='refresh'`` and a unique ``jti``.
    """

    days = expires_days or settings.REFRESH_TOKEN_EXPIRE_DAYS
    now = dt.datetime.now(dt.timezone.utc)
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(subject),
        "type": REFRESH_TOKEN_TYPE,
        "jti": jti,
        "iat": now,
        "exp": now + dt.timedelta(days=days),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)
    return token, jti


def decode_token(token: str, expected_type: str | None = None) -> dict:
    """Decode and validate a JWT, raising on signature, expiry or type errors.

    When ``expected_type`` is given the token's ``type`` claim must match it,
    otherwise an :class:`jwt.InvalidTokenError` is raised.
    """

    payload = jwt.decode(
        token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG]
    )
    if expected_type is not None and payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("Tipo de token no válido.")
    return payload
