"""Add indexes for dated attendance, punch lookup, and live sessions."""

import sqlalchemy as sa

from alembic import op

revision = "2c3d4e5f6071"
down_revision = "1b2c3d4e5f60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL requires CREATE INDEX CONCURRENTLY outside a transaction.
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_attendance_records_date_employee",
            "attendance_records",
            ["attendance_date", "employee_id"],
            if_not_exists=True,
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_attendance_punches_employee_time_type",
            "attendance_punches",
            ["employee_id", "punch_time", "punch_type"],
            if_not_exists=True,
            postgresql_concurrently=True,
        )
        op.create_index(
            "ix_auth_sessions_live_user_created",
            "auth_sessions",
            ["user_id", sa.text("created_at DESC"), sa.text("id DESC")],
            postgresql_where=sa.text("revoked_at IS NULL"),
            if_not_exists=True,
            postgresql_concurrently=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for table, name in (
            ("auth_sessions", "ix_auth_sessions_live_user_created"),
            ("attendance_punches", "ix_attendance_punches_employee_time_type"),
            ("attendance_records", "ix_attendance_records_date_employee"),
        ):
            op.drop_index(name, table_name=table, if_exists=True, postgresql_concurrently=True)
