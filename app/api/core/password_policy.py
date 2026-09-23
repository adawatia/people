"""Password policy.

Design notes (deliberate, documented because this is a security control):

* **Length first.** Minimum 12 characters, and the ceiling is generous (256) so
  passphrases and password-manager output are never rejected.  Argon2 (the
  configured hasher) has no bcrypt-style 72-byte truncation, so a long password
  is verified in full.
* **Composition rules are kept.** They add little against a targeted attacker,
  but removing a control that exists today would be a silent weakening of the
  policy; they stay and are documented instead.
* **Strength scoring.** zxcvbn must rate the password at least 3/4, considering
  the user's own name/email/username as inputs.
* **Breach checking is pluggable and fail-open.** A password check must never
  make sign-in or password change depend on a third party being reachable.  The
  local list is the default; a remote (k-anonymity) checker can be configured and
  any network failure logs and admits the password rather than blocking the user.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

from zxcvbn import zxcvbn

from core.settings import Settings, get_settings

logger = logging.getLogger("hrms.auth.password")


class PasswordPolicyError(ValueError):
    """Raised with a user-facing reason when a password is unacceptable."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# A small, high-value blocklist.  Deliberately short: the local checker exists to
# catch the obvious "Password@123"-class choices that pass composition rules, not
# to be a full corpus (that is what the remote checker is for).
COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "password", "password1", "password123", "password@123", "passw0rd", "p@ssw0rd", "p@ssword123",
        "123456", "1234567", "12345678", "123456789", "1234567890", "12345678910", "111111", "000000",
        "qwerty", "qwerty123", "qwertyuiop", "1q2w3e4r", "1qaz2wsx", "asdfghjkl", "zxcvbnm",
        "letmein", "welcome", "welcome1", "welcome@123", "welcome123", "admin", "administrator", "admin@123",
        "root", "toor", "changeme", "changeit", "trustno1", "monkey", "dragon", "sunshine", "football",
        "baseball", "superman", "batman", "iloveyou", "princess", "whatever", "abc123", "abcd1234",
        "india123", "india@123", "hrms", "hrms@123", "hrms@1234", "people@123", "people123", "people@1234",
        "datlabs", "datlabs@123", "temp1234", "temporary@123", "test@1234", "test1234", "demo@1234",
        "employee@123", "company@123", "office@123", "summer2026", "winter2026", "spring2026",
    }
)


@dataclass(frozen=True)
class PasswordCheckContext:
    """Personal information a password must not contain."""

    email: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None

    def inputs(self) -> list[str]:
        parts: list[str] = []
        if self.email:
            parts.append(str(self.email).split("@")[0])
            parts.append(str(self.email))
        for value in (self.username, self.first_name, self.last_name):
            if value:
                parts.append(str(value))
        return [part.strip().lower() for part in parts if part and part.strip()]


class BreachChecker:
    """Interface for a compromised-password check."""

    async def is_breached(self, password: str) -> bool:  # pragma: no cover - interface
        raise NotImplementedError


class NullBreachChecker(BreachChecker):
    """``PASSWORD_BREACH_CHECK=off``."""

    async def is_breached(self, password: str) -> bool:
        return False


class LocalBreachChecker(BreachChecker):
    """Embedded common-password list plus trivial pattern detection."""

    async def is_breached(self, password: str) -> bool:
        lowered = password.lower()
        if lowered in COMMON_PASSWORDS:
            return True
        # Strip a trailing year/season and punctuation: "Welcome@2026" is the
        # same guess as "welcome" to any real cracker.
        simplified = re.sub(r"[\d\W_]+", "", lowered)
        if simplified and simplified in COMMON_PASSWORDS:
            return True
        # Sequential runs are the second-most common human choice.
        return bool(re.search(r"(0123|1234|2345|3456|4567|5678|6789|abcd|bcde|cdef|qwer|asdf|zxcv)", lowered))


class RemoteBreachChecker(BreachChecker):
    """k-anonymity breach lookup (Have I Been Pwned range API).

    Only the first five characters of the SHA-1 hash leave the server, which is
    the documented privacy-preserving protocol.  Any failure is treated as "not
    breached" and logged: an unreachable checker must not lock users out.
    """

    def __init__(self, url: str, *, timeout_seconds: float = 2.0) -> None:
        self.url = url
        self.timeout_seconds = timeout_seconds

    async def is_breached(self, password: str) -> bool:
        # SHA-1 is required by the range API protocol, and only a truncated hash
        # prefix is ever sent.
        digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
        prefix, suffix = digest[:5], digest[5:]
        try:
            import httpx

            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(f"{self.url.rstrip('/')}/{prefix}")
                response.raise_for_status()
            return any(line.split(":")[0].strip() == suffix for line in response.text.splitlines())
        except Exception as exc:
            logger.warning(
                "breach check unavailable; admitting password",
                extra={"event": "password_breach_check_failed", "error": str(exc)[:200]},
            )
            return False


def build_breach_checker(settings: Settings | None = None) -> BreachChecker:
    resolved = settings or get_settings()
    mode = resolved.password_breach_check.strip().lower()
    if mode == "remote" and resolved.password_breach_check_url:
        return RemoteBreachChecker(resolved.password_breach_check_url)
    if mode == "off":
        return NullBreachChecker()
    return LocalBreachChecker()


def _check_composition(password: str, settings: Settings) -> None:
    if len(password) < settings.password_min_length:
        raise PasswordPolicyError(f"Password must be at least {settings.password_min_length} characters long")
    if len(password) > settings.password_max_length:
        raise PasswordPolicyError(f"Password must be at most {settings.password_max_length} characters long")
    if not re.search(r"[A-Z]", password):
        raise PasswordPolicyError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise PasswordPolicyError("Password must contain at least one lowercase letter")
    if not re.search(r"\d", password):
        raise PasswordPolicyError("Password must contain at least one number")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise PasswordPolicyError("Password must contain at least one special character")


def _squash(value: str) -> str:
    """Lower-case and drop separators, so ``Warm-Comet`` still matches ``warmcomet``.

    Without this, trivial punctuation padding (dots, dashes, underscores, spaces)
    would defeat the personal-information rule entirely.
    """
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _check_personal_info(password: str, context: PasswordCheckContext) -> None:
    squashed = _squash(password)
    for part in context.inputs():
        needle = _squash(part)
        if len(needle) >= 3 and needle in squashed:
            raise PasswordPolicyError("Password must not contain your name, email, or username")


async def validate_password_policy(
    password: str,
    *,
    context: PasswordCheckContext | None = None,
    settings: Settings | None = None,
    breach_checker: BreachChecker | None = None,
) -> None:
    """Validate a candidate password, raising ``PasswordPolicyError`` on failure."""
    if not password:
        raise PasswordPolicyError("Password is required")
    resolved = settings or get_settings()
    context = context or PasswordCheckContext()
    _check_composition(password, resolved)
    _check_personal_info(password, context)

    results = zxcvbn(password, user_inputs=context.inputs())
    if results.get("score", 0) < 3:
        reason = results.get("feedback", {}).get("warning") or "Password is too weak"
        raise PasswordPolicyError(reason)

    checker = breach_checker or build_breach_checker(resolved)
    if await checker.is_breached(password):
        raise PasswordPolicyError("This password appears in a known breach. Choose a different one.")
