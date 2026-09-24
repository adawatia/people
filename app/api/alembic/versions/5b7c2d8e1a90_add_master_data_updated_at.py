"""add updated_at to ERP-owned master data"""

import sqlalchemy as sa

from alembic import op

revision = "5b7c2d8e1a90"
down_revision = "4f2c1a7d9b10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("organizations", "units", "departments", "designations"):
        op.add_column(table, sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))


def downgrade() -> None:
    for table in ("designations", "departments", "units", "organizations"):
        op.drop_column(table, "updated_at")
