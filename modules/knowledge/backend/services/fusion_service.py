"""第4层页级融合服务。

把同一页的三轮独立采集结果（文本 / OCR / 视觉构成）交叉印证，
消解冲突，输出带置信度的权威描述。

后台任务模式（kb_fuse）：逐页 fuse → 逐页 commit，超时只丢当前页。
"""
import json
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.gateway.router import gateway_router
from app.services.task_worker import register_task_handler

from ..models import KbDocument, KbPageFusion, KbRawData

logger = logging.getLogger("v2.knowledge").getChild("fusion")

FUSION_SYSTEM_PROMPT = """你是企业文档内容融合专家。以下是对同一文档页的三轮独立采集结果，请交叉印证后输出融合内容。

规则：
1. 三轮一致的直接取信
2. 有两轮一致、一轮偏离的，采信多数，在 conflicts 中记录不一致
3. 三轮全不同时，按常识判断最合理的，置信度降低
4. 保持原文信息不丢失，禁止编造
5. 用中文输出

输出严格 JSON（不要 markdown 代码块标记）：
{
  "fused_text": "交叉印证后的权威正文",
  "page_summary": "一句话页面摘要",
  "page_title": "页面标题(如有)",
  "entities": [{"name": "实体名", "type": "人名/组织/产品/术语/事件/其他"}],
  "attributes": {"键": "值"},
  "tags": ["标签1", "标签2"],
  "conflicts": [{"type": "内容矛盾/数量矛盾/格式矛盾", "detail": "具体描述", "rounds": [1,2,3]}],
  "confidence": 0.85
}"""


def _detect_simple_conflicts(
    round_texts: dict[int, str],
) -> list[dict]:
    """简单启发式冲突检测（行数差异/长度差异过大）。"""
    conflicts = []
    lines = {r: len(t.splitlines()) if t else 0 for r, t in round_texts.items()}
    chars = {r: len(t) if t else 0 for r, t in round_texts.items()}

    # 文本轮 vs OCR轮 行数差异 >5 行 → 潜在冲突
    if lines.get(1, 0) > 0 and lines.get(2, 0) > 0:
        if abs(lines[1] - lines[2]) > 5:
            conflicts.append({
                "type": "行数矛盾",
                "detail": f"文本提取 {lines[1]} 行 vs OCR {lines[2]} 行",
                "rounds": [1, 2],
            })

    # 长度差异 >50% → 内容矛盾
    for r1, r2 in [(1, 2), (1, 3), (2, 3)]:
        c1, c2 = chars.get(r1, 0), chars.get(r2, 0)
        if c1 > 0 and c2 > 0 and max(c1, c2) / max(min(c1, c2), 1) > 2.0:
            conflicts.append({
                "type": "长度矛盾",
                "detail": f"Round {r1}: {c1} chars vs Round {r2}: {c2} chars",
                "rounds": [r1, r2],
            })

    return conflicts[:5]  # 最多 5 条


def _compute_confidence(round_texts: dict[int, str], conflicts: list[dict]) -> float:
    """启发式置信度计算。

    参考 V1 规则：
    - 3 轮都有内容且无冲突 → 0.92
    - 3 轮都有内容但有冲突 → 0.80
    - 2 轮有内容 → 0.75
    - 1 轮有内容 → 0.60
    - 全空 → 0.30
    """
    non_empty = sum(1 for t in round_texts.values() if t and len(t.strip()) > 10)
    has_conflicts = len(conflicts) > 0

    if non_empty >= 3:
        return 0.80 if has_conflicts else 0.92
    elif non_empty == 2:
        return 0.70 if has_conflicts else 0.75
    elif non_empty == 1:
        return 0.60
    else:
        return 0.30


async def _llm_fuse(round_texts: dict[int, str]) -> dict:
    """调用 LLM 进行交叉印证融合。"""
    user_message = f"""请交叉印证以下三轮采集结果，输出融合后的权威描述。

=== 第1轮：文本提取 ===
{round_texts.get(1, '(无)')[:4000]}

=== 第2轮：截图 OCR ===
{round_texts.get(2, '(无)')[:4000]}

=== 第3轮：视觉构成 ===
{round_texts.get(3, '(无)')[:4000]}"""

    try:
        result = await gateway_router.chat(
            messages=[
                {"role": "system", "content": FUSION_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            profile_key="deepseek-v4-flash",
        )
        content = (result.get("content") or "").strip()
        # 去除可能的 markdown 代码块标记
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:]) if len(lines) > 1 else content
            if content.endswith("```"):
                content = content[:-3].strip()
        return json.loads(content)
    except Exception as e:
        logger.warning("LLM fusion failed, using heuristic fallback: %s", e)
        return {
            "fused_text": round_texts.get(1, "") or round_texts.get(2, "") or round_texts.get(3, ""),
            "page_summary": "",
            "page_title": None,
            "entities": [],
            "attributes": {},
            "tags": [],
            "conflicts": [],
            "confidence": _compute_confidence(round_texts, []),
        }


async def fuse_page(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
    page: int,
) -> dict:
    """第4层页级融合：交叉印证 → 冲突消解 → 权威描述。

    返回融合结果 dict，包含 fused_text / confidence / conflicts 等。
    """
    # 1. 读取该页三轮原始数据
    r = await db.execute(
        select(KbRawData)
        .where(
            KbRawData.document_id == document_id,
            KbRawData.page == page,
        )
        .order_by(KbRawData.round)
    )
    raw_records = r.scalars().all()

    round_texts: dict[int, str] = {}
    for rec in raw_records:
        round_texts[rec.round] = rec.content or ""

    if not round_texts:
        logger.warning("No raw data for document_id=%d page=%d", document_id, page)
        return {"fused_text": "", "confidence": 0.0, "conflicts": [], "page": page}

    # 2. 启发式冲突检测
    simple_conflicts = _detect_simple_conflicts(round_texts)

    # 3. LLM 交叉印证融合
    fusion_result = await _llm_fuse(round_texts)

    # 4. 综合置信度（LLM 给的 + 启发式加权）
    llm_confidence = fusion_result.get("confidence", 0.7)
    heuristic_confidence = _compute_confidence(round_texts, simple_conflicts)
    final_confidence = round((llm_confidence * 0.6 + heuristic_confidence * 0.4), 2)

    # 5. 合并冲突记录
    all_conflicts = fusion_result.get("conflicts", []) + simple_conflicts

    # 6. 写入 kb_page_fusions
    from sqlalchemy import delete as sa_delete
    await db.execute(
        sa_delete(KbPageFusion).where(
            KbPageFusion.document_id == document_id,
            KbPageFusion.page == page,
        )
    )

    pf = KbPageFusion(
        document_id=document_id,
        owner_id=owner_id,
        page=page,
        fused_text=fusion_result.get("fused_text", ""),
        page_summary=fusion_result.get("page_summary", ""),
        page_title=fusion_result.get("page_title"),
        body_json=fusion_result.get("entities"),
        attributes_json=fusion_result.get("attributes"),
        tags_json=fusion_result.get("tags"),
        conflicts_json=all_conflicts,
        evidence_json=[rec.id for rec in raw_records],
        source_version=1,
        fusion_version=1,
        fusion_status="done",
        confidence=final_confidence,
    )
    db.add(pf)
    await db.flush()

    return {
        "id": pf.id,
        "page": page,
        "fused_text": pf.fused_text[:500],
        "page_summary": pf.page_summary,
        "page_title": pf.page_title,
        "entities": pf.body_json,
        "attributes": pf.attributes_json,
        "tags": pf.tags_json,
        "conflicts": all_conflicts,
        "confidence": final_confidence,
        "fusion_version": pf.fusion_version,
    }


async def fuse_all_pages(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
) -> dict:
    """批量执行所有页的页级融合（逐页 commit，幂等可重入）。

    已完成的页（kb_page_fusions 已有记录且 fusion_status='done'）跳过。
    返回: {"document_id": int, "pages_fused": int, "results": [...]}
    """
    # 获取文档页数
    df = await db.execute(select(KbDocument).where(KbDocument.id == document_id))
    doc = df.scalar_one_or_none()
    if not doc:
        raise ValueError(f"Document {document_id} not found")

    total_pages = doc.total_pages or 1

    # 更新状态
    doc.fusion_status = "running"
    await db.commit()

    # 查询已完成页
    r = await db.execute(
        select(KbPageFusion.page).where(
            KbPageFusion.document_id == document_id,
            KbPageFusion.fusion_status == "done",
        )
    )
    done_pages = {row[0] for row in r.all()}

    results = []
    for page in range(1, total_pages + 1):
        if page in done_pages:
            logger.info("Fusion page=%d already done, skip", page)
            results.append({"page": page, "skipped": True})
            continue

        try:
            result = await fuse_page(db, document_id, owner_id, page)
            results.append(result)
            # 逐页 commit：超时/中断只丢当前页
            await db.commit()
            logger.info("Fusion page=%d committed (confidence=%.2f)", page, result.get("confidence", 0))
        except Exception as e:
            logger.error("Fusion failed for doc_id=%d page=%d: %s", document_id, page, e)
            results.append({"page": page, "error": str(e)})
            # 出错也 commit 状态，避免事务膨胀
            try:
                await db.commit()
            except Exception:
                await db.rollback()

    # 更新文档状态
    await db.refresh(doc)
    doc.fusion_status = "done"
    await db.commit()

    # 第4层融合落库后,把"融合正文"切块+向量化写进 kb_chunks
    # → 对外检索(hybrid_search)默认召回的就是融合层内容(华哥设计:对外用第4层)
    try:
        indexed = await index_fusions_to_chunks(db, document_id, owner_id)
        logger.info("Indexed fusion layer to chunks: doc_id=%d chunks=%d", document_id, indexed)
    except Exception as e:
        logger.error("Index fusion to chunks failed for doc_id=%d (non-fatal): %s", document_id, e)

    return {
        "document_id": document_id,
        "pages_fused": len([r for r in results if "error" not in r or r.get("skipped")]),
        "results": results,
    }


async def index_fusions_to_chunks(db: AsyncSession, document_id: int, owner_id: int) -> int:
    """把第4层融合正文切块+向量化写入 kb_chunks,使检索召回融合层内容。

    重建式:先清掉该文档旧 chunk(无论来自老解析还是上轮融合),再按融合层重灌。
    """
    from sqlalchemy import delete as sa_delete
    from ..models import KbChunk
    from .embedding_service import chunk_and_embed, store_chunks

    # 读各页融合正文
    r = await db.execute(
        select(KbPageFusion)
        .where(KbPageFusion.document_id == document_id, KbPageFusion.fused_text != "")
        .order_by(KbPageFusion.page)
    )
    fusions = r.scalars().all()
    blocks = [
        {"type": "融合", "text": pf.fused_text, "page": pf.page, "resource_ref": None}
        for pf in fusions
        if pf.fused_text and pf.fused_text.strip()
    ]
    if not blocks:
        return 0

    # 清旧 chunk + 重灌融合层
    await db.execute(sa_delete(KbChunk).where(KbChunk.document_id == document_id))
    await db.commit()

    chunks = await chunk_and_embed(document_id, owner_id, blocks, caller=f"fusion:{document_id}")
    count = await store_chunks(db, chunks)

    # 回写文档向量状态
    df = await db.execute(select(KbDocument).where(KbDocument.id == document_id))
    doc = df.scalar_one_or_none()
    if doc:
        doc.total_chunks = count
        doc.vector_status = "done" if count > 0 else "error"
        await db.commit()
    return count


# ── 框架任务 handler ────────────────────────────────


async def _fuse_handler(params: dict) -> dict:
    """框架后台任务 handler：处理 kb_fuse 任务。"""
    document_id = int(params.get("document_id", 0))
    if document_id <= 0:
        return {"error": "document_id required", "status": "failed"}

    async with AsyncSessionLocal() as db:
        df = await db.execute(select(KbDocument).where(KbDocument.id == document_id))
        doc = df.scalar_one_or_none()
        if not doc:
            return {"error": f"Document {document_id} not found", "status": "failed"}

        owner_id = doc.owner_id
        try:
            result = await fuse_all_pages(db, document_id, owner_id)
            return {"status": "done", **result}
        except Exception as e:
            logger.error("Fuse handler failed for document_id=%d: %s", document_id, e)
            try:
                doc.fusion_status = "failed"
                await db.commit()
            except Exception:
                pass
            return {"error": str(e), "status": "failed"}


register_task_handler("kb_fuse", _fuse_handler)


async def get_page_fusion_detail(
    db: AsyncSession,
    document_id: int,
    page: int,
) -> dict | None:
    """获取页级融合详情（含冲突/置信度/证据）。"""
    r = await db.execute(
        select(KbPageFusion).where(
            KbPageFusion.document_id == document_id,
            KbPageFusion.page == page,
        )
    )
    pf = r.scalar_one_or_none()
    if not pf:
        return None
    return {
        "id": pf.id,
        "document_id": pf.document_id,
        "page": pf.page,
        "fused_text": pf.fused_text,
        "page_summary": pf.page_summary,
        "page_title": pf.page_title,
        "entities": pf.body_json,
        "attributes": pf.attributes_json,
        "tags": pf.tags_json,
        "conflicts": pf.conflicts_json,
        "evidence_ids": pf.evidence_json,
        "confidence": pf.confidence,
        "fusion_version": pf.fusion_version,
        "fusion_status": pf.fusion_status,
        "created_at": pf.created_at.isoformat() if pf.created_at else None,
    }
