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


def encrypt(plaintext: str) -> str:
    """Encrypt ``plaintext`` and return the ciphertext as a str token."""

    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """Decrypt a token produced by :func:`encrypt` back to plaintext."""

    return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
