"""Cryptographic primitives for authentication tokens.

Nothing in this module touches the database or the application state: it is the
single place that mints and hashes credentials, so callers cannot accidentally
invent their own (e.g. a refresh token without hashing).

Two credential types:

*Refresh token* — an opaque 384-bit URL-safe secret.  Only its SHA-256 hash is
persisted, so a database leak cannot be replayed.  It is rotated on every use
and must never be logged.

*Access token* — a short-lived HS256 JWT accepted by fastapi-users' bearer
dependency (the ``fastapi-users:auth`` audience is required).  It carries only
the subject, the audience, the session id (``sid``) and the token purpose
(``typ``).  Permissions are deliberately *not* embedded: authorization is
resolved from the database on every request, so a role change takes effect
immediately.  The practical consequence — documented in the architecture
reference — is that an access token cannot be revoked before it expires, which
is why its lifetime is short.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

import jwt

ACCESS_TOKEN_AUDIENCE = "fastapi-users:auth"
# The MFA challenge is signed with the same key but a *different* audience.
# fastapi-users' bearer dependency requires ``fastapi-users:auth`` in ``aud``,
# so a challenge token can never be replayed as an access token.
MFA_CHALLENGE_AUDIENCE = "hrms:mfa"
ACCESS_TOKEN_PURPOSE = "access"
MFA_CHALLENGE_PURPOSE = "mfa"
# 48 random bytes → 64 URL-safe characters ≈ 384 bits of entropy.
REFRESH_TOKEN_BYTES = 48


def generate_refresh_token() -> str:
    """Return a fresh opaque refresh secret (the only time it exists in clear)."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(raw_token: str) -> str:
    """Hash a refresh token for storage/lookup.

    SHA-256 (not a password hash) is correct here: the input is a full-entropy
    random secret, so there is nothing to brute-force, and a deterministic hash
    is what makes O(1) indexed lookup possible.  Callers must still compare only
    hashes, never raw values.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def token_fingerprint(raw_token: str) -> str:
    """Short, non-reversible label for logs/audit (never the token itself)."""
    return hash_refresh_token(raw_token)[:12]


def create_access_token(
    *,
    subject: str | int,
    secret: str,
    ttl_seconds: int,
    now: datetime,
    session_id: int | None = None,
    purpose: str = ACCESS_TOKEN_PURPOSE,
    audience: str = ACCESS_TOKEN_AUDIENCE,
    algorithm: str = "HS256",
) -> str:
    """Mint a short-lived access token for ``subject``."""
    payload: dict[str, Any] = {
        "sub": str(subject),
        "aud": [audience],
        "typ": purpose,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    if session_id is not None:
        payload["sid"] = session_id
    return jwt.encode(payload, secret, algorithm=algorithm)


def create_mfa_challenge_token(
    *,
    subject: str | int,
    secret: str,
    ttl_seconds: int,
    now: datetime,
    enrollment_required: bool,
    algorithm: str = "HS256",
) -> str:
    """Mint the second-factor challenge credential issued after a password check."""
    payload: dict[str, Any] = {
        "sub": str(subject),
        "aud": [MFA_CHALLENGE_AUDIENCE],
        "typ": MFA_CHALLENGE_PURPOSE,
        "enrol": bool(enrollment_required),
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_token(
    raw_token: str,
    *,
    secret: str,
    audience: str = ACCESS_TOKEN_AUDIENCE,
    algorithm: str = "HS256",
) -> dict[str, Any]:
    """Decode and verify a token this module minted.

    Raises ``jwt.PyJWTError`` (expired, bad signature, wrong audience) — callers
    translate that into a 401 rather than leaking the underlying reason.
    """
    return jwt.decode(raw_token, secret, algorithms=[algorithm], audience=audience)
