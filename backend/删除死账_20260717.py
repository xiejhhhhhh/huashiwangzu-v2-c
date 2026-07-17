"""一次性硬删除3个铁死账文档 + 级联清关联表,删前导出JSON备份可回退。
死账: 8639(美容18W.xlsx 0字节) / 18029(DSC04238.jpg 0字节) / 14610(DSC09219.jpg 垃圾字节)
用法: cd backend && .venv/bin/python 删除死账_20260717.py
"""
import asyncio
import json
import os
from datetime import datetime, timezone

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DB_PASSWORD", "123rgE123")

import asyncpg

死账IDS = [8639, 18029, 14610]
备份路径 = "data/backup/删除死账备份_20260717.json"
连接串 = "postgresql://postgres:123rgE123@127.0.0.1:5432/华世王镞_v2"

# 清理顺序: 先子表(引用document_id)再主表。含所有实测有数据+可能有数据的关联表。
按document_id清理的表 = [
    "kb_artifact_lineage",
    "kb_analysis_artifacts",
    "kb_chunk_entities",
    "kb_chunk_embeddings",
    "kb_chunks",
    "kb_page_fusions",
    "kb_raw_data",
    "kb_document_profile_vectors",
    "kb_document_profiles",
    "kb_evidence",
    "kb_conclusion_evidence",
    "kb_governance_candidates",
    "kb_causal_candidates",
    "kb_fact_candidates",
    "kb_doc_subjects",
    "kb_image_assets",
    "kb_term_occurrences",
    "kb_file_knowledge_links",
    "kb_source_file_manifest",
    "kb_pipeline_stage_runs",
    "kb_pipeline_runs",
    "kb_pipeline_stale",
    "kb_retrieval_learning_events",
    "framework_system_task_queues",
]
# 关系表用 source/target 双列
关系表_双列 = ["kb_file_relations", "kb_doc_relations"]


async def 主流程():
    conn = await asyncpg.connect(连接串)
    ids = 死账IDS
    idlist = ",".join(str(i) for i in ids)

    # ── 1. 导出备份 ──
    备份 = {
        "备份时间": datetime.now(timezone.utc).isoformat(),
        "说明": "硬删除3个铁死账前的完整备份, 可回退",
        "死账ID": ids,
        "kb_documents": [],
        "关联表": {},
    }
    rows = await conn.fetch(f"SELECT * FROM kb_documents WHERE id IN ({idlist})")
    备份["kb_documents"] = [dict(r) for r in rows]

    for t in 按document_id清理的表:
        try:
            rs = await conn.fetch(f"SELECT * FROM {t} WHERE document_id IN ({idlist})")
        except Exception as e:
            备份["关联表"][t] = {"错误": str(e)}
            continue
        if rs:
            备份["关联表"][t] = [dict(r) for r in rs]

    for t in 关系表_双列:
        try:
            rs = await conn.fetch(
                f"SELECT * FROM {t} WHERE source_document_id IN ({idlist}) OR target_document_id IN ({idlist})"
            )
        except Exception as e:
            备份["关联表"][t] = {"错误": str(e)}
            continue
        if rs:
            备份["关联表"][t] = [dict(r) for r in rs]

    def _默认(o):
        if isinstance(o, datetime):
            return o.isoformat()
        return str(o)

    os.makedirs(os.path.dirname(备份路径), exist_ok=True)
    with open(备份路径, "w", encoding="utf-8") as f:
        json.dump(备份, f, ensure_ascii=False, indent=2, default=_默认)
    print(f"[备份] 已写入 {备份路径}")
    print(f"[备份] kb_documents={len(备份['kb_documents'])} 条; 关联表 {len(备份['关联表'])} 张有数据")

    # ── 2. 级联硬删(事务) ──
    清理统计 = {}
    async with conn.transaction():
        for t in 按document_id清理的表:
            try:
                r = await conn.execute(f"DELETE FROM {t} WHERE document_id IN ({idlist})")
                n = int(r.split()[-1])
                if n:
                    清理统计[t] = n
            except Exception as e:
                print(f"[警告] 删 {t} 失败(可能无此列/表): {e}")
        for t in 关系表_双列:
            try:
                r = await conn.execute(
                    f"DELETE FROM {t} WHERE source_document_id IN ({idlist}) OR target_document_id IN ({idlist})"
                )
                n = int(r.split()[-1])
                if n:
                    清理统计[t] = n
            except Exception as e:
                print(f"[警告] 删 {t} 失败: {e}")
        # 最后删主表
        r = await conn.execute(f"DELETE FROM kb_documents WHERE id IN ({idlist})")
        清理统计["kb_documents"] = int(r.split()[-1])

    print("[删除完成] 各表清理条数:")
    for t, n in 清理统计.items():
        print(f"    {t}: {n}")

    # ── 3. 验证 ──
    print("[验证] 复查各表残留:")
    残留 = 0
    d = await conn.fetchval(f"SELECT count(*) FROM kb_documents WHERE id IN ({idlist})")
    print(f"    kb_documents: {d}")
    残留 += d
    for t in 按document_id清理的表:
        try:
            c = await conn.fetchval(f"SELECT count(*) FROM {t} WHERE document_id IN ({idlist})")
            if c:
                print(f"    残留! {t}: {c}")
                残留 += c
        except Exception:
            pass
    if 残留 == 0:
        print("[验证] 通过: 3个死账及全部关联记录已清空,无孤儿")
    else:
        print(f"[验证] 警告: 仍有 {残留} 条残留")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(主流程())
