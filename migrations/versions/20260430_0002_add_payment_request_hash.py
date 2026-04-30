"""add payment request hash

Revision ID: 20260430_0002
Revises: 20260427_0001
Create Date: 2026-04-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260430_0002"
down_revision: str | None = "20260427_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column(
            "request_hash",
            sa.String(length=64),
            server_default="legacy",
            nullable=False,
        ),
    )
    op.alter_column("payments", "request_hash", server_default=None)


def downgrade() -> None:
    op.drop_column("payments", "request_hash")
