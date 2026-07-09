"""Add versioned knowledge chunk embedding sidecar.

Revision ID: 9f1a2b3c4d5e
Revises: 3b8f6e1a2c4d
Create Date: 2026-07-09 10:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "9f1a2b3c4d5e"
down_revision: Union[str, Sequence[str], None] = "3b8f6e1a2c4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "kb_chunk_embeddings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("chunk_id", sa.BigInteger(), nullable=False),
        sa.Column("index_layer", sa.String(length=32), nullable=False, server_default="base_parse"),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("embedding_dim", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("diagnostics_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "chunk_id",
            "embedding_model",
            "embedding_version",
            name="uq_kb_chunk_embeddings_owner_chunk_model_version",
        ),
    )
    op.create_index(
        "idx_kb_chunk_embeddings_chunk",
        "kb_chunk_embeddings",
        ["owner_id", "chunk_id"],
    )
    op.create_index(
        "idx_kb_chunk_embeddings_doc",
        "kb_chunk_embeddings",
        ["owner_id", "document_id"],
    )
    op.create_index(
        "idx_kb_chunk_embeddings_model_status",
        "kb_chunk_embeddings",
        ["owner_id", "embedding_model", "embedding_version", "status"],
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_kb_chunk_embeddings_qwen3_8b_hnsw
        ON kb_chunk_embeddings USING hnsw
        ((subvector(embedding::vector(4096), 1, 2000)::vector(2000)) vector_cosine_ops)
        WITH (m = 16, ef_construction = 200)
        WHERE embedding_model = 'qwen3-embedding-8b'
          AND embedding_version = 1
          AND embedding_dim = 4096
          AND status = 'active'
        """
    )


def downgrade() -> None:
    op.drop_index("idx_kb_chunk_embeddings_qwen3_8b_hnsw", table_name="kb_chunk_embeddings")
    op.drop_index("idx_kb_chunk_embeddings_model_status", table_name="kb_chunk_embeddings")
    op.drop_index("idx_kb_chunk_embeddings_doc", table_name="kb_chunk_embeddings")
    op.drop_index("idx_kb_chunk_embeddings_chunk", table_name="kb_chunk_embeddings")
    op.drop_table("kb_chunk_embeddings")
