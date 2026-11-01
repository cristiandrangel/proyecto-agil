"""Retain input billing categories without inventing historical usage.

Revision ID: backend_0004
Revises: backend_0003
"""

import sqlalchemy as sa
from alembic import op

revision = "backend_0004"
down_revision = "backend_0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inference_reservation", sa.Column("cached_input_tokens", sa.Integer()))
    op.add_column("inference_reservation", sa.Column("cache_write_tokens", sa.Integer()))


def downgrade():
    op.drop_column("inference_reservation", "cache_write_tokens")
    op.drop_column("inference_reservation", "cached_input_tokens")
