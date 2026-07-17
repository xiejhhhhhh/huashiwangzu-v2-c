# -*- coding: utf-8 -*-
"""全库重刷词层 · 多进程版 —— 喂满 M3 Ultra 多核。
背景:单进程单核只跑 5 文档/秒,32核睡觉。改 N 个 worker 进程分片并跑。
安全:
  · 每 worker 设 DB_USE_NULL_POOL=1(用完即还),16 worker 峰值连接远低于 PG max_connections=300。
  · derive 内 source_hash 去重 + 开头清本文档 occurrence,可重跑幂等,worker 间不同文档无冲突。
断点续跑:每 worker 写独立 completed_w{i}.json,启动时并所有分片跳过已完成。
用法:
  cd backend && ./.venv/bin/python ../开发文档/临时文档/本轮运维脚本_20260717/重刷词层_多进程_20260717.py [worker数] [limit]
"""
import json
import multiprocessing as mp
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "../../.."))

_主进度 = "/tmp/探针结果/重刷词层_completed.json"       # 旧单进程留下的,也算已完成
_分片进度 = "/tmp/探针结果/重刷词层_w{}.json"
_日志文件 = "/tmp/探针结果/重刷词层_多进程.log"


def _log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(_日志文件, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _载入已完成(worker数: int) -> set[int]:
    done: set[int] = set()
    files = [_主进度] + [_分片进度.format(i) for i in range(worker数)]
    for fp in files:
        if os.path.exists(fp):
            try:
                done |= set(json.load(open(fp, encoding="utf-8")))
            except Exception:
                pass
    return done


def worker(wid: int, 分片: list) -> None:
    """单个 worker 进程:极小池,跑自己那片文档。"""
    os.environ["DB_USE_NULL_POOL"] = "1"  # 必须在 import database 前设
    sys.path.insert(0, os.path.join(_ROOT, "backend"))
    sys.path.insert(0, _ROOT)
    import asyncio

    from app.database import AsyncSessionLocal
    from modules.knowledge.backend.services.cognitive_index_service import (
        derive_document_cognitive_index,
    )

    进度fp = _分片进度.format(wid)
    done: set[int] = set()
    if os.path.exists(进度fp):
        try:
            done = set(json.load(open(进度fp, encoding="utf-8")))
        except Exception:
            done = set()

    async def run() -> None:
        cnt = 0
        t0 = time.time()
        for owner_id, doc_id in 分片:
            if doc_id in done:
                continue
            try:
                async with AsyncSessionLocal() as db:
                    await derive_document_cognitive_index(
                        db, owner_id=owner_id, document_id=doc_id, limit=200
                    )
                done.add(doc_id)
            except Exception as e:  # noqa: BLE001
                _log(f"  w{wid} 文档 {doc_id} 失败: {e}")
            cnt += 1
            if cnt % 20 == 0:
                json.dump(sorted(done), open(进度fp, "w", encoding="utf-8"))
                速度 = cnt / (time.time() - t0)
                _log(f"  w{wid} 进度 {cnt}/{len(分片)} | {速度:.2f}文档/秒")
        json.dump(sorted(done), open(进度fp, "w", encoding="utf-8"))
        _log(f"  w{wid} 完成 {cnt} 个")

    try:
        asyncio.run(run())
    except BaseException as e:  # noqa: BLE001 抓整体异常(含 SystemExit/KeyboardInterrupt),定死因
        import traceback
        _log(f"  w{wid} 整体崩溃: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        raise


def main() -> None:
    worker数 = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None

    # 主进程查全部待刷(单独进程查,避免污染 worker 环境)
    sys.path.insert(0, os.path.join(_ROOT, "backend"))
    sys.path.insert(0, _ROOT)
    import asyncio

    from app.database import AsyncSessionLocal
    from sqlalchemy import text as sa_text

    async def 取待刷():
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(sa_text(
                "SELECT owner_id, id FROM kb_documents WHERE deleted=false ORDER BY id"
            ))).all()
        return [(int(o), int(d)) for o, d in rows]

    全部 = asyncio.run(取待刷())
    done = _载入已完成(worker数)
    待刷 = [(o, d) for o, d in 全部 if d not in done]
    if limit:
        待刷 = 待刷[:limit]

    # round-robin 分片
    分片列表 = [[] for _ in range(worker数)]
    for idx, item in enumerate(待刷):
        分片列表[idx % worker数].append(item)

    _log(f"多进程重刷 | {worker数} worker | 待刷 {len(待刷)} 个(已完成 {len(done)} 跳过) | 每片~{len(待刷)//worker数}")
    t0 = time.time()
    procs = []
    for wid in range(worker数):
        if not 分片列表[wid]:
            continue
        p = mp.Process(target=worker, args=(wid, 分片列表[wid]))
        p.start()
        procs.append(p)
    for p in procs:
        p.join()

    # 报每个 worker 的 exitcode:0=正常,-6=SIGABRT,-9=SIGKILL(被杀),其它=异常退出
    退出码 = [(i, p.exitcode) for i, p in enumerate(procs)]
    异常退出 = [(i, c) for i, c in 退出码 if c not in (0, None)]
    if 异常退出:
        _log(f"⚠️ 异常退出的 worker(编号,exitcode): {异常退出}  (-6=SIGABRT/-9=SIGKILL)")

    dt = time.time() - t0
    最终 = _载入已完成(worker数)
    _log(f"全部完成 | 耗时 {dt/60:.1f}分 | 累计已完成 {len(最终)} 个文档")


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    main()
