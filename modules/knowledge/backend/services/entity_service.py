"""知识库实体抽取与图谱服务。

用 gateway 大模型从解析内容中抽取实体、关系、证据，构建知识图谱。
"""
import json
import logging

from app.database import AsyncSessionLocal
from app.gateway.router import gateway_router
from app.services.task_worker import register_task_handler
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .llm_diagnostics import timed_llm_chat
from .prompt_utils import TENTITY, TFUSION_LEGACY, load_prompt

logger = logging.getLogger("v2.knowledge").getChild("entity")

async def extract_entities_from_text(
    text: str,
    profile_key: str = "deepseek-v4-flash",
    db: AsyncSession | None = None,
) -> dict:
    """用大模型从文本中提取实体和关系。返回 {"entities": [...], "relationships": [...]}。"""
    if not text.strip():
        return {"entities": [], "relationships": []}

    system_prompt = await load_prompt(db, TENTITY)
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请提取以下内容的实体和关系：\n\n{text[:6000]}"},
        ]
        resp = await timed_llm_chat(
            logger=logger,
            stage="entity",
            profile_key=profile_key,
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
        return {"entities": entities, "relationships": relationships}
    except Exception as e:
        logger.warning("Entity extraction failed: %s", e)
        return {"entities": [], "relationships": [], "errors": [str(e)]}


async def fuse_page_text(
    text: str,
    profile_key: str = "deepseek-v4-flash",
    db: AsyncSession | None = None,
) -> str:
    """用大模型融合页级文本。"""
    if not text.strip():
        return text

    system_prompt = await load_prompt(db, TFUSION_LEGACY)
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请融合以下分块内容：\n\n{text[:8000]}"},
        ]
        resp = await timed_llm_chat(
            logger=logger,
            stage="legacy_page_fusion",
            profile_key=profile_key,
            messages=messages,
            chat_func=gateway_router.chat,
            extra={"text_chars": len(text)},
        )
        result = resp.get("content", "")
        return result.strip() if result else text
    except Exception as e:
        logger.warning("Page fusion failed: %s", e)
        return text


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
    processed_pages = 0

    for page, texts in page_texts.items():
        combined = "\n\n".join(texts)
        if len(combined) < 20:
            continue

        # 每页抽取一次实体
        result = await extract_entities_from_text(combined, db=db)
        all_entities.extend(result.get("entities", []))
        all_relationships.extend(result.get("relationships", []))
        stats["errors"].extend(result.get("errors", []))
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
    )

    stats = {"entities_found": 0, "relationships_found": 0, "errors": []}

    # ── 幂等：捕获旧实体ID后再清数据 ──
    # 先查出本文档旧证据引用的 entity_id（在删之前捕获，用于后续删 graph node/edge）
    old_evidence_entity_r = await db.execute(
        select(KbEvidence.entity_id).where(KbEvidence.document_id == document_id)
    )
    old_entity_ids_for_nodes = {row[0] for row in old_evidence_entity_r.all()}

    # 再删本文档的 evidence、chunk_entity 和 governance_candidate
    await db.execute(
        sa_delete(KbEvidence).where(KbEvidence.document_id == document_id)
    )
    await db.execute(
        sa_delete(KbChunkEntity).where(KbChunkEntity.document_id == document_id)
    )
    await db.execute(
        sa_delete(KbGovernanceCandidate).where(KbGovernanceCandidate.document_id == document_id)
    )

    # 删图谱节点和边
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

    logger.info("Cleared old entity/graph data for document_id=%d (uncommitted, safe on crash)", document_id)

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

    all_entities: list[dict] = []
    all_relationships: list[dict] = []
    entity_page: list[int] = []  # tracks which page each raw entity came from (parallel to all_entities)
    processed_pages = 0

    for pf in fusions:
        text = pf.fused_text
        if len(text) < 20:
            continue

        result = await extract_entities_from_text(text, db=db)
        page_ents = result.get("entities", [])
        all_entities.extend(page_ents)
        entity_page.extend([pf.page] * len(page_ents))
        all_relationships.extend(result.get("relationships", []))
        stats["errors"].extend(result.get("errors", []))
        processed_pages += 1

        if processed_pages % 3 == 0 and len(fusions) > 3:
            import asyncio
            await asyncio.sleep(0.5)

    # 去重 + 写入（复用同逻辑）
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
            evidence = KbEvidence(
                owner_id=owner_id, entity_id=entity_id,
                document_id=document_id, chunk_id=first_chunk_id,
                page=page,
                excerpt=(description or "")[:500],
                confidence=0.7, status="pending",
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

    # 关系写入
    seen_relations: set = set()
    for rel in all_relationships:
        source_name = rel.get("source", "")
        target_name = rel.get("target", "")
        rel_type = rel.get("relation", "相关")
        rel_key = f"{source_name}|{target_name}|{rel_type}"
        if rel_key in seen_relations:
            continue
        seen_relations.add(rel_key)

        # 查找源/目标 node
        src_node_r = await db.execute(
            select(KbGraphNode).where(KbGraphNode.label == source_name, KbGraphNode.owner_id == owner_id).limit(1)
        )
        src_node = src_node_r.scalars().first()
        tgt_node_r = await db.execute(
            select(KbGraphNode).where(KbGraphNode.label == target_name, KbGraphNode.owner_id == owner_id).limit(1)
        )
        tgt_node = tgt_node_r.scalars().first()

        if src_node and tgt_node:
            # 查重（node 维度的唯一性检查）
            dup_r = await db.execute(
                select(KbGraphEdge).where(
                    KbGraphEdge.source_node_id == src_node.id,
                    KbGraphEdge.target_node_id == tgt_node.id,
                    KbGraphEdge.relation == rel_type,
                ).limit(1)
            )
            if dup_r.scalars().first():
                continue
            edge = KbGraphEdge(
                owner_id=owner_id, source_node_id=src_node.id,
                target_node_id=tgt_node.id, relation=rel_type,
                weight=1.0, description=rel.get("description", ""),
            )
            db.add(edge)

    stats["relationships_found"] = len(seen_relations)
    if processed_pages > 0 and not seen_entities and stats["errors"]:
        stats["status"] = "degraded"
        stats["reason"] = "entity_extraction_failed"
    await db.commit()
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


# ── 框架任务 handler:第6层图谱重建(后台,防同步超时) ────────────────
async def _graph_handler(params: dict) -> dict:
    """框架后台任务 handler:处理 kb_graph 任务(从融合层重建实体/图谱)。"""
    from ..models import KbDocument

    document_id = int(params.get("document_id", 0))
    if document_id <= 0:
        return {"error": "document_id required", "status": "failed"}

    async with AsyncSessionLocal() as db:
        df = await db.execute(select(KbDocument).where(KbDocument.id == document_id))
        doc = df.scalar_one_or_none()
        if not doc:
            return {"error": f"Document {document_id} not found", "status": "failed"}
        try:
            result = await process_document_entities_from_fusions(db, document_id, doc.owner_id)
            await db.commit()
            return {"status": "done", **result}
        except Exception as e:
            logger.error("Graph rebuild failed for document_id=%d: %s", document_id, e)
            return {"error": str(e), "status": "failed"}


register_task_handler("kb_graph", _graph_handler)
