"""Time-based one-time passwords (RFC 6238) for Super Admin MFA.

Implemented with the standard library only: adding an MFA dependency for ~40
lines of well-specified cryptography would be a poor trade, and it keeps the
verification path auditable.  Compatible with Google Authenticator, 1Password,
Authy and any other RFC 6238 client (6 digits, 30-second step, SHA-1 — the
defaults every authenticator app assumes).

Recovery codes are stored as SHA-256 hashes, exactly like refresh tokens: they
are high-entropy random values, so a lookup hash is appropriate and the raw code
is shown to the user once.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from datetime import datetime
from urllib.parse import quote, urlencode

DEFAULT_DIGITS = 6
DEFAULT_STEP_SECONDS = 30
# ±1 step (30s) of clock drift, the usual tolerance for TOTP.
DEFAULT_WINDOW_STEPS = 1
RECOVERY_CODE_COUNT = 10
SECRET_BYTES = 20  # 160 bits, the RFC 4226 recommendation for SHA-1


def generate_secret() -> str:
    """Return a new base32 TOTP secret (padding stripped, authenticator-friendly)."""
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode("ascii").rstrip("=")


def _hotp(secret: str, counter: int, *, digits: int = DEFAULT_DIGITS) -> str:
    padded = secret + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**digits)).zfill(digits)


def totp_at(secret: str, moment: datetime, *, digits: int = DEFAULT_DIGITS, step_seconds: int = DEFAULT_STEP_SECONDS) -> str:
    """The code a client would display at ``moment`` (used by tests and docs)."""
    return _hotp(secret, int(moment.timestamp()) // step_seconds, digits=digits)


def verify_totp(
    code: str,
    secret: str,
    moment: datetime,
    *,
    digits: int = DEFAULT_DIGITS,
    step_seconds: int = DEFAULT_STEP_SECONDS,
    window_steps: int = DEFAULT_WINDOW_STEPS,
) -> bool:
    """Constant-time check of a submitted code against a small drift window."""
    candidate = (code or "").strip().replace(" ", "")
    if not candidate.isdigit() or len(candidate) != digits:
        return False
    counter = int(moment.timestamp()) // step_seconds
    # hmac.compare_digest keeps the comparison constant-time; the loop length is
    # fixed, so no information leaks through timing.
    matched = False
    for offset in range(-window_steps, window_steps + 1):
        expected = _hotp(secret, counter + offset, digits=digits)
        matched |= hmac.compare_digest(candidate, expected)
    return matched


def provisioning_uri(*, secret: str, account: str, issuer: str) -> str:
    """``otpauth://`` URI for the authenticator app QR code."""
    label = quote(f"{issuer}:{account}", safe="")
    query = urlencode({"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": DEFAULT_DIGITS, "period": DEFAULT_STEP_SECONDS})
    return f"otpauth://totp/{label}?{query}"


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Human-transferable single-use codes (shown once, stored hashed)."""
    codes = []
    for _ in range(count):
        raw = base64.b32encode(secrets.token_bytes(10)).decode("ascii").rstrip("=")
        formatted = f"{raw[:5]}-{raw[5:10]}-{raw[10:]}"
        codes.append(formatted)
    return codes


def hash_recovery_code(code: str) -> str:
    """Normalise (case/format-insensitive) and hash a recovery code."""
    normalized = (code or "").strip().replace("-", "").replace(" ", "").upper()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
