"""Store leave balance quantities in half-day precision."""

import sqlalchemy as sa

from alembic import op

revision = "1b2c3d4e5f60"
down_revision = "0a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in ("allocated", "used", "pending"):
        op.alter_column(
            "leave_balances",
            column,
            existing_type=sa.Integer(),
            type_=sa.Numeric(5, 1),
            existing_nullable=False,
        )


def downgrade() -> None:
    for column in ("allocated", "used", "pending"):
        op.alter_column(
            "leave_balances",
            column,
            existing_type=sa.Numeric(5, 1),
            type_=sa.Integer(),
            existing_nullable=False,
            postgresql_using=f"trunc({column})::integer",
        )
