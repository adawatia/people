"""durable ERP outbox events and bulk batch audit

Revision ID: 3d4e5f607182
Revises: 2c3d4e5f6071
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3d4e5f607182"
down_revision: str | None = "2c3d4e5f6071"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "erp_outbox_events",
        sa.Column("sequence", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=120), nullable=True),
        sa.PrimaryKeyConstraint("sequence"),
    )
    op.create_index("ix_erp_outbox_events_event_id", "erp_outbox_events", ["event_id"], unique=True)
    # The feed query is always "unacknowledged rows in sequence order"; the
    # partial index keeps that scan proportional to the backlog, not to history.
    op.create_index(
        "ix_erp_outbox_events_pending",
        "erp_outbox_events",
        ["entity_type", "sequence"],
        unique=False,
        postgresql_where=sa.text("acknowledged_at IS NULL"),
    )
    op.create_index(
        "ix_erp_outbox_events_entity",
        "erp_outbox_events",
        ["entity_type", "entity_id"],
        unique=False,
    )

    op.create_table(
        "erp_sync_batches",
        sa.Column("batch_id", sa.String(length=128), nullable=False),
        sa.Column("endpoint", sa.String(length=80), nullable=False),
        sa.Column("client_id", sa.String(length=120), nullable=True),
        sa.Column("received_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("accepted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duplicate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("retryable_failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="COMPLETED", nullable=False),
        sa.Column("http_status", sa.Integer(), server_default="200", nullable=False),
        sa.Column("last_error_code", sa.String(length=60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("batch_id"),
    )
    op.create_index(
        "ix_erp_sync_batches_endpoint_created",
        "erp_sync_batches",
        ["endpoint", "created_at"],
        unique=False,
    )

    # Backfill: before this revision the only trace of an unacknowledged leave
    # outcome was the (overwritable) erp_event_id on the application row. Carry
    # whatever is still pending into the outbox so the switch to sequence
    # cursors cannot drop an event the ERP has not yet fetched.
    op.execute(
        """
        INSERT INTO erp_outbox_events
            (event_id, entity_type, entity_id, event_type, payload, created_at)
        SELECT
            la.erp_event_id,
            'LEAVE_APPLICATION',
            la.id,
            la.status,
            jsonb_build_object(
                'leave_id', la.id,
                'employee_code', e.employee_code,
                'leave_code', lt.code,
                'from_date', la.from_date,
                'to_date', la.to_date,
                'days', la.days_count,
                'status', la.status,
                'reason', la.reason,
                'rejection_reason', la.rejection_reason,
                'approved_at', la.actioned_at
            ),
            COALESCE(la.actioned_at, la.applied_at, now())
        FROM leave_applications la
        JOIN employees e ON e.id = la.employee_id
        JOIN leave_types lt ON lt.id = la.leave_type_id
        WHERE la.erp_event_id IS NOT NULL
          AND la.erp_sync_status <> 'ACKNOWLEDGED'
          AND la.status IN ('APPROVED', 'REJECTED', 'CANCELLED')
        ON CONFLICT (event_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_erp_sync_batches_endpoint_created", table_name="erp_sync_batches")
    op.drop_table("erp_sync_batches")
    op.drop_index("ix_erp_outbox_events_entity", table_name="erp_outbox_events")
    op.drop_index("ix_erp_outbox_events_pending", table_name="erp_outbox_events")
    op.drop_index("ix_erp_outbox_events_event_id", table_name="erp_outbox_events")
    op.drop_table("erp_outbox_events")
