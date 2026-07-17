# -*- coding: utf-8 -*-
"""全库重刷词层 —— 用新分词器(term_tokenizer)重跑 derive_document_cognitive_index。
背景:病根正则已换成 jieba+业务词典+双向剥离,存量1.6万文档词层仍是旧正则产物,需重刷。
安全:kb_terms / kb_term_occurrences 已备份(带日期表)。derive 内 source_hash 去重 + 开头清本文档 occurrence,可重跑幂等。
断点续跑:已完成 doc_id 落盘 completed.json,中断再跑自动跳过。
用法:
  cd backend && ./.venv/bin/python ../开发文档/临时文档/本轮运维脚本_20260717/重刷词层_分词器v1_20260717.py [limit]
  limit 省略=全量;给数字=只刷前 N 个(小批验证)。
"""
import asyncio
import json
import os
import sys
import time

# backend 目录进 path(import app / modules)
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "../../.."))
sys.path.insert(0, os.path.join(_ROOT, "backend"))
sys.path.insert(0, _ROOT)

from app.database import AsyncSessionLocal  # noqa: E402
from sqlalchemy import text as sa_text  # noqa: E402
from modules.knowledge.backend.services.cognitive_index_service import (  # noqa: E402
    derive_document_cognitive_index,
)

_进度文件 = "/tmp/探针结果/重刷词层_completed.json"
_日志文件 = "/tmp/探针结果/重刷词层.log"


def _载入已完成() -> set[int]:
    if os.path.exists(_进度文件):
        try:
            return set(json.load(open(_进度文件, encoding="utf-8")))
        except Exception:
            return set()
    return set()


def _存已完成(done: set[int]) -> None:
    json.dump(sorted(done), open(_进度文件, "w", encoding="utf-8"))


def _log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(_日志文件, "a", encoding="utf-8") as f:
        f.write(line + "\n")


async def main(limit: int | None) -> None:
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(sa_text(
            "SELECT owner_id, id FROM kb_documents WHERE deleted=false ORDER BY id"
        ))).all()
    待刷 = [(int(o), int(d)) for o, d in rows]
    done = _载入已完成()
    待刷 = [(o, d) for o, d in 待刷 if d not in done]
    if limit:
        待刷 = 待刷[:limit]

    _log(f"本次待刷 {len(待刷)} 个文档 (已完成 {len(done)} 个跳过) | limit={limit}")
    t0 = time.time()
    统计 = {"terms": 0, "term_occurrences": 0, "fact_candidates": 0, "causal_candidates": 0, "err": 0}
    for i, (owner_id, doc_id) in enumerate(待刷, 1):
        try:
            async with AsyncSessionLocal() as db:
                r = await derive_document_cognitive_index(
                    db, owner_id=owner_id, document_id=doc_id, limit=200
                )
            for k in ("terms", "term_occurrences", "fact_candidates", "causal_candidates"):
                统计[k] += int(r.get(k, 0))
            done.add(doc_id)
        except Exception as e:  # noqa: BLE001
            统计["err"] += 1
            _log(f"  文档 {doc_id} 失败: {e}")
        if i % 20 == 0:
            _存已完成(done)
            dt = time.time() - t0
            速度 = i / dt
            剩 = (len(待刷) - i) / 速度 if 速度 else 0
            _log(f"  进度 {i}/{len(待刷)} | {速度:.2f}文档/秒 | 预计剩 {剩/60:.1f}分 | 累计词{统计['terms']}")
    _存已完成(done)
    dt = time.time() - t0
    _log(f"完成 {len(待刷)} 个 | 耗时 {dt/60:.1f}分 | 统计 {统计}")


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(main(lim))
