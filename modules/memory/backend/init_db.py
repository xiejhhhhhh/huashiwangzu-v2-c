"""Memory module table initialization (idempotent)."""
import logging

from app.database import engine
from sqlalchemy import text

from .models import MemoryChunk, MemoryExperience, MemoryLink, MemoryRecord, MemoryStableRule

logger = logging.getLogger("v2.memory").getChild("init_db")

TABLES = [MemoryRecord.__table__, MemoryLink.__table__, MemoryExperience.__table__, MemoryChunk.__table__, MemoryStableRule.__table__]


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
            "ALTER TABLE memory_experiences ADD COLUMN IF NOT EXISTS owner_id INTEGER",
            "ALTER TABLE memory_experiences ADD COLUMN IF NOT EXISTS scope VARCHAR(16)",
            "UPDATE memory_experiences SET scope = 'global' WHERE scope IS NULL",
            "ALTER TABLE memory_experiences ALTER COLUMN scope SET DEFAULT 'user'",
            "ALTER TABLE memory_experiences ALTER COLUMN scope SET NOT NULL",
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

        chunk_alters = [
            "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS owner_id INTEGER",
            "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS memory_record_id INTEGER",
            "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS chunk_index INTEGER DEFAULT 0",
            "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS summary TEXT",
            "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS embedding vector(1024)",
            "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS source VARCHAR(32)",
            "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS conversation_id BIGINT",
            "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS provenance TEXT",
            "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS start_char INTEGER",
            "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS end_char INTEGER",
            "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS confidence FLOAT DEFAULT 1.0",
            "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS access_count INTEGER DEFAULT 0",
            "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE memory_chunks ALTER COLUMN confidence SET DEFAULT 1.0",
            "ALTER TABLE memory_chunks ALTER COLUMN access_count SET DEFAULT 0",
            "ALTER TABLE memory_chunks ALTER COLUMN embedding TYPE vector(1024) USING embedding::vector(1024)",
        ]
        for alter in chunk_alters:
            try:
                await conn.execute(text(alter))
            except Exception as e:
                logger.warning("Chunk ALTER non-fatal: %s", e)

        stable_rule_alters = [
            "ALTER TABLE memory_stable_rules ADD COLUMN IF NOT EXISTS owner_id INTEGER",
            "ALTER TABLE memory_stable_rules ADD COLUMN IF NOT EXISTS rule_type VARCHAR(32)",
            "ALTER TABLE memory_stable_rules ADD COLUMN IF NOT EXISTS content TEXT",
            "ALTER TABLE memory_stable_rules ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 0",
            "ALTER TABLE memory_stable_rules ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT true",
            "ALTER TABLE memory_stable_rules ADD COLUMN IF NOT EXISTS source VARCHAR(64)",
            "ALTER TABLE memory_stable_rules ADD COLUMN IF NOT EXISTS hit_count INTEGER DEFAULT 0",
            "ALTER TABLE memory_stable_rules ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE memory_stable_rules ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
            "ALTER TABLE memory_stable_rules ALTER COLUMN priority SET DEFAULT 0",
            "ALTER TABLE memory_stable_rules ALTER COLUMN active SET DEFAULT true",
            "ALTER TABLE memory_stable_rules ALTER COLUMN hit_count SET DEFAULT 0",
        ]
        for alter in stable_rule_alters:
            try:
                await conn.execute(text(alter))
            except Exception as e:
                logger.warning("Stable rule ALTER non-fatal: %s", e)

        orphan_chunk_cleanup_sql = """
            DELETE FROM memory_chunks c
            WHERE c.memory_record_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM memory_records r WHERE r.id = c.memory_record_id
              )
        """
        orphan_link_cleanup_sql = """
            DELETE FROM memory_links l
            WHERE l.from_id = l.to_id
               OR NOT EXISTS (
                SELECT 1 FROM memory_records r WHERE r.id = l.from_id
            )
               OR NOT EXISTS (
                SELECT 1 FROM memory_records r WHERE r.id = l.to_id
            )
        """
        try:
            await conn.execute(text(orphan_chunk_cleanup_sql))
            await conn.execute(text(orphan_link_cleanup_sql))
        except Exception as e:
            logger.warning("Memory orphan cleanup non-fatal: %s", e)

        link_dedupe_sql = """
            DELETE FROM memory_links ml
            USING memory_links dup
            WHERE ml.id > dup.id
              AND ml.owner_id = dup.owner_id
              AND LEAST(ml.from_id, ml.to_id) = LEAST(dup.from_id, dup.to_id)
              AND GREATEST(ml.from_id, ml.to_id) = GREATEST(dup.from_id, dup.to_id)
              AND ml.relation = dup.relation
        """
        try:
            await conn.execute(text(link_dedupe_sql))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_memory_links_owner_pair_relation "
                "ON memory_links (owner_id, LEAST(from_id, to_id), GREATEST(from_id, to_id), relation)"
            ))
        except Exception as e:
            logger.warning("Memory link unique index non-fatal: %s", e)

        try:
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_memory_experiences_scope_owner "
                "ON memory_experiences (scope, owner_id)"
            ))
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_memory_experiences_active_scope_content "
                "ON memory_experiences (scope, COALESCE(owner_id, 0), md5(trigger_condition), md5(steps)) "
                "WHERE active = true"
            ))
        except Exception as e:
            logger.warning("Experience scope indexes non-fatal: %s", e)

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
        try:
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_memory_chunks_embedding "
                "ON memory_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
            ))
        except Exception as e:
            logger.warning("Chunk vector index creation non-fatal: %s", e)
    logger.info("Memory tables and migration ensured")
