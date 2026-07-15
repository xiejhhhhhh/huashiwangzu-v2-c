# -*- coding: utf-8 -*-
"""第一层:文本层字级权威打齐(存量回填,分轮法)。全自动、零LLM、精度第一。

第一性原理:文本层字绝对正确(除乱序)→ 逐字滑窗查该位权威字 → 变体并入锚点。一次命中。
分轮:每轮取 align_status='pending' 的一批实体跑尺子,跑完打 'done',下轮只跑 pending,
      滚到没有为止(华哥分轮法,天然续跑/幂等,不用外部进度文件)。
覆盖:被chunk引用、含汉字、非merged 的实体(真正影响召回的)。owner=4。
用法: python 批_文本层打齐分轮.py [--batch 2000] [--rounds 1] [--dry]
      --rounds 0 = 一直滚到 pending 清空。
"""
import asyncio, sys, time, argparse
sys.path.insert(0, "backend"); sys.path.insert(0, ".")
from app.database import AsyncSessionLocal
from sqlalchemy import text as T
from modules.knowledge.backend.services.semantic_align_service import (
    canonicalize_name, _resolve_canonical_entity, _merge_variant_into,
)

OWNER = 4


SHARD = 0     # 本进程分片号(id % SHARDS == SHARD 才处理)
SHARDS = 1    # 总分片数(1=不分片)


async def fetch_batch(db, batch):
    """取一批未验证、被chunk引用、含汉字的实体。短名优先。按 id 取模分片(并行用)。"""
    r = await db.execute(T("""
        SELECT ed.id, ed.name, ed.category
        FROM kb_entity_dictionary ed
        WHERE ed.owner_id=:o AND ed.status!='merged'
          AND COALESCE(ed.align_status,'pending')='pending'
          AND ed.name ~ '[一-鿿]' AND length(ed.name)>=2
          AND (mod(ed.id, :shards) = :shard)
          AND EXISTS (SELECT 1 FROM kb_chunk_entities ce WHERE ce.entity_id=ed.id AND ce.owner_id=:o)
        ORDER BY length(ed.name), ed.id
        LIMIT :b
    """), {"o": OWNER, "b": batch, "shards": SHARDS, "shard": SHARD})
    return [(int(i), n, c) for i, n, c in r.all()]


async def mark_done(db, ids):
    if not ids:
        return
    await db.execute(
        T("UPDATE kb_entity_dictionary SET align_status='done' WHERE owner_id=:o AND id = ANY(:ids)"),
        {"o": OWNER, "ids": ids},
    )
    await db.commit()


async def run_round(batch, dry):
    async with AsyncSessionLocal() as db:
        ents = await fetch_batch(db, batch)
    if not ents:
        return 0, 0, 0
    checked = aligned = 0
    done_ids: list[int] = []
    for eid, name, category in ents:
        checked += 1
        try:
            async with AsyncSessionLocal() as db:  # 每实体独立短会话,防长事务/连接超时
                canonical_name, fixes = await canonicalize_name(db, OWNER, name)
                if fixes and canonical_name != name:
                    cid = await _resolve_canonical_entity(db, OWNER, canonical_name, category)
                    await _merge_variant_into(db, OWNER, eid, name, cid, canonical_name, fixes)
                    if dry:
                        await db.rollback()
                    else:
                        await db.commit()
                    aligned += 1
                    print(f"    {name} → {canonical_name}  {[(f['from'],f['to'],f['evidence']) for f in fixes]}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"    !实体{eid}({name})异常: {str(exc)[:120]}", flush=True)
        done_ids.append(eid)
    if not dry:
        async with AsyncSessionLocal() as db:
            await mark_done(db, done_ids)
    return checked, aligned, len(ents)


async def pending_count():
    async with AsyncSessionLocal() as db:
        r = await db.execute(T("""
            SELECT count(*) FROM kb_entity_dictionary ed
            WHERE ed.owner_id=:o AND ed.status!='merged'
              AND COALESCE(ed.align_status,'pending')='pending'
              AND ed.name ~ '[一-鿿]' AND length(ed.name)>=2
              AND (mod(ed.id, :shards) = :shard)
              AND EXISTS (SELECT 1 FROM kb_chunk_entities ce WHERE ce.entity_id=ed.id AND ce.owner_id=:o)
        """), {"o": OWNER, "shards": SHARDS, "shard": SHARD})
        return r.first()[0]


async def main(batch, rounds, dry):
    pend = await pending_count()
    print(f"待验证(pending)实体: {pend}, 批次={batch}, 轮数={'滚到清空' if rounds==0 else rounds}, dry={dry}", flush=True)
    t0 = time.time()
    total_checked = total_aligned = rnd = 0
    while True:
        rnd += 1
        rt = time.time()
        checked, aligned, got = await run_round(batch, dry)
        total_checked += checked; total_aligned += aligned
        print(f"[第{rnd}轮] 取{got} 查{checked} 合并{aligned}  用时{time.time()-rt:.0f}s  累计合并{total_aligned}", flush=True)
        if got == 0:
            print("pending 已清空。", flush=True); break
        if dry:
            print("dry 模式跑一轮即停(未打done,不会推进)。", flush=True); break
        if rounds and rnd >= rounds:
            break
    left = await pending_count()
    print(f"\n结束: {rnd}轮, 查{total_checked}, 合并{total_aligned}, 剩pending {left}, 总用时{time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=2000)
    ap.add_argument("--rounds", type=int, default=1)  # 默认跑1轮,0=滚到清空
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--shard", type=int, default=0)   # 本进程分片号
    ap.add_argument("--shards", type=int, default=1)  # 总分片数(并行时>1)
    a = ap.parse_args()
    SHARD = a.shard
    SHARDS = max(1, a.shards)
    asyncio.run(main(a.batch, a.rounds, a.dry))
