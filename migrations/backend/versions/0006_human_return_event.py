"""Persist the channel event which completed a human handoff.

Revision ID: backend_0006
Revises: backend_0005
"""

import sqlalchemy as sa
from alembic import op

revision = "backend_0006"
down_revision = "backend_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("human_case", sa.Column("return_event_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_human_case_return_event", "human_case", "inbox_event", ["return_event_id"], ["id"]
    )


def downgrade():
    op.drop_constraint("fk_human_case_return_event", "human_case", type_="foreignkey")
    op.drop_column("human_case", "return_event_id")
