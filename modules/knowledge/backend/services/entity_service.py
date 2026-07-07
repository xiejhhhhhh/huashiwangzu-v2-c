"""知识库实体抽取与图谱服务。

用 gateway 大模型从解析内容中抽取实体、关系、证据，构建知识图谱。
"""
import asyncio
import json
import logging
from time import perf_counter

from app.database import AsyncSessionLocal
from app.gateway.router import gateway_router
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .analysis_artifact_service import model_used_from_result, resolve_stage_prompt_hash, stable_hash
from .llm_diagnostics import timed_llm_chat
from .model_routing import resolve_knowledge_concurrency, resolve_knowledge_profile
from .prompt_utils import TENTITY, TFUSION_LEGACY, load_prompt_detached

logger = logging.getLogger("v2.knowledge").getChild("entity")

ENTITY_PAGE_CONCURRENCY = 6

async def extract_entities_from_text(
    text: str,
    profile_key: str | None = None,
    db: AsyncSession | None = None,
) -> dict:
    """用大模型从文本中提取实体和关系。返回 {"entities": [...], "relationships": [...]}。"""
    if not text.strip():
        return {"entities": [], "relationships": []}

    resolved_profile_key = resolve_knowledge_profile("entity", profile_key)
    system_prompt = await load_prompt_detached(TENTITY)
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请提取以下内容的实体和关系：\n\n{text[:6000]}"},
        ]
        resp = await timed_llm_chat(
            logger=logger,
            stage="entity",
            profile_key=resolved_profile_key,
            messages=messages,
            chat_func=gateway_router.chat,
            extra={"text_chars": len(text)},
        )
        content = resp.get("content", "")
        if not content:
            return {"entities": [], "relationships": []}

        # 提取 JSON
        # 尝试直接解析
        content = content.strip()
        if content.startswith("```"):
            # 去掉 markdown 代码块标记
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            content = "\n".join(lines)

        parsed = json.loads(content)
        entities = parsed.get("entities", [])
        relationships = parsed.get("relationships", [])
        return {
            "entities": entities,
            "relationships": relationships,
            "model_degraded": bool(resp.get("model_degraded")),
            "model_diagnostics": resp.get("model_diagnostics") or {},
        }
    except Exception as e:
        logger.warning("Entity extraction failed: %s", e)
        return {"entities": [], "relationships": [], "errors": [str(e)]}


async def fuse_page_text(
    text: str,
    profile_key: str | None = None,
    db: AsyncSession | None = None,
) -> str:
    """用大模型融合页级文本。"""
    if not text.strip():
        return text

    resolved_profile_key = resolve_knowledge_profile("legacy_page_fusion", profile_key)
    system_prompt = await load_prompt_detached(TFUSION_LEGACY)
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请融合以下分块内容：\n\n{text[:8000]}"},
        ]
        resp = await timed_llm_chat(
            logger=logger,
            stage="legacy_page_fusion",
            profile_key=resolved_profile_key,
            messages=messages,
            chat_func=gateway_router.chat,
            extra={"text_chars": len(text)},
        )
        result = resp.get("content", "")
        return result.strip() if result else text
    except Exception as e:
        logger.warning("Page fusion failed: %s", e)
        return text


def _first_model_diagnostics_value(diagnostics: dict | list | None, key: str) -> str | None:
    if isinstance(diagnostics, list):
        for item in diagnostics:
            if isinstance(item, dict) and item.get(key):
                return str(item[key])
    if isinstance(diagnostics, dict) and diagnostics.get(key):
        return str(diagnostics[key])
    return None


def _model_used_from_diagnostics(diagnostics: dict | list | None) -> str | None:
    return (
        _first_model_diagnostics_value(diagnostics, "selected_profile")
        or _first_model_diagnostics_value(diagnostics, "model_used")
    )


async def _latest_analysis_artifact_id(db: AsyncSession, document_id: int, owner_id: int, stage: str) -> int | None:
    from ..models import KbAnalysisArtifact

    result = await db.execute(
        select(KbAnalysisArtifact.id)
        .where(
            KbAnalysisArtifact.document_id == document_id,
            KbAnalysisArtifact.owner_id == owner_id,
            KbAnalysisArtifact.stage == stage,
        )
        .order_by(KbAnalysisArtifact.id.desc())
        .limit(1)
    )
    value = result.scalar_one_or_none()
    return int(value) if value is not None else None


def _fusion_source_hash(fusion, raw_rows: list) -> str:
    return stable_hash({
        "page_fusion_id": getattr(fusion, "id", None),
        "page": getattr(fusion, "page", None),
        "fused_text": getattr(fusion, "fused_text", ""),
        "raw_hashes": [getattr(row, "content_hash", None) for row in raw_rows],
    })


async def process_document_entities(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
    blocks: list[dict],
) -> dict:
    """处理文档实体抽取：分块提取实体、建词典、建图谱节点边、存证据。

    返回统计：{"entities_found": int, "relationships_found": int, "errors": [...]}
    """
    from ..models import (
        KbChunk,
        KbChunkEntity,
        KbEntityDictionary,
        KbEvidence,
        KbGovernanceCandidate,
        KbGraphEdge,
        KbGraphNode,
    )

    stats = {"entities_found": 0, "relationships_found": 0, "errors": []}

    # 收集所有文本按页分组
    page_texts: dict[int, list[str]] = {}
    for block in blocks:
        text = (block.get("text") or "").strip()
        page = block.get("page") or 0
        if text:
            if page not in page_texts:
                page_texts[page] = []
            page_texts[page].append(text)

    all_entities: list[dict] = []
    all_relationships: list[dict] = []
    page_model_diagnostics: dict[int, dict | list | None] = {}
    page_model_used: dict[int, str | None] = {}
    processed_pages = 0

    for page, texts in page_texts.items():
        combined = "\n\n".join(texts)
        if len(combined) < 20:
            continue

        # 每页抽取一次实体
        result = await extract_entities_from_text(combined, db=db)
        page_model_diagnostics[page] = result.get("model_diagnostics")
        page_model_used[page] = model_used_from_result(result) or _model_used_from_diagnostics(
            page_model_diagnostics[page]
        )
        all_entities.extend(result.get("entities", []))
        all_relationships.extend(result.get("relationships", []))
        stats["errors"].extend(result.get("errors", []))
        if result.get("model_degraded"):
            stats["model_degraded"] = True
            stats.setdefault("model_diagnostics", []).append(result.get("model_diagnostics") or {})
        processed_pages += 1

        # 小延迟避免 API 限流
        if processed_pages % 3 == 0 and len(page_texts) > 3:
            import asyncio
            await asyncio.sleep(0.5)

    # 去重实体（同名 + 同类别视为同一实体）
    seen_entities: dict[str, dict] = {}
    for ent in all_entities:
        name = (ent.get("name") or "").strip()
        category = ent.get("category", "通用")
        key = f"{name}|{category}"
        if key not in seen_entities:
            seen_entities[key] = ent
        else:
            # 合并描述
            existing = seen_entities[key]
            existing_desc = existing.get("description", "") or ""
            new_desc = ent.get("description", "") or ""
            if new_desc and new_desc not in existing_desc:
                existing["description"] = existing_desc + "; " + new_desc if existing_desc else new_desc

    # 保存实体到词典和图谱
    entity_name_to_id: dict[str, int] = {}
    # 本地 dedup：避免同一 session 内重复 governance candidate
    created_candidates: set[str] = set()
    for key, ent in seen_entities.items():
        name = ent["name"]
        category = ent.get("category", "通用")
        description = ent.get("description", "")

        # 查重：是否已有同名实体
        existing_r = await db.execute(
            select(KbEntityDictionary).where(
                KbEntityDictionary.name == name,
                KbEntityDictionary.owner_id == owner_id,
            ).order_by(KbEntityDictionary.id).limit(1)
        )
        existing_entity = existing_r.scalars().first()

        if existing_entity:
            entity_id = existing_entity.id
            entity_name_to_id[name] = entity_id
        else:
            # 新建实体词典条目
            new_entity = KbEntityDictionary(
                owner_id=owner_id,
                name=name,
                category=category,
                description=description,
                status="candidate",  # 新抽取实体先标记 candidate，待确认
                source="extraction",
            )
            db.add(new_entity)
            await db.flush()
            entity_id = new_entity.id
            entity_name_to_id[name] = entity_id

            # 建图谱节点
            node = KbGraphNode(
                owner_id=owner_id,
                entity_id=entity_id,
                label=name,
                category=category,
                description=description,
            )
            db.add(node)
            await db.flush()

            # 写入治理候选（本地 set 去重）
            if name not in created_candidates:
                created_candidates.add(name)
                candidate = KbGovernanceCandidate(
                    owner_id=owner_id,
                    document_id=document_id,
                    entity_name=name,
                    category=category,
                    excerpt=description[:300] if description else name,
                    confidence=0.7,
                    audit_status="pending",
                )
                db.add(candidate)

    # 保存关系（图谱边）
    for rel in all_relationships:
        source_name = (rel.get("source") or "").strip()
        target_name = (rel.get("target") or "").strip()
        relation = rel.get("relation", "相关")

        source_id = entity_name_to_id.get(source_name)
        target_id = entity_name_to_id.get(target_name)

        if not source_id or not target_id:
            continue

        # 查 source/target node_id（entity_id 到 node_id）
        s_node_r = await db.execute(
            select(KbGraphNode).where(KbGraphNode.entity_id == source_id, KbGraphNode.owner_id == owner_id).limit(1)
        )
        t_node_r = await db.execute(
            select(KbGraphNode).where(KbGraphNode.entity_id == target_id, KbGraphNode.owner_id == owner_id).limit(1)
        )
        s_node = s_node_r.scalars().first()
        t_node = t_node_r.scalars().first()
        if not s_node or not t_node:
            continue

        # 查重（按 node_id 查，entity_id ≠ node_id；用 .first() 防历史重复抛 MultipleResultsFound）
        existing_r = await db.execute(
            select(KbGraphEdge).where(
                KbGraphEdge.source_node_id == s_node.id,
                KbGraphEdge.target_node_id == t_node.id,
                KbGraphEdge.relation == relation,
            ).order_by(KbGraphEdge.id).limit(1)
        )
        if existing_r.scalars().first():
            continue

        edge = KbGraphEdge(
            owner_id=owner_id,
            source_node_id=s_node.id,
            target_node_id=t_node.id,
            relation=relation,
            weight=1.0,
            description=rel.get("description", ""),
        )
        db.add(edge)
        stats["relationships_found"] += 1

    chunks_r = await db.execute(
        select(KbChunk)
        .where(KbChunk.document_id == document_id, KbChunk.owner_id == owner_id)
        .order_by(KbChunk.page, KbChunk.chunk_index)
    )
    page_to_chunks: dict[int, list[int]] = {}
    for ch in chunks_r.scalars().all():
        page_to_chunks.setdefault(ch.page or 0, []).append(ch.id)

    seen_evidence_key: set[tuple[int, int]] = set()
    seen_chunk_entity_key: set[tuple[int, int]] = set()
    graph_prompt_hash = await resolve_stage_prompt_hash(db, "graph")

    # 保存证据与 chunk-entity 关联。旧版本曾写 chunk_id=0，导致证据链不可追溯。
    for ent in all_entities:
        name = ent.get("name", "")
        entity_id = entity_name_to_id.get(name)
        if not entity_id:
            continue
        page = 0
        description_prefix = (ent.get("description") or "").strip()[:20]
        for block in blocks:
            text = (block.get("text") or "").strip()
            if text and (name in text or (description_prefix and description_prefix in text)):
                page = block.get("page") or 0
                break
        chunk_ids = page_to_chunks.get(page, [])
        evidence_text = ent.get("description", "")
        if evidence_text and len(evidence_text) >= 5:
            ev_key = (entity_id, page)
            if ev_key not in seen_evidence_key:
                seen_evidence_key.add(ev_key)
                evidence = KbEvidence(
                    owner_id=owner_id,
                    entity_id=entity_id,
                    document_id=document_id,
                    chunk_id=chunk_ids[0] if chunk_ids else 0,
                    page=page,
                    excerpt=evidence_text[:500],
                    confidence=0.7,
                    status="pending",
                    source_round="chunk",
                    claim_type="entity",
                    source_hash=stable_hash({
                        "document_id": document_id,
                        "page": page,
                        "chunk_ids": chunk_ids,
                        "excerpt": evidence_text[:500],
                    }),
                    prompt_hash=graph_prompt_hash,
                    model_used=page_model_used.get(page),
                    diagnostics_json={
                        "model_diagnostics": page_model_diagnostics.get(page),
                        "source": "legacy_chunk_entity_extraction",
                    },
                )
                db.add(evidence)
        for cid in chunk_ids:
            ce_key = (entity_id, cid)
            if ce_key in seen_chunk_entity_key:
                continue
            seen_chunk_entity_key.add(ce_key)
            db.add(KbChunkEntity(
                owner_id=owner_id,
                chunk_id=cid,
                entity_id=entity_id,
                document_id=document_id,
                confidence=0.7,
            ))

    stats["entities_found"] = len(seen_entities)
    await db.commit()
    logger.info(
        "Document %d entity extraction: %d entities, %d relationships, %d pages",
        document_id, stats["entities_found"], stats["relationships_found"], processed_pages,
    )
    return stats


async def process_document_entities_from_fusions(
    db: AsyncSession,
    document_id: int,
    owner_id: int,
) -> dict:
    """基于融合层重建实体/图谱（第6层）。

    从 kb_page_fusions 读取各页融合正文 → LLM 抽取 → 去重 → 写入图谱表。
    幂等：每次重跑先清该文档的旧实体/图谱数据（kb_entity_dictionary 保留已有条目供其他文档引用）。
    """
    from ..models import (
        KbChunk,
        KbChunkEntity,
        KbEntityDictionary,
        KbEvidence,
        KbGovernanceCandidate,
        KbGraphEdge,
        KbGraphNode,
        KbPageFusion,
        KbRawData,
    )

    stage_started = perf_counter()
    stats = {"entities_found": 0, "relationships_found": 0, "errors": []}

    cleanup_duration_ms = 0

    # 读取所有页融合正文
    r = await db.execute(
        select(KbPageFusion)
        .where(
            KbPageFusion.document_id == document_id,
            KbPageFusion.owner_id == owner_id,
            KbPageFusion.fused_text != "",
        )
        .order_by(KbPageFusion.page)
    )
    fusions = r.scalars().all()

    if not fusions:
        stats["errors"].append("No fused pages found")
        return stats

    fusion_by_page = {int(pf.page): pf for pf in fusions}
    raw_rows_r = await db.execute(
        select(KbRawData)
        .where(KbRawData.document_id == document_id, KbRawData.owner_id == owner_id)
        .order_by(KbRawData.page, KbRawData.round, KbRawData.id)
    )
    page_to_raw_rows: dict[int, list[KbRawData]] = {}
    for raw in raw_rows_r.scalars().all():
        page_to_raw_rows.setdefault(int(raw.page), []).append(raw)
    fusion_artifact_id = await _latest_analysis_artifact_id(db, document_id, owner_id, "fusion")
    graph_prompt_hash = await resolve_stage_prompt_hash(db, "graph")
    await db.commit()

    all_entities: list[dict] = []
    all_relationships: list[dict] = []
    entity_page: list[int] = []  # tracks which page each raw entity came from (parallel to all_entities)
    page_model_diagnostics: dict[int, dict | list | None] = {}
    page_model_used: dict[int, str | None] = {}
    processed_pages = 0
    extraction_started = perf_counter()
    page_durations: dict[int, int] = {}

    page_concurrency = resolve_knowledge_concurrency("entity_extract", ENTITY_PAGE_CONCURRENCY)
    sem = asyncio.Semaphore(page_concurrency)

    async def _extract_page(pf) -> dict:
        text = pf.fused_text
        page = int(pf.page)
        if len(text) < 20:
            return {"page": page, "skipped": True}
        async with sem:
            page_started = perf_counter()
            async with AsyncSessionLocal() as prompt_db:
                result = await extract_entities_from_text(text, db=prompt_db)
            return {
                "page": page,
                "duration_ms": round((perf_counter() - page_started) * 1000),
                "result": result,
            }

    page_results = await asyncio.gather(
        *(_extract_page(pf) for pf in fusions),
        return_exceptions=True,
    )
    for item in page_results:
        if isinstance(item, Exception):
            stats["errors"].append(str(item))
            continue
        if item.get("skipped"):
            continue
        page = int(item["page"])
        result = item["result"]
        page_durations[page] = int(item.get("duration_ms") or 0)
        page_ents = result.get("entities", [])
        page_model_diagnostics[page] = result.get("model_diagnostics")
        page_model_used[page] = model_used_from_result(result) or _model_used_from_diagnostics(
            page_model_diagnostics[page]
        )
        all_entities.extend(page_ents)
        entity_page.extend([page] * len(page_ents))
        all_relationships.extend(result.get("relationships", []))
        stats["errors"].extend(result.get("errors", []))
        if result.get("model_degraded"):
            stats["model_degraded"] = True
            stats.setdefault("model_diagnostics", []).append(result.get("model_diagnostics") or {})
        processed_pages += 1
    extraction_duration_ms = round((perf_counter() - extraction_started) * 1000)

    cleanup_started = perf_counter()
    old_evidence_entity_r = await db.execute(
        select(KbEvidence.entity_id).where(KbEvidence.document_id == document_id)
    )
    old_entity_ids_for_nodes = {row[0] for row in old_evidence_entity_r.all()}
    await db.execute(
        sa_delete(KbEvidence).where(KbEvidence.document_id == document_id)
    )
    await db.execute(
        sa_delete(KbChunkEntity).where(KbChunkEntity.document_id == document_id)
    )
    await db.execute(
        sa_delete(KbGovernanceCandidate).where(KbGovernanceCandidate.document_id == document_id)
    )
    if old_entity_ids_for_nodes:
        node_ids_r = await db.execute(
            select(KbGraphNode.id).where(
                KbGraphNode.entity_id.in_(old_entity_ids_for_nodes),
                KbGraphNode.owner_id == owner_id,
            )
        )
        node_ids = [row[0] for row in node_ids_r.all()]
        if node_ids:
            await db.execute(
                sa_delete(KbGraphEdge).where(
                    (KbGraphEdge.source_node_id.in_(node_ids))
                    | (KbGraphEdge.target_node_id.in_(node_ids))
                )
            )
            await db.execute(
                sa_delete(KbGraphNode).where(
                    KbGraphNode.entity_id.in_(old_entity_ids_for_nodes),
                    KbGraphNode.owner_id == owner_id,
                )
            )
    cleanup_duration_ms = round((perf_counter() - cleanup_started) * 1000)
    logger.info("Cleared old entity/graph data for document_id=%d before graph write", document_id)
    await db.commit()

    # 去重 + 写入（复用同逻辑）
    write_started = perf_counter()
    seen_entities: dict[str, dict] = {}
    for ent in all_entities:
        name = (ent.get("name") or "").strip()
        category = ent.get("category", "通用")
        key = f"{name}|{category}"
        if key not in seen_entities:
            seen_entities[key] = ent

    # 本地 dedup：避免重复 governance candidate（DB query 看不到 same-session 未 flush 的数据）
    seen_candidate_names: set[str] = set()
    entity_name_to_id: dict[str, int] = {}

    for key, ent in seen_entities.items():
        name = ent.get("name", key.split("|")[0])
        category = ent.get("category", "通用")
        description = ent.get("description", "")

        # 查重：是否已有同名实体（避免跨文档重复创建）
        existing_r = await db.execute(
            select(KbEntityDictionary).where(
                KbEntityDictionary.name == name,
                KbEntityDictionary.owner_id == owner_id,
            ).order_by(KbEntityDictionary.id).limit(1)
        )
        existing_entity = existing_r.scalars().first()

        if existing_entity:
            entity_id = existing_entity.id
            entity_name_to_id[name] = entity_id
            # 更新描述（保留更长的那个）
            existing_desc = existing_entity.description or ""
            if len(description) > len(existing_desc):
                existing_entity.description = description
            # 建图谱节点（如果还没有的话）
            node_r = await db.execute(
                select(KbGraphNode)
                .where(KbGraphNode.entity_id == entity_id, KbGraphNode.owner_id == owner_id)
                .limit(1)
            )
            existing_node = node_r.scalars().first()
            if not existing_node:
                node = KbGraphNode(
                    owner_id=owner_id, entity_id=entity_id,
                    label=name, category=category, description=description,
                )
                db.add(node)
                await db.flush()
        else:
            entity_record = KbEntityDictionary(
                owner_id=owner_id, name=name, category=category,
                description=description, status="candidate", source="fusion_extraction",
            )
            db.add(entity_record)
            await db.flush()
            entity_id = entity_record.id
            entity_name_to_id[name] = entity_id

            node = KbGraphNode(
                owner_id=owner_id, entity_id=entity_id,
                label=name, category=category, description=description,
            )
            db.add(node)
            await db.flush()

        # 治理候选（本文档的，本地 set 去重避免 same-session 重复）
        if name not in seen_candidate_names:
            seen_candidate_names.add(name)
            candidate = KbGovernanceCandidate(
                owner_id=owner_id, document_id=document_id,
                entity_name=name, category=category, excerpt=description[:500],
                confidence=0.7, audit_status="pending",
            )
            db.add(candidate)

    stats["entities_found"] = len(seen_entities)
    await db.commit()

    # ── 第2步：构建页→chunk映射 ──────────────────────────
    # Fusion 层 chunk 由 index_fusions_to_chunks() 写入 kb_chunks，
    # 每块携带 page 号。查询本文档所有 chunk 建立 page→[chunk_id] 映射。
    chunks_r = await db.execute(
        select(KbChunk)
        .where(KbChunk.document_id == document_id, KbChunk.owner_id == owner_id)
        .order_by(KbChunk.page, KbChunk.chunk_index)
    )
    all_doc_chunks = chunks_r.scalars().all()
    page_to_chunks: dict[int, list[int]] = {}
    for ch in all_doc_chunks:
        p = ch.page or 0
        page_to_chunks.setdefault(p, []).append(ch.id)

    # ── 第3步：证据 + chunk_entity 关联（逐原始实体逐页写入） ──
    # 用 entity_name_to_id 把原始非去重实体列表按页写出精确关联
    seen_evidence_key: set[tuple[int, int]] = set()  # (entity_id, page)
    seen_chunk_entity_key: set[tuple[int, int]] = set()  # (entity_id, chunk_id)
    for raw_idx, ent in enumerate(all_entities):
        name = (ent.get("name") or "").strip()
        entity_id = entity_name_to_id.get(name)
        if not entity_id:
            continue
        page = entity_page[raw_idx] if raw_idx < len(entity_page) else 0
        description = ent.get("description", "")
        chunk_ids = page_to_chunks.get(page, [])

        # 证据：每个(实体,页)写一条，chunk_id 取该页第一个 chunk
        ev_key = (entity_id, page)
        if ev_key not in seen_evidence_key:
            seen_evidence_key.add(ev_key)
            first_chunk_id = chunk_ids[0] if chunk_ids else 0
            fusion = fusion_by_page.get(int(page))
            raw_rows = page_to_raw_rows.get(int(page), [])
            raw_data_id = int(raw_rows[0].id) if raw_rows else None
            evidence = KbEvidence(
                owner_id=owner_id, entity_id=entity_id,
                document_id=document_id, chunk_id=first_chunk_id,
                page=page,
                excerpt=(description or "")[:500],
                confidence=0.7, status="pending",
                raw_data_id=raw_data_id,
                page_fusion_id=int(fusion.id) if fusion is not None else None,
                artifact_id=fusion_artifact_id,
                source_round="fusion",
                claim_type="entity",
                source_hash=_fusion_source_hash(fusion, raw_rows) if fusion is not None else None,
                prompt_hash=graph_prompt_hash,
                model_used=page_model_used.get(int(page)),
                diagnostics_json={
                    "model_diagnostics": page_model_diagnostics.get(int(page)),
                    "source": {
                        "page_fusion_id": int(fusion.id) if fusion is not None else None,
                        "raw_data_ids": [int(row.id) for row in raw_rows],
                        "artifact_stage": "fusion" if fusion_artifact_id is not None else None,
                    },
                },
            )
            db.add(evidence)

        # chunk_entity：将该实体关联到该页所有 chunk
        for cid in chunk_ids:
            ce_key = (entity_id, cid)
            if ce_key not in seen_chunk_entity_key:
                seen_chunk_entity_key.add(ce_key)
                ce = KbChunkEntity(
                    owner_id=owner_id, chunk_id=cid,
                    entity_id=entity_id, document_id=document_id,
                    confidence=0.7,
                )
                db.add(ce)

    await db.commit()

    # 关系写入
    seen_relations: set = set()
    relation_names: set[str] = set()
    for rel in all_relationships:
        source_name = (rel.get("source") or "").strip()
        target_name = (rel.get("target") or "").strip()
        if source_name and target_name:
            relation_names.add(source_name)
            relation_names.add(target_name)

    nodes_by_label: dict[str, KbGraphNode] = {}
    existing_edge_keys: set[tuple[int, int, str]] = set()
    if relation_names:
        nodes_r = await db.execute(
            select(KbGraphNode).where(
                KbGraphNode.owner_id == owner_id,
                KbGraphNode.label.in_(list(relation_names)),
            )
        )
        for node in nodes_r.scalars().all():
            nodes_by_label.setdefault(str(node.label), node)

        node_ids = [int(node.id) for node in nodes_by_label.values()]
        if node_ids:
            edge_r = await db.execute(
                select(
                    KbGraphEdge.source_node_id,
                    KbGraphEdge.target_node_id,
                    KbGraphEdge.relation,
                ).where(
                    KbGraphEdge.owner_id == owner_id,
                    KbGraphEdge.source_node_id.in_(node_ids),
                    KbGraphEdge.target_node_id.in_(node_ids),
                )
            )
            existing_edge_keys = {
                (int(source_id), int(target_id), str(relation))
                for source_id, target_id, relation in edge_r.all()
            }
    await db.commit()

    pending_edges = 0
    for rel in all_relationships:
        source_name = (rel.get("source") or "").strip()
        target_name = (rel.get("target") or "").strip()
        rel_type = rel.get("relation", "相关")
        rel_key = f"{source_name}|{target_name}|{rel_type}"
        if rel_key in seen_relations:
            continue
        seen_relations.add(rel_key)

        src_node = nodes_by_label.get(source_name)
        tgt_node = nodes_by_label.get(target_name)

        if src_node and tgt_node:
            edge_key = (int(src_node.id), int(tgt_node.id), str(rel_type))
            if edge_key in existing_edge_keys:
                continue
            edge = KbGraphEdge(
                owner_id=owner_id, source_node_id=src_node.id,
                target_node_id=tgt_node.id, relation=rel_type,
                weight=1.0, description=rel.get("description", ""),
            )
            db.add(edge)
            existing_edge_keys.add(edge_key)
            pending_edges += 1
            if pending_edges >= 100:
                await db.commit()
                pending_edges = 0

    stats["relationships_found"] = len(seen_relations)
    if processed_pages > 0 and not seen_entities and stats["errors"]:
        stats["status"] = "degraded"
        stats["reason"] = "entity_extraction_failed"
    await db.commit()
    write_duration_ms = round((perf_counter() - write_started) * 1000)
    stats["timing"] = {
        "stage_wall_ms": round((perf_counter() - stage_started) * 1000),
        "cleanup_ms": cleanup_duration_ms,
        "llm_extract_ms": extraction_duration_ms,
        "graph_write_ms": write_duration_ms,
        "processed_pages": processed_pages,
        "page_durations_ms": dict(sorted(page_durations.items())),
        "execution_mode": "parallel_pages",
        "page_concurrency": page_concurrency,
    }
    logger.info("Fusion-entity extraction doc_id=%d: %d entities, %d relationships", document_id, stats["entities_found"], stats["relationships_found"])
    return stats


async def get_entity_dictionary(db: AsyncSession, owner_id: int, keyword: str = "") -> list[dict]:
    """查询实体词典。"""
    from ..models import KbEntityDictionary

    stmt = select(KbEntityDictionary).where(KbEntityDictionary.owner_id == owner_id)
    if keyword:
        stmt = stmt.where(KbEntityDictionary.name.ilike(f"%{keyword}%"))
    stmt = stmt.order_by(KbEntityDictionary.name).limit(200)
    r = await db.execute(stmt)
    entities = r.scalars().all()
    return [
        {
            "id": e.id,
            "name": e.name,
            "category": e.category,
            "description": e.description,
            "status": e.status,
            "source": e.source,
        }
        for e in entities
    ]


async def get_graph_context(db: AsyncSession, owner_id: int, entity_id: int) -> dict:
    """查询实体在图谱中的上下文（关联节点 + 边）。"""
    from ..models import KbGraphEdge, KbGraphNode

    # 查当前节点
    node_r = await db.execute(
        select(KbGraphNode).where(KbGraphNode.entity_id == entity_id, KbGraphNode.owner_id == owner_id)
    )
    node = node_r.scalars().first()
    if not node:
        return {"node": None, "edges": [], "nodes": []}

    # 查出边、入边
    edges_r = await db.execute(
        select(KbGraphEdge).where(
            ((KbGraphEdge.source_node_id == node.id) | (KbGraphEdge.target_node_id == node.id)),
            KbGraphEdge.owner_id == owner_id,
        ).limit(50)
    )
    edges = edges_r.scalars().all()

    related_node_ids: set[int] = set()
    for e in edges:
        related_node_ids.add(e.source_node_id)
        related_node_ids.add(e.target_node_id)
    if related_node_ids:
        nodes_r = await db.execute(
            select(KbGraphNode).where(KbGraphNode.id.in_(related_node_ids), KbGraphNode.owner_id == owner_id)
        )
        nodes = nodes_r.scalars().all()
    else:
        nodes = []

    return {
        "node": {"id": node.id, "entity_id": node.entity_id, "label": node.label, "category": node.category},
        "edges": [
            {"id": e.id, "source": e.source_node_id, "target": e.target_node_id, "relation": e.relation}
            for e in edges
        ],
        "nodes": [
            {"id": n.id, "entity_id": n.entity_id, "label": n.label, "category": n.category}
            for n in nodes
        ],
    }


async def get_page_fusion(
    db: AsyncSession,
    document_id: int,
    page: int,
    owner_id: int | None = None,
) -> dict | None:
    """获取页级融合内容。"""
    from ..models import KbPageFusion

    stmt = select(KbPageFusion).where(
        KbPageFusion.document_id == document_id,
        KbPageFusion.page == page,
    )
    if owner_id is not None:
        stmt = stmt.where(KbPageFusion.owner_id == owner_id)
    r = await db.execute(
        stmt
    )
    pf = r.scalar_one_or_none()
    if not pf:
        return None
    return {
        "id": pf.id,
        "document_id": pf.document_id,
        "page": pf.page,
        "fused_text": pf.fused_text,
        "enhanced_text": pf.enhanced_text,
    }
