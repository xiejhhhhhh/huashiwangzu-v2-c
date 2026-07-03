"""知识库混合检索服务：向量检索 + 关键词检索 + RRF 融合排序。"""
import json
import logging
import math
from collections.abc import Sequence

from app.models.file import File
from app.services.model_services import get_embedding, rerank
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("v2.knowledge").getChild("search")

# RRF 常数
RRF_K = 60


def _live_source_fields() -> dict[str, bool | str]:
    return {"source_available": True, "source_state": "available"}


def _live_chunk_select():
    from ..models import KbChunk, KbDocument

    return (
        select(KbChunk)
        .join(KbDocument, KbDocument.id == KbChunk.document_id)
        .join(File, File.id == KbDocument.file_id)
        .where(
            KbDocument.deleted.is_(False),
            File.deleted.is_(False),
        )
    )


def _normalize_vector(vec: object) -> list[float] | None:
    """Normalize stored vectors to ``list[float]``.

    Knowledge data has a few historical shapes:
    - native JSON/list from the current schema
    - JSON text from older rows
    - DB driver / extension return values that already behave like sequences
    """
    if vec is None:
        return None
    if isinstance(vec, str):
        text = vec.strip()
        if not text:
            return None
        try:
            vec = json.loads(text)
        except json.JSONDecodeError:
            return None
    if hasattr(vec, "tolist"):
        vec = vec.tolist()
    if not isinstance(vec, Sequence):
        return None

    normalized: list[float] = []
    for item in vec:
        try:
            normalized.append(float(item))
        except (TypeError, ValueError):
            return None
    return normalized


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """计算两个向量的余弦相似度。"""
    vec_a = _normalize_vector(vec_a) or []
    vec_b = _normalize_vector(vec_b) or []
    if not vec_a or not vec_b:
        return 0.0
    if len(vec_a) != len(vec_b):
        logger.warning(
            "Vector dimension mismatch skipped in knowledge search: query_dim=%d chunk_dim=%d",
            len(vec_a),
            len(vec_b),
        )
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def keyword_search(db: AsyncSession, query: str, owner_id: int, top_k: int = 20) -> list[dict]:
    """关键词全文检索（ILIKE on text + keywords）。"""
    from ..models import KbChunk, KbDocument

    if not query.strip():
        return []

    terms = [t.strip() for t in query.split() if len(t.strip()) >= 1]
    if not terms:
        return []

    # 构建 ILIKE 条件
    conditions = []
    for term in terms:
        pattern = f"%{term}%"
        conditions.append(
            or_(
                KbChunk.text.ilike(pattern),
                KbChunk.keywords.ilike(pattern),
            )
        )

    clause = and_(*conditions) if len(conditions) > 1 else conditions[0]
    stmt = (
        _live_chunk_select()
        .where(
            clause,
            KbChunk.owner_id == owner_id,
            KbDocument.owner_id == owner_id,
        )
        .order_by(KbChunk.id.desc())
        .limit(top_k * 2)
    )
    r = await db.execute(stmt)
    chunks = r.scalars().all()

    results = []
    for i, ch in enumerate(chunks):
        # 计算关键词得分：匹配词越多得分越高
        score = 0.0
        matched_terms = 0
        for term in terms:
            if term.lower() in (ch.text or "").lower():
                score += 1.0
                matched_terms += 1
            elif ch.keywords and term.lower() in ch.keywords.lower():
                score += 0.5
                matched_terms += 0.5

        # tf 近似：词频越高分越高（限制在文本中）
        text_lower = (ch.text or "").lower()
        for term in terms:
            tf = text_lower.count(term.lower())
            if tf > 0:
                score += math.log(1 + tf) * 0.3

        results.append({
            "chunk_id": ch.id,
            "document_id": ch.document_id,
            "page": ch.page,
            "block_type": ch.block_type,
            "text": ch.text[:500],
            "keywords": ch.keywords,
            "score": round(score, 4),
            "rank": i + 1,
            "source": "keyword",
            **_live_source_fields(),
        })

    # 按得分排序取 top_k
    results.sort(key=lambda x: -x["score"])
    return results[:top_k]


async def vector_search(db: AsyncSession, query: str, owner_id: int, top_k: int = 20) -> list[dict]:
    """向量检索：用 query embedding 与已存储 chunk embedding 计算余弦相似度。"""
    from ..models import KbChunk, KbDocument

    # 获取 query 向量
    try:
        query_emb = await get_embedding(query)
    except Exception as e:
        logger.warning("get_embedding failed for query '%s': %s", query[:50], e)
        return []

    if not query_emb:
        return []

    # 查询有 embedding 的 chunk（移除硬上限，大文档也能召全）
    stmt = (
        _live_chunk_select()
        .where(
            KbChunk.owner_id == owner_id,
            KbDocument.owner_id == owner_id,
            KbChunk.embedding.isnot(None),
        )
    )
    r = await db.execute(stmt)
    chunks = r.scalars().all()

    scored = []
    for ch in chunks:
        emb = _normalize_vector(ch.embedding)
        if not emb:
            continue
        sim = cosine_similarity(query_emb, emb)
        if sim > 0.0:
            scored.append({
                "chunk_id": ch.id,
                "document_id": ch.document_id,
                "page": ch.page,
                "block_type": ch.block_type,
                "text": ch.text[:500],
                "keywords": ch.keywords,
                "score": round(sim, 4),
                "rank": 0,
                "source": "vector",
                **_live_source_fields(),
            })

    scored.sort(key=lambda x: -x["score"])
    for i, item in enumerate(scored):
        item["rank"] = i + 1

    return scored[:top_k]


def rrf_fusion(keyword_results: list[dict], vector_results: list[dict], top_k: int = 10) -> list[dict]:
    """RRF 融合排序：合并关键词和向量检索结果。"""
    # 用 chunk_id 去重
    seen: set[int] = set()
    fused: list[dict] = []

    for item in keyword_results + vector_results:
        cid = item["chunk_id"]
        if cid in seen:
            continue
        seen.add(cid)

        kw_score = item["score"]
        vec_score = item["score"]

        # 找在另一组中的排名
        kw_rank = None
        vec_rank = None
        for kw in keyword_results:
            if kw["chunk_id"] == cid:
                kw_rank = kw["rank"]
                kw_score = kw["score"]
                break
        for vec in vector_results:
            if vec["chunk_id"] == cid:
                vec_rank = vec["rank"]
                vec_score = vec["score"]
                break

        # RRF 分数
        rrf = 0.0
        if kw_rank:
            rrf += 1.0 / (RRF_K + kw_rank)
        if vec_rank:
            rrf += 1.0 / (RRF_K + vec_rank)

        fused.append({
            **item,
            "rrf_score": round(rrf, 4),
            "kw_score": kw_score,
            "vec_score": vec_score,
            "kw_rank": kw_rank,
            "vec_rank": vec_rank,
        })

    fused.sort(key=lambda x: -x["rrf_score"])
    for i, item in enumerate(fused):
        item["final_rank"] = i + 1

    return fused[:top_k]


async def hybrid_search(
    db: AsyncSession,
    query: str,
    owner_id: int,
    top_k: int = 10,
    use_rerank: bool = False,
) -> list[dict]:
    """混合检索：向量 + 关键词 → RRF 融合 → 可选 rerank。"""
    # 并行关键词和向量检索
    kw_results = await keyword_search(db, query, owner_id, top_k=top_k * 2)
    vec_results = await vector_search(db, query, owner_id, top_k=top_k * 2)

    # RRF 融合
    results = rrf_fusion(kw_results, vec_results, top_k=top_k * 2)

    # 可选 rerank
    if use_rerank and results:
        try:
            docs = [r["text"] for r in results]
            reranked = await rerank(query, docs, top_k=top_k)
            rerank_map = {}
            for i, rr in enumerate(reranked):
                idx = rr.get("index")
                score = rr.get("relevance_score", 0)
                if idx is not None and idx < len(results):
                    rerank_map[idx] = score
            for i, r in enumerate(results):
                if i in rerank_map:
                    r["rerank_score"] = rerank_map[i]
            results.sort(key=lambda x: -(x.get("rerank_score", 0) or 0))
            for i, r in enumerate(results):
                r["final_rank"] = i + 1
        except Exception as e:
            logger.warning("Rerank failed (non-fatal): %s", e)

    return results[:top_k]


async def get_document_chunks(db: AsyncSession, document_id: int, owner_id: int | None = None) -> list[dict]:
    """获取某文档的所有内容块（按页和块索引排序）。"""
    from ..models import KbChunk, KbDocument

    stmt = (
        _live_chunk_select()
        .where(KbChunk.document_id == document_id)
        .order_by(KbChunk.page, KbChunk.chunk_index)
    )
    if owner_id is not None:
        stmt = stmt.where(KbChunk.owner_id == owner_id, KbDocument.owner_id == owner_id)
    r = await db.execute(stmt)
    chunks = r.scalars().all()
    return [
        {
            "id": ch.id,
            "document_id": ch.document_id,
            "page": ch.page,
            "chunk_index": ch.chunk_index,
            "block_type": ch.block_type,
            "text": ch.text,
            "keywords": ch.keywords,
            **_live_source_fields(),
        }
        for ch in chunks
    ]
