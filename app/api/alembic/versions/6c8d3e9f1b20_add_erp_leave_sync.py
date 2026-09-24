"""Add ERP synchronization metadata to leave applications."""

import sqlalchemy as sa

from alembic import op

revision = "6c8d3e9f1b20"
down_revision = "5b7c2d8e1a90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leave_applications",
        sa.Column("erp_event_id", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "leave_applications",
        sa.Column("erp_sync_status", sa.String(length=30), server_default="PENDING", nullable=False),
    )
    op.add_column(
        "leave_applications",
        sa.Column("erp_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_leave_applications_erp_event_id",
        "leave_applications",
        ["erp_event_id"],
        unique=True,
    )
    op.create_index(
        "ix_leave_applications_erp_sync_status",
        "leave_applications",
        ["erp_sync_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_leave_applications_erp_sync_status", table_name="leave_applications")
    op.drop_index("ix_leave_applications_erp_event_id", table_name="leave_applications")
    op.drop_column("leave_applications", "erp_synced_at")
    op.drop_column("leave_applications", "erp_sync_status")
    op.drop_column("leave_applications", "erp_event_id")
