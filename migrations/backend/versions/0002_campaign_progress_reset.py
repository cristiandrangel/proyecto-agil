"""Campaign progress timestamps and resumable coordinated reset maintenance.

Revision ID: backend_0002
Revises: backend_0001
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "backend_0002"
down_revision = "backend_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "inbox_event",
        sa.Column("identity_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("inbox_event", "identity_revision", server_default=None)
    op.add_column(
        "human_case",
        sa.Column("open_observed", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("human_case", "open_observed", server_default=None)
    op.add_column(
        "campaign_recipient", sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "campaign_recipient", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("campaign_recipient", sa.Column("reason", sa.String(100), nullable=True))
    op.add_column(
        "reset_metadata",
        sa.Column("maintenance_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("reset_metadata", "maintenance_mode", server_default=None)
    op.add_column("reset_metadata", sa.Column("reset_operation_key", sa.Text(), nullable=True))
    op.add_column("reset_metadata", sa.Column("reset_stage", sa.String(40), nullable=True))
    op.add_column("reset_metadata", sa.Column("reset_result", JSONB(), nullable=True))

    op.execute("""
        CREATE OR REPLACE FUNCTION backend_immutable_destination() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.thread_id IS DISTINCT FROM OLD.thread_id
             OR NEW.account_id IS DISTINCT FROM OLD.account_id
             OR NEW.inbox_id IS DISTINCT FROM OLD.inbox_id
             OR NEW.conversation_id IS DISTINCT FROM OLD.conversation_id
             OR NEW.identity_revision IS DISTINCT FROM OLD.identity_revision THEN
            RAISE EXCEPTION 'event/output destination or identity revision is immutable';
          END IF;
          RETURN NEW;
        END $$;
    """)


def downgrade():
    op.execute("""
        CREATE OR REPLACE FUNCTION backend_immutable_destination() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.thread_id IS DISTINCT FROM OLD.thread_id
             OR NEW.account_id IS DISTINCT FROM OLD.account_id
             OR NEW.inbox_id IS DISTINCT FROM OLD.inbox_id
             OR NEW.conversation_id IS DISTINCT FROM OLD.conversation_id THEN
            RAISE EXCEPTION 'event/output destination is immutable';
          END IF;
          RETURN NEW;
        END $$;
    """)
    op.drop_column("inbox_event", "identity_revision")
    op.drop_column("human_case", "open_observed")
    for column in ("reset_result", "reset_stage", "reset_operation_key", "maintenance_mode"):
        op.drop_column("reset_metadata", column)
    for column in ("reason", "processed_at", "sent_at"):
        op.drop_column("campaign_recipient", column)
