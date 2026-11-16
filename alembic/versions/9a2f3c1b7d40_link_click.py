"""link_click

Revision ID: 9a2f3c1b7d40
Revises: 3fd8e7597199
Create Date: 2026-11-12

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a2f3c1b7d40"
down_revision: str | None = "3fd8e7597199"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "link_click",
        sa.Column("url", sa.String(length=512), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("count", sa.BigInteger(), nullable=True),
        sa.Column("last_time", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("url"),
    )


def downgrade() -> None:
    op.drop_table("link_click")
