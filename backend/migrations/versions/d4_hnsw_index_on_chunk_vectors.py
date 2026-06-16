"""D4 - HNSW index on knowledge_chunk_vectors

Revision ID: d40000000001
Revises: d10000000001
Create Date: 2026-06-15 08:00:01.000000

Note: CREATE EXTENSION vector is a safety guard. D1 migration already
creates it, but adding it here ensures fresh installs without D1 also work.

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d40000000001"
down_revision: Union[str, Sequence[str], None] = "d10000000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_chunk_vectors_hnsw_embedding
        ON knowledge_chunk_vectors
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 12, ef_construction = 64)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_vectors_hnsw_embedding")
