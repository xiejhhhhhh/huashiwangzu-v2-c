"""add_bound_conclusions_to_evidences

Revision ID: d16000000001
Revises: d15000000001
Create Date: 2026-06-15 20:46:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa


revision: str = "d16000000001"
down_revision: Union[str, Sequence[str], None] = "d15000000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_evidences",
        sa.Column("bound_conclusions", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_evidences", "bound_conclusions")
