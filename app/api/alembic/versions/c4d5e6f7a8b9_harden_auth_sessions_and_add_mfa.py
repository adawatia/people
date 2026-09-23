"""Harden auth sessions and add MFA enrolment columns.

Non-destructive and session-preserving:

* ``auth_sessions.absolute_expires_at`` is added with a backfill of
  ``created_at + REFRESH TTL`` (mirrored by the model default), so every session
  that is valid today stays valid — nobody is logged out by this migration. New
  sessions get the configured absolute lifetime, which is what stops a refresh
  chain from living forever.
* ``ip_address`` / ``user_agent`` / ``revoked_reason`` record session context
  for the signed-in-device list and the security audit.
* ``users.mfa_*`` prepares TOTP enrolment; all columns are nullable/false, so
  enabling enforcement is a configuration change rather than a deploy.

Indexes added: ``revoked_at`` (bulk revocation lookups), ``replaced_by_id``
(rotation-chain tracing) and ``absolute_expires_at`` (expiry sweeps).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "b3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 30 days — the refresh TTL that was in force when this migration runs.
_LEGACY_REFRESH_WINDOW = "interval '30 days'"


def upgrade() -> None:
    # ── auth_sessions ────────────────────────────────────────────────────────
    op.add_column(
        "auth_sessions",
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        f"UPDATE auth_sessions SET absolute_expires_at = created_at + {_LEGACY_REFRESH_WINDOW} "
        "WHERE absolute_expires_at IS NULL"
    )
    op.alter_column("auth_sessions", "absolute_expires_at", nullable=False)
    op.create_index(
        op.f("ix_auth_sessions_absolute_expires_at"), "auth_sessions", ["absolute_expires_at"], unique=False
    )

    op.add_column("auth_sessions", sa.Column("revoked_reason", sa.String(length=40), nullable=True))
    op.add_column("auth_sessions", sa.Column("ip_address", sa.String(length=64), nullable=True))
    op.add_column("auth_sessions", sa.Column("user_agent", sa.String(length=255), nullable=True))
    op.create_index(op.f("ix_auth_sessions_revoked_at"), "auth_sessions", ["revoked_at"], unique=False)
    op.create_index(op.f("ix_auth_sessions_replaced_by_id"), "auth_sessions", ["replaced_by_id"], unique=False)

    # ── users: MFA preparation ───────────────────────────────────────────────
    op.add_column("users", sa.Column("mfa_secret", sa.String(length=64), nullable=True))
    op.add_column(
        "users",
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("users", sa.Column("mfa_enrolled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("mfa_recovery_code_hashes", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("last_mfa_verified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "last_mfa_verified_at")
    op.drop_column("users", "mfa_recovery_code_hashes")
    op.drop_column("users", "mfa_enrolled_at")
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "mfa_secret")

    op.drop_index(op.f("ix_auth_sessions_replaced_by_id"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_revoked_at"), table_name="auth_sessions")
    op.drop_column("auth_sessions", "user_agent")
    op.drop_column("auth_sessions", "ip_address")
    op.drop_column("auth_sessions", "revoked_reason")
    op.drop_index(op.f("ix_auth_sessions_absolute_expires_at"), table_name="auth_sessions")
    op.drop_column("auth_sessions", "absolute_expires_at")
