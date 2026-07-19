"""Symmetric encryption for OAuth tokens at rest (Fernet, design.md
"Cifrado en reposo"). ``settings.INTEGRATIONS_FERNET_KEY`` is a urlsafe
base64 32-byte key, same shape as ``JWT_SECRET``'s dev default — production
MUST override it via the environment.
"""

from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import settings


@lru_cache
def _fernet() -> Fernet:
    return Fernet(settings.INTEGRATIONS_FERNET_KEY.encode("utf-8"))


def validate_key(key: str) -> None:
    """Fail fast with a clear message when ``key`` is not a well-formed
    Fernet key (urlsafe-base64, 32 raw bytes).

    Called from ``app/main.py``'s lifespan at boot so a misconfigured
    ``INTEGRATIONS_FERNET_KEY`` breaks startup immediately instead of only
    surfacing later when the first OAuth callback tries to encrypt a token.
    """

    try:
        Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "INTEGRATIONS_FERNET_KEY no es una llave Fernet válida. Genera "
            "una con: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        ) from exc


def encrypt(plaintext: str) -> str:
    """Encrypt ``plaintext`` and return the ciphertext as a str token."""

    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """Decrypt a token produced by :func:`encrypt` back to plaintext."""

    return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
