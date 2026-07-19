"""RED tests for Fernet-based token encryption at rest (design.md "Cifrado
en reposo", Security Requirements)."""

import pytest
from cryptography.fernet import Fernet

from app.integrations import crypto


def test_validate_key_accepts_a_well_formed_fernet_key() -> None:
    """A key shaped like ``Fernet.generate_key()``'s output passes silently
    (no exception) — the shape ``INTEGRATIONS_FERNET_KEY`` must have."""

    crypto.validate_key(Fernet.generate_key().decode("utf-8"))


def test_validate_key_rejects_a_malformed_key_with_a_clear_message() -> None:
    """An invalid ``INTEGRATIONS_FERNET_KEY`` fails fast with a message that
    names the variable — the boot-time guard in ``app/main.py``'s lifespan
    relies on this raising before the app starts serving traffic."""

    with pytest.raises(RuntimeError, match="INTEGRATIONS_FERNET_KEY"):
        crypto.validate_key("not-a-valid-fernet-key")


def test_encrypt_decrypt_round_trip_and_ciphertext_differs_from_plaintext() -> None:
    """Scenario base del cifrado: `ciphertext != plaintext` and decrypting
    the ciphertext recovers the exact original plaintext."""

    plaintext = "ya29.a0-fake-access-token-value"

    ciphertext = crypto.encrypt(plaintext)

    assert ciphertext != plaintext
    assert crypto.decrypt(ciphertext) == plaintext


def test_different_plaintexts_produce_different_ciphertexts() -> None:
    """Triangulation: two distinct tokens encrypt to two distinct values,
    each decrypting back to its own plaintext (proves real Fernet logic
    runs, not a hardcoded passthrough)."""

    first = crypto.encrypt("token-one")
    second = crypto.encrypt("token-two")

    assert first != second
    assert crypto.decrypt(first) == "token-one"
    assert crypto.decrypt(second) == "token-two"
