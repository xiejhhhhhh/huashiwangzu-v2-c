"""Memory module table initialization (idempotent)."""
import logging
from sqlalchemy import text
from app.database import engine
from .models import MemoryRecord, MemoryLink, MemoryExperience
from app.models.base import Base

logger = logging.getLogger("v2.memory").getChild("init_db")

TABLES = [MemoryRecord.__table__, MemoryLink.__table__, MemoryExperience.__table__]


async def run_init() -> None:
    async with engine.begin() as conn:
        # Ensure pgvector extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        # Create tables
        for table in TABLES:
            await conn.run_sync(table.create, checkfirst=True)
        # Idempotent ALTER for new columns (safe if already exist)
        alters = [
            "ALTER TABLE memory_records ADD COLUMN IF NOT EXISTS summary TEXT",
            "ALTER TABLE memory_records ADD COLUMN IF NOT EXISTS confidence FLOAT DEFAULT 1.0",
            "ALTER TABLE memory_records ADD COLUMN IF NOT EXISTS recency_score FLOAT DEFAULT 1.0",
            "ALTER TABLE memory_records ADD COLUMN IF NOT EXISTS raw_id INTEGER",
            "ALTER TABLE memory_records ADD COLUMN IF NOT EXISTS conversation_id BIGINT",
            "ALTER TABLE memory_records ADD COLUMN IF NOT EXISTS source VARCHAR(32)",
            "ALTER TABLE memory_records ADD COLUMN IF NOT EXISTS memory_type VARCHAR(32)",
            "ALTER TABLE memory_records ADD COLUMN IF NOT EXISTS keywords TEXT",
            "ALTER TABLE memory_records ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0",
            "ALTER TABLE memory_records ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE memory_records ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE memory_records ALTER COLUMN confidence SET DEFAULT 1.0",
            "ALTER TABLE memory_records ALTER COLUMN recency_score SET DEFAULT 1.0",
            "ALTER TABLE memory_records ALTER COLUMN access_count SET DEFAULT 0",
            "ALTER TABLE memory_records ALTER COLUMN embedding TYPE vector(1024) USING embedding::vector(1024)",
        ]
        for alter in alters:
            try:
                await conn.execute(text(alter))
            except Exception as e:
                logger.warning("ALTER non-fatal: %s", e)
        # Idempotent ALTER for experience table
        exp_alters = [
            "ALTER TABLE memory_experiences ADD COLUMN IF NOT EXISTS trigger_embedding vector(1024)",
            "ALTER TABLE memory_experiences ADD COLUMN IF NOT EXISTS tools_used TEXT",
            "ALTER TABLE memory_experiences ADD COLUMN IF NOT EXISTS fail_notes TEXT",
            "ALTER TABLE memory_experiences ADD COLUMN IF NOT EXISTS source_conversation_id BIGINT",
            "ALTER TABLE memory_experiences ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT true",
            "ALTER TABLE memory_experiences ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE memory_experiences ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE memory_experiences ALTER COLUMN success_weight SET DEFAULT 1",
            "ALTER TABLE memory_experiences ALTER COLUMN fail_count SET DEFAULT 0",
        ]
        for alter in exp_alters:
            try:
                await conn.execute(text(alter))
            except Exception as e:
                logger.warning("ALTER non-fatal: %s", e)

        # Create vector index for experience embedding
        try:
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_memory_experiences_trigger_embedding "
                "ON memory_experiences USING ivfflat (trigger_embedding vector_cosine_ops) WITH (lists = 100)"
            ))
        except Exception as e:
            logger.warning("Experience vector index creation non-fatal: %s", e)

        # Create vector index for cosine similarity (IVFFlat for 1024d)
        try:
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_memory_records_embedding "
                "ON memory_records USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
            ))
        except Exception as e:
            logger.warning("Vector index creation non-fatal: %s", e)
    logger.info("Memory tables and migration ensured")
