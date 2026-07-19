"""RED tests for Fernet-based token encryption at rest (design.md "Cifrado
en reposo", Security Requirements)."""

from app.integrations import crypto


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
