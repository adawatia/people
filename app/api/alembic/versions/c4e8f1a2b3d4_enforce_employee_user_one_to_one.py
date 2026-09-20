"""enforce one employee profile per portal account

Revision ID: c4e8f1a2b3d4
Revises: 9b7c2a1d4e5f
"""

from alembic import op


revision = "c4e8f1a2b3d4"
down_revision = "9b7c2a1d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL's unique constraint permits multiple NULLs, which is required
    # for employees who do not have portal access.
    op.create_unique_constraint("uq_employees_user_id", "employees", ["user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_employees_user_id", "employees", type_="unique")
