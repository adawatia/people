"""mfa replay protection, pending factor, encrypted secrets

Three changes that together close real weaknesses in the TOTP second factor:

* ``mfa_last_used_step`` makes each code single-use.  The verification path
  previously recorded a wall-clock timestamp, so one code could be replayed for
  as long as its drift window stayed open (up to ~90 seconds) and mint further
  sessions each time.
* ``mfa_pending_secret`` separates a replacement factor from the active one.
  ``start_enrollment`` used to overwrite the live seed and clear ``mfa_enabled``
  immediately, so an abandoned "issue a new secret" left the account with MFA
  off and a dead authenticator.
* ``mfa_secret`` is widened to hold AES-256-GCM ciphertext instead of a plaintext
  seed.  Existing rows are encrypted **only when ``MFA_ENCRYPTION_KEY`` is set**
  in the environment: a migration must not fail a deploy over a missing key, and
  a value without the ``v1:`` prefix is still read as-is (then re-encrypted on the
  next write), so a partially migrated deployment keeps working either way.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
"""

from __future__ import annotations

import logging

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | None = None
depends_on: str | None = None

logger = logging.getLogger("alembic.runtime.migration")


def _encrypt_existing_secrets() -> None:
    """Encrypt plaintext seeds when a real encryption key is configured."""
    from core.secret_box import DEVELOPMENT_KEY, SecretBoxError, encrypt_secret, is_encrypted  # noqa: PLC0415
    from core.settings import get_settings  # noqa: PLC0415

    key = get_settings().mfa_secret_key()
    if key == DEVELOPMENT_KEY:
        # The public development key. Encrypting production rows with it would be
        # worse than leaving them plaintext, because it *looks* protected.
        logger.warning(
            "MFA_ENCRYPTION_KEY is unset or the development default: existing TOTP "
            "secrets stay in plaintext and will be encrypted on their next write"
        )
        return

    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT user_id, mfa_secret FROM users WHERE mfa_secret IS NOT NULL")
    ).fetchall()
    upgraded = 0
    for user_id, secret in rows:
        if is_encrypted(secret):
            continue
        try:
            ciphertext = encrypt_secret(secret, key)
        except SecretBoxError as exc:  # pragma: no cover - misconfiguration guard
            logger.warning("Could not encrypt the TOTP secret for user %s: %s", user_id, exc)
            continue
        connection.execute(
            sa.text("UPDATE users SET mfa_secret = :secret WHERE user_id = :user_id"),
            {"secret": ciphertext, "user_id": user_id},
        )
        upgraded += 1
    if upgraded:
        logger.info("Encrypted %d existing TOTP secret(s)", upgraded)


def upgrade() -> None:
    # Existing seeds widen first, so the column can hold ciphertext either way.
    op.alter_column(
        "users",
        "mfa_secret",
        existing_type=sa.String(length=64),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
    op.add_column("users", sa.Column("mfa_pending_secret", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("mfa_last_used_step", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("password_recovery_token_hash", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("password_recovery_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_users_password_recovery_token_hash"), "users", ["password_recovery_token_hash"], unique=False)
    _encrypt_existing_secrets()


def downgrade() -> None:
    # Deliberately no un-encryption: the plaintext seed is not recoverable without
    # the key at rollback time, and writing ciphertext into a 64-character column
    # would truncate it.  Shorten only if it fits; rows that would not fit keep
    # their value, which is why the widening is the last thing to be reverted.
    connection = op.get_bind()
    oversized = connection.execute(
        sa.text("SELECT count(*) FROM users WHERE length(mfa_secret) > 64 OR length(mfa_pending_secret) > 64")
    ).scalar_one()
    op.drop_column("users", "mfa_last_used_step")
    op.drop_column("users", "mfa_pending_secret")
    op.drop_index(op.f("ix_users_password_recovery_token_hash"), table_name="users")
    op.drop_column("users", "password_recovery_expires_at")
    op.drop_column("users", "password_recovery_token_hash")
    if oversized:
        logger.warning(
            "Leaving users.mfa_secret at 255: %d encrypted value(s) do not fit the "
            "previous 64-character column. Affected accounts must re-enrol if the "
            "column is shortened manually.",
            oversized,
        )
        return
    op.alter_column(
        "users",
        "mfa_secret",
        existing_type=sa.String(length=255),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
