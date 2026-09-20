"""add_organization_profile_fields

Revision ID: 9b7c2a1d4e5f
Revises: 73c3bcfdfaa2
Create Date: 2026-09-20 00:00:00.000000
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "9b7c2a1d4e5f"
down_revision: str | None = "73c3bcfdfaa2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("address_line1", sa.String(length=255), nullable=True))
    op.add_column("organizations", sa.Column("address_line2", sa.String(length=255), nullable=True))
    op.add_column("organizations", sa.Column("city", sa.String(length=100), nullable=True))
    op.add_column("organizations", sa.Column("state", sa.String(length=100), nullable=True))
    op.add_column("organizations", sa.Column("country", sa.String(length=100), nullable=True))
    op.add_column("organizations", sa.Column("postal_code", sa.String(length=20), nullable=True))
    op.add_column("organizations", sa.Column("phone", sa.String(length=30), nullable=True))
    op.add_column("organizations", sa.Column("email", sa.String(length=320), nullable=True))
    op.add_column("organizations", sa.Column("website", sa.String(length=255), nullable=True))
    op.add_column("organizations", sa.Column("tax_id", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "tax_id")
    op.drop_column("organizations", "website")
    op.drop_column("organizations", "email")
    op.drop_column("organizations", "phone")
    op.drop_column("organizations", "postal_code")
    op.drop_column("organizations", "country")
    op.drop_column("organizations", "state")
    op.drop_column("organizations", "city")
    op.drop_column("organizations", "address_line2")
    op.drop_column("organizations", "address_line1")
