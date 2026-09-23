"""Authenticated encryption for secrets the server must be able to read back.

A TOTP seed cannot be hashed the way a password or a refresh token is: every
future code is derived from it, so verification needs the original value.  What
protects it is *encryption at rest* with a key that lives outside the database,
so a leaked dump (or a backup, or an over-privileged reader) yields ciphertext
rather than a permanently usable second factor for every enrolled account.

Construction: AES-256-GCM with a fresh random 96-bit nonce per call, stored as
``v1:<base64url(nonce || ciphertext || tag)>``.  GCM is authenticated, so a
tampered value fails to decrypt instead of silently producing a wrong secret, and
the random nonce means encrypting the same secret twice never yields the same
ciphertext (so a dump cannot be compared against a known value).

The version prefix is what makes the format migratable: it is also the marker for
"this value is encrypted".  A value with no prefix is a legacy plaintext secret
from before this module existed, and is read as-is so a deployment is never
broken by the upgrade; the next write replaces it with ciphertext.
"""

from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PREFIX = "v1:"
NONCE_BYTES = 12
KEY_BYTES = 32

# Documented development default so a contributor can run the stack without
# provisioning a key. It is refused outside development by
# ``Settings.validate_runtime_secrets()``, exactly like the JWT and Super Admin
# development defaults, because a secret committed to a repository must never
# protect a real deployment.
DEVELOPMENT_KEY = "mrW7YdZ0k9Q2xV5tBnJ4aP8cL1eH6uS3gX0iR7oT2wQ="


class SecretBoxError(RuntimeError):
    """Raised when a value cannot be decrypted with the configured key."""


def _decode_key(key: str) -> bytes:
    """Accept a base64 (preferred) or hex key; reject anything the wrong size."""
    candidate = (key or "").strip()
    if not candidate:
        raise SecretBoxError("MFA encryption key is not configured")
    raw: bytes | None = None
    try:
        raw = base64.urlsafe_b64decode(candidate + "=" * (-len(candidate) % 4))
    except (binascii.Error, ValueError):
        raw = None
    if raw is None or len(raw) != KEY_BYTES:
        try:
            raw = bytes.fromhex(candidate)
        except ValueError as exc:
            raise SecretBoxError("MFA encryption key must be base64 or hex") from exc
    if len(raw) != KEY_BYTES:
        raise SecretBoxError(f"MFA encryption key must decode to {KEY_BYTES} bytes")
    return raw


def is_encrypted(value: str | None) -> bool:
    """Whether a stored value is ciphertext produced by this module."""
    return bool(value) and value.startswith(PREFIX)


def encrypt_secret(plaintext: str, key: str) -> str:
    """Encrypt a secret for storage (fresh nonce per call)."""
    if plaintext is None:
        raise SecretBoxError("Nothing to encrypt")
    nonce = os.urandom(NONCE_BYTES)
    sealed = AESGCM(_decode_key(key)).encrypt(nonce, plaintext.encode("utf-8"), None)
    return PREFIX + base64.urlsafe_b64encode(nonce + sealed).decode("ascii")


def decrypt_secret(stored: str, key: str) -> str:
    """Recover a stored secret.

    A value without the version prefix predates encryption and is returned
    unchanged, so introducing this module cannot lock existing users out of their
    authenticator; the caller re-encrypts it on the next write.
    """
    if not stored:
        raise SecretBoxError("Nothing to decrypt")
    if not is_encrypted(stored):
        return stored
    payload = stored[len(PREFIX):]
    try:
        blob = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
    except (binascii.Error, ValueError) as exc:
        raise SecretBoxError("Stored secret is not valid base64") from exc
    if len(blob) <= NONCE_BYTES:
        raise SecretBoxError("Stored secret is truncated")
    nonce, sealed = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    try:
        plaintext = AESGCM(_decode_key(key)).decrypt(nonce, sealed, None)
    except (InvalidTag, ValueError) as exc:
        # Wrong key or tampered ciphertext. Fail closed: never fall back to
        # treating the ciphertext as the secret.
        raise SecretBoxError("Stored secret could not be decrypted") from exc
    return plaintext.decode("utf-8")
