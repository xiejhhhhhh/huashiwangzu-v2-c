"""删除6个error坏账:数据库级联删(复用阶段1表顺序)+ 物理文件删 + framework_file_items软删。
坏账id: 8673 8773 8916 8942 8944 15171
删前完整备份到 data/backup/删除坏账批次_20260717.json,可回退。
用法: cd backend && .venv/bin/python 删除坏账批次_20260717.py
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DB_PASSWORD", "123rgE123")

import asyncpg

坏账IDS = [8673, 8773, 8916, 8942, 8944, 15171]
备份路径 = "data/backup/删除坏账批次_20260717.json"
上传根 = Path("data/uploads")  # 物理文件根目录
连接串 = "postgresql://postgres:123rgE123@127.0.0.1:5432/华世王镞_v2"

按document_id清理的表 = [
    "kb_artifact_lineage", "kb_analysis_artifacts", "kb_chunk_entities",
    "kb_chunk_embeddings", "kb_chunks", "kb_page_fusions", "kb_raw_data",
    "kb_document_profile_vectors", "kb_document_profiles", "kb_evidence",
    "kb_conclusion_evidence", "kb_governance_candidates", "kb_causal_candidates",
    "kb_fact_candidates", "kb_doc_subjects", "kb_image_assets", "kb_term_occurrences",
    "kb_file_knowledge_links", "kb_source_file_manifest", "kb_pipeline_stage_runs",
    "kb_pipeline_runs", "kb_pipeline_stale", "kb_retrieval_learning_events",
    "framework_system_task_queues",
]
关系表_双列 = ["kb_file_relations", "kb_doc_relations"]


async def 主流程():
    conn = await asyncpg.connect(连接串)
    ids = 坏账IDS
    idlist = ",".join(str(i) for i in ids)

    # ── 1. 备份 ──
    备份 = {
        "备份时间": datetime.now(timezone.utc).isoformat(),
        "说明": "6个error坏账删除前完整备份(华哥拍板全删,含物理文件),可回退",
        "坏账ID": ids,
        "kb_documents": [], "framework_file_items": [], "关联表": {}, "物理文件": [],
    }
    docs = await conn.fetch(f"SELECT * FROM kb_documents WHERE id IN ({idlist})")
    备份["kb_documents"] = [dict(r) for r in docs]
    file_ids = [int(r["file_id"]) for r in docs if r["file_id"] is not None]
    fidlist = ",".join(str(i) for i in file_ids) or "0"
    fitems = await conn.fetch(f"SELECT * FROM framework_file_items WHERE id IN ({fidlist})")
    备份["framework_file_items"] = [dict(r) for r in fitems]

    for t in 按document_id清理的表:
        try:
            rs = await conn.fetch(f"SELECT * FROM {t} WHERE document_id IN ({idlist})")
        except Exception as e:
            备份["关联表"][t] = {"错误": str(e)}; continue
        if rs:
            备份["关联表"][t] = [dict(r) for r in rs]
    for t in 关系表_双列:
        try:
            rs = await conn.fetch(f"SELECT * FROM {t} WHERE source_document_id IN ({idlist}) OR target_document_id IN ({idlist})")
        except Exception as e:
            备份["关联表"][t] = {"错误": str(e)}; continue
        if rs:
            备份["关联表"][t] = [dict(r) for r in rs]
    # 物理文件路径快照
    for r in fitems:
        sp = r["storage_path"]
        if sp:
            full = 上传根 / sp
            备份["物理文件"].append({"file_id": r["id"], "storage_path": sp, "存在": full.exists(), "大小": full.stat().st_size if full.exists() else 0})

    def _默认(o):
        return o.isoformat() if isinstance(o, datetime) else str(o)

    os.makedirs(os.path.dirname(备份路径), exist_ok=True)
    with open(备份路径, "w", encoding="utf-8") as f:
        json.dump(备份, f, ensure_ascii=False, indent=2, default=_默认)
    print(f"[备份] {备份路径} | docs={len(docs)} file_items={len(fitems)} 关联表{len(备份['关联表'])}张 物理文件{len(备份['物理文件'])}个")

    # ── 2. 级联硬删(事务)+ framework_file_items 软删 ──
    清理统计 = {}
    async with conn.transaction():
        for t in 按document_id清理的表:
            try:
                r = await conn.execute(f"DELETE FROM {t} WHERE document_id IN ({idlist})")
                n = int(r.split()[-1])
                if n: 清理统计[t] = n
            except Exception as e:
                print(f"[警告] 删 {t}: {e}")
        for t in 关系表_双列:
            try:
                r = await conn.execute(f"DELETE FROM {t} WHERE source_document_id IN ({idlist}) OR target_document_id IN ({idlist})")
                n = int(r.split()[-1])
                if n: 清理统计[t] = n
            except Exception as e:
                print(f"[警告] 删 {t}: {e}")
        r = await conn.execute(f"DELETE FROM kb_documents WHERE id IN ({idlist})")
        清理统计["kb_documents"] = int(r.split()[-1])
        # framework_file_items 软删(标 deleted,不硬删避免其自身外键)
        if file_ids:
            r = await conn.execute(f"UPDATE framework_file_items SET deleted=true, updated_at=now() WHERE id IN ({fidlist})")
            清理统计["framework_file_items(软删)"] = int(r.split()[-1])

    print("[删除完成] 各表:")
    for t, n in 清理统计.items():
        print(f"    {t}: {n}")

    # ── 3. 删物理文件 ──
    删文件数 = 0
    for item in 备份["物理文件"]:
        full = 上传根 / item["storage_path"]
        if full.exists():
            try:
                full.unlink()
                删文件数 += 1
                print(f"[删文件] {item['storage_path']} ({item['大小']}字节)")
            except Exception as e:
                print(f"[警告] 删物理文件失败 {item['storage_path']}: {e}")
        else:
            print(f"[跳过] 物理文件不存在 {item['storage_path']}")

    # ── 4. 验证 ──
    残留 = await conn.fetchval(f"SELECT count(*) FROM kb_documents WHERE id IN ({idlist})")
    print(f"[验证] kb_documents 残留={残留}")
    still = [i["storage_path"] for i in 备份["物理文件"] if (上传根/i["storage_path"]).exists()]
    print(f"[验证] 物理文件残留={len(still)} {still}")
    print(f"[汇总] 删文档6、物理文件删{删文件数}个")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(主流程())
