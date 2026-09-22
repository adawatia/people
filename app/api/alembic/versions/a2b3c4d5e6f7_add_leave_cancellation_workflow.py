"""Add audited early-return fields to leave applications."""

import sqlalchemy as sa

from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "9a1d2e3f4b5c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leave_applications", sa.Column("cancellation_requested_by", sa.Integer(), nullable=True))
    op.add_column("leave_applications", sa.Column("cancellation_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leave_applications", sa.Column("cancellation_effective_date", sa.Date(), nullable=True))
    op.add_column("leave_applications", sa.Column("cancellation_reason", sa.Text(), nullable=True))
    op.add_column("leave_applications", sa.Column("cancellation_actioned_by", sa.Integer(), nullable=True))
    op.add_column("leave_applications", sa.Column("cancellation_actioned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leave_applications", sa.Column("cancellation_rejection_reason", sa.Text(), nullable=True))
    op.create_foreign_key("fk_leave_cancellation_requested_by", "leave_applications", "users", ["cancellation_requested_by"], ["user_id"])
    op.create_foreign_key("fk_leave_cancellation_actioned_by", "leave_applications", "users", ["cancellation_actioned_by"], ["user_id"])


def downgrade() -> None:
    op.drop_constraint("fk_leave_cancellation_actioned_by", "leave_applications", type_="foreignkey")
    op.drop_constraint("fk_leave_cancellation_requested_by", "leave_applications", type_="foreignkey")
    op.drop_column("leave_applications", "cancellation_rejection_reason")
    op.drop_column("leave_applications", "cancellation_actioned_at")
    op.drop_column("leave_applications", "cancellation_actioned_by")
    op.drop_column("leave_applications", "cancellation_reason")
    op.drop_column("leave_applications", "cancellation_effective_date")
    op.drop_column("leave_applications", "cancellation_requested_at")
    op.drop_column("leave_applications", "cancellation_requested_by")
