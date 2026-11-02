"""Bound deterministic authentication failures to a single PIN challenge.

Revision ID: backend_0005
Revises: backend_0004
"""

import sqlalchemy as sa
from alembic import op

revision = "backend_0005"
down_revision = "backend_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "verified_context",
        sa.Column("auth_failures", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_verified_context_auth_failures", "verified_context", "auth_failures BETWEEN 0 AND 3"
    )


def downgrade():
    op.drop_constraint("ck_verified_context_auth_failures", "verified_context", type_="check")
    op.drop_column("verified_context", "auth_failures")
