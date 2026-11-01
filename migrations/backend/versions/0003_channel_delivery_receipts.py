"""Minimal durable delivery receipts independent of conversational ingress.

Revision ID: backend_0003
Revises: backend_0002
"""

import sqlalchemy as sa
from alembic import op

revision = "backend_0003"
down_revision = "backend_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "channel_delivery_event",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("inbox_id", sa.Text(), nullable=False),
        sa.Column("conversation_id", sa.Text(), nullable=False),
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column("delivery_status", sa.String(20), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outbox_id", sa.Uuid(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pending_reason", sa.String(60), nullable=True),
        sa.CheckConstraint("delivery_status IN ('unknown','delivered','read','failed')"),
        sa.ForeignKeyConstraint(["outbox_id"], ["outbox.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "message_id", "delivery_status"),
    )
    op.create_index(
        "ix_channel_delivery_pending", "channel_delivery_event", ["processed_at", "received_at"]
    )


def downgrade():
    op.drop_index("ix_channel_delivery_pending", table_name="channel_delivery_event")
    op.drop_table("channel_delivery_event")
