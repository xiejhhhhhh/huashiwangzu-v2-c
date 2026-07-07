"""Guarded cleanup helper for obsolete knowledge orphan data."""

import argparse
import asyncio
import logging

from app.config import get_settings
from app.database import AsyncSessionLocal
from sqlalchemy import text

logger = logging.getLogger("v2.knowledge.cleanup")
EXPECTED_DB_NAME = "华世王镞_v2"
CONFIRM_TOKEN = "CLEAN_KNOWLEDGE_ORPHANS"


async def _counts() -> dict[str, int]:
    tables = (
        "kb_page_fusions",
        "kb_raw_data",
        "kb_chunk_entities",
        "kb_evidence",
        "kb_conclusion_evidence",
        "kb_governance_candidates",
        "kb_document_profiles",
        "kb_graph_edges",
        "kb_graph_nodes",
        "kb_file_relations",
        "kb_documents",
    )
    async with AsyncSessionLocal() as db:
        result: dict[str, int] = {}
        for table in tables:
            value = await db.scalar(text(f"SELECT count(*) FROM {table}"))
            result[table] = int(value or 0)
        return result


def _assert_expected_db() -> None:
    db_name = get_settings().DB_NAME
    if db_name != EXPECTED_DB_NAME:
        raise SystemExit(f"Refusing cleanup on DB_NAME={db_name!r}; expected {EXPECTED_DB_NAME!r}")


async def cleanup(*, apply: bool, confirm: str) -> tuple[int, int, int]:
    _assert_expected_db()
    if not apply:
        counts = await _counts()
        print({"dry_run": True, "db": EXPECTED_DB_NAME, "counts": counts})
        return 0, 0, 0
    if confirm != CONFIRM_TOKEN:
        raise SystemExit(f"Refusing cleanup without --confirm {CONFIRM_TOKEN}")

    async with AsyncSessionLocal() as db:
        # 1. 删除页级融合
        r1 = await db.execute(text("DELETE FROM kb_page_fusions"))
        deleted_fusions = r1.rowcount

        # 2. 删除原始采集数据
        r2 = await db.execute(text("DELETE FROM kb_raw_data"))
        deleted_raw = r2.rowcount

        # 3. 删除其他依赖 kb_documents 的数据（图谱、关系等）
        await db.execute(text("DELETE FROM kb_chunk_entities"))
        await db.execute(text("DELETE FROM kb_evidence"))
        await db.execute(text("DELETE FROM kb_conclusion_evidence"))
        await db.execute(text("DELETE FROM kb_governance_candidates"))
        await db.execute(text("DELETE FROM kb_document_profiles"))
        await db.execute(text("DELETE FROM kb_graph_edges"))
        await db.execute(text("DELETE FROM kb_graph_nodes"))
        await db.execute(text("DELETE FROM kb_file_relations"))

        # 4. 删除文档（不含 chunks 的孤儿）
        r3 = await db.execute(text("DELETE FROM kb_documents"))
        deleted_docs = r3.rowcount

        await db.commit()

        logger.info(
            "Cleanup complete: deleted %d documents, %d raw_data, %d page_fusions",
            deleted_docs, deleted_raw, deleted_fusions,
        )
        return deleted_docs, deleted_raw, deleted_fusions


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    deleted_docs, deleted_raw, deleted_fusions = await cleanup(apply=args.apply, confirm=args.confirm)

    if args.apply:
        print(f"OK: deleted {deleted_docs} documents, {deleted_raw} raw_data, {deleted_fusions} page_fusions")
        print("Knowledge base is now clean.")


if __name__ == "__main__":
    asyncio.run(main())
