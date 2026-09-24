"""add ERP overtime synchronization fields"""

import sqlalchemy as sa

from alembic import op

revision = "8e0f5a1b2c43"
down_revision = "7d9e4f0a2b31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("overtime_records", sa.Column("erp_event_id", sa.String(length=120), nullable=True))
    op.add_column("overtime_records", sa.Column("overtime_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("overtime_records", sa.Column("overtime_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column("overtime_records", sa.Column("source", sa.String(length=30), server_default="ERP", nullable=False))
    op.create_index("ix_overtime_records_erp_event_id", "overtime_records", ["erp_event_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_overtime_records_erp_event_id", table_name="overtime_records")
    op.drop_column("overtime_records", "source")
    op.drop_column("overtime_records", "overtime_end")
    op.drop_column("overtime_records", "overtime_start")
    op.drop_column("overtime_records", "erp_event_id")
