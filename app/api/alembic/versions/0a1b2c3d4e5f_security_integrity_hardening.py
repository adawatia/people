"""security and workflow integrity hardening

Revision ID: 0a1b2c3d4e5f
Revises: f7a8b9c0d1e2
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0a1b2c3d4e5f"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("mfa_verified_at", sa.DateTime(timezone=True), nullable=True))
    for table in ("organizations", "units", "departments", "designations", "employees", "shifts"):
        op.add_column(table, sa.Column("erp_id", sa.String(length=120), nullable=True))
        op.create_index(f"ix_{table}_erp_id", table, ["erp_id"], unique=True)

    op.create_table(
        "notification_receipts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("notification_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.notification_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_id", "user_id", name="uq_notification_receipt_user"),
    )
    op.create_index("ix_notification_receipts_notification_id", "notification_receipts", ["notification_id"])
    op.create_index("ix_notification_receipts_user_id", "notification_receipts", ["user_id"])

    # Preserve read state for direct notifications. Shared rows cannot be
    # backfilled safely because the old schema did not record which viewer read.
    op.execute(
        """
        INSERT INTO notification_receipts (notification_id, user_id, read_at)
        SELECT notification_id, user_id, COALESCE(created_at, now())
        FROM notifications
        WHERE user_id IS NOT NULL AND is_read IS TRUE
        ON CONFLICT DO NOTHING
        """
    )

    op.create_unique_constraint(
        "uq_leave_allocation_period",
        "leave_allocations",
        ["employee_id", "leave_type_id", "leave_period_id"],
    )
    op.create_unique_constraint(
        "uq_leave_ledger_transaction",
        "leave_ledger_entries",
        ["transaction_type", "transaction_id"],
    )
    op.create_unique_constraint(
        "uq_leave_balance_year",
        "leave_balances",
        ["employee_id", "leave_type_id", "year"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_leave_balance_year", "leave_balances", type_="unique")
    op.drop_constraint("uq_leave_ledger_transaction", "leave_ledger_entries", type_="unique")
    op.drop_constraint("uq_leave_allocation_period", "leave_allocations", type_="unique")
    op.drop_index("ix_notification_receipts_user_id", table_name="notification_receipts")
    op.drop_index("ix_notification_receipts_notification_id", table_name="notification_receipts")
    op.drop_table("notification_receipts")
    for table in reversed(("organizations", "units", "departments", "designations", "employees", "shifts")):
        op.drop_index(f"ix_{table}_erp_id", table_name=table)
        op.drop_column(table, "erp_id")
    op.drop_column("auth_sessions", "mfa_verified_at")
