"""add ERP holiday identifier"""

from alembic import op
import sqlalchemy as sa

revision = "7d9e4f0a2b31"
down_revision = "6c8d3e9f1b20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("holidays", sa.Column("erp_holiday_id", sa.String(length=120), nullable=True))
    op.create_index("ix_holidays_erp_holiday_id", "holidays", ["erp_holiday_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_holidays_erp_holiday_id", table_name="holidays")
    op.drop_column("holidays", "erp_holiday_id")
