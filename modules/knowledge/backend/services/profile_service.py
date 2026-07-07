"""第5层 文件画像服务。

把 N 页融合内容上下串联 → 文件级主旨/摘要/结构/关键实体（参考 V1 文档画像生成服务）。

统一 DAG stage 模式（profile）：LLM 提炼 → 写入 kb_document_profiles。
"""
import json
import logging
from time import perf_counter

from app.gateway.router import gateway_router
from app.services.model_services import get_embedding
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import KbDocument, KbDocumentProfile, KbPageFusion
from .llm_diagnostics import timed_llm_chat
from .model_routing import resolve_knowledge_profile
from .prompt_utils import TPROFILE, load_prompt_detached

logger = logging.getLogger("v2.knowledge").getChild("profile")


async def generate_document_profile(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
    profile_key: str | None = None,
) -> dict:
    """生成文件级画像。

    从 kb_page_fusions 聚合所有页的融合正文 → LLM 提炼文件画像 → 写入 kb_document_profiles。
    """
    stage_started = perf_counter()
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

    df = await db.execute(select(KbDocument).where(KbDocument.id == document_id))
    doc = df.scalar_one_or_none()
    try:
        await db.commit()
    except Exception as exc:
        try:
            await db.rollback()
        except Exception:
            logger.warning("Profile pre-model rollback failed for document_id=%d", document_id, exc_info=True)
        logger.warning("Profile pre-model transaction release failed for document_id=%d: %s", document_id, exc)

    # 聚合各页融合正文
    pages_text = []
    for pf in fusions:
        pages_text.append(f"=== 第{pf.page}页 ===\n{pf.fused_text[:3000]}")

    all_text = "\n\n".join(pages_text)

    # 2. LLM 提炼
    resolved_profile_key = resolve_knowledge_profile("profile", profile_key)
    model_degraded = False
    model_diagnostics: dict = {}
    llm_duration_ms = 0
    embedding_duration_ms = 0
    db_write_duration_ms = 0
    system_prompt = await load_prompt_detached(TPROFILE)
    try:
        llm_started = perf_counter()
        result = await timed_llm_chat(
            logger=logger,
            stage="profile",
            profile_key=resolved_profile_key,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请分析以下文档内容，生成文件画像：\n\n{all_text[:12000]}"},
            ],
            chat_func=gateway_router.chat,
            document_id=document_id,
            extra={"pages": len(fusions)},
        )
        llm_duration_ms = round((perf_counter() - llm_started) * 1000)
        model_degraded = bool(result.get("model_degraded"))
        model_diagnostics = result.get("model_diagnostics") or {}
        content = (result.get("content") or "").strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:]) if len(lines) > 1 else content
            if content.endswith("```"):
                content = content[:-3].strip()
        profile_data = json.loads(content)
    except Exception as e:
        if llm_duration_ms == 0:
            llm_duration_ms = round((perf_counter() - llm_started) * 1000) if "llm_started" in locals() else 0
        logger.warning("LLM profiling failed for document_id=%d, using heuristic: %s", document_id, e)
        profile_data = _heuristic_profile(fusions)

    # 3. 生成嵌入向量（用于跨文件相似度）
    profile_text_for_embed = f"{profile_data.get('subject', '')} {profile_data.get('doc_summary', '')}"
    profile_embedding = None
    try:
        embedding_started = perf_counter()
        profile_embedding = await get_embedding(profile_text_for_embed[:2000])
        embedding_duration_ms = round((perf_counter() - embedding_started) * 1000)
    except Exception as e:
        if embedding_duration_ms == 0:
            embedding_duration_ms = round((perf_counter() - embedding_started) * 1000) if "embedding_started" in locals() else 0
        logger.warning("Profile embedding failed for document_id=%d: %s", document_id, e)

    # 4. 写入 kb_document_profiles
    db_write_started = perf_counter()
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
        labels_json=profile_data.get("labels") or profile_data.get("labels_json") or {},
        applicable_scenarios=profile_data.get("applicable_scenarios", ""),
        expiry_risk=profile_data.get("expiry_risk", "low"),
        confidence=profile_data.get("confidence", 0.7),
        profile_version=1,
        profile_embedding=profile_embedding,
    )
    db.add(profile)
    await db.flush()

    # 同步更新文档摘要
    if doc:
        doc.summary = profile_data.get("doc_summary", "")[:500]
        doc.profile_status = "done"
    await db.commit()
    db_write_duration_ms = round((perf_counter() - db_write_started) * 1000)

    return {
        "document_id": document_id,
        "subject": profile.subject,
        "doc_type": profile.doc_type,
        "key_entities": profile.key_entities,
        "doc_summary": profile.doc_summary,
        "labels_json": profile.labels_json,
        "confidence": profile.confidence,
        "model_degraded": model_degraded,
        "model_diagnostics": model_diagnostics,
        "timing": {
            "stage_wall_ms": round((perf_counter() - stage_started) * 1000),
            "llm_ms": llm_duration_ms,
            "embedding_ms": embedding_duration_ms,
            "db_write_ms": db_write_duration_ms,
            "pages": len(fusions),
            "input_chars": len(all_text),
        },
    }


def _heuristic_profile(fusions: list) -> dict:
    """启发式画像（LLM 不可用时的后备方案）。"""
    if not fusions:
        return {
            "subject": "", "doc_type": "其他", "chapter_structure": [],
            "core_conclusions": "", "key_entities": [], "doc_summary": "",
            "searchable_phrases": [], "labels": {}, "applicable_scenarios": "", "expiry_risk": "low", "confidence": 0.3,
        }

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
        "labels": {
            "business_tags": searchable_phrases,
            "usage_tags": ["待人工复核"],
            "content_boundaries": ["LLM 不可用时由启发式兜底生成，需人工复核"],
            "business_objects": [],
            "evidence": [],
        },
        "applicable_scenarios": "",
        "expiry_risk": "low",
        "confidence": 0.3,
    }


async def get_document_profile(db: AsyncSession, document_id: int, owner_id: int | None = None) -> dict | None:
    """获取文件画像。支持 owner_id 验证（防止越权访问其他用户的文档画像）。"""
    q = select(KbDocumentProfile).where(KbDocumentProfile.document_id == document_id)
    if owner_id is not None:
        q = q.where(KbDocumentProfile.owner_id == owner_id)
    r = await db.execute(q)
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
        "labels_json": profile.labels_json,
        "applicable_scenarios": profile.applicable_scenarios,
        "expiry_risk": profile.expiry_risk,
        "confidence": profile.confidence,
        "profile_version": profile.profile_version,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }
