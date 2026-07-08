"""Derived governance backfills for searchable knowledge side indexes."""
from __future__ import annotations

import asyncio
import json
import logging
import re
import unicodedata
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    KbAnalysisArtifact,
    KbArtifactLineage,
    KbConclusionEvidence,
    KbDisambiguation,
    KbEntityAlias,
    KbEntityDictionary,
    KbEvidence,
    KbFactCandidate,
)
from .llm_diagnostics import timed_llm_chat
from .model_routing import resolve_knowledge_profile

logger = logging.getLogger("v2.knowledge").getChild("derived_governance")

DERIVED_GOVERNANCE_VERSION = "kb_derived_governance_v1"
CONCLUSION_EVIDENCE_TIMEOUT_SECONDS = 45.0
_INNER_ALIAS_SPLIT_RE = re.compile(r"[/／|｜,，;；、]+")
_OUTER_ALIAS_SPLIT_RE = re.compile(r"[/／|｜]+")
_PAREN_RE = re.compile(r"[（(]([^（）()]{1,120})[）)]")
_SPACE_RE = re.compile(r"\s+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_TERM_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][A-Za-z0-9_.-]{1,}")


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    return _SPACE_RE.sub("", text)


def _clean_alias(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return _SPACE_RE.sub(" ", text)


def _is_low_signal_alias(value: str) -> bool:
    normalized = _normalize_text(value)
    if not normalized:
        return True
    if normalized.isdigit() and len(normalized) <= 4:
        return True
    if len(normalized) <= 1:
        return True
    return False


def _alias_candidates(name: str) -> list[str]:
    """Extract open-ended aliases from punctuation/parenthetical variants."""
    cleaned_name = _clean_alias(name)
    if not cleaned_name:
        return []
    candidates: set[str] = set()
    for match in _PAREN_RE.finditer(cleaned_name):
        inner = match.group(1)
        for part in _INNER_ALIAS_SPLIT_RE.split(inner):
            alias = _clean_alias(part)
            if alias and alias != cleaned_name:
                candidates.add(alias)
    outer = _PAREN_RE.sub(" ", cleaned_name)
    if _OUTER_ALIAS_SPLIT_RE.search(outer):
        for part in _OUTER_ALIAS_SPLIT_RE.split(outer):
            alias = _clean_alias(part)
            if alias and alias != cleaned_name:
                candidates.add(alias)
    compact = _SPACE_RE.sub("", cleaned_name)
    if compact and compact != cleaned_name and _CJK_RE.search(cleaned_name):
        candidates.add(compact)
    return sorted(
        alias
        for alias in candidates
        if len(alias) <= 256
        and not _is_low_signal_alias(alias)
        and _normalize_text(alias) != _normalize_text(cleaned_name)
    )


def _as_int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        try:
            parsed = int(item)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            result.append(parsed)
    return result


def _claim_terms(value: str) -> set[str]:
    terms: set[str] = set()
    for match in _TERM_RE.finditer(unicodedata.normalize("NFKC", str(value or ""))):
        term = _normalize_text(match.group(0))
        if len(term) >= 2 and not (term.isdigit() and len(term) <= 4):
            terms.add(term)
    return terms


def _evidence_match_score(claim: str, evidence_excerpt: str) -> float:
    claim_norm = _normalize_text(claim)
    evidence_norm = _normalize_text(evidence_excerpt)
    if not claim_norm or not evidence_norm:
        return 0.0
    if claim_norm in evidence_norm:
        return 1.0
    if evidence_norm in claim_norm and len(evidence_norm) >= 12:
        return 0.92
    claim_terms = _claim_terms(claim)
    evidence_terms = _claim_terms(evidence_excerpt)
    if not claim_terms or not evidence_terms:
        return 0.0
    overlap = claim_terms & evidence_terms
    if not overlap:
        return 0.0
    coverage = len(overlap) / max(1, len(claim_terms))
    density = len(overlap) / max(1, len(evidence_terms))
    return (coverage * 0.75) + (density * 0.25)


def _best_evidence_ids(claim: str, evidence_rows: list[KbEvidence]) -> list[int]:
    return [evidence_id for _, evidence_id in _best_evidence_scores(claim, evidence_rows, limit=5)]


def _best_evidence_scores(claim: str, evidence_rows: list[KbEvidence], *, limit: int) -> list[tuple[float, int]]:
    scored: list[tuple[float, int]] = []
    for evidence in evidence_rows:
        score = _evidence_match_score(claim, evidence.excerpt)
        if score >= 0.28:
            scored.append((score, int(evidence.id)))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[:limit]


def _extract_json_object(text: str) -> dict | None:
    raw = str(text or "").strip()
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


def _clamp_float(value: object, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


async def _llm_judge_conclusion_evidence(
    *,
    claim: str,
    document_id: int,
    evidence_candidates: list[KbEvidence],
) -> dict:
    if not evidence_candidates:
        return {"supported": False, "evidence_ids": [], "confidence": 0.0, "reason": "no_candidates"}
    from app.gateway.router import gateway_router

    profile_key = resolve_knowledge_profile("derived_governance_evidence")
    digest = [
        {
            "evidence_id": int(evidence.id),
            "page": evidence.page,
            "confidence": evidence.confidence,
            "excerpt": str(evidence.excerpt or "")[:800],
        }
        for evidence in evidence_candidates[:8]
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "你是企业知识库证据链裁判。只返回 JSON，不要解释。"
                "任务是判断一个结论是否被候选证据明确支持。"
                "只能选择候选 evidence_id，不允许创造证据。"
                "若证据只是主题相关但不能支持结论，supported=false。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"document_id: {document_id}\n"
                f"结论: {claim[:1600]}\n"
                f"候选证据: {json.dumps(digest, ensure_ascii=False)}\n\n"
                "返回 JSON: {\"supported\":true,"
                "\"evidence_ids\":[1,2],\"confidence\":0.82,"
                "\"reason\":\"一句话说明证据如何支持结论\"}"
            ),
        },
    ]
    try:
        result = await asyncio.wait_for(
            timed_llm_chat(
                logger=logger,
                stage="derived_governance_evidence",
                profile_key=profile_key,
                messages=messages,
                chat_func=gateway_router.chat,
                document_id=document_id,
                extra={"candidate_count": len(digest)},
            ),
            timeout=CONCLUSION_EVIDENCE_TIMEOUT_SECONDS,
        )
        content = str(result.get("content") or "")
        parsed = _extract_json_object(content) or {}
        allowed_ids = {int(evidence.id) for evidence in evidence_candidates}
        selected_ids = []
        for raw_id in parsed.get("evidence_ids") or []:
            try:
                evidence_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if evidence_id in allowed_ids and evidence_id not in selected_ids:
                selected_ids.append(evidence_id)
        supported = bool(parsed.get("supported")) and bool(selected_ids)
        return {
            "supported": supported,
            "evidence_ids": selected_ids[:5],
            "confidence": _clamp_float(parsed.get("confidence"), 0.0, 1.0, 0.75 if supported else 0.0),
            "reason": str(parsed.get("reason") or "")[:1000],
            "model_used": str(
                result.get("model")
                or result.get("model_used")
                or (result.get("model_diagnostics") or {}).get("selected_profile")
                or profile_key
            ),
            "diagnostics": {
                "schema_version": DERIVED_GOVERNANCE_VERSION,
                "source": "llm_evidence_judge",
                "profile_key": profile_key,
                "model_diagnostics": result.get("model_diagnostics") or {},
                "candidate_evidence_ids": [int(evidence.id) for evidence in evidence_candidates[:8]],
                "reason": str(parsed.get("reason") or "")[:1000],
            },
        }
    except Exception as exc:
        logger.warning("Conclusion evidence LLM judge failed document_id=%s: %s", document_id, exc)
        return {"supported": False, "evidence_ids": [], "confidence": 0.0, "reason": str(exc)}


async def backfill_derived_governance(
    db: AsyncSession,
    *,
    owner_id: int,
    dry_run: bool = True,
    limit: int = 5000,
    include_lineage: bool = True,
    include_conclusion_evidence: bool = True,
    include_entity_aliases: bool = True,
    include_disambiguation: bool = True,
    use_llm_evidence_judge: bool = False,
    llm_limit: int = 100,
) -> dict:
    """Backfill derived governance side tables from existing knowledge outputs.

    This intentionally reuses existing artifacts, fact candidates and entity
    dictionary rows. It does not invent taxonomy catalogs or merge-log records
    without provenance from an actual algorithmic decision or feedback signal.
    """
    bounded_limit = max(1, min(int(limit or 5000), 50000))
    bounded_llm_limit = max(0, min(int(llm_limit or 0), 5000))
    counts = {
        "artifact_lineage": 0,
        "conclusion_evidence": 0,
        "entity_aliases": 0,
        "disambiguation": 0,
        "catalogs": 0,
        "entity_merge_log": 0,
    }
    previews: dict[str, list[dict]] = {
        "artifact_lineage": [],
        "conclusion_evidence": [],
        "entity_aliases": [],
        "disambiguation": [],
    }

    if include_lineage:
        counts["artifact_lineage"] = await _backfill_artifact_lineage(
            db,
            owner_id=owner_id,
            dry_run=dry_run,
            limit=bounded_limit,
            previews=previews["artifact_lineage"],
        )
    if include_conclusion_evidence:
        counts["conclusion_evidence"] = await _backfill_conclusion_evidence(
            db,
            owner_id=owner_id,
            dry_run=dry_run,
            limit=bounded_limit,
            previews=previews["conclusion_evidence"],
            use_llm_evidence_judge=use_llm_evidence_judge,
            llm_limit=bounded_llm_limit,
        )
    if include_entity_aliases or include_disambiguation:
        alias_count, disambiguation_count = await _backfill_entity_governance(
            db,
            owner_id=owner_id,
            dry_run=dry_run,
            limit=bounded_limit,
            include_aliases=include_entity_aliases,
            include_disambiguation=include_disambiguation,
            alias_preview=previews["entity_aliases"],
            disambiguation_preview=previews["disambiguation"],
        )
        counts["entity_aliases"] = alias_count
        counts["disambiguation"] = disambiguation_count

    if not dry_run:
        await db.commit()

    return {
        "dry_run": bool(dry_run),
        "will_mutate": not dry_run,
        "limit": bounded_limit,
        "llm_limit": bounded_llm_limit,
        "use_llm_evidence_judge": bool(use_llm_evidence_judge),
        "schema_version": DERIVED_GOVERNANCE_VERSION,
        "counts": counts,
        "previews": previews if dry_run else {},
        "skipped": {
            "kb_catalogs": (
                "catalogs need algorithm provenance/feedback fields before auto-writing; "
                "derive them as candidates first instead of mutating the primary taxonomy"
            ),
            "kb_entity_merge_log": "merge logs are written only when an algorithmic or feedback-confirmed merge action happens",
        },
    }


async def _backfill_artifact_lineage(
    db: AsyncSession,
    *,
    owner_id: int,
    dry_run: bool,
    limit: int,
    previews: list[dict],
) -> int:
    existing_ids = set(
        (await db.execute(
            select(KbArtifactLineage.artifact_id).where(KbArtifactLineage.owner_id == owner_id)
        )).scalars().all()
    )
    artifacts = (
        await db.execute(
            select(KbAnalysisArtifact)
            .where(
                KbAnalysisArtifact.owner_id == owner_id,
                KbAnalysisArtifact.id.not_in(existing_ids or {-1}),
            )
            .order_by(KbAnalysisArtifact.id.asc())
            .limit(limit)
        )
    ).scalars().all()
    for artifact in artifacts:
        payload = {
            "artifact_id": int(artifact.id),
            "document_id": int(artifact.document_id),
            "stage": artifact.stage,
            "unit_type": artifact.unit_type or "document",
            "unit_key": artifact.unit_key or "document",
        }
        if dry_run:
            if len(previews) < 10:
                previews.append(payload)
            continue
        db.add(
            KbArtifactLineage(
                owner_id=owner_id,
                artifact_id=int(artifact.id),
                document_id=int(artifact.document_id),
                stage=artifact.stage,
                unit_type=artifact.unit_type or "document",
                unit_key=artifact.unit_key or "document",
                source_artifact_ids=artifact.source_artifact_ids or [],
                reused_from_artifact_id=None,
                reuse_type="new",
                input_hash=artifact.input_hash or "",
                output_hash=artifact.output_hash or "",
                schema_version=artifact.schema_version or "v1",
                diagnostics_json={
                    "schema_version": DERIVED_GOVERNANCE_VERSION,
                    "source": "kb_analysis_artifacts",
                },
            )
        )
    return len(artifacts)


async def _backfill_conclusion_evidence(
    db: AsyncSession,
    *,
    owner_id: int,
    dry_run: bool,
    limit: int,
    previews: list[dict],
    use_llm_evidence_judge: bool,
    llm_limit: int,
) -> int:
    existing = {
        (int(document_id), _normalize_text(conclusion))
        for document_id, conclusion in (
            await db.execute(
                select(KbConclusionEvidence.document_id, KbConclusionEvidence.conclusion)
                .where(KbConclusionEvidence.owner_id == owner_id)
            )
        ).all()
    }
    facts = (
        await db.execute(
            select(KbFactCandidate)
            .where(
                KbFactCandidate.owner_id == owner_id,
                KbFactCandidate.claim_text != "",
            )
            .order_by(KbFactCandidate.confidence.desc().nullslast(), KbFactCandidate.id.asc())
            .limit(limit)
        )
    ).scalars().all()
    document_ids = sorted({int(fact.document_id) for fact in facts})
    evidence_by_document: dict[int, list[KbEvidence]] = defaultdict(list)
    if document_ids:
        evidence_rows = (
            await db.execute(
                select(KbEvidence)
                .where(
                    KbEvidence.owner_id == owner_id,
                    KbEvidence.document_id.in_(document_ids),
                    KbEvidence.excerpt != "",
                )
                .order_by(KbEvidence.confidence.desc(), KbEvidence.id.asc())
            )
        ).scalars().all()
        for evidence in evidence_rows:
            evidence_by_document[int(evidence.document_id)].append(evidence)
    created = 0
    llm_calls = 0
    for fact in facts:
        evidence_ids = _as_int_list(fact.evidence_ids)
        conclusion = _clean_alias(fact.claim_text)
        evidence_rows = evidence_by_document.get(int(fact.document_id), [])
        local_scores = _best_evidence_scores(conclusion, evidence_rows, limit=8)
        evidence_by_id = {int(evidence.id): evidence for evidence in evidence_rows}
        llm_result: dict | None = None
        if not conclusion or not evidence_ids:
            evidence_ids = [evidence_id for _, evidence_id in local_scores[:5]]
        if (
            not dry_run
            and use_llm_evidence_judge
            and llm_calls < llm_limit
            and conclusion
            and evidence_rows
        ):
            candidate_ids = evidence_ids or [evidence_id for _, evidence_id in local_scores[:8]]
            if not candidate_ids:
                candidate_ids = [int(evidence.id) for evidence in evidence_rows[:8]]
            llm_result = await _llm_judge_conclusion_evidence(
                claim=conclusion,
                document_id=int(fact.document_id),
                evidence_candidates=[evidence_by_id[eid] for eid in candidate_ids[:8] if eid in evidence_by_id],
            )
            llm_calls += 1
            if llm_result.get("supported"):
                evidence_ids = _as_int_list(llm_result.get("evidence_ids"))
            else:
                evidence_ids = []
        if not conclusion or not evidence_ids:
            continue
        key = (int(fact.document_id), _normalize_text(conclusion))
        if key in existing:
            continue
        existing.add(key)
        created += 1
        payload = {
            "document_id": int(fact.document_id),
            "conclusion": conclusion[:160],
            "evidence_ids": evidence_ids[:20],
            "confidence": (
                float(llm_result["confidence"])
                if llm_result and llm_result.get("supported")
                else float(fact.confidence if fact.confidence is not None else 0.5)
            ),
        }
        if dry_run:
            if len(previews) < 10:
                previews.append(payload)
            continue
        db.add(
            KbConclusionEvidence(
                owner_id=owner_id,
                document_id=int(fact.document_id),
                conclusion=conclusion,
                evidence_ids=evidence_ids,
                confidence=payload["confidence"],
                source="llm_evidence_judge" if llm_result and llm_result.get("supported") else "algorithmic_overlap",
                model_used=str(llm_result.get("model_used") or "") if llm_result else None,
                diagnostics_json=(
                    llm_result.get("diagnostics")
                    if llm_result and llm_result.get("diagnostics")
                    else {
                        "schema_version": DERIVED_GOVERNANCE_VERSION,
                        "source": "algorithmic_overlap",
                        "local_scores": [
                            {"score": round(score, 4), "evidence_id": evidence_id}
                            for score, evidence_id in local_scores[:8]
                        ],
                    }
                ),
            )
        )
    return created


async def _backfill_entity_governance(
    db: AsyncSession,
    *,
    owner_id: int,
    dry_run: bool,
    limit: int,
    include_aliases: bool,
    include_disambiguation: bool,
    alias_preview: list[dict],
    disambiguation_preview: list[dict],
) -> tuple[int, int]:
    entities = (
        await db.execute(
            select(KbEntityDictionary)
            .where(KbEntityDictionary.owner_id == owner_id, KbEntityDictionary.status != "archived")
            .order_by(KbEntityDictionary.id.asc())
            .limit(limit)
        )
    ).scalars().all()
    existing_aliases = {
        (int(entity_id), _normalize_text(alias))
        for entity_id, alias in (
            await db.execute(
                select(KbEntityAlias.entity_id, KbEntityAlias.alias).where(KbEntityAlias.owner_id == owner_id)
            )
        ).all()
    }
    alias_to_entities: dict[str, set[int]] = defaultdict(set)
    for entity in entities:
        normalized_name = _normalize_text(entity.name)
        if normalized_name:
            alias_to_entities[normalized_name].add(int(entity.id))
        for alias in _alias_candidates(entity.name):
            alias_to_entities[_normalize_text(alias)].add(int(entity.id))

    alias_count = 0
    if include_aliases:
        for entity in entities:
            for alias in _alias_candidates(entity.name):
                key = (int(entity.id), _normalize_text(alias))
                if key in existing_aliases:
                    continue
                existing_aliases.add(key)
                alias_count += 1
                payload = {"entity_id": int(entity.id), "entity": entity.name, "alias": alias}
                if dry_run:
                    if len(alias_preview) < 10:
                        alias_preview.append(payload)
                    continue
                db.add(KbEntityAlias(owner_id=owner_id, entity_id=int(entity.id), alias=alias))

    disambiguation_count = 0
    if include_disambiguation:
        existing_terms = set(
            (await db.execute(
                select(KbDisambiguation.term).where(KbDisambiguation.owner_id == owner_id)
            )).scalars().all()
        )
        for term, entity_ids in sorted(alias_to_entities.items()):
            if len(entity_ids) < 2 or term in existing_terms:
                continue
            disambiguation_count += 1
            payload = {"term": term, "entity_ids": sorted(entity_ids)}
            if dry_run:
                if len(disambiguation_preview) < 10:
                    disambiguation_preview.append(payload)
                continue
            db.add(
                KbDisambiguation(
                    owner_id=owner_id,
                    term=term,
                    entity_ids=sorted(entity_ids),
                    resolved=False,
                )
            )
    return alias_count, disambiguation_count


async def derived_governance_counts(db: AsyncSession, *, owner_id: int) -> dict[str, int]:
    return {
        "artifact_lineage": int(await db.scalar(select(func.count(KbArtifactLineage.id)).where(KbArtifactLineage.owner_id == owner_id)) or 0),
        "conclusion_evidence": int(await db.scalar(select(func.count(KbConclusionEvidence.id)).where(KbConclusionEvidence.owner_id == owner_id)) or 0),
        "entity_aliases": int(await db.scalar(select(func.count(KbEntityAlias.id)).where(KbEntityAlias.owner_id == owner_id)) or 0),
        "disambiguation": int(await db.scalar(select(func.count(KbDisambiguation.id)).where(KbDisambiguation.owner_id == owner_id)) or 0),
    }
