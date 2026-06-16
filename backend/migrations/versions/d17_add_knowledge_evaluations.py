"""add_knowledge_evaluations

Revision ID: d17000000001
Revises: d16000000001
Create Date: 2026-06-15 21:05:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d17000000001"
down_revision: Union[str, Sequence[str], None] = "d16000000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_evaluations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_name", sa.String(length=128), nullable=False),
        sa.Column("dataset_version", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=True),
        sa.Column("question_count", sa.Integer(), nullable=True),
        sa.Column("passed_count", sa.Integer(), nullable=True),
        sa.Column("average_score", sa.Float(), nullable=True),
        sa.Column("recall_rate", sa.Float(), nullable=True),
        sa.Column("hallucination_rate", sa.Float(), nullable=True),
        sa.Column("average_latency_ms", sa.Integer(), nullable=True),
        sa.Column("summary", postgresql.JSONB(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_knowledge_evaluations_created_at", "knowledge_evaluations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_evaluations_created_at", table_name="knowledge_evaluations")
    op.drop_table("knowledge_evaluations")
