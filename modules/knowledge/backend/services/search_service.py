"""知识库混合检索服务：向量检索 + 关键词检索 + RRF 融合排序。"""
import asyncio
import json
import logging
import math
import re
import time
from collections.abc import Sequence

from app.gateway.config import get_model_type_config
from app.models.file import File
from app.models.file_share import FileShare
from app.services.file_share_service import active_share_conditions
from app.services.model_services import get_embedding, get_embedding_profile_contract, rerank
from sqlalchemy import and_, bindparam, or_, select
from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from .retrieval_learning_service import get_learning_priors_for_documents

logger = logging.getLogger("v2.knowledge").getChild("search")

# RRF 常数
RRF_K = 60
VECTOR_SEARCH_EF_SEARCH = 240
VECTOR_SEARCH_MAX_CANDIDATES = 200
DOCUMENT_SEARCH_MAX_CANDIDATES = 200
QUERY_PLAN_TIMEOUT_SECONDS = 8.0
QUERY_PLAN_MAX_TERMS = 16
RETRIEVAL_SCORE_VERSION = "kb_retrieval_score_v1"
# 重排分阈值:bge-reranker输出0~1,低于此分视为不相关砍掉。保守取0.3宁多留不错杀。
# 只在真跑了重排时按此过滤(rerank分有明确量纲);没跑重排不按此砍(RRF融合分量纲不同)。
RERANK_SCORE_THRESHOLD = 0.3
MODEL_WARM_THRESHOLD_MS = 1500.0
MODEL_COLD_THRESHOLD_MS = 3000.0
LEGACY_CHUNK_EMBEDDING_PROFILE = "bge-m3"
GENERIC_QUERY_STOP_WORDS = {
    "有",
    "没",
    "没有",
    "不是",
    "吗",
    "呢",
    "啊",
    "呀",
    "的",
    "了",
    "和",
    "与",
    "或",
    "及",
    "给",
    "我",
    "个",
    "两个",
    "然后",
    "资料",
    "里面",
    "现在",
    "对吧",
    "是否",
    "是不是",
    "一下",
    "什么",
    "哪些",
    "有没有",
    "有什么",
    "名单",
    "列表",
    "列出",
}


class SearchResults(list):
    """List-like search results with retrieval diagnostics attached."""

    def __init__(
        self,
        items: list[dict],
        *,
        query_plan: dict | None = None,
        diagnostics: dict | None = None,
    ) -> None:
        super().__init__(items)
        self.query_plan = query_plan or {}
        self.diagnostics = diagnostics or {}


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


def _knowledge_vector_profile_key(profile_key: str | None = None) -> str | None:
    if profile_key:
        return profile_key
    embedding_config = get_model_type_config("embedding")
    return str(
        embedding_config.get("knowledge_sidecar_primary")
        or embedding_config.get("primary")
        or ""
    ) or None


def _merge_vector_fallback_results(primary: list[dict], fallback: list[dict], *, limit: int) -> list[dict]:
    merged: list[dict] = []
    seen_chunks: set[int] = set()
    for item in [*primary, *fallback]:
        chunk_id = item.get("chunk_id")
        if chunk_id is not None:
            chunk_key = int(chunk_id)
            if chunk_key in seen_chunks:
                continue
            seen_chunks.add(chunk_key)
        merged.append(dict(item))
        if len(merged) >= limit:
            break
    for index, item in enumerate(merged):
        item["rank"] = index + 1
    return merged


def _classify_model_warm_state(duration_ms: float | None, *, status: str = "done") -> str:
    if status in {"failed", "unavailable"}:
        return "unavailable"
    if duration_ms is None:
        return "unknown"
    if duration_ms >= MODEL_COLD_THRESHOLD_MS:
        return "cold_or_loading"
    if duration_ms >= MODEL_WARM_THRESHOLD_MS:
        return "warming_or_busy"
    return "warm"


class _RetrievalDiagnostics:
    """In-memory stage ledger for one retrieval call."""

    def __init__(self, *, query: str, top_k: int, use_rerank: bool) -> None:
        self._started_at = time.perf_counter()
        self._stages: list[dict] = []
        self._model_nodes: list[dict] = []
        self._path: dict = {
            "query": query,
            "top_k": top_k,
            "use_rerank": use_rerank,
        }

    def set_path(self, **values: object) -> None:
        self._path.update(values)

    def stage(
        self,
        name: str,
        *,
        duration_ms: float | None = None,
        status: str = "done",
        result_count: int | None = None,
        reason: str | None = None,
        error: str | None = None,
        **extra: object,
    ) -> None:
        entry = {
            "name": name,
            "status": status,
        }
        if duration_ms is not None:
            entry["duration_ms"] = duration_ms
        if result_count is not None:
            entry["result_count"] = result_count
        if reason:
            entry["reason"] = reason
        if error:
            entry["error"] = error[:300]
        entry.update({key: value for key, value in extra.items() if value is not None})
        self._stages.append(entry)

    def skipped(self, name: str, reason: str) -> None:
        self.stage(name, status="skipped", reason=reason, duration_ms=0.0)

    def model_node(
        self,
        name: str,
        *,
        used: bool,
        duration_ms: float | None = None,
        status: str = "done",
        reason: str | None = None,
        error: str | None = None,
    ) -> None:
        self._model_nodes.append({
            "name": name,
            "used": used,
            "status": status,
            "duration_ms": duration_ms,
            "warm_state": _classify_model_warm_state(duration_ms, status=status) if used else "not_used",
            "basis": "observed_call_latency_ms" if used else "not_called",
            "warm_threshold_ms": MODEL_WARM_THRESHOLD_MS,
            "cold_threshold_ms": MODEL_COLD_THRESHOLD_MS,
            **({"reason": reason} if reason else {}),
            **({"error": error[:300]} if error else {}),
        })

    def build(self, *, result_count: int) -> dict:
        total_duration_ms = _elapsed_ms(self._started_at)
        slowest_stage = max(
            self._stages,
            key=lambda item: float(item.get("duration_ms") or 0.0),
            default=None,
        )
        return {
            "schema_version": "kb_retrieval_diagnostics_v1",
            "total_duration_ms": total_duration_ms,
            "result_count": result_count,
            "path": self._path,
            "stages": self._stages,
            "model_nodes": self._model_nodes,
            "slowest_stage": slowest_stage,
        }


def _live_source_fields() -> dict[str, bool | str]:
    return {"source_available": True, "source_state": "available"}


def _accessible_document_clause(viewer_id: int):
    from ..models import KbDocument

    return or_(
        File.owner_id == viewer_id,
        KbDocument.file_id.in_(
            select(FileShare.file_id).where(*active_share_conditions(user_id=viewer_id))
        ),
    )


def _accessible_file_sql() -> str:
    return """
    (
        f.owner_id = :owner_id
        OR EXISTS (
            SELECT 1
            FROM framework_file_shares share
            WHERE share.file_id = d.file_id
              AND share.shared_with_user_id = :owner_id
              AND (share.expiry IS NULL OR share.expiry > now())
        )
    )
    """


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


def _preferred_index_clause():
    """Prefer verified fusion chunks while keeping parser chunks as fallback.

    If a document has any fusion_verified chunk, base_parse chunks for the same
    document are hidden from default search. Documents without fusion output
    remain searchable through their early parser index.
    """
    from ..models import KbChunk

    fusion_chunk = aliased(KbChunk)
    fusion_exists = (
        select(fusion_chunk.id)
        .where(
            fusion_chunk.document_id == KbChunk.document_id,
            fusion_chunk.owner_id == KbChunk.owner_id,
            fusion_chunk.index_layer == "fusion_verified",
        )
        .limit(1)
        .exists()
    )
    return or_(
        KbChunk.index_layer.is_(None),
        KbChunk.index_layer != "base_parse",
        ~fusion_exists,
    )


def _clean_query_text(query: str) -> str:
    text = re.sub(r"[\s,，。；;：:、/\\|（）()【】\\[\\]{}<>《》!?！？]+", " ", query)
    return re.sub(r"\s+", " ", text).strip()


def _local_query_terms(query: str, custom_terms: Sequence[str] | None = None) -> list[str]:
    compact = re.sub(r"\s+", "", query)
    terms: list[str] = []
    for custom_term in custom_terms or []:
        term = str(custom_term or "").strip()
        if len(term) >= 2 and term in compact and term not in terms:
            terms.append(term)
    tokens: list[str] = []
    try:
        import jieba

        tokens = [
            re.sub(r"[\s,，。；;：:、/\\|（）()【】\[\]{}<>《》!?！？]+", "", str(token).strip())
            for token in jieba.cut_for_search(compact)
        ]
    except Exception:
        tokens = re.findall(r"[A-Za-z0-9_+-]+|[\u4e00-\u9fff]{2,6}", compact)

    useful_tokens = [
        token
        for token in tokens
        if len(token) >= 2 and token not in GENERIC_QUERY_STOP_WORDS
    ]
    for token in useful_tokens:
        if token not in terms:
            terms.append(token)

    for left, right in zip(useful_tokens, useful_tokens[1:]):
        phrase = f"{left}{right}"
        if 3 <= len(phrase) <= 12 and phrase not in terms:
            terms.append(phrase)

    stop_pattern = "|".join(re.escape(word) for word in sorted(GENERIC_QUERY_STOP_WORDS, key=len, reverse=True))
    for segment in re.split(stop_pattern, compact):
        segment = re.sub(r"[\s,，。；;：:、/\\|（）()【】\[\]{}<>《》!?！？]+", "", segment.strip())
        if 2 <= len(segment) <= 12 and segment not in terms:
            terms.append(segment)

    for match in re.findall(r"[\u4e00-\u9fff]{2,8}", compact):
        if match in GENERIC_QUERY_STOP_WORDS:
            continue
        if any(stop_word in match for stop_word in GENERIC_QUERY_STOP_WORDS):
            continue
        if match not in terms:
            terms.append(match)
    return terms[:QUERY_PLAN_MAX_TERMS]


def _rule_value(rule: object, key: str, default: object = None) -> object:
    if isinstance(rule, dict):
        return rule.get(key, default)
    return getattr(rule, key, default)


def _split_rule_patterns(pattern: object) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"[\n,，;；]+", str(pattern or ""))
        if part.strip()
    ]


def _matched_rule_patterns(rule: object, *, query: str, terms: list[str]) -> list[str]:
    match_type = str(_rule_value(rule, "match_type", "contains") or "contains")
    patterns = _split_rule_patterns(_rule_value(rule, "pattern", ""))
    if not patterns:
        return []

    compact = re.sub(r"\s+", "", query).lower()
    normalized_terms = {_normalize_term_text(term) for term in terms}
    matched: list[str] = []
    for pattern in patterns:
        normalized_pattern = _normalize_term_text(pattern)
        if not normalized_pattern:
            continue
        if match_type in {"contains", "any_contains"} and normalized_pattern in compact:
            matched.append(pattern)
        elif match_type == "term" and normalized_pattern in normalized_terms:
            matched.append(pattern)
        elif match_type == "regex":
            try:
                if re.search(pattern, query, flags=re.I):
                    matched.append(pattern)
            except re.error:
                logger.warning("Invalid query routing regex skipped: %s", pattern)
    return matched


def _rule_diagnostics(rule: object) -> dict:
    diagnostics = _rule_value(rule, "diagnostics_json", {}) or {}
    return diagnostics if isinstance(diagnostics, dict) else {}


def _build_local_query_plan_from_rules(
    query: str,
    rules: Sequence[object],
    custom_terms: Sequence[str] | None = None,
) -> dict | None:
    terms = _local_query_terms(query, custom_terms=custom_terms)
    if not terms:
        return None

    intent_scores: dict[str, float] = {}
    source_scores: dict[str, float] = {}
    answer_shape_scores: dict[str, float] = {}
    document_score = 0.0
    llm_required_score = 0.0
    filtered_patterns: list[str] = []
    document_patterns: list[str] = []
    matched_rules: list[dict] = []

    for rule in rules:
        if _rule_value(rule, "enabled", True) is False:
            continue
        matched_patterns = _matched_rule_patterns(rule, query=query, terms=terms)
        if not matched_patterns:
            continue

        rule_type = str(_rule_value(rule, "rule_type", "intent") or "intent")
        weight = float(_rule_value(rule, "weight", 1.0) or 0.0)
        diagnostics = _rule_diagnostics(rule)
        matched_rules.append({
            "rule_key": _rule_value(rule, "rule_key", ""),
            "rule_type": rule_type,
            "matched_patterns": matched_patterns[:8],
            "weight": weight,
            "priority": _rule_value(rule, "priority", 0),
        })

        if diagnostics.get("filter_matched_patterns_from_terms"):
            filtered_patterns.extend(matched_patterns)
        if rule_type == "llm_required":
            llm_required_score += weight
            continue

        intent = str(_rule_value(rule, "intent", "") or "")
        if intent:
            intent_scores[intent] = intent_scores.get(intent, 0.0) + weight
        route_source = str(_rule_value(rule, "route_source", "") or "")
        if route_source:
            source_scores[route_source] = source_scores.get(route_source, 0.0) + weight
        answer_shape = str(_rule_value(rule, "answer_shape", "") or "")
        if answer_shape:
            answer_shape_scores[answer_shape] = answer_shape_scores.get(answer_shape, 0.0) + weight
        if rule_type == "document_level" or diagnostics.get("need_document_level_results") is True:
            document_score += weight
            document_patterns.extend(matched_patterns)
        elif diagnostics.get("need_document_level_results") is False:
            document_score = min(document_score, 0.0)

    local_score = sum(intent_scores.values()) + document_score
    if not matched_rules or local_score <= 0.0:
        return None
    if llm_required_score >= max(3.5, local_score + 0.5):
        return None

    filtered_norms = {_normalize_term_text(pattern) for pattern in filtered_patterns}
    plan_terms = [
        term
        for term in terms
        if not any(pattern and pattern in _normalize_term_text(term) for pattern in filtered_norms)
    ] or terms
    plan_terms = plan_terms[:QUERY_PLAN_MAX_TERMS]
    source = max(source_scores.items(), key=lambda item: item[1])[0] if source_scores else "local_simple_keyword_query"
    if source.startswith("local_fast_"):
        plan_terms.sort(key=lambda item: (-len(item), item))
    intent = max(intent_scores.items(), key=lambda item: item[1])[0] if intent_scores else "local_keyword_lookup"
    answer_shape = (
        max(answer_shape_scores.items(), key=lambda item: item[1])[0]
        if answer_shape_scores
        else ("list" if document_score > 0.0 else "mixed")
    )
    document_types = [
        term
        for term in terms
        if any(_normalize_term_text(pattern) in _normalize_term_text(term) for pattern in document_patterns)
    ][:4]
    entities = []
    if source.startswith("local_fast_") and plan_terms:
        entities = [sorted(plan_terms, key=lambda item: (-len(item), item))[0]]

    return {
        "intent": intent,
        "need_document_level_results": document_score > 0.0,
        "answer_shape": answer_shape,
        "terms": plan_terms,
        "entities": entities,
        "document_types": document_types,
        "constraints": [],
        "source": source,
        "query": query,
        "query_routing": {
            "schema_version": "kb_query_routing_v1",
            "matched_rules": matched_rules,
            "intent_scores": intent_scores,
            "document_score": round(document_score, 4),
            "llm_required_score": round(llm_required_score, 4),
            "source_scores": source_scores,
            "custom_terms_count": len(custom_terms or []),
        },
    }


# 实体IDF表缓存：owner_id -> (加载时刻, 全库文档数N, [(归一名, 原名, 分类, 文档频率df)])
# 用途：查询理解层用 IDF 给命中词自动定权——泛词(高df)沉底、专名(低df)高权，
# 不靠任何硬编码停用词表，纯数据驱动，能扛混沌问题。
_TERM_CACHE: dict[int, tuple[float, int, list[tuple[str, str, str, int]]]] = {}
_TERM_CACHE_TTL = 1800  # 30分钟；词典/文档频率变化慢，长缓存省重复统计


def _idf_weight(df: int, doc_count: int) -> float:
    """标准 IDF：文档频率越低权重越高。df=1 的专名权重远高于高频泛词。"""
    n = max(1, int(doc_count or 1))
    d = max(0, int(df or 0))
    return math.log((n + 1.0) / (d + 1.0)) + 1.0


async def _load_entity_idf_table(
    db: AsyncSession | None, owner_id: int | None
) -> tuple[int, list[tuple[str, str, str, int]]]:
    """加载词典实体 + 每个实体的文档频率(df)，缓存。返回 (全库文档数N, pairs)。

    pairs 元素：(归一化名, 原名, 分类, 文档频率df)。全量约0.7秒(10万实体)，靠TTL缓存复用。
    """
    if db is None or owner_id is None or not hasattr(db, "execute"):
        return 0, []
    now = time.time()
    cached = _TERM_CACHE.get(owner_id)
    if cached is not None and (now - cached[0]) <= _TERM_CACHE_TTL:
        return cached[1], cached[2]
    try:
        # 一次拿到：词典实体(name/category) + 该实体在多少篇文档出现(df)
        # LEFT JOIN 让没有chunk关联的实体 df=0 也保留（它们仍可被查询命中，只是IDF最高）
        result = await db.execute(
            sa_text(
                """
                WITH ef AS (
                    SELECT entity_id, count(DISTINCT document_id) AS df
                    FROM kb_chunk_entities
                    WHERE owner_id = :owner_id
                    GROUP BY entity_id
                )
                SELECT ed.name, ed.category, COALESCE(ef.df, 0) AS df
                FROM kb_entity_dictionary ed
                LEFT JOIN ef ON ef.entity_id = ed.id
                WHERE ed.owner_id = :owner_id
                  AND ed.status IN ('candidate', 'confirmed')
                  AND ed.name <> ''
                """
            ),
            {"owner_id": owner_id},
        )
        pairs = [
            (_normalize_term_text(str(name)), str(name), str(cat or "通用"), int(df or 0))
            for name, cat, df in result.all()
            if str(name or "").strip()
        ]
        # 别名接入(同义词命中的关键):别名文本也可被查询命中,但原名映射回规范实体名,
        # 沿用规范实体的 category/df(权重量纲一致)。用户用别名提问 → 命中 → 下游检索词用规范名。
        seen_norm = {p[0] for p in pairs}
        try:
            alias_result = await db.execute(
                sa_text(
                    """
                    WITH ef AS (
                        SELECT entity_id, count(DISTINCT document_id) AS df
                        FROM kb_chunk_entities
                        WHERE owner_id = :owner_id
                        GROUP BY entity_id
                    )
                    SELECT a.alias, ed.name, ed.category, COALESCE(ef.df, 0) AS df
                    FROM kb_entity_aliases a
                    JOIN kb_entity_dictionary ed ON ed.id = a.entity_id
                    LEFT JOIN ef ON ef.entity_id = a.entity_id
                    WHERE a.owner_id = :owner_id
                      AND ed.status IN ('candidate', 'confirmed')
                      AND a.alias <> ''
                    """
                ),
                {"owner_id": owner_id},
            )
            for alias, canon_name, cat, df in alias_result.all():
                norm_alias = _normalize_term_text(str(alias))
                if not norm_alias or norm_alias in seen_norm or not str(canon_name or "").strip():
                    continue
                seen_norm.add(norm_alias)
                pairs.append((norm_alias, str(canon_name), str(cat or "通用"), int(df or 0)))
        except Exception as alias_exc:  # noqa: BLE001
            logger.warning("Entity alias load failed (non-fatal): %s", alias_exc)
        doc_count_row = await db.execute(
            sa_text("SELECT count(*) FROM kb_documents WHERE owner_id = :owner_id AND deleted IS FALSE"),
            {"owner_id": owner_id},
        )
        doc_count = int(doc_count_row.scalar() or 0)
        _TERM_CACHE[owner_id] = (now, doc_count, pairs)
        return doc_count, pairs
    except Exception as exc:
        logger.warning("Entity IDF table unavailable: %s", exc)
        return 0, []


async def _match_query_entities(
    db: AsyncSession | None, owner_id: int | None, query: str
) -> list[tuple[str, str, float, int]]:
    """把查询里出现的词典实体全捞出来，带 IDF 权重。返回 [(原名, 分类, idf权重, df)] 按权重降序。

    这是查询理解层的核心：不判断"是不是泛词"，而是给每个命中词算 IDF 权重，
    让下游按权重使用——专名自然高权，泛词自然低权。混沌问题也适用。
    """
    if db is None or owner_id is None:
        return []
    compact = _normalize_term_text(query)
    if len(compact) < 2:
        return []
    doc_count, pairs = await _load_entity_idf_table(db, owner_id)
    if not pairs:
        return []
    matched: list[tuple[str, str, float, int]] = []
    seen: set[str] = set()
    for normalized_name, name, category, df in pairs:
        if not normalized_name or normalized_name in seen:
            continue
        if normalized_name in compact:
            seen.add(normalized_name)
            matched.append((name, category, _idf_weight(df, doc_count), df))
    # 按 (IDF权重, 名字长度) 降序：高权专名、长词优先
    matched.sort(key=lambda t: (t[2], len(t[0])), reverse=True)
    return matched


async def _load_query_tokenizer_terms(db: AsyncSession | None, owner_id: int | None, query: str) -> list[str]:
    """兼容旧调用：返回查询命中的词典实体名（按IDF权重降序）。"""
    matched = await _match_query_entities(db, owner_id, query)
    return [name for name, _cat, _w, _df in matched[:40] if name.strip()]


async def _load_query_routing_rules(db: AsyncSession | None, owner_id: int | None) -> list[object]:
    if db is None or owner_id is None or not hasattr(db, "execute"):
        return []
    try:
        from ..models import KbQueryRoutingRule

        result = await db.execute(
            select(KbQueryRoutingRule)
            .where(
                KbQueryRoutingRule.enabled.is_(True),
                KbQueryRoutingRule.owner_id.in_([0, owner_id]),
            )
            .order_by(KbQueryRoutingRule.priority.desc(), KbQueryRoutingRule.weight.desc(), KbQueryRoutingRule.id.asc())
            .limit(200)
        )
        return list(result.scalars().all())
    except Exception as exc:
        logger.warning("Query routing rules unavailable, falling back to LLM planner: %s", exc)
        return []


def _attach_core_entities(
    plan: dict, matched_entities: list[tuple[str, str, float, int]] | None
) -> None:
    """把带 IDF 权重的词典实体挂到检索计划上。

    产出 plan["core_entities"] = [{name, category, weight, df}]（按权重降序），
    这是查询理解层的核心产物：下游召回/打分按 weight 使用——专名高权、泛词低权，
    不靠死词表，纯 IDF 数据驱动，混沌问题也能自适应。
    同时把核心实体名前置进 entities/terms，保证现有下游通道能用上。
    """
    if not isinstance(plan, dict) or not matched_entities:
        return
    core = [
        {"name": name, "category": category, "weight": round(weight, 4), "df": df}
        for name, category, weight, df in matched_entities[:12]
    ]
    plan["core_entities"] = core

    core_names = [c["name"] for c in core]
    # entities：核心实体名并入（去重，保留原有）
    existing_entities = plan.get("entities") if isinstance(plan.get("entities"), list) else []
    merged_entities: list[str] = []
    for name in core_names + [str(e) for e in existing_entities]:
        if name and name not in merged_entities:
            merged_entities.append(name)
    plan["entities"] = merged_entities[:12]

    # terms：核心实体前置（高权实体优先参与关键词/结构化召回）
    existing_terms = plan.get("terms") if isinstance(plan.get("terms"), list) else []
    merged_terms: list[str] = []
    for name in core_names + [str(t) for t in existing_terms]:
        if name and name not in merged_terms:
            merged_terms.append(name)
    plan["terms"] = merged_terms[:QUERY_PLAN_MAX_TERMS]


def _default_query_plan(
    query: str, matched_entities: list[tuple[str, str, float, int]] | None = None
) -> dict:
    """本地兜底检索计划。

    matched_entities 是词典反查命中的实体（带IDF权重）。历史实现把它丢了导致
    entities 永远为空，结构化召回锚不到实体，精度大幅丢失。这里通过
    _attach_core_entities 把带权重的实体接进 core_entities/entities/terms。
    """
    plan = {
        "intent": "semantic_search",
        "need_document_level_results": False,
        "answer_shape": "mixed",
        "terms": _local_query_terms(query),
        "entities": [],
        "core_entities": [],
        "document_types": [],
        "constraints": [],
        "source": "local_fallback",
        "query": query,
    }
    _attach_core_entities(plan, matched_entities)
    return plan


def _normalize_dual_layer_plan(query: str, parsed: dict) -> dict:
    """把本地LLM的双层拆词结果规范成标准 query_plan（core_entities 由 _merge 补齐）。"""
    low = [str(w).strip() for w in (parsed.get("low_level") or []) if str(w).strip()]
    high = [str(w).strip() for w in (parsed.get("high_level") or []) if str(w).strip()]
    terms: list[str] = []
    for w in low + high:
        if len(w) >= 2 and w not in terms:
            terms.append(w[:80])
    if not terms:
        terms = _local_query_terms(query)
    return {
        "intent": str(parsed.get("intent") or "semantic_search").strip()[:64] or "semantic_search",
        "need_document_level_results": bool(parsed.get("need_document_level_results", False)),
        "answer_shape": str(parsed.get("answer_shape") or "mixed").strip()[:64] or "mixed",
        "terms": terms[:QUERY_PLAN_MAX_TERMS],
        "entities": [],
        "core_entities": [],
        "concept_terms": [w for w in high][:10],
        "document_types": [],
        "constraints": [],
        "source": "llm_dual",
        "query": query,
    }


def _merge_llm_and_idf_entities(
    plan: dict,
    parsed: dict,
    matched_entities: list[tuple[str, str, float, int]] | None,
) -> None:
    """LLM定性 + IDF定量：只把LLM认可为low_level的词当核心实体，权重取IDF。

    这是"IDF+本地LLM双层拆词全都要"的融合点：
    - LLM 判断哪些是真实体（自动排除分词碎片'烟酰'、把'推荐/功效'归入high_level）
    - IDF 给这些实体定量权重（专名高权、泛词低权）
    - LLM 认可但词典未收录的词，给参考权重（本地模型认为它是实体，予以信任）
    """
    low = [str(w).strip() for w in (parsed.get("low_level") or []) if str(w).strip()]
    if not low:
        # LLM 没给低层实体，退回纯 IDF 结果
        _attach_core_entities(plan, matched_entities)
        return
    matched_entities = matched_entities or []
    idf_by_norm: dict[str, tuple[str, str, float, int]] = {}
    for name, cat, weight, df in matched_entities:
        idf_by_norm[_normalize_term_text(name)] = (name, cat, weight, df)
    weights = [w for _n, _c, w, _d in matched_entities]
    ref_weight = round(sum(weights) / len(weights), 4) if weights else 8.0

    core: list[tuple[str, str, float, int]] = []
    seen: set[str] = set()
    for orig in low:
        norm = _normalize_term_text(orig)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        if norm in idf_by_norm:
            core.append(idf_by_norm[norm])  # 词典命中：用真实IDF权重
            continue
        # 子串匹配（LLM给"积雪草苷"、词典存"积雪草苷"变体）取最高权重那个
        best: tuple[str, str, float, int] | None = None
        for k, tup in idf_by_norm.items():
            if k and (k in norm or norm in k):
                if best is None or tup[2] > best[2]:
                    best = tup
        if best is not None:
            core.append(best)
        else:
            core.append((orig, "LLM识别", ref_weight, 0))  # 词典没有,信任LLM
    core.sort(key=lambda t: (t[2], len(t[0])), reverse=True)
    _attach_core_entities(plan, core)


def _extract_json_object(text: str) -> dict | None:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw, flags=re.I).strip()
        raw = re.sub(r"```$", "", raw).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.S)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _normalize_query_plan(query: str, plan: dict | None, *, source: str) -> dict:
    fallback = _default_query_plan(query)
    if not plan:
        return fallback

    def _string_list(key: str) -> list[str]:
        value = plan.get(key)
        if not isinstance(value, list):
            return []
        items: list[str] = []
        for item in value:
            text = str(item).strip()
            if len(text) >= 2 and text not in items:
                items.append(text[:80])
        return items[:QUERY_PLAN_MAX_TERMS]

    terms: list[str] = []
    for key in ("terms", "entities", "document_types", "constraints"):
        for term in _string_list(key):
            if term not in terms:
                terms.append(term)
    if not terms:
        terms = fallback["terms"]

    intent = str(plan.get("intent") or fallback["intent"]).strip()[:64] or "semantic_search"
    answer_shape = str(plan.get("answer_shape") or fallback["answer_shape"]).strip()[:64] or "mixed"
    need_document_level = bool(plan.get("need_document_level_results", fallback["need_document_level_results"]))
    return {
        "intent": intent,
        "need_document_level_results": need_document_level,
        "answer_shape": answer_shape,
        "terms": terms[:QUERY_PLAN_MAX_TERMS],
        "entities": _string_list("entities"),
        "document_types": _string_list("document_types"),
        "constraints": _string_list("constraints"),
        "source": source,
        "query": query,
    }


async def plan_query(query: str, db: AsyncSession | None = None, owner_id: int | None = None) -> dict:
    """Use the model to translate a natural query into a structured retrieval plan."""
    rules = await _load_query_routing_rules(db, owner_id)
    matched_entities = await _match_query_entities(db, owner_id, query)  # [(名,分类,IDF权重,df)]
    custom_terms = [name for name, _c, _w, _d in matched_entities]
    local_plan = _build_local_query_plan_from_rules(query, rules, custom_terms=custom_terms)
    if local_plan is not None:
        _attach_core_entities(local_plan, matched_entities)
        return local_plan

    # 短查询（<25字）直接用本地默认规划，不浪费时间调 LLM；词典实体带IDF权重接入
    if len(query.strip()) < 25:
        return _default_query_plan(query, matched_entities=matched_entities)

    # 长/混沌查询：本地LLM双层拆词（低层具体实体 vs 高层概念意图），本地qwen免费无限。
    # 低层词=可精确锚定的实体（成分/产品/品牌等），纠正IDF被分词碎片骗高的问题；
    # 高层词=概念/意图/维度（功效/搭配/浓度等），不做精确锚定、走语义/关系召回。
    messages = [
        {
            "role": "system",
            "content": (
                "你是知识库检索查询分析器。把用户问题拆成两层关键词。只返回JSON，不解释。\n"
                "JSON字段:\n"
                "  low_level: 具体实体词数组（产品名/成分/品牌/型号/专有名词等能精确指向某个东西的词）\n"
                "  high_level: 高层概念词数组（功效/作用/原理/搭配/浓度/推荐等抽象维度或意图）\n"
                "  intent: 检索意图\n"
                "  need_document_level_results: 是否优先返回文件/报告/清单(true/false)\n"
                "  answer_shape: list/summary/qa/mixed 之一\n"
                "规则:不要把分词碎片(如'烟酰'这种不完整的词)当low_level;low_level只放完整、有意义、能独立指代的实体。"
            ),
        },
        {
            "role": "user",
            "content": f"拆解这个知识库查询:\n{query}",
        },
    ]
    try:
        from app.gateway.config import get_models_config
        from app.gateway.router import gateway_router

        _routing = get_models_config().get("module_routing", {}).get("knowledge", {})
        # 拆词用本地profile(免费无限)，不烧云端额度；未配则回退agent_search_profile
        _planner_profile = _routing.get("query_planning_profile") or _routing.get("agent_search_profile") or "deepseek-v4-flash"
        result = await asyncio.wait_for(
            gateway_router.chat(messages=messages, profile_key=_planner_profile),
            timeout=QUERY_PLAN_TIMEOUT_SECONDS,
        )
        content = str(result.get("content") or "") or str(result.get("thinking") or "")
        if result.get("error") or not content:
            raise RuntimeError(str(result.get("error") or "empty query plan"))
        parsed = _extract_json_object(content)
        plan = _normalize_dual_layer_plan(query, parsed)
        # LLM定性(哪些是实体) + IDF定量(权重)：只保留LLM认可为low_level的核心实体，赋IDF权重
        _merge_llm_and_idf_entities(plan, parsed, matched_entities)
        return plan
    except Exception as exc:
        logger.warning("LLM dual-layer planning failed, using IDF local fallback: %s", exc)
        return _default_query_plan(query, matched_entities=matched_entities)


def _result_key(item: dict, *, dedupe_by_document: bool) -> tuple:
    if dedupe_by_document and item.get("document_id") is not None:
        return ("document", int(item["document_id"]))
    if item.get("chunk_id") is not None:
        return ("chunk", int(item["chunk_id"]))
    if item.get("document_id") is not None:
        return ("document", int(item["document_id"]))
    return ("transient", id(item))


def _query_plan_groups(query_plan: dict | None) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    if not isinstance(query_plan, dict):
        return groups
    for group_name in ("entities", "document_types", "constraints"):
        values: list[str] = []
        raw_values = query_plan.get(group_name)
        if not isinstance(raw_values, list):
            continue
        for value in raw_values:
            text = str(value or "").strip().lower()
            if len(text) >= 2 and text not in values:
                values.append(text)
        if values:
            groups[group_name] = values
    return groups


def _query_plan_terms(query_plan: dict | None) -> list[str]:
    terms: list[str] = []
    if not isinstance(query_plan, dict):
        return terms
    for group_name in ("terms", "entities", "document_types", "constraints"):
        raw_values = query_plan.get(group_name)
        if not isinstance(raw_values, list):
            continue
        for value in raw_values:
            text = str(value or "").strip().lower()
            if len(text) >= 2 and text not in terms:
                terms.append(text)
    return terms


def _query_plan_needles(query_plan: dict | None) -> list[str]:
    needles = _query_plan_terms(query_plan)
    return [needle for needle in needles if needle][:QUERY_PLAN_MAX_TERMS]


def _is_fast_local_query_plan(query_plan: dict | None) -> bool:
    if not isinstance(query_plan, dict):
        return False
    return str(query_plan.get("source") or "").startswith("local_fast_")


def _keyword_query_for_plan(query: str, query_plan: dict | None) -> str:
    if not _is_fast_local_query_plan(query_plan):
        return query
    needles = _query_plan_needles(query_plan)
    return " ".join(needles[:3]) if needles else query


def _normalize_term_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _item_search_text(item: dict) -> str:
    parts = [
        item.get("text"),
        item.get("keywords"),
        item.get("block_type"),
        item.get("index_layer"),
        item.get("source_stage"),
    ]
    candidate = item.get("document_candidate")
    if isinstance(candidate, dict):
        parts.extend([
            candidate.get("filename"),
            candidate.get("extension"),
            candidate.get("parse_status"),
            candidate.get("raw_status"),
            candidate.get("fusion_status"),
        ])
    return "\n".join(str(part) for part in parts if part).lower()


def _item_matches_query_plan(item: dict, query_plan: dict | None) -> tuple[bool, int]:
    text = _item_search_text(item)
    if not text:
        return False, 0

    matched_count = 0
    groups = _query_plan_groups(query_plan)
    for values in groups.values():
        if not any(value in text for value in values):
            return False, matched_count
        matched_count += 1

    terms = _query_plan_terms(query_plan)
    matched_count += sum(1 for term in terms if term in text)
    if groups:
        return True, matched_count
    return matched_count > 0, matched_count


def _is_document_level_mode(query_plan: dict | None, *, dedupe_by_document: bool) -> bool:
    if not dedupe_by_document:
        return False
    if not isinstance(query_plan, dict):
        return False
    answer_shape = str(query_plan.get("answer_shape") or "").strip().lower()
    return bool(query_plan.get("need_document_level_results")) or answer_shape in {"list", "table", "catalog"}


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
            KbChunk.owner_id == KbDocument.owner_id,
            _accessible_document_clause(owner_id),
            _preferred_index_clause(),
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
            "index_layer": ch.index_layer or "base_parse",
            "source_stage": ch.source_stage or "",
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


async def vector_search(
    db: AsyncSession,
    query: str,
    owner_id: int,
    top_k: int = 20,
    diagnostics: _RetrievalDiagnostics | None = None,
    embedding_profile: str | None = None,
    *,
    _allow_legacy_fallback: bool = True,
    _fallback_from: str | None = None,
) -> list[dict]:
    """向量检索：用 pgvector 在数据库侧召回 TopK，避免 Python 全量扫块。"""
    from .profile_vector_service import vector_literal

    # 获取 query 向量
    embedding_started_at = time.perf_counter()
    embedding_contract = get_embedding_profile_contract(_knowledge_vector_profile_key(embedding_profile))
    embedding_model = str(embedding_contract.get("profile_key") or embedding_profile or "")
    vector_store = str(embedding_contract.get("vector_store") or "")
    configured_dim = int(embedding_contract.get("dimensions") or embedding_contract.get("embedding_dim") or 0)
    try:
        query_emb = await get_embedding(query, profile_key=embedding_model)
    except Exception as e:
        duration_ms = _elapsed_ms(embedding_started_at)
        if diagnostics is not None:
            diagnostics.stage(
                "embedding_request",
                duration_ms=duration_ms,
                status="failed",
                error=str(e),
                vector_store=vector_store,
                embedding_model=embedding_model,
                fallback_from=_fallback_from,
            )
            diagnostics.model_node(
                "embedding",
                used=True,
                duration_ms=duration_ms,
                status="failed",
                error=str(e),
            )
        logger.warning("get_embedding failed for query '%s': %s", query[:50], e)
        if _allow_legacy_vector_fallback(
            embedding_model=embedding_model,
            vector_store=vector_store,
            fallback_from=_fallback_from,
            allow=_allow_legacy_fallback,
        ):
            if diagnostics is not None:
                diagnostics.stage(
                    "vector_fallback",
                    status="done",
                    reason="embedding_request_failed",
                    result_count=0,
                    fallback_from=embedding_model,
                    fallback_to=LEGACY_CHUNK_EMBEDDING_PROFILE,
                )
            return await vector_search(
                db,
                query,
                owner_id,
                top_k=top_k,
                diagnostics=diagnostics,
                embedding_profile=LEGACY_CHUNK_EMBEDDING_PROFILE,
                _allow_legacy_fallback=False,
                _fallback_from=embedding_model,
            )
        return []
    duration_ms = _elapsed_ms(embedding_started_at)
    if diagnostics is not None:
        embedding_status = "done" if query_emb else "empty"
        diagnostics.stage(
            "embedding_request",
            duration_ms=duration_ms,
            status=embedding_status,
            result_count=1 if query_emb else 0,
            vector_store=vector_store,
            embedding_model=embedding_model,
            fallback_from=_fallback_from,
        )
        diagnostics.model_node(
            "embedding",
            used=True,
            duration_ms=duration_ms,
            status=embedding_status,
            reason=None if query_emb else "empty_embedding",
        )

    if not query_emb:
        return []

    limit = max(1, min(int(top_k or 20), VECTOR_SEARCH_MAX_CANDIDATES))
    query_vector = vector_literal(query_emb)
    embedding_dim = len(query_emb)
    if configured_dim and configured_dim != embedding_dim:
        if diagnostics is not None:
            diagnostics.stage(
                "vector_sql",
                status="skipped",
                reason="embedding_dimension_contract_mismatch",
                result_count=0,
                vector_store=vector_store,
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
                configured_dim=configured_dim,
                fallback_from=_fallback_from,
            )
        return []
    use_chunk_embedding_sidecar = vector_store == "kb_chunk_embeddings"
    use_legacy_chunk_column = vector_store in {"", "kb_chunks"} and embedding_dim == 1024
    if not use_chunk_embedding_sidecar and not use_legacy_chunk_column:
        if diagnostics is not None:
            diagnostics.stage(
                "vector_sql",
                status="skipped",
                reason="unsupported_vector_store_for_embedding_dimension",
                result_count=0,
                vector_store=vector_store,
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
                fallback_from=_fallback_from,
            )
        return []
    sql_started_at = time.perf_counter()
    await db.execute(sa_text(f"SET LOCAL hnsw.ef_search = {int(VECTOR_SEARCH_EF_SEARCH)}"))
    if use_chunk_embedding_sidecar:
        index_dim = int(embedding_contract.get("index_dimensions") or min(embedding_dim, 2000))
        index_dim = max(1, min(index_dim, embedding_dim, 2000))
        candidate_limit = max(limit, min(VECTOR_SEARCH_MAX_CANDIDATES * 4, limit * 8))
        distance_expr = f"e.embedding::vector({embedding_dim}) <=> CAST(:query_vector AS vector({embedding_dim}))"
        order_expr = distance_expr
        sidecar_sql = f"""
                SELECT
                    c.id AS chunk_id,
                    c.document_id,
                    c.page,
                    c.block_type,
                    COALESCE(c.index_layer, 'base_parse') AS index_layer,
                    COALESCE(c.source_stage, '') AS source_stage,
                    left(COALESCE(c.text, ''), 500) AS text,
                    c.keywords,
                    1 - ({distance_expr}) AS score
                FROM kb_chunk_embeddings e
                JOIN kb_chunks c ON c.id = e.chunk_id
                JOIN kb_documents d ON d.id = c.document_id
                JOIN framework_file_items f ON f.id = d.file_id
                WHERE
                    e.owner_id = d.owner_id
                    AND c.owner_id = d.owner_id
                    AND d.deleted IS FALSE
                    AND f.deleted IS FALSE
                    AND {_accessible_file_sql()}
                    AND e.embedding_model = :embedding_model
                    AND e.embedding_version = :embedding_version
                    AND e.embedding_dim = :embedding_dim
                    AND e.status = 'active'
                    AND (
                        c.index_layer IS NULL
                        OR c.index_layer != 'base_parse'
                        OR NOT EXISTS (
                            SELECT 1
                            FROM kb_chunks fusion_chunk
                            WHERE fusion_chunk.document_id = c.document_id
                              AND fusion_chunk.owner_id = c.owner_id
                              AND fusion_chunk.index_layer = 'fusion_verified'
                        )
                    )
                ORDER BY {order_expr}
                LIMIT :limit
        """
        if embedding_dim > 2000 or bool(embedding_contract.get("rerank_full_vector")):
            coarse_expr = (
                f"subvector(e.embedding::vector({embedding_dim}), 1, {index_dim})::vector({index_dim}) "
                f"<=> subvector(CAST(:query_vector AS vector({embedding_dim})), 1, {index_dim})::vector({index_dim})"
            )
            sidecar_sql = f"""
                WITH coarse AS (
                    SELECT
                        c.id AS chunk_id,
                        c.document_id,
                        c.page,
                        c.block_type,
                        COALESCE(c.index_layer, 'base_parse') AS index_layer,
                        COALESCE(c.source_stage, '') AS source_stage,
                        left(COALESCE(c.text, ''), 500) AS text,
                        c.keywords,
                        e.embedding
                    FROM kb_chunk_embeddings e
                    JOIN kb_chunks c ON c.id = e.chunk_id
                    JOIN kb_documents d ON d.id = c.document_id
                    JOIN framework_file_items f ON f.id = d.file_id
                    WHERE
                        e.owner_id = d.owner_id
                        AND c.owner_id = d.owner_id
                        AND d.deleted IS FALSE
                        AND f.deleted IS FALSE
                        AND {_accessible_file_sql()}
                        AND e.embedding_model = :embedding_model
                        AND e.embedding_version = :embedding_version
                        AND e.embedding_dim = :embedding_dim
                        AND e.status = 'active'
                        AND (
                            c.index_layer IS NULL
                            OR c.index_layer != 'base_parse'
                            OR NOT EXISTS (
                                SELECT 1
                                FROM kb_chunks fusion_chunk
                                WHERE fusion_chunk.document_id = c.document_id
                                  AND fusion_chunk.owner_id = c.owner_id
                                  AND fusion_chunk.index_layer = 'fusion_verified'
                            )
                        )
                    ORDER BY {coarse_expr}
                    LIMIT :candidate_limit
                )
                SELECT
                    chunk_id,
                    document_id,
                    page,
                    block_type,
                    index_layer,
                    source_stage,
                    text,
                    keywords,
                    1 - (embedding::vector({embedding_dim}) <=> CAST(:query_vector AS vector({embedding_dim}))) AS score
                FROM coarse
                ORDER BY embedding::vector({embedding_dim}) <=> CAST(:query_vector AS vector({embedding_dim}))
                LIMIT :limit
            """
        result = await db.execute(
            sa_text(sidecar_sql),
            {
                "owner_id": owner_id,
                "query_vector": query_vector,
                "limit": limit,
                "candidate_limit": candidate_limit,
                "embedding_model": embedding_model,
                "embedding_version": int(embedding_contract.get("embedding_version") or 1),
                "embedding_dim": embedding_dim,
            },
        )
        active_vector_store = "kb_chunk_embeddings"
    else:
        result = await db.execute(
            sa_text(
                f"""
                SELECT
                    c.id AS chunk_id,
                    c.document_id,
                    c.page,
                    c.block_type,
                    COALESCE(c.index_layer, 'base_parse') AS index_layer,
                    COALESCE(c.source_stage, '') AS source_stage,
                    left(COALESCE(c.text, ''), 500) AS text,
                    c.keywords,
                    1 - (c.embedding <=> CAST(:query_vector AS vector)) AS score
                FROM kb_chunks c
                JOIN kb_documents d ON d.id = c.document_id
                JOIN framework_file_items f ON f.id = d.file_id
                WHERE
                    c.owner_id = d.owner_id
                    AND d.deleted IS FALSE
                    AND f.deleted IS FALSE
                    AND {_accessible_file_sql()}
                    AND c.embedding IS NOT NULL
                    AND (
                        c.index_layer IS NULL
                        OR c.index_layer != 'base_parse'
                        OR NOT EXISTS (
                            SELECT 1
                            FROM kb_chunks fusion_chunk
                            WHERE fusion_chunk.document_id = c.document_id
                              AND fusion_chunk.owner_id = c.owner_id
                              AND fusion_chunk.index_layer = 'fusion_verified'
                        )
                    )
                ORDER BY c.embedding <=> CAST(:query_vector AS vector)
                LIMIT :limit
                """
            ),
            {
                "owner_id": owner_id,
                "query_vector": query_vector,
                "limit": limit,
            },
        )
        active_vector_store = "kb_chunks"
    rows = result.mappings().all()
    if diagnostics is not None:
        diagnostics.stage(
            "vector_sql",
            duration_ms=_elapsed_ms(sql_started_at),
            result_count=len(rows),
            vector_store=active_vector_store,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
            fallback_from=_fallback_from,
        )
    scored: list[dict] = []
    for i, row in enumerate(rows):
        score = float(row["score"] or 0.0)
        if score <= 0.0:
            continue
        scored.append({
            "chunk_id": int(row["chunk_id"]),
            "document_id": int(row["document_id"]),
            "page": row["page"],
            "block_type": row["block_type"],
            "index_layer": row["index_layer"],
            "source_stage": row["source_stage"],
            "text": row["text"],
            "keywords": row["keywords"],
            "score": round(score, 4),
            "rank": i + 1,
            "source": "vector",
            "vector_store": active_vector_store,
            "embedding_model": embedding_model,
            "fallback_from": _fallback_from,
            **_live_source_fields(),
        })

    if len(scored) < limit and _allow_legacy_vector_fallback(
        embedding_model=embedding_model,
        vector_store=active_vector_store,
        fallback_from=_fallback_from,
        allow=_allow_legacy_fallback,
    ):
        if diagnostics is not None:
            diagnostics.stage(
                "vector_fallback",
                status="done",
                reason="primary_vector_results_below_limit" if scored else "empty_primary_vector_results",
                result_count=len(scored),
                fallback_from=embedding_model,
                fallback_to=LEGACY_CHUNK_EMBEDDING_PROFILE,
            )
        fallback_results = await vector_search(
            db,
            query,
            owner_id,
            top_k=top_k,
            diagnostics=diagnostics,
            embedding_profile=LEGACY_CHUNK_EMBEDDING_PROFILE,
            _allow_legacy_fallback=False,
            _fallback_from=embedding_model,
        )
        return _merge_vector_fallback_results(scored, fallback_results, limit=limit)

    return scored


def _allow_legacy_vector_fallback(
    *,
    embedding_model: str,
    vector_store: str,
    fallback_from: str | None,
    allow: bool,
) -> bool:
    # bge-m3 已废弃（1024维 vs 数据库4096维），永远不 fallback
    return False


async def document_candidate_search(
    db: AsyncSession,
    query_plan: dict,
    owner_id: int,
    top_k: int = 20,
) -> list[dict]:
    """文档级候选召回：服务“有哪些/名单/报告”类企业查询。"""
    term_groups: dict[str, list[str]] = {}
    for group_name in ("entities", "document_types", "constraints", "terms"):
        values: list[str] = []
        for term in query_plan.get(group_name) or []:
            text = str(term).strip()
            if len(text) >= 2 and text not in values:
                values.append(text)
        term_groups[group_name] = values[:QUERY_PLAN_MAX_TERMS]
    needles = []
    for group_name in ("entities", "document_types", "constraints", "terms"):
        for term in term_groups[group_name]:
            if term not in needles:
                needles.append(term)
    needles = needles[:QUERY_PLAN_MAX_TERMS]
    if not needles:
        return []

    limit = max(1, min(int(top_k or 20), DOCUMENT_SEARCH_MAX_CANDIDATES))
    score_parts: list[str] = []
    any_match_parts: list[str] = []
    params: dict[str, object] = {"owner_id": owner_id, "limit": limit}

    def _match_expr(key: str) -> str:
        return f"""
        (
            haystack ILIKE :{key}
            OR EXISTS (
                SELECT 1
                FROM kb_chunks c
                WHERE c.document_id = base.document_id
                  AND c.owner_id = base.doc_owner_id
                  AND (
                    c.text ILIKE :{key}
                    OR c.keywords ILIKE :{key}
                  )
                LIMIT 1
            )
        )
        """

    required_group_parts: list[str] = []
    for group_name, terms in term_groups.items():
        group_parts: list[str] = []
        for index, term in enumerate(terms):
            key = f"{group_name}_{index}"
            params[key] = f"%{term}%"
            match_expr = _match_expr(key)
            group_parts.append(match_expr)
            any_match_parts.append(match_expr)
            group_weight = {
                "entities": 8,
                "document_types": 10,
                "constraints": 5,
                "terms": 3,
            }.get(group_name, 2)
            score_parts.append(f"CASE WHEN {match_expr} THEN {group_weight} ELSE 0 END")
        if group_name in {"entities", "document_types"} and group_parts:
            required_group_parts.append(f"({' OR '.join(group_parts)})")

    if not score_parts or not any_match_parts:
        return []

    required_clause = " AND ".join(required_group_parts) if required_group_parts else f"({' OR '.join(any_match_parts)})"
    any_match_clause = f"({' OR '.join(any_match_parts)})"

    result = await db.execute(
        sa_text(
            f"""
            WITH base AS (
                SELECT
                    d.id AS document_id,
                    d.owner_id AS doc_owner_id,
                    d.file_id,
                    d.filename,
                    d.extension,
                    d.total_pages,
                    d.parse_status,
                    d.raw_status,
                    d.fusion_status,
                    COALESCE(p.subject, '') AS subject,
                    COALESCE(p.doc_type, '') AS doc_type,
                    LEFT(COALESCE(p.doc_summary, ''), 320) AS doc_summary,
                    LEFT(COALESCE(p.core_conclusions, ''), 320) AS core_conclusions,
                    CONCAT_WS(
                        ' ',
                        d.filename,
                        COALESCE(p.subject, ''),
                        COALESCE(p.doc_type, ''),
                        COALESCE(p.doc_summary, ''),
                        COALESCE(p.core_conclusions, '')
                    ) AS haystack
                FROM kb_documents d
                JOIN framework_file_items f ON f.id = d.file_id
                LEFT JOIN kb_document_profiles p
                    ON p.document_id = d.id
                    AND p.owner_id = d.owner_id
                WHERE
                    d.deleted IS FALSE
                    AND f.deleted IS FALSE
                    AND {_accessible_file_sql()}
            ),
            candidates AS (
                SELECT
                    *,
                    ({' + '.join(score_parts)}) AS score
                FROM base
                WHERE {any_match_clause}
                  AND {required_clause}
            )
            SELECT
                document_id,
                file_id,
                filename,
                extension,
                total_pages,
                parse_status,
                raw_status,
                fusion_status,
                subject,
                doc_type,
                doc_summary,
                core_conclusions,
                score
            FROM candidates
            WHERE score > 0
            ORDER BY score DESC, document_id DESC
            LIMIT :limit
            """
        ),
        params,
    )
    rows = result.mappings().all()
    scored: list[dict] = []
    for i, row in enumerate(rows):
        text = "\n".join(
            item
            for item in (
                row["filename"],
                row["subject"],
                row["doc_type"],
                row["doc_summary"],
                row["core_conclusions"],
            )
            if item
        )
        scored.append({
            "chunk_id": None,
            "document_id": int(row["document_id"]),
            "page": None,
            "block_type": "文档画像",
            "index_layer": "document_profile",
            "source_stage": "profile",
            "text": text[:500],
            "keywords": ", ".join(needles),
            "score": round(float(row["score"] or 0.0), 4),
            "rank": i + 1,
            "source": "document_profile",
            "query_plan": query_plan,
            "document_candidate": {
                "file_id": row["file_id"],
                "filename": row["filename"],
                "extension": row["extension"],
                "total_pages": row["total_pages"],
                "parse_status": row["parse_status"],
                "raw_status": row["raw_status"],
                "fusion_status": row["fusion_status"],
            },
            **_live_source_fields(),
        })
    return scored


async def structured_signal_search(
    db: AsyncSession,
    query_plan: dict,
    owner_id: int,
    top_k: int = 50,
) -> list[dict]:
    """Recall document candidates from durable terms, entities, facts, and causal signals."""
    needles = _query_plan_needles(query_plan)
    if not needles:
        return []

    limit = max(1, min(int(top_k or 50), DOCUMENT_SEARCH_MAX_CANDIDATES))
    params: dict[str, object] = {"owner_id": owner_id, "limit": limit}
    term_conditions: list[str] = []
    for index, needle in enumerate(needles):
        key = f"needle_{index}"
        params[key] = f"%{needle}%"
        term_conditions.append(
            f"""
            (
                ed.name ILIKE :{key}
                OR ea.alias ILIKE :{key}
                OR fc.claim_text ILIKE :{key}
                OR fc.subject ILIKE :{key}
                OR fc.predicate ILIKE :{key}
                OR fc.object_value ILIKE :{key}
                OR cc.context ILIKE :{key}
                OR cc.cause ILIKE :{key}
                OR cc.effect ILIKE :{key}
            )
            """
        )
    match_clause = " OR ".join(term_conditions)

    await db.execute(sa_text("SET LOCAL work_mem = '64MB'"))
    result = await db.execute(
        sa_text(
            f"""
            WITH live_docs AS (
                SELECT d.id AS document_id, d.owner_id AS doc_owner_id, d.file_id, d.filename
                FROM kb_documents d
                JOIN framework_file_items f ON f.id = d.file_id
                WHERE d.deleted IS FALSE
                  AND f.deleted IS FALSE
                  AND {_accessible_file_sql()}
            ),
            entity_hits AS (
                SELECT
                    ce.document_id,
                    min(ce.chunk_id) AS chunk_id,
                    count(DISTINCT ce.entity_id) AS entity_count,
                    avg(COALESCE(ce.confidence, 0.0)) AS entity_confidence,
                    left(string_agg(DISTINCT ed.name, ', '), 500) AS evidence_text
                FROM kb_chunk_entities ce
                JOIN kb_entity_dictionary ed ON ed.id = ce.entity_id AND ed.owner_id = ce.owner_id
                JOIN live_docs ld ON ld.document_id = ce.document_id AND ld.doc_owner_id = ce.owner_id
                LEFT JOIN kb_entity_aliases ea ON ea.entity_id = ed.id AND ea.owner_id = ed.owner_id
                LEFT JOIN kb_fact_candidates fc ON false
                LEFT JOIN kb_causal_candidates cc ON false
                WHERE ed.status IN ('candidate', 'confirmed')
                  AND ({match_clause})
                GROUP BY ce.document_id
            ),
            fact_hits AS (
                SELECT
                    fc.document_id,
                    min(fc.page) AS page,
                    count(*) AS fact_count,
                    avg(COALESCE(fc.confidence, 0.55)) AS fact_confidence,
                    left(string_agg(DISTINCT fc.claim_text, E'\n'), 500) AS evidence_text
                FROM kb_fact_candidates fc
                JOIN live_docs ld ON ld.document_id = fc.document_id AND ld.doc_owner_id = fc.owner_id
                LEFT JOIN kb_entity_dictionary ed ON false
                LEFT JOIN kb_entity_aliases ea ON false
                LEFT JOIN kb_causal_candidates cc ON false
                WHERE fc.status IN ('candidate', 'confirmed')
                  AND ({match_clause})
                GROUP BY fc.document_id
            ),
            causal_hits AS (
                SELECT
                    cc.document_id,
                    min(cc.page) AS page,
                    count(*) AS causal_count,
                    avg(COALESCE(cc.confidence, 0.55)) AS causal_confidence,
                    left(string_agg(DISTINCT COALESCE(cc.context, CONCAT(cc.cause, ' -> ', cc.effect)), E'\n'), 500) AS evidence_text
                FROM kb_causal_candidates cc
                JOIN live_docs ld ON ld.document_id = cc.document_id AND ld.doc_owner_id = cc.owner_id
                LEFT JOIN kb_entity_dictionary ed ON false
                LEFT JOIN kb_entity_aliases ea ON false
                LEFT JOIN kb_fact_candidates fc ON false
                WHERE cc.status IN ('candidate', 'confirmed')
                  AND ({match_clause})
                GROUP BY cc.document_id
            ),
            merged AS (
                SELECT
                    ld.document_id,
                    ld.file_id,
                    ld.filename,
                    eh.chunk_id,
                    COALESCE(fh.page, ch.page) AS page,
                    COALESCE(eh.entity_count, 0) AS entity_count,
                    COALESCE(eh.entity_confidence, 0) AS entity_confidence,
                    COALESCE(fh.fact_count, 0) AS fact_count,
                    COALESCE(fh.fact_confidence, 0) AS fact_confidence,
                    COALESCE(ch.causal_count, 0) AS causal_count,
                    COALESCE(ch.causal_confidence, 0) AS causal_confidence,
                    CONCAT_WS(E'\n', eh.evidence_text, fh.evidence_text, ch.evidence_text) AS evidence_text
                FROM live_docs ld
                LEFT JOIN entity_hits eh ON eh.document_id = ld.document_id
                LEFT JOIN fact_hits fh ON fh.document_id = ld.document_id
                LEFT JOIN causal_hits ch ON ch.document_id = ld.document_id
                WHERE eh.document_id IS NOT NULL
                   OR fh.document_id IS NOT NULL
                   OR ch.document_id IS NOT NULL
            )
            SELECT
                *,
                (
                    entity_count * 5
                    + fact_count * 6
                    + causal_count * 4
                    + entity_confidence * 2
                    + fact_confidence * 2
                    + causal_confidence * 2
                ) AS score
            FROM merged
            ORDER BY score DESC, document_id DESC
            LIMIT :limit
            """
        ),
        params,
    )
    rows = result.mappings().all()
    scored: list[dict] = []
    for i, row in enumerate(rows):
        channels = [
            name
            for name, count in (
                ("entity_graph", row["entity_count"]),
                ("fact_candidate", row["fact_count"]),
                ("causal_candidate", row["causal_count"]),
            )
            if int(count or 0) > 0
        ]
        text = "\n".join(
            item
            for item in (
                row["filename"],
                row["evidence_text"],
            )
            if item
        )
        scored.append({
            "chunk_id": int(row["chunk_id"]) if row["chunk_id"] is not None else None,
            "document_id": int(row["document_id"]),
            "page": row["page"],
            "block_type": "结构化证据",
            "index_layer": "structured_signal",
            "source_stage": "cognitive_index",
            "text": text[:500],
            "keywords": ", ".join(needles),
            "score": round(float(row["score"] or 0.0), 4),
            "rank": i + 1,
            "source": "structured_signal",
            "query_plan": query_plan,
            "structured_signal": {
                "file_id": row["file_id"],
                "filename": row["filename"],
                "channels": channels,
                "entity_count": int(row["entity_count"] or 0),
                "fact_count": int(row["fact_count"] or 0),
                "causal_count": int(row["causal_count"] or 0),
            },
            **_live_source_fields(),
        })
    return scored


# 图谱扩展召回:关系/列举型问题的关键。命中主体节点→沿边摸一跳下级实体→回填document_id进融合。
# 华哥核心诉求"华世王镞有什么品牌":主体命中后必须顺藤摸出下级,而不只是返回提到主体的文本块。
_GRAPH_RELATION_TYPES = ("拥有", "属于", "产生", "包含", "领导", "生产", "含有", "涉及", "用于")


# 关系/列举型问句的措辞信号(直接看原始query,不依赖LLM意图字段——短问句走本地规划intent恒为semantic_search)
_RELATIONAL_QUERY_MARKERS = (
    "有什么", "有哪些", "哪些", "什么品牌", "什么产品", "旗下", "下级", "包含哪",
    "属于", "拥有", "旗下有", "有几个", "都有", "含哪", "分别是", "子品牌", "系列有",
)

# 图谱遍历主体停用词:疑问词 + 护肤品域通名/类别词。这些是"问句问的目标类别"或噪音,
# 不能当遍历起点(否则摸出"品牌→拥有→最终解释权""产品→产生→细菌"这类废话)。
# 专名(华世王镞/俏小喵/娇薇诗)才是起点。换行业只需换这张通名表。
_GRAPH_SUBJECT_STOPWORDS = {
    # 疑问/指代
    "什么", "哪些", "哪个", "怎么", "如何", "多少", "为什么", "是否", "可以", "这个", "那个",
    # 护肤品域通名/类别(问句里问的过滤目标,非遍历主体)
    "品牌", "产品", "公司", "顾客", "客户", "化妆品", "护肤品", "系列", "套盒", "成分",
    "功效", "品类", "原料", "规格", "肤质", "美容院", "门店", "代理商", "厂家", "企业",
    "东西", "项目", "内容", "活动", "方案", "服务", "团队", "人员",
}


def _should_graph_expand(query_plan: dict | None) -> bool:
    """门控:能锚到主体节点(有core_entities)且是列举/关系型问句才触发图谱遍历。

    保守设计:普通语义检索不触发,零影响现有召回。只有"有什么/属于谁"这类问题才多走一路。
    出问题可直接 return False 关掉整条路。
    """
    if not query_plan:
        return False
    core = query_plan.get("core_entities") or []
    if not core:
        return False
    if query_plan.get("need_document_level_results"):
        return True
    answer_shape = str(query_plan.get("answer_shape") or "")
    if answer_shape in {"list", "table", "catalog"}:
        return True
    intent = str(query_plan.get("intent") or "")
    if any(kw in intent for kw in ("关系", "列举", "拥有", "包含", "下级", "旗下", "属于", "有哪些", "有什么")):
        return True
    # 兜底:直接看原始问句措辞(短问句intent恒为semantic_search,靠这个救)
    raw_query = str(query_plan.get("query") or "")
    return any(marker in raw_query for marker in _RELATIONAL_QUERY_MARKERS)


async def graph_expansion_search(
    db: AsyncSession, query_plan: dict | None, owner_id: int, top_k: int = 40
) -> list[dict]:
    """图谱扩展召回:核心实体→图谱节点→沿关系边摸一跳下级实体→回填文档→结果。

    单跳遍历(BFS depth=1),全程 owner_id 过滤 + limit 防爆。索引齐全(source/target/entity_id 都有btree)。
    结果对齐现有 chunk 结构,source=graph_expansion,进 RRF 第五路 + verify_and_score 二次校验。
    """
    if not query_plan:
        return []
    core = query_plan.get("core_entities") or []
    if not core:
        return []
    # 主体选择(关键):IDF对高频核心主体是反的(华世王镞df447权重最低,碎片df低权重反高),
    # df也区分不了(华世王镞df687>泛词品牌df59)。真正区别在语义:专名(华世王镞/俏小喵)是遍历起点,
    # 通名/类别词(品牌/产品/公司)是问句里问的"过滤目标"不是起点。用通名停用表挡掉。
    # 策略:①滤疑问词+通名 ②完整词优先(长度降序) ③图谱节点表当最终过滤器(label=ANY)。
    candidates = [
        str(c.get("name")).strip()
        for c in core
        if c.get("name")
        and str(c.get("name")).strip() not in _GRAPH_SUBJECT_STOPWORDS
        and len(str(c.get("name")).strip()) >= 2
    ]
    # 完整词优先(长度降序),去重保序,最多取8个候选喂给图谱匹配
    seen: set[str] = set()
    core_names: list[str] = []
    for nm in sorted(candidates, key=len, reverse=True):
        if nm not in seen:
            seen.add(nm)
            core_names.append(nm)
    core_names = core_names[:8]
    if not core_names:
        return []
    try:
        # 一条SQL打通:主体节点(按label命中)→出边+入边(关系型)→下级节点→回填document_id
        # 出边:主体--关系-->下级;入边:下级--属于-->主体(归属关系常反向建),两向都摸。
        rows = await db.execute(
            sa_text(
                """
                WITH subject_nodes AS (
                    SELECT id AS node_id, label AS subject_label, entity_id
                    FROM kb_graph_nodes
                    WHERE owner_id = :owner_id AND label = ANY(:names)
                ),
                rel_edges AS (
                    -- 出边:主体 → 下级
                    SELECT s.subject_label, e.relation, e.target_node_id AS neighbor_node_id, e.weight
                    FROM kb_graph_edges e
                    JOIN subject_nodes s ON e.source_node_id = s.node_id
                    WHERE e.owner_id = :owner_id AND e.relation = ANY(:relations)
                    UNION ALL
                    -- 入边:下级 → 主体(反向归属)
                    SELECT s.subject_label, e.relation, e.source_node_id AS neighbor_node_id, e.weight
                    FROM kb_graph_edges e
                    JOIN subject_nodes s ON e.target_node_id = s.node_id
                    WHERE e.owner_id = :owner_id AND e.relation = ANY(:relations)
                ),
                neighbors AS (
                    SELECT re.subject_label, re.relation, re.weight,
                           n.entity_id AS neighbor_entity_id, n.label AS neighbor_label, n.category AS neighbor_category
                    FROM rel_edges re
                    JOIN kb_graph_nodes n ON n.id = re.neighbor_node_id AND n.owner_id = :owner_id
                    LIMIT :edge_limit
                )
                -- 回填 document_id/chunk_id:下级实体反查 chunk_entities(取每实体最早一条做代表块)
                SELECT DISTINCT ON (nb.neighbor_entity_id)
                    nb.subject_label, nb.relation, nb.neighbor_label, nb.neighbor_category, nb.weight,
                    ce.document_id, ce.chunk_id
                FROM neighbors nb
                LEFT JOIN kb_chunk_entities ce
                    ON ce.entity_id = nb.neighbor_entity_id AND ce.owner_id = :owner_id
                ORDER BY nb.neighbor_entity_id, ce.document_id
                """
            ),
            {
                "owner_id": owner_id,
                "names": core_names,
                "relations": list(_GRAPH_RELATION_TYPES),
                "edge_limit": max(50, top_k * 4),
            },
        )
        results: list[dict] = []
        rank = 0
        for row in rows.mappings().all():
            document_id = row["document_id"]
            if document_id is None:
                # 下级实体没绑到任何文档块,进不了 verify_and_score,跳过(仍可后续补)
                continue
            rank += 1
            subject = str(row["subject_label"] or "")
            relation = str(row["relation"] or "相关")
            neighbor = str(row["neighbor_label"] or "")
            category = str(row["neighbor_category"] or "")
            weight = float(row["weight"] or 1.0)
            # 图谱路 score:边权归一(weight多为1),给个稳定基线便于融合
            score = min(1.0, 0.5 + weight * 0.1)
            text = f"{subject} —{relation}→ {neighbor}" + (f"（{category}）" if category else "")
            results.append({
                "chunk_id": row["chunk_id"],
                "document_id": int(document_id),
                "page": None,
                "block_type": "图谱扩展",
                "index_layer": "graph_expansion",
                "source_stage": "graph",
                "text": text,
                "keywords": neighbor,
                "score": round(score, 4),
                "rank": rank,
                "source": "graph_expansion",
                "query_plan": query_plan,
                "graph_expansion": {
                    "subject": subject,
                    "relation": relation,
                    "neighbor": neighbor,
                    "neighbor_category": category,
                },
                **_live_source_fields(),
            })
        return results
    except Exception as exc:  # noqa: BLE001
        logger.warning("graph_expansion_search failed (non-fatal): %s", exc)
        return []


def rrf_fusion(
    keyword_results: list[dict],
    vector_results: list[dict],
    top_k: int = 10,
    *,
    document_results: list[dict] | None = None,
    structured_results: list[dict] | None = None,
    graph_results: list[dict] | None = None,
    dedupe_by_document: bool = False,
    query_plan: dict | None = None,
) -> list[dict]:
    """RRF 融合排序：合并文档候选、结构化信号、图谱扩展、关键词和向量检索结果。"""
    result_groups = [
        ("document_profile", document_results or []),
        ("structured_signal", structured_results or []),
        ("graph_expansion", graph_results or []),
        ("keyword", keyword_results),
        ("vector", vector_results),
    ]
    fused_by_key: dict[tuple, dict] = {}

    for group_name, group_results in result_groups:
        for item in group_results:
            key = _result_key(item, dedupe_by_document=dedupe_by_document)
            rank = int(item.get("rank") or len(group_results) + 1)
            score = float(item.get("score") or 0.0)
            entry = fused_by_key.setdefault(
                key,
                {
                    "item": dict(item),
                    "rrf": 0.0,
                    "scores": {},
                    "ranks": {},
                },
            )
            if (
                dedupe_by_document
                and item.get("source") in {"document_profile", "structured_signal", "graph_expansion"}
                and entry["item"].get("source") not in {"document_profile", "structured_signal", "graph_expansion"}
            ):
                entry["item"] = dict(item)
            elif score > float(entry["item"].get("score") or 0.0):
                entry["item"] = {**entry["item"], **dict(item)}
            entry["rrf"] += 1.0 / (RRF_K + rank)
            entry["scores"][group_name] = score
            entry["ranks"][group_name] = rank

    document_level_mode = _is_document_level_mode(query_plan, dedupe_by_document=dedupe_by_document)
    fused: list[dict] = []
    for entry in fused_by_key.values():
        item = dict(entry["item"])
        scores = entry["scores"]
        ranks = entry["ranks"]
        plan_matched, plan_match_count = _item_matches_query_plan(item, query_plan)
        item.update({
            "rrf_score": round(float(entry["rrf"]), 4),
            "doc_score": scores.get("document_profile"),
            "kw_score": scores.get("keyword", item.get("score")),
            "vec_score": scores.get("vector", item.get("score")),
            "structured_score": scores.get("structured_signal"),
            "graph_expansion_score": scores.get("graph_expansion"),
            "doc_rank": ranks.get("document_profile"),
            "structured_rank": ranks.get("structured_signal"),
            "graph_rank": ranks.get("graph_expansion"),
            "kw_rank": ranks.get("keyword"),
            "vec_rank": ranks.get("vector"),
            "query_plan_matched": plan_matched,
            "query_plan_match_count": plan_match_count,
        })
        fused.append(item)

    if document_level_mode:
        def _document_bucket(item: dict) -> int:
            if item.get("doc_rank") is not None or item.get("source") == "document_profile":
                return 0
            if item.get("structured_rank") is not None or item.get("source") == "structured_signal":
                return 1
            if item.get("graph_rank") is not None or item.get("source") == "graph_expansion":
                return 1
            if item.get("query_plan_matched"):
                return 1
            return 2

        fused.sort(
            key=lambda x: (
                _document_bucket(x),
                -float(x.get("doc_score") or 0.0),
                -float(x.get("structured_score") or 0.0),
                -int(x.get("query_plan_match_count") or 0),
                -float(x.get("rrf_score") or 0.0),
                -float(x.get("score") or 0.0),
            )
        )
    else:
        fused.sort(key=lambda x: (-float(x.get("rrf_score") or 0.0), -float(x.get("score") or 0.0)))
    for i, item in enumerate(fused):
        item["final_rank"] = i + 1

    return fused[:top_k]


async def verify_and_score_results(
    db: AsyncSession,
    results: list[dict],
    *,
    owner_id: int,
    query_plan: dict | None,
) -> list[dict]:
    """Use durable evidence, graph, and pipeline signals as the final ranking judge."""
    document_ids = sorted({
        int(item["document_id"])
        for item in results
        if item.get("document_id") is not None
    })
    if not document_ids:
        return results

    stmt = sa_text(
        f"""
        WITH doc_ids AS (
            SELECT CAST(value AS bigint) AS document_id
            FROM unnest(CAST(:document_ids AS bigint[])) AS value
        ),
        live AS (
                SELECT
                    d.id AS document_id,
                    d.owner_id AS doc_owner_id,
                    d.parse_status,
                    d.raw_status,
                    d.fusion_status,
                    d.profile_status,
                    d.graph_status
                FROM kb_documents d
                JOIN framework_file_items f ON f.id = d.file_id
                JOIN doc_ids ids ON ids.document_id = d.id
                WHERE d.deleted IS FALSE
                  AND f.deleted IS FALSE
                  AND {_accessible_file_sql()}
            ),
        evidence_stats AS (
            SELECT
                ev.document_id,
                count(*) AS evidence_count,
                avg(COALESCE(ev.confidence, 0.0)) AS evidence_confidence,
                count(*) FILTER (
                    WHERE ev.raw_data_id IS NOT NULL
                       OR ev.page_fusion_id IS NOT NULL
                       OR ev.artifact_id IS NOT NULL
                       OR ev.source_hash IS NOT NULL
                ) AS lineage_count
                FROM kb_evidence ev
                JOIN live ON live.document_id = ev.document_id AND live.doc_owner_id = ev.owner_id
                WHERE ev.status IN ('pending', 'confirmed')
                GROUP BY ev.document_id
        ),
        fusion_stats AS (
            SELECT
                    pf.document_id,
                count(*) AS fusion_count,
                avg(COALESCE(pf.confidence, 0.65)) AS fusion_confidence,
                count(*) FILTER (
                    WHERE pf.conflicts_json IS NOT NULL
                      AND json_typeof(pf.conflicts_json) = 'array'
                      AND json_array_length(pf.conflicts_json) > 0
                ) AS conflict_count
                FROM kb_page_fusions pf
                JOIN live ON live.document_id = pf.document_id AND live.doc_owner_id = pf.owner_id
                WHERE pf.fusion_status = 'done'
                GROUP BY pf.document_id
        ),
        raw_stats AS (
            SELECT
                rd.document_id,
                count(*) AS raw_count,
                count(DISTINCT rd.source_type) AS raw_source_count
                FROM kb_raw_data rd
                JOIN live ON live.document_id = rd.document_id AND live.doc_owner_id = rd.owner_id
                WHERE rd.status IN ('done', 'degraded')
                GROUP BY rd.document_id
        ),
        fact_stats AS (
            SELECT
                fc.document_id,
                count(*) AS fact_count,
                avg(COALESCE(fc.confidence, 0.55)) AS fact_confidence
                FROM kb_fact_candidates fc
                JOIN live ON live.document_id = fc.document_id AND live.doc_owner_id = fc.owner_id
                WHERE fc.status IN ('candidate', 'confirmed')
                GROUP BY fc.document_id
        ),
        causal_stats AS (
            SELECT
                cc.document_id,
                count(*) AS causal_count,
                avg(COALESCE(cc.confidence, 0.55)) AS causal_confidence
                FROM kb_causal_candidates cc
                JOIN live ON live.document_id = cc.document_id AND live.doc_owner_id = cc.owner_id
                WHERE cc.status IN ('candidate', 'confirmed')
                GROUP BY cc.document_id
        ),
        entity_stats AS (
            SELECT
                ce.document_id,
                count(DISTINCT ce.entity_id) AS entity_count,
                avg(COALESCE(ce.confidence, 0.0)) AS entity_confidence,
                count(DISTINCT ge.id) AS graph_edge_count
            FROM kb_chunk_entities ce
            JOIN kb_entity_dictionary ed ON ed.id = ce.entity_id AND ed.owner_id = ce.owner_id AND ed.status IN ('candidate', 'confirmed')
            LEFT JOIN kb_graph_nodes gn ON gn.owner_id = ce.owner_id AND gn.entity_id = ce.entity_id
            LEFT JOIN kb_graph_edges ge ON ge.owner_id = ce.owner_id AND (ge.source_node_id = gn.id OR ge.target_node_id = gn.id)
                JOIN live ON live.document_id = ce.document_id AND live.doc_owner_id = ce.owner_id
                GROUP BY ce.document_id
        )
        SELECT
            live.document_id,
            live.parse_status,
            live.raw_status,
            live.fusion_status,
            live.profile_status,
            live.graph_status,
            COALESCE(es.evidence_count, 0) AS evidence_count,
            COALESCE(es.evidence_confidence, 0) AS evidence_confidence,
            COALESCE(es.lineage_count, 0) AS lineage_count,
            COALESCE(fs.fusion_count, 0) AS fusion_count,
            COALESCE(fs.fusion_confidence, 0) AS fusion_confidence,
            COALESCE(fs.conflict_count, 0) AS conflict_count,
            COALESCE(rs.raw_count, 0) AS raw_count,
            COALESCE(rs.raw_source_count, 0) AS raw_source_count,
            COALESCE(facts.fact_count, 0) AS fact_count,
            COALESCE(facts.fact_confidence, 0) AS fact_confidence,
            COALESCE(causal.causal_count, 0) AS causal_count,
            COALESCE(causal.causal_confidence, 0) AS causal_confidence,
            COALESCE(ent.entity_count, 0) AS entity_count,
            COALESCE(ent.entity_confidence, 0) AS entity_confidence,
            COALESCE(ent.graph_edge_count, 0) AS graph_edge_count
        FROM live
        LEFT JOIN evidence_stats es ON es.document_id = live.document_id
        LEFT JOIN fusion_stats fs ON fs.document_id = live.document_id
        LEFT JOIN raw_stats rs ON rs.document_id = live.document_id
        LEFT JOIN fact_stats facts ON facts.document_id = live.document_id
        LEFT JOIN causal_stats causal ON causal.document_id = live.document_id
        LEFT JOIN entity_stats ent ON ent.document_id = live.document_id
        """
    ).bindparams(bindparam("document_ids", expanding=False))
    rows = (await db.execute(stmt, {"owner_id": owner_id, "document_ids": document_ids})).mappings().all()
    stats_by_doc = {int(row["document_id"]): row for row in rows}
    learning_priors = await get_learning_priors_for_documents(
        db,
        owner_id=owner_id,
        query_plan=query_plan,
        document_ids=document_ids,
    )

    verified: list[dict] = []
    for item in results:
        document_id = item.get("document_id")
        if document_id is None:
            verified.append(item)
            continue
        row = stats_by_doc.get(int(document_id))
        if row is None:
            verified.append(item)
            continue

        semantic_score = max(0.0, min(1.0, float(item.get("vec_score") or 0.0)))
        lexical_score = min(1.0, float(item.get("query_plan_match_count") or 0) / max(1, len(_query_plan_needles(query_plan))))
        document_profile_score = min(1.0, float(item.get("doc_score") or 0.0) / 24.0)
        structured_score = min(1.0, float(item.get("structured_score") or 0.0) / 30.0)
        rrf_norm = min(1.0, float(item.get("rrf_score") or 0.0) * 30.0)
        term_entity_score = min(
            1.0,
            structured_score
            + min(0.25, float(row["entity_count"] or 0) / 20.0)
            + min(0.25, float(row["fact_count"] or 0) / 12.0),
        )
        intent_score = 1.0 if item.get("query_plan_matched") else 0.35

        lineage_count = float(row["lineage_count"] or 0)
        evidence_count = float(row["evidence_count"] or 0)
        evidence_score = min(
            1.0,
            (min(evidence_count, 8.0) / 8.0) * 0.45
            + (min(lineage_count, 8.0) / 8.0) * 0.35
            + float(row["evidence_confidence"] or 0.0) * 0.20,
        )
        graph_score = min(
            1.0,
            min(float(row["entity_count"] or 0), 10.0) / 10.0 * 0.55
            + min(float(row["graph_edge_count"] or 0), 20.0) / 20.0 * 0.35
            + float(row["entity_confidence"] or 0.0) * 0.10,
        )
        multi_source_score = min(
            1.0,
            min(float(row["fusion_count"] or 0), 4.0) / 4.0 * 0.30
            + min(float(row["raw_source_count"] or 0), 3.0) / 3.0 * 0.30
            + min(float(row["fact_count"] or 0), 6.0) / 6.0 * 0.20
            + min(float(row["causal_count"] or 0), 4.0) / 4.0 * 0.10
            + float(row["fusion_confidence"] or 0.0) * 0.10,
        )
        done_statuses = sum(
            1
            for key in ("parse_status", "raw_status", "fusion_status", "profile_status", "graph_status")
            if str(row[key] or "") == "done"
        )
        source_quality = min(1.0, done_statuses / 5.0)
        conflict_penalty = min(1.0, float(row["conflict_count"] or 0) / 5.0)
        learning_info = learning_priors.get(int(document_id), {})
        learning_prior = float(learning_info.get("prior") or 0.0)
        learning_bonus = max(-0.08, min(0.08, learning_prior * 0.08))

        recall_prior = (
            0.20 * rrf_norm
            + 0.15 * semantic_score
            + 0.20 * lexical_score
            + 0.20 * document_profile_score
            + 0.25 * term_entity_score
        )
        verification = (
            0.35 * evidence_score
            + 0.25 * graph_score
            + 0.20 * multi_source_score
            + 0.10 * source_quality
            + 0.10 * intent_score
            - 0.30 * conflict_penalty
        )
        final_score = max(0.0, min(1.0, 0.30 * recall_prior + 0.55 * verification + learning_bonus))
        if item.get("kw_rank") is not None and lexical_score >= 0.8:
            final_score = max(final_score, 0.62)
        if item.get("doc_rank") is not None and lexical_score >= 0.8:
            final_score = max(final_score, 0.68)
        if item.get("structured_rank") is not None and lexical_score >= 0.8:
            final_score = max(final_score, 0.66)

        score_breakdown = {
            "version": RETRIEVAL_SCORE_VERSION,
            "recall_prior": round(recall_prior, 4),
            "verification": round(verification, 4),
            "final_score": round(final_score, 4),
            "features": {
                "rrf_norm": round(rrf_norm, 4),
                "semantic_score": round(semantic_score, 4),
                "lexical_score": round(lexical_score, 4),
                "document_profile_score": round(document_profile_score, 4),
                "term_entity_score": round(term_entity_score, 4),
                "evidence_score": round(evidence_score, 4),
                "graph_score": round(graph_score, 4),
                "multi_source_score": round(multi_source_score, 4),
                "source_quality": round(source_quality, 4),
                "intent_score": round(intent_score, 4),
                "conflict_penalty": round(conflict_penalty, 4),
                "learning_prior": round(learning_prior, 4),
                "learning_bonus": round(learning_bonus, 4),
            },
            "stats": {
                "evidence_count": int(row["evidence_count"] or 0),
                "lineage_count": int(row["lineage_count"] or 0),
                "fusion_count": int(row["fusion_count"] or 0),
                "raw_count": int(row["raw_count"] or 0),
                "raw_source_count": int(row["raw_source_count"] or 0),
                "fact_count": int(row["fact_count"] or 0),
                "causal_count": int(row["causal_count"] or 0),
                "entity_count": int(row["entity_count"] or 0),
                "graph_edge_count": int(row["graph_edge_count"] or 0),
                "conflict_count": int(row["conflict_count"] or 0),
                "learning_event_count": int(learning_info.get("event_count") or 0),
            },
        }
        updated = dict(item)
        updated["retrieval_score"] = round(final_score, 4)
        updated["score_breakdown"] = score_breakdown
        updated["explain"] = {
            "retrieval_score_version": RETRIEVAL_SCORE_VERSION,
            "main_signal": updated.get("source"),
            "score_breakdown": score_breakdown,
        }
        verified.append(updated)

    verified.sort(
        key=lambda x: (
            -float(x.get("retrieval_score") or 0.0),
            -float(x.get("doc_score") or 0.0),
            -float(x.get("structured_score") or 0.0),
            -float(x.get("rrf_score") or 0.0),
        )
    )
    for index, item in enumerate(verified):
        item["final_rank"] = index + 1
    return verified


async def hybrid_search(
    db: AsyncSession,
    query: str,
    owner_id: int,
    top_k: int = 10,
    use_rerank: bool = False,
    embedding_profile: str | None = None,
) -> list[dict]:
    """混合检索：向量 + 关键词 → RRF 融合 → 可选 rerank。"""
    _search_t0 = time.perf_counter()
    diagnostics = _RetrievalDiagnostics(query=query, top_k=top_k, use_rerank=use_rerank)
    planning_started_at = time.perf_counter()
    query_plan = await plan_query(query, db=db, owner_id=owner_id)
    diagnostics.stage(
        "query_plan",
        duration_ms=_elapsed_ms(planning_started_at),
        source=query_plan.get("source"),
        intent=query_plan.get("intent"),
        answer_shape=query_plan.get("answer_shape"),
    )
    document_intent = bool(query_plan.get("need_document_level_results"))
    fast_local_plan = _is_fast_local_query_plan(query_plan)
    diagnostics.set_path(
        query_plan_source=query_plan.get("source"),
        intent=query_plan.get("intent"),
        answer_shape=query_plan.get("answer_shape"),
        document_intent=document_intent,
        fast_local_plan=fast_local_plan,
    )

    # 关键词和向量检索保留原有高召回；名单/报告类查询额外走文档画像候选。
    doc_results = []
    if document_intent and not fast_local_plan:
        stage_started_at = time.perf_counter()
        doc_results = await document_candidate_search(db, query_plan, owner_id, top_k=top_k * 4)
        logger.info("[SEARCH_STAGE] doc_candidate=%dms n=%d", _elapsed_ms(stage_started_at), len(doc_results))
        diagnostics.stage(
            "document_candidate_search",
            duration_ms=_elapsed_ms(stage_started_at),
            result_count=len(doc_results),
        )
    else:
        diagnostics.skipped(
            "document_candidate_search",
            "fast_local_plan" if fast_local_plan else "query_plan_not_document_level",
        )
    structured_results = []
    if not fast_local_plan:
        stage_started_at = time.perf_counter()
        structured_results = await structured_signal_search(db, query_plan, owner_id, top_k=top_k * 4)
        logger.info("[SEARCH_STAGE] structured_signal=%dms n=%d", _elapsed_ms(stage_started_at), len(structured_results))
        diagnostics.stage(
            "structured_signal_search",
            duration_ms=_elapsed_ms(stage_started_at),
            result_count=len(structured_results),
        )
    else:
        diagnostics.skipped("structured_signal_search", "fast_local_plan")
    # 图谱扩展召回(第五路):关系/列举型问题命中主体→沿边摸下级实体。门控保守,普通检索不触发。
    graph_results = []
    if not fast_local_plan and _should_graph_expand(query_plan):
        stage_started_at = time.perf_counter()
        graph_results = await graph_expansion_search(db, query_plan, owner_id, top_k=top_k * 4)
        logger.info("[SEARCH_STAGE] graph_expansion=%dms n=%d", _elapsed_ms(stage_started_at), len(graph_results))
        diagnostics.stage(
            "graph_expansion_search",
            duration_ms=_elapsed_ms(stage_started_at),
            result_count=len(graph_results),
        )
    else:
        diagnostics.skipped(
            "graph_expansion_search",
            "fast_local_plan" if fast_local_plan else "not_relational_intent",
        )
    stage_started_at = time.perf_counter()
    kw_results = await keyword_search(db, _keyword_query_for_plan(query, query_plan), owner_id, top_k=top_k * 2)
    logger.info("[SEARCH_STAGE] keyword=%dms n=%d", _elapsed_ms(stage_started_at), len(kw_results))
    diagnostics.stage("keyword_search", duration_ms=_elapsed_ms(stage_started_at), result_count=len(kw_results))
    vec_results = []
    if not fast_local_plan:
        stage_started_at = time.perf_counter()
        vec_results = await vector_search(
            db,
            query,
            owner_id,
            top_k=top_k * 2,
            diagnostics=diagnostics,
            embedding_profile=embedding_profile,
        )
        logger.info("[SEARCH_STAGE] vector=%dms n=%d", _elapsed_ms(stage_started_at), len(vec_results))
        diagnostics.stage("vector_search", duration_ms=_elapsed_ms(stage_started_at), result_count=len(vec_results))
    else:
        diagnostics.skipped("vector_search", "fast_local_plan")
        diagnostics.model_node("embedding", used=False, status="skipped", reason="fast_local_plan")

    # RRF 融合
    stage_started_at = time.perf_counter()
    results = rrf_fusion(
        kw_results,
        vec_results,
        top_k=top_k * 2,
        document_results=doc_results,
        structured_results=structured_results,
        graph_results=graph_results,
        dedupe_by_document=document_intent,
        query_plan=query_plan,
    )
    diagnostics.stage("rrf_fusion", duration_ms=_elapsed_ms(stage_started_at), result_count=len(results))
    for result in results:
        result.setdefault("query_plan", query_plan)
    stage_started_at = time.perf_counter()
    results = await verify_and_score_results(db, results, owner_id=owner_id, query_plan=query_plan)
    logger.info("[SEARCH_STAGE] verify_score=%dms n=%d", _elapsed_ms(stage_started_at), len(results))
    diagnostics.stage(
        "verify_and_score_results",
        duration_ms=_elapsed_ms(stage_started_at),
        result_count=len(results),
    )

    # 可选 rerank
    logger.info(
        "[SEARCH_TIMING] query='%s' total=%dms plan_source=%s fast=%s doc=%d struct=%d kw=%d vec=%d fused=%d verified=%d",
        query[:30], _elapsed_ms(_search_t0),
        query_plan.get("source", "?"), fast_local_plan,
        len(doc_results), len(structured_results), len(kw_results), len(vec_results),
        len(results), len(results),
    )
    reranked_ran = False
    if use_rerank and results:
        stage_started_at = time.perf_counter()
        try:
            docs = [r["text"] for r in results]
            reranked = await rerank(query, docs, top_k=top_k)
            reranked_ran = True
            rerank_duration_ms = _elapsed_ms(stage_started_at)
            diagnostics.model_node("rerank", used=True, duration_ms=rerank_duration_ms)
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
            diagnostics.stage("rerank", duration_ms=rerank_duration_ms, result_count=len(reranked))
        except Exception as e:
            rerank_duration_ms = _elapsed_ms(stage_started_at)
            diagnostics.model_node(
                "rerank",
                used=True,
                duration_ms=rerank_duration_ms,
                status="failed",
                error=str(e),
            )
            diagnostics.stage("rerank", duration_ms=rerank_duration_ms, status="failed", error=str(e))
            logger.warning("Rerank failed (non-fatal): %s", e)
    else:
        reason = "use_rerank_false" if not use_rerank else "empty_results"
        diagnostics.skipped("rerank", reason)
        diagnostics.model_node("rerank", used=False, status="skipped", reason=reason)

    # 重排分阈值过滤:只在真跑了重排时按分砍(量纲明确),砍掉低相关噪音,精度优先。
    # 兜底:若全被砍光则退回原序top_k,不返空。
    if reranked_ran:
        before_n = len(results)
        kept = [r for r in results if (r.get("rerank_score") or 0) >= RERANK_SCORE_THRESHOLD]
        if kept:
            results = kept
        diagnostics.stage(
            "rerank_threshold_filter",
            result_count=len(results),
            threshold=RERANK_SCORE_THRESHOLD,
            filtered_out=before_n - len(results),
        )
    final_results = results[:top_k]
    return SearchResults(
        final_results,
        query_plan=query_plan,
        diagnostics=diagnostics.build(result_count=len(final_results)),
    )


async def get_document_chunks(db: AsyncSession, document_id: int, owner_id: int | None = None) -> list[dict]:
    """获取某文档的所有内容块（按页和块索引排序）。"""
    from ..models import KbChunk, KbDocument

    stmt = (
        _live_chunk_select()
        .where(KbChunk.document_id == document_id)
        .order_by(KbChunk.page, KbChunk.chunk_index)
    )
    if owner_id is not None:
        stmt = stmt.where(
            KbChunk.owner_id == KbDocument.owner_id,
            _accessible_document_clause(owner_id),
        )
    r = await db.execute(stmt)
    chunks = r.scalars().all()
    return [
        {
            "id": ch.id,
            "document_id": ch.document_id,
            "page": ch.page,
            "chunk_index": ch.chunk_index,
            "block_type": ch.block_type,
            "index_layer": ch.index_layer or "base_parse",
            "source_stage": ch.source_stage or "",
            "source_ref_id": ch.source_ref_id,
            "text": ch.text,
            "keywords": ch.keywords,
            **_live_source_fields(),
        }
        for ch in chunks
    ]
