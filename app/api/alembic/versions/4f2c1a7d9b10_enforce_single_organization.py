"""enforce one organization record"""

import sqlalchemy as sa

from alembic import op

revision = "4f2c1a7d9b10"
down_revision = "8d57e49c7af9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("singleton_key", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_unique_constraint(
        "uq_organizations_singleton_key",
        "organizations",
        ["singleton_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_organizations_singleton_key", "organizations", type_="unique")
    op.drop_column("organizations", "singleton_key")
