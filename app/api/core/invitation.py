import hashlib
import secrets
from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import User, now_ist

IST = ZoneInfo("Asia/Kolkata")
INVITATION_EXPIRE_HOURS = 48


def generate_invitation_token() -> str:
    """Generates a cryptographically secure, URL-safe random invitation token."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """Computes SHA-256 hash of the invitation token to store in the database."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def create_invitation_for_user(user: User) -> str:
    """
    Sets invitation metadata on the user model and returns the RAW token to be emailed.
    The raw token is NEVER stored in the database.
    """
    raw_token = generate_invitation_token()
    token_hash = hash_token(raw_token)
    
    user.invitation_token_hash = token_hash
    user.invitation_sent_at = now_ist()
    user.invitation_expires_at = now_ist() + timedelta(hours=INVITATION_EXPIRE_HOURS)
    user.invitation_used_at = None
    
    return raw_token


async def find_user_by_invitation_token(session: AsyncSession, raw_token: str) -> tuple[User | None, str | None]:
    """
    Locates user by raw token and verifies expiration & usage.
    Returns (User, None) if valid, or (None, error_reason) if invalid/expired/used.
    """
    if not raw_token or len(raw_token.strip()) < 10:
        return None, "Invalid invitation token format."

    token_hash = hash_token(raw_token)
    query = select(User).where(User.invitation_token_hash == token_hash)
    result = await session.execute(query)
    user = result.scalars().first()

    if not user:
        return None, "Invitation link is invalid or has already been replaced."

    if user.invitation_used_at is not None:
        return None, "This invitation link has already been used. Please log in."

    now = now_ist()
    expires_at = user.invitation_expires_at
    if expires_at is not None:
        # SQLite returns naive datetimes; normalize before comparing.
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=IST)
        if expires_at < now:
            return None, "This invitation link has expired. Please request a new invitation from your administrator."

    return user, None
