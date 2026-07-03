"""一次性脚本：清理知识库孤儿文档数据。

现状：kb_documents=101 条，kb_chunks=0 条（有壳无肉）。
所有文档均处于 pending 状态且无已处理的 chunks，其中 89 条的原文件已从 framework 删除。

操作：
1. 删除所有 kb_page_fusions 记录（100 条，无对应 chunks）
2. 删除所有 kb_raw_data 记录（107 条，无对应已处理文档）
3. 删除所有 kb_documents 记录（101 条，均为空壳）
4. 重置序列

执行：.venv/bin/python -m modules.knowledge.backend.cleanup_orphans
"""
import asyncio
import logging

from app.database import AsyncSessionLocal
from sqlalchemy import text

logger = logging.getLogger("v2.knowledge.cleanup")


async def cleanup():
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
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    deleted_docs, deleted_raw, deleted_fusions = await cleanup()

    print(f"OK: deleted {deleted_docs} documents, {deleted_raw} raw_data, {deleted_fusions} page_fusions")
    print("Knowledge base is now clean.")


if __name__ == "__main__":
    asyncio.run(main())
