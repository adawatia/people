"""Reconcile password-recovery columns for databases with an older MFA head."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add columns that may be absent when d5 was applied before it was amended."""
    connection = op.get_bind()
    columns = {column["name"] for column in sa.inspect(connection).get_columns("users")}

    if "password_recovery_token_hash" not in columns:
        op.add_column("users", sa.Column("password_recovery_token_hash", sa.String(length=64), nullable=True))
    if "password_recovery_expires_at" not in columns:
        op.add_column("users", sa.Column("password_recovery_expires_at", sa.DateTime(timezone=True), nullable=True))

    indexes = {index["name"] for index in sa.inspect(connection).get_indexes("users")}
    if "ix_users_password_recovery_token_hash" not in indexes:
        op.create_index(
            "ix_users_password_recovery_token_hash",
            "users",
            ["password_recovery_token_hash"],
            unique=False,
        )


def downgrade() -> None:
    # This reconciliation may be a no-op on a fresh database where d5 already
    # created the columns, so it must not remove columns owned by that migration.
    pass
