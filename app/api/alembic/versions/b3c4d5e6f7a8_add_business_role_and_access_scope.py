"""Add explicit business role and access scope columns to employees.

Backward compatible: the legacy ``employees.role`` column is preserved and
every existing row is backfilled so its effective access is unchanged.

    EMPLOYEE            → business_role NULL,   SELF
    DEPARTMENT_MANAGER  → business_role set,    DEPARTMENT + department_id
    HR_ADMIN            → business_role set,    UNIT + unit_id
    ORGANIZATION_OWNER  → business_role set,    ORGANIZATION + NULL

A unit-scoped HR admin is therefore provisioned as ``HR_ADMIN`` + ``UNIT``;
organization-level HR is the same role with ``access_scope = 'ORGANIZATION'``
and no scope id, which the ERP integration can set explicitly.
"""

import sqlalchemy as sa

from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None

_ROLE_COLUMN = """
    CASE
        WHEN role IN ('DEPARTMENT_MANAGER', 'HR_ADMIN', 'ORGANIZATION_OWNER') THEN role
        ELSE NULL
    END
"""

_SCOPE_COLUMN = """
    CASE
        WHEN role = 'HR_ADMIN' THEN 'UNIT'
        WHEN role = 'DEPARTMENT_MANAGER' THEN 'DEPARTMENT'
        WHEN role = 'ORGANIZATION_OWNER' THEN 'ORGANIZATION'
        ELSE 'SELF'
    END
"""

_SCOPE_ID_COLUMN = """
    CASE
        WHEN role = 'HR_ADMIN' THEN unit_id
        WHEN role = 'DEPARTMENT_MANAGER' THEN department_id
        ELSE NULL
    END
"""


def upgrade() -> None:
    op.add_column("employees", sa.Column("business_role", sa.String(length=30), nullable=True))
    op.add_column(
        "employees",
        sa.Column("access_scope", sa.String(length=20), nullable=False, server_default="SELF"),
    )
    op.add_column("employees", sa.Column("access_scope_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_employees_business_role"), "employees", ["business_role"], unique=False)

    # Preserve each existing employee's current effective access.
    op.execute(
        f"""
        UPDATE employees
        SET business_role = {_ROLE_COLUMN},
            access_scope = {_SCOPE_COLUMN},
            access_scope_id = {_SCOPE_ID_COLUMN}
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_employees_business_role"), table_name="employees")
    op.drop_column("employees", "access_scope_id")
    op.drop_column("employees", "access_scope")
    op.drop_column("employees", "business_role")
