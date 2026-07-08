"""知识库混合检索服务：向量检索 + 关键词检索 + RRF 融合排序。"""
import asyncio
import json
import logging
import math
import re
import time
from collections.abc import Sequence

from app.models.file import File
from app.services.model_services import get_embedding, rerank
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
QUERY_PLAN_TIMEOUT_SECONDS = 15.0
QUERY_PLAN_MAX_TERMS = 16
RETRIEVAL_SCORE_VERSION = "kb_retrieval_score_v1"
MODEL_WARM_THRESHOLD_MS = 1500.0
MODEL_COLD_THRESHOLD_MS = 3000.0
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


async def _load_query_tokenizer_terms(db: AsyncSession | None, owner_id: int | None, query: str) -> list[str]:
    if db is None or owner_id is None or not hasattr(db, "execute"):
        return []
    compact = _normalize_term_text(query)
    if len(compact) < 2:
        return []
    try:
        from ..models import KbTerm

        result = await db.execute(
            select(KbTerm.term)
            .where(
                KbTerm.owner_id == owner_id,
                KbTerm.status == "active",
                KbTerm.normalized != "",
                sa_text(":compact LIKE '%' || kb_terms.normalized || '%'"),
            )
            .order_by(sa_text("length(kb_terms.normalized) DESC"), KbTerm.confidence.desc().nullslast())
            .limit(40),
            {"compact": compact},
        )
        return [str(term) for term in result.scalars().all() if str(term or "").strip()]
    except Exception as exc:
        logger.warning("Query tokenizer terms unavailable, using generic tokenizer: %s", exc)
        return []


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


def _default_query_plan(query: str) -> dict:
    terms = _local_query_terms(query)
    return {
        "intent": "semantic_search",
        "need_document_level_results": True,
        "answer_shape": "mixed",
        "terms": terms,
        "entities": [],
        "document_types": [],
        "constraints": [],
        "source": "local_fallback",
        "query": query,
    }


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
    custom_terms = await _load_query_tokenizer_terms(db, owner_id, query)
    local_plan = _build_local_query_plan_from_rules(query, rules, custom_terms=custom_terms)
    if local_plan is not None:
        return local_plan

    messages = [
        {
            "role": "system",
            "content": (
                "你是企业知识库检索规划器。只返回 JSON，不要解释。"
                "不要使用固定业务枚举；根据用户原句抽取检索意图、实体、资料类型、约束。"
                "JSON 字段: intent, need_document_level_results, answer_shape, terms, entities, "
                "document_types, constraints。terms/entities/document_types/constraints 都是字符串数组。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请为下面查询生成检索计划。"
                "need_document_level_results 表示是否应优先返回文件/报告/资料清单；"
                "answer_shape 可为 list、summary、qa、mixed。\n"
                f"查询: {query}"
            ),
        },
    ]
    try:
        from app.gateway.router import gateway_router

        result = await asyncio.wait_for(
            gateway_router.chat(messages=messages),
            timeout=QUERY_PLAN_TIMEOUT_SECONDS,
        )
        content = str(result.get("content") or "")
        if result.get("error") or not content:
            raise RuntimeError(str(result.get("error") or "empty query plan"))
        parsed = _extract_json_object(content)
        return _normalize_query_plan(query, parsed, source="llm")
    except Exception as exc:
        logger.warning("LLM query planning failed, using local fallback: %s", exc)
        return _default_query_plan(query)


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
            KbChunk.owner_id == owner_id,
            KbDocument.owner_id == owner_id,
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
) -> list[dict]:
    """向量检索：用 pgvector 在数据库侧召回 TopK，避免 Python 全量扫块。"""
    from .profile_vector_service import vector_literal

    # 获取 query 向量
    embedding_started_at = time.perf_counter()
    try:
        query_emb = await get_embedding(query)
    except Exception as e:
        duration_ms = _elapsed_ms(embedding_started_at)
        if diagnostics is not None:
            diagnostics.stage("embedding_request", duration_ms=duration_ms, status="failed", error=str(e))
            diagnostics.model_node(
                "embedding",
                used=True,
                duration_ms=duration_ms,
                status="failed",
                error=str(e),
            )
        logger.warning("get_embedding failed for query '%s': %s", query[:50], e)
        return []
    duration_ms = _elapsed_ms(embedding_started_at)
    if diagnostics is not None:
        embedding_status = "done" if query_emb else "empty"
        diagnostics.stage(
            "embedding_request",
            duration_ms=duration_ms,
            status=embedding_status,
            result_count=1 if query_emb else 0,
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
    sql_started_at = time.perf_counter()
    await db.execute(sa_text(f"SET LOCAL hnsw.ef_search = {int(VECTOR_SEARCH_EF_SEARCH)}"))
    result = await db.execute(
        sa_text(
            """
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
                c.owner_id = :owner_id
                AND d.owner_id = :owner_id
                AND d.deleted IS FALSE
                AND f.deleted IS FALSE
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
    rows = result.mappings().all()
    if diagnostics is not None:
        diagnostics.stage("vector_sql", duration_ms=_elapsed_ms(sql_started_at), result_count=len(rows))
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
            **_live_source_fields(),
        })

    return scored


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
                  AND c.owner_id = :owner_id
                  AND (
                    c.text ILIKE :{key}
                    OR COALESCE(c.keywords, '') ILIKE :{key}
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
                    d.owner_id = :owner_id
                    AND f.owner_id = :owner_id
                    AND d.deleted IS FALSE
                    AND f.deleted IS FALSE
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
        norm_key = f"needle_norm_{index}"
        params[key] = f"%{needle}%"
        params[norm_key] = f"%{_normalize_term_text(needle)}%"
        term_conditions.append(
            f"""
            (
                t.term ILIKE :{key}
                OR t.normalized ILIKE :{norm_key}
                OR ed.name ILIKE :{key}
                OR ea.alias ILIKE :{key}
                OR fc.claim_text ILIKE :{key}
                OR COALESCE(fc.subject, '') ILIKE :{key}
                OR COALESCE(fc.predicate, '') ILIKE :{key}
                OR COALESCE(fc.object_value, '') ILIKE :{key}
                OR cc.context ILIKE :{key}
                OR cc.cause ILIKE :{key}
                OR cc.effect ILIKE :{key}
            )
            """
        )
    match_clause = " OR ".join(term_conditions)

    result = await db.execute(
        sa_text(
            f"""
            WITH live_docs AS (
                SELECT d.id AS document_id, d.file_id, d.filename
                FROM kb_documents d
                JOIN framework_file_items f ON f.id = d.file_id
                WHERE d.owner_id = :owner_id
                  AND f.owner_id = :owner_id
                  AND d.deleted IS FALSE
                  AND f.deleted IS FALSE
            ),
            term_hits AS (
                SELECT
                    o.document_id,
                    min(o.chunk_id) AS chunk_id,
                    min(o.page) AS page,
                    count(DISTINCT o.term_id) AS term_count,
                    sum(COALESCE(o.weight, 1.0)) AS term_weight,
                    left(string_agg(DISTINCT CONCAT(t.term, ': ', COALESCE(o.context, '')), E'\n'), 500) AS evidence_text
                FROM kb_term_occurrences o
                JOIN kb_terms t ON t.id = o.term_id AND t.owner_id = o.owner_id
                JOIN live_docs ld ON ld.document_id = o.document_id
                LEFT JOIN kb_entity_dictionary ed ON false
                LEFT JOIN kb_entity_aliases ea ON false
                LEFT JOIN kb_fact_candidates fc ON false
                LEFT JOIN kb_causal_candidates cc ON false
                WHERE o.owner_id = :owner_id
                  AND t.status = 'active'
                  AND ({match_clause})
                GROUP BY o.document_id
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
                JOIN live_docs ld ON ld.document_id = ce.document_id
                LEFT JOIN kb_entity_aliases ea ON ea.entity_id = ed.id AND ea.owner_id = ed.owner_id
                LEFT JOIN kb_terms t ON false
                LEFT JOIN kb_fact_candidates fc ON false
                LEFT JOIN kb_causal_candidates cc ON false
                WHERE ce.owner_id = :owner_id
                  AND ed.status IN ('candidate', 'confirmed')
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
                JOIN live_docs ld ON ld.document_id = fc.document_id
                LEFT JOIN kb_terms t ON false
                LEFT JOIN kb_entity_dictionary ed ON false
                LEFT JOIN kb_entity_aliases ea ON false
                LEFT JOIN kb_causal_candidates cc ON false
                WHERE fc.owner_id = :owner_id
                  AND fc.status IN ('candidate', 'confirmed')
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
                JOIN live_docs ld ON ld.document_id = cc.document_id
                LEFT JOIN kb_terms t ON false
                LEFT JOIN kb_entity_dictionary ed ON false
                LEFT JOIN kb_entity_aliases ea ON false
                LEFT JOIN kb_fact_candidates fc ON false
                WHERE cc.owner_id = :owner_id
                  AND cc.status IN ('candidate', 'confirmed')
                  AND ({match_clause})
                GROUP BY cc.document_id
            ),
            merged AS (
                SELECT
                    ld.document_id,
                    ld.file_id,
                    ld.filename,
                    th.chunk_id,
                    COALESCE(th.page, fh.page, ch.page) AS page,
                    COALESCE(th.term_count, 0) AS term_count,
                    COALESCE(th.term_weight, 0) AS term_weight,
                    COALESCE(eh.entity_count, 0) AS entity_count,
                    COALESCE(eh.entity_confidence, 0) AS entity_confidence,
                    COALESCE(fh.fact_count, 0) AS fact_count,
                    COALESCE(fh.fact_confidence, 0) AS fact_confidence,
                    COALESCE(ch.causal_count, 0) AS causal_count,
                    COALESCE(ch.causal_confidence, 0) AS causal_confidence,
                    CONCAT_WS(E'\n', th.evidence_text, eh.evidence_text, fh.evidence_text, ch.evidence_text) AS evidence_text
                FROM live_docs ld
                LEFT JOIN term_hits th ON th.document_id = ld.document_id
                LEFT JOIN entity_hits eh ON eh.document_id = ld.document_id
                LEFT JOIN fact_hits fh ON fh.document_id = ld.document_id
                LEFT JOIN causal_hits ch ON ch.document_id = ld.document_id
                WHERE th.document_id IS NOT NULL
                   OR eh.document_id IS NOT NULL
                   OR fh.document_id IS NOT NULL
                   OR ch.document_id IS NOT NULL
            )
            SELECT
                *,
                (
                    term_count * 4
                    + LEAST(term_weight, 10)
                    + entity_count * 5
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
                ("term_graph", row["term_count"]),
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
            "source_stage": "cognitive_v3",
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
                "term_count": int(row["term_count"] or 0),
                "entity_count": int(row["entity_count"] or 0),
                "fact_count": int(row["fact_count"] or 0),
                "causal_count": int(row["causal_count"] or 0),
            },
            **_live_source_fields(),
        })
    return scored


def rrf_fusion(
    keyword_results: list[dict],
    vector_results: list[dict],
    top_k: int = 10,
    *,
    document_results: list[dict] | None = None,
    structured_results: list[dict] | None = None,
    dedupe_by_document: bool = False,
    query_plan: dict | None = None,
) -> list[dict]:
    """RRF 融合排序：合并文档候选、关键词和向量检索结果。"""
    result_groups = [
        ("document_profile", document_results or []),
        ("structured_signal", structured_results or []),
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
                and item.get("source") in {"document_profile", "structured_signal"}
                and entry["item"].get("source") not in {"document_profile", "structured_signal"}
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
            "doc_rank": ranks.get("document_profile"),
            "structured_rank": ranks.get("structured_signal"),
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
        """
        WITH doc_ids AS (
            SELECT CAST(value AS bigint) AS document_id
            FROM unnest(CAST(:document_ids AS bigint[])) AS value
        ),
        live AS (
            SELECT d.id AS document_id, d.parse_status, d.raw_status, d.fusion_status, d.profile_status, d.graph_status
            FROM kb_documents d
            JOIN framework_file_items f ON f.id = d.file_id
            JOIN doc_ids ids ON ids.document_id = d.id
            WHERE d.owner_id = :owner_id
              AND f.owner_id = :owner_id
              AND d.deleted IS FALSE
              AND f.deleted IS FALSE
        ),
        evidence_stats AS (
            SELECT
                document_id,
                count(*) AS evidence_count,
                avg(COALESCE(confidence, 0.0)) AS evidence_confidence,
                count(*) FILTER (
                    WHERE raw_data_id IS NOT NULL
                       OR page_fusion_id IS NOT NULL
                       OR artifact_id IS NOT NULL
                       OR source_hash IS NOT NULL
                ) AS lineage_count
            FROM kb_evidence
            WHERE owner_id = :owner_id
              AND document_id IN (SELECT document_id FROM doc_ids)
              AND status IN ('pending', 'confirmed')
            GROUP BY document_id
        ),
        fusion_stats AS (
            SELECT
                document_id,
                count(*) AS fusion_count,
                avg(COALESCE(confidence, 0.65)) AS fusion_confidence,
                count(*) FILTER (
                    WHERE conflicts_json IS NOT NULL
                      AND json_typeof(conflicts_json) = 'array'
                      AND json_array_length(conflicts_json) > 0
                ) AS conflict_count
            FROM kb_page_fusions
            WHERE owner_id = :owner_id
              AND document_id IN (SELECT document_id FROM doc_ids)
              AND fusion_status = 'done'
            GROUP BY document_id
        ),
        raw_stats AS (
            SELECT
                document_id,
                count(*) AS raw_count,
                count(DISTINCT source_type) AS raw_source_count
            FROM kb_raw_data
            WHERE owner_id = :owner_id
              AND document_id IN (SELECT document_id FROM doc_ids)
              AND status IN ('done', 'degraded')
            GROUP BY document_id
        ),
        fact_stats AS (
            SELECT
                document_id,
                count(*) AS fact_count,
                avg(COALESCE(confidence, 0.55)) AS fact_confidence
            FROM kb_fact_candidates
            WHERE owner_id = :owner_id
              AND document_id IN (SELECT document_id FROM doc_ids)
              AND status IN ('candidate', 'confirmed')
            GROUP BY document_id
        ),
        causal_stats AS (
            SELECT
                document_id,
                count(*) AS causal_count,
                avg(COALESCE(confidence, 0.55)) AS causal_confidence
            FROM kb_causal_candidates
            WHERE owner_id = :owner_id
              AND document_id IN (SELECT document_id FROM doc_ids)
              AND status IN ('candidate', 'confirmed')
            GROUP BY document_id
        ),
        entity_stats AS (
            SELECT
                ce.document_id,
                count(DISTINCT ce.entity_id) AS entity_count,
                avg(COALESCE(ce.confidence, 0.0)) AS entity_confidence,
                count(DISTINCT ge.id) AS graph_edge_count
            FROM kb_chunk_entities ce
            LEFT JOIN kb_graph_nodes gn ON gn.owner_id = ce.owner_id AND gn.entity_id = ce.entity_id
            LEFT JOIN kb_graph_edges ge ON ge.owner_id = ce.owner_id AND (ge.source_node_id = gn.id OR ge.target_node_id = gn.id)
            WHERE ce.owner_id = :owner_id
              AND ce.document_id IN (SELECT document_id FROM doc_ids)
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
) -> list[dict]:
    """混合检索：向量 + 关键词 → RRF 融合 → 可选 rerank。"""
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
        diagnostics.stage(
            "structured_signal_search",
            duration_ms=_elapsed_ms(stage_started_at),
            result_count=len(structured_results),
        )
    else:
        diagnostics.skipped("structured_signal_search", "fast_local_plan")
    stage_started_at = time.perf_counter()
    kw_results = await keyword_search(db, _keyword_query_for_plan(query, query_plan), owner_id, top_k=top_k * 2)
    diagnostics.stage("keyword_search", duration_ms=_elapsed_ms(stage_started_at), result_count=len(kw_results))
    vec_results = []
    if not fast_local_plan:
        stage_started_at = time.perf_counter()
        vec_results = await vector_search(db, query, owner_id, top_k=top_k * 2, diagnostics=diagnostics)
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
        dedupe_by_document=document_intent,
        query_plan=query_plan,
    )
    diagnostics.stage("rrf_fusion", duration_ms=_elapsed_ms(stage_started_at), result_count=len(results))
    for result in results:
        result.setdefault("query_plan", query_plan)
    stage_started_at = time.perf_counter()
    results = await verify_and_score_results(db, results, owner_id=owner_id, query_plan=query_plan)
    diagnostics.stage(
        "verify_and_score_results",
        duration_ms=_elapsed_ms(stage_started_at),
        result_count=len(results),
    )

    # 可选 rerank
    if use_rerank and results:
        stage_started_at = time.perf_counter()
        try:
            docs = [r["text"] for r in results]
            reranked = await rerank(query, docs, top_k=top_k)
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
            "index_layer": ch.index_layer or "base_parse",
            "source_stage": ch.source_stage or "",
            "source_ref_id": ch.source_ref_id,
            "text": ch.text,
            "keywords": ch.keywords,
            **_live_source_fields(),
        }
        for ch in chunks
    ]
