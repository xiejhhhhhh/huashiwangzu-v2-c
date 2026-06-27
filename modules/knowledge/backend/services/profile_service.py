"""第5层 文件画像服务。

把 N 页融合内容上下串联 → 文件级主旨/摘要/结构/关键实体（参考 V1 文档画像生成服务）。

后台任务模式（kb_profile）：LLM 提炼 → 写入 kb_document_profiles。
"""
import json
import logging
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.gateway.router import gateway_router
from app.services.model_services import get_embedding
from app.services.task_worker import register_task_handler

from ..models import KbDocument, KbPageFusion, KbDocumentProfile

logger = logging.getLogger("v2.knowledge").getChild("profile")

PROFILE_SYSTEM_PROMPT = """你是企业文档分析专家。请根据以下各页的融合内容，生成文件级画像。

输出严格 JSON（不要 markdown 标记）：
{
  "subject": "文件主旨（一句话）",
  "doc_type": "品牌介绍/产品说明/培训手册/数据报表/配方文件/会员方案/管理制度/其他",
  "chapter_structure": [{"title": "章节标题", "page": 1, "summary": "该章节内容"}],
  "core_conclusions": "核心结论（2-3句话）",
  "key_entities": [{"name": "实体名", "type": "产品/品牌/成分/人物/事件/其他", "relevance": "high"}],
  "doc_summary": "文档级摘要（3-5句话）",
  "searchable_phrases": ["搜索短语1", "搜索短语2"],
  "applicable_scenarios": "适用场景描述",
  "expiry_risk": "none/low/medium/high"
}"""


async def generate_document_profile(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
    profile_key: str = "deepseek-v4-flash",
) -> dict:
    """生成文件级画像。

    从 kb_page_fusions 聚合所有页的融合正文 → LLM 提炼文件画像 → 写入 kb_document_profiles。
    """
    # 1. 读取所有页融合内容（过滤空文本，与 fusion_service / entity_service 一致）
    r = await db.execute(
        select(KbPageFusion)
        .where(
            KbPageFusion.document_id == document_id,
            KbPageFusion.fusion_status == "done",
            KbPageFusion.fused_text != "",
        )
        .order_by(KbPageFusion.page)
    )
    fusions = r.scalars().all()

    if not fusions:
        logger.warning("No fused pages for document_id=%d, skipping profile", document_id)
        return {"document_id": document_id, "status": "skipped", "reason": "no_fused_pages"}

    # 聚合各页融合正文
    pages_text = []
    for pf in fusions:
        pages_text.append(f"=== 第{pf.page}页 ===\n{pf.fused_text[:3000]}")

    all_text = "\n\n".join(pages_text)

    # 2. LLM 提炼
    try:
        result = await gateway_router.chat(
            messages=[
                {"role": "system", "content": PROFILE_SYSTEM_PROMPT},
                {"role": "user", "content": f"请分析以下文档内容，生成文件画像：\n\n{all_text[:12000]}"},
            ],
            profile_key=profile_key,
        )
        content = (result.get("content") or "").strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:]) if len(lines) > 1 else content
            if content.endswith("```"):
                content = content[:-3].strip()
        profile_data = json.loads(content)
    except Exception as e:
        logger.warning("LLM profiling failed for document_id=%d, using heuristic: %s", document_id, e)
        profile_data = _heuristic_profile(fusions)

    # 3. 生成嵌入向量（用于跨文件相似度）
    profile_text_for_embed = f"{profile_data.get('subject', '')} {profile_data.get('doc_summary', '')}"
    profile_embedding = None
    try:
        profile_embedding = await get_embedding(profile_text_for_embed[:2000])
    except Exception as e:
        logger.warning("Profile embedding failed for document_id=%d: %s", document_id, e)

    # 4. 写入 kb_document_profiles
    await db.execute(
        sa_delete(KbDocumentProfile).where(KbDocumentProfile.document_id == document_id)
    )

    profile = KbDocumentProfile(
        document_id=document_id,
        owner_id=owner_id,
        subject=profile_data.get("subject", ""),
        doc_type=profile_data.get("doc_type", ""),
        chapter_structure=profile_data.get("chapter_structure", []),
        core_conclusions=profile_data.get("core_conclusions", ""),
        key_entities=profile_data.get("key_entities", []),
        doc_summary=profile_data.get("doc_summary", ""),
        searchable_phrases=profile_data.get("searchable_phrases", []),
        applicable_scenarios=profile_data.get("applicable_scenarios", ""),
        expiry_risk=profile_data.get("expiry_risk", "low"),
        confidence=profile_data.get("confidence", 0.7),
        profile_version=1,
        profile_embedding=profile_embedding,
    )
    db.add(profile)
    await db.flush()

    # 同步更新文档摘要
    df = await db.execute(select(KbDocument).where(KbDocument.id == document_id))
    doc = df.scalar_one_or_none()
    if doc:
        doc.summary = profile_data.get("doc_summary", "")[:500]
    await db.commit()

    return {
        "document_id": document_id,
        "subject": profile.subject,
        "doc_type": profile.doc_type,
        "key_entities": profile.key_entities,
        "doc_summary": profile.doc_summary,
        "confidence": profile.confidence,
    }


def _heuristic_profile(fusions: list) -> dict:
    """启发式画像（LLM 不可用时的后备方案）。"""
    if not fusions:
        return {
            "subject": "", "doc_type": "其他", "chapter_structure": [],
            "core_conclusions": "", "key_entities": [], "doc_summary": "",
            "searchable_phrases": [], "applicable_scenarios": "", "expiry_risk": "low", "confidence": 0.3,
        }

    total_pages = len(fusions)
    all_text = "\n".join(pf.fused_text for pf in fusions)

    # 简单启发式：取第一页前100字作为主题
    first_text = fusions[0].fused_text if fusions else ""
    subject = first_text[:100].strip()

    # 摘要取所有融合摘要的拼接
    summaries = [pf.page_summary for pf in fusions if pf.page_summary]
    doc_summary = "\n".join(summaries) if summaries else first_text[:500]

    # 标签合并
    tags = set()
    for pf in fusions:
        if pf.tags_json:
            for t in pf.tags_json:
                tags.add(str(t))
    searchable_phrases = list(tags)[:20]

    # 实体合并
    all_entities = []
    seen = set()
    for pf in fusions:
        if pf.body_json:
            for ent in pf.body_json:
                name = ent.get("name", "") if isinstance(ent, dict) else str(ent)
                if name and name not in seen:
                    seen.add(name)
                    all_entities.append({"name": name, "type": "其他", "relevance": "medium"})

    return {
        "subject": subject,
        "doc_type": "其他",
        "chapter_structure": [{"title": f"第{pf.page}页", "page": pf.page, "summary": (pf.page_summary or pf.fused_text[:200])} for pf in fusions[:20]],
        "core_conclusions": doc_summary[:500],
        "key_entities": all_entities[:30],
        "doc_summary": doc_summary[:1000],
        "searchable_phrases": searchable_phrases,
        "applicable_scenarios": "",
        "expiry_risk": "low",
        "confidence": 0.3,
    }


async def get_document_profile(db: AsyncSession, document_id: int) -> dict | None:
    """获取文件画像。"""
    r = await db.execute(
        select(KbDocumentProfile).where(KbDocumentProfile.document_id == document_id)
    )
    profile = r.scalar_one_or_none()
    if not profile:
        return None
    return {
        "id": profile.id,
        "document_id": profile.document_id,
        "subject": profile.subject,
        "doc_type": profile.doc_type,
        "chapter_structure": profile.chapter_structure,
        "core_conclusions": profile.core_conclusions,
        "key_entities": profile.key_entities,
        "doc_summary": profile.doc_summary,
        "searchable_phrases": profile.searchable_phrases,
        "applicable_scenarios": profile.applicable_scenarios,
        "expiry_risk": profile.expiry_risk,
        "confidence": profile.confidence,
        "profile_version": profile.profile_version,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }


# ── 框架任务 handler ────────────────────────────────


async def _profile_handler(params: dict) -> dict:
    """框架后台任务 handler：处理 kb_profile 任务。"""
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
            result = await generate_document_profile(db, document_id, owner_id)
            return {"status": "done", **result}
        except Exception as e:
            logger.error("Profile handler failed for document_id=%d: %s", document_id, e)
            return {"error": str(e), "status": "failed"}


register_task_handler("kb_profile", _profile_handler)
