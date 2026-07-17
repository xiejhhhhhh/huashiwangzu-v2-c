"""阶段2:4个广东娇宇logo一句话描述入库,使其可被搜索命中。
VLM(raw_vision)早已跑成功,品牌已认出,不再重复调VLM。
做法:合成一句话品牌描述 → 写回 kb_documents.summary → 插一条 fusion_verified chunk
     → 生成 qwen3-embedding-8b 向量写入 kb_chunk_embeddings → 状态改为搜索可见。

用法: cd backend && JWT_SECRET=test-secret DB_PASSWORD=123rgE123 .venv/bin/python logo轻描述入库_20260717.py
"""
import asyncio
import os

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("DB_PASSWORD", "123rgE123")

from app.database import AsyncSessionLocal
from app.services.model_services import get_embedding, get_embedding_profile_contract
from sqlalchemy import text

# 每个doc的一句话品牌描述(基于VLM已确认品牌合成)。带别名/关键词冗余,提高搜索命中率。
LOGO描述 = {
    3810: "广东娇宇（GUANGDONG JIAOYU）品牌logo源文件。这是广东娇宇/娇宇品牌的标志logo矢量PDF素材，紫红色品牌标准色，用于品牌视觉识别。关键词：广东娇宇、GUANGDONG JIAOYU、娇宇、JIAOYU、品牌logo、企业标识、logo源文件。",
    7369: "广东娇宇（GUANGDONG JIAOYU）品牌logo源文件。这是广东娇宇/娇宇品牌的标志logo矢量PDF素材，紫红色品牌标准色，用于品牌视觉识别。关键词：广东娇宇、GUANGDONG JIAOYU、娇宇、JIAOYU、品牌logo、企业标识、logo源文件。",
    3823: "娇宇（JIAOYU）品牌logo与VI视觉规范源文件。这是娇宇/广东娇宇品牌的logo及品牌标准色规范页矢量PDF素材，品牌主色PANTONE 248C（CMYK C44 M96 Y5 K0），紫红色。关键词：娇宇、JIAOYU、广东娇宇、品牌logo、VI规范、品牌标准色、PANTONE 248C、logo源文件。",
    7352: "娇宇（JIAOYU）品牌logo与VI视觉规范源文件。这是娇宇/广东娇宇品牌的logo及品牌标准色规范页矢量PDF素材，品牌主色PANTONE 248C（CMYK C44 M96 Y5 K0），紫红色。关键词：娇宇、JIAOYU、广东娇宇、品牌logo、VI规范、品牌标准色、PANTONE 248C、logo源文件。",
}


def _vector_literal(vec):
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


async def 主流程():
    contract = get_embedding_profile_contract(None)
    profile_key = str(contract.get("profile_key") or "qwen3-embedding-8b")
    emb_version = int(contract.get("embedding_version") or 1)
    print(f"[嵌入契约] profile={profile_key} version={emb_version} configured_dim={contract.get('dimensions')}")

    async with AsyncSessionLocal() as db:
        for doc_id, 描述 in LOGO描述.items():
            row = (await db.execute(text(
                "SELECT id, owner_id, filename FROM kb_documents WHERE id=:i AND deleted=false"
            ), {"i": doc_id})).first()
            if not row:
                print(f"[跳过] doc {doc_id} 不存在或已删")
                continue
            owner_id = int(row.owner_id)

            # 幂等:先清掉本脚本之前可能插入的 logo_vision chunk 及其 embedding
            old_ids = [r[0] for r in (await db.execute(text(
                "SELECT id FROM kb_chunks WHERE document_id=:d AND source_stage='logo_vision'"
            ), {"d": doc_id})).all()]
            if old_ids:
                await db.execute(text("DELETE FROM kb_chunk_embeddings WHERE chunk_id = ANY(:ids)"), {"ids": old_ids})
                await db.execute(text("DELETE FROM kb_chunks WHERE id = ANY(:ids)"), {"ids": old_ids})

            # 1) 写回 summary
            await db.execute(text(
                "UPDATE kb_documents SET summary=:s, updated_at=now() WHERE id=:i"
            ), {"s": 描述, "i": doc_id})

            # 2) 插入可搜索 chunk(fusion_verified 优先索引层)
            chunk_id = (await db.execute(text("""
                INSERT INTO kb_chunks
                    (document_id, owner_id, page, chunk_index, block_type, text, keywords,
                     index_layer, index_version, source_stage, created_at, updated_at)
                VALUES
                    (:d, :o, 1, 0, '图片', :t, :kw,
                     'fusion_verified', 1, 'logo_vision', now(), now())
                RETURNING id
            """), {
                "d": doc_id, "o": owner_id, "t": 描述,
                "kw": "广东娇宇,GUANGDONG JIAOYU,娇宇,JIAOYU,品牌logo,logo源文件,VI规范,品牌标准色",
            })).scalar_one()

            # 3) 生成向量并写入 sidecar 表
            vec = await get_embedding(描述, profile_key=profile_key)
            dim = len(vec)
            await db.execute(text("""
                INSERT INTO kb_chunk_embeddings
                    (owner_id, document_id, chunk_id, index_layer, embedding_model,
                     embedding_version, embedding_dim, embedding, status, created_at, updated_at)
                VALUES
                    (:o, :d, :c, 'fusion_verified', :m, :v, :dim,
                     CAST(:emb AS vector), 'active', now(), now())
            """), {
                "o": owner_id, "d": doc_id, "c": chunk_id, "m": profile_key,
                "v": emb_version, "dim": dim, "emb": _vector_literal(vec),
            })

            # 4) 状态改为搜索可见:fusion done,parse degraded(矢量提不出文字属正常),
            #    profile/graph/relation 标 skipped(华哥要求不过度读取,不再跑LLM三阶段)
            await db.execute(text("""
                UPDATE kb_documents SET
                    parse_status='degraded',
                    vector_status='done',
                    raw_status='done',
                    fusion_status='done',
                    profile_status='skipped',
                    graph_status='skipped',
                    relation_status='skipped',
                    total_chunks=1,
                    parse_error='矢量logo无文字块，已由VLM看图生成品牌描述并入库可搜索',
                    updated_at=now()
                WHERE id=:i
            """), {"i": doc_id})

            print(f"[完成] doc {doc_id}({row.filename}) chunk={chunk_id} 向量维度={dim} 描述={描述[:30]}...")

        await db.commit()

    # 验证:能否搜到
    print("\n[验证] 关键词搜索复查:")
    async with AsyncSessionLocal() as db:
        for kw in ["广东娇宇", "娇宇logo", "JIAOYU"]:
            rows = (await db.execute(text("""
                SELECT c.document_id, left(c.text,20)
                FROM kb_chunks c JOIN kb_documents d ON d.id=c.document_id
                WHERE d.deleted=false AND c.source_stage='logo_vision' AND c.text ILIKE :p
            """), {"p": f"%{kw}%"})).all()
            print(f"    '{kw}' 命中 {len(rows)} 条: {[r[0] for r in rows]}")


if __name__ == "__main__":
    asyncio.run(主流程())
