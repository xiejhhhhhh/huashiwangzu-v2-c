"""后台进程注册表服务(全盘进程管理器)。

各 spawn 点开一行调 注册进程() 登记 PID;退出调 注销进程();
巡检对账 巡检对账() 把 pid 已死但没注销的标 stale。查询 列出活进程()。
同步接口(用独立短会话),subprocess/screen 起进程后即可调用,不阻塞。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.models.background_process import BackgroundProcess

logger = logging.getLogger("v2.process_registry")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _采pid创建时间(pid: int | None) -> float | None:
    """采进程创建时间戳,用于防 PID 复用误判。刚 spawn 完立即采最准。"""
    if pid is None:
        return None
    try:
        import psutil
        return float(psutil.Process(int(pid)).create_time())
    except Exception:  # noqa: BLE001
        return None


async def 注册进程(
    *, label: str, pid: int | None, kind: str = "other", source: str = "",
    command: str = "", log_path: str = "", ref_id: int | None = None, note: str = "",
    run_token: str = "",
) -> dict | None:
    """登记一个后台进程,返回 {reg_id, run_token}。失败不抛(登记是辅助,别拖垮主流程)。

    run_token:进程自己的稳定 id(不随 PID 变)。不传则内部生成 uuid。
    长驻进程可把 run_token 传给子进程(环境变量),子进程自报心跳/找回时带上它。
    pid_create_time:进程创建时间,巡检时比对——PID 被系统回收给别人时能认出原进程已暴毙。
    """
    import uuid

    from app.database import AsyncSessionLocal
    token = (run_token or uuid.uuid4().hex)[:64]
    try:
        async with AsyncSessionLocal() as db:
            row = BackgroundProcess(
                label=label[:128], pid=pid, kind=kind[:32], source=source[:64],
                command=(command or "")[:4000], log_path=(log_path or "")[:2000],
                status="running", started_at=_now(), heartbeat_at=_now(),
                ref_id=ref_id, note=(note or "")[:2000],
                run_token=token, pid_create_time=_采pid创建时间(pid),
            )
            db.add(row)
            await db.commit()
            return {"reg_id": int(row.id), "run_token": token}
    except Exception as exc:  # noqa: BLE001
        logger.warning("注册进程失败 label=%s pid=%s: %s", label, pid, exc)
        return None


async def 按token找回(run_token: str) -> dict | None:
    """靠稳定 id 找回一条记录(PID 变了也能找到)。返回含判活结论 alive/暴毙。"""
    import psutil

    from app.database import AsyncSessionLocal
    if not run_token:
        return None
    try:
        async with AsyncSessionLocal() as db:
            row = (await db.execute(
                select(BackgroundProcess).where(BackgroundProcess.run_token == run_token)
                .order_by(BackgroundProcess.id.desc())
            )).scalars().first()
            if row is None:
                return None
            alive = False
            if row.status == "running" and row.pid is not None:
                if psutil.pid_exists(int(row.pid)):
                    if row.pid_create_time is None:
                        alive = True
                    else:
                        try:
                            实际 = float(psutil.Process(int(row.pid)).create_time())
                            alive = abs(实际 - float(row.pid_create_time)) <= 1.0
                        except Exception:  # noqa: BLE001
                            alive = False
            return {
                "reg_id": row.id, "run_token": row.run_token, "label": row.label,
                "pid": row.pid, "kind": row.kind, "status": row.status,
                "log_path": row.log_path, "alive": alive,
                "暴毙": (row.status == "running" and not alive),
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("按token找回失败 token=%s: %s", run_token, exc)
        return None


async def 注销进程(*, pid: int | None = None, reg_id: int | None = None,
                   status: str = "exited", exit_code: int | None = None) -> None:
    """进程退出时标状态(exited/killed)。按 reg_id 或 pid 定位最近一条 running。"""
    from app.database import AsyncSessionLocal
    if pid is None and reg_id is None:
        return
    try:
        async with AsyncSessionLocal() as db:
            stmt = update(BackgroundProcess).values(
                status=status, exit_code=exit_code, ended_at=_now()
            )
            if reg_id is not None:
                stmt = stmt.where(BackgroundProcess.id == reg_id)
            else:
                stmt = stmt.where(
                    BackgroundProcess.pid == pid,
                    BackgroundProcess.status == "running",
                )
            await db.execute(stmt)
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("注销进程失败 pid=%s reg_id=%s: %s", pid, reg_id, exc)


async def 心跳(*, reg_id: int) -> None:
    """长驻后台进程可周期性打心跳,便于判活。"""
    from app.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(BackgroundProcess).where(BackgroundProcess.id == reg_id)
                .values(heartbeat_at=_now())
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.debug("心跳失败 reg_id=%s: %s", reg_id, exc)


async def 巡检对账(*, 心跳超时秒: int = 0) -> int:
    """把 status=running 但实际已死的记录标 stale。返回标记数。

    判死三档(任一命中即暴毙):
    1. PID 不存在 → 死了
    2. PID 存在但 create_time 和登记时对不上 → 这 PID 被系统回收给别的进程了,原进程暴毙
    3. (可选)有心跳基线且超时未更新 → 卡死/暴毙(心跳超时秒>0 才启用,给长驻进程用)
    """
    import psutil

    from app.database import AsyncSessionLocal
    标记 = 0
    now = _now()
    try:
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(BackgroundProcess).where(BackgroundProcess.status == "running")
            )).scalars().all()
            for row in rows:
                死了 = False
                if row.pid is None:
                    死了 = True
                elif not psutil.pid_exists(int(row.pid)):
                    死了 = True
                elif row.pid_create_time is not None:
                    # PID 还在,但要确认是不是当初那个进程(防复用)
                    try:
                        实际create = float(psutil.Process(int(row.pid)).create_time())
                        if abs(实际create - float(row.pid_create_time)) > 1.0:
                            死了 = True  # create_time 对不上 = PID 被回收给别人了
                    except Exception:  # noqa: BLE001
                        死了 = True
                if not 死了 and 心跳超时秒 > 0 and row.heartbeat_at is not None:
                    if (now - row.heartbeat_at).total_seconds() > 心跳超时秒:
                        死了 = True
                if 死了:
                    row.status = "stale"
                    row.ended_at = now
                    标记 += 1
            if 标记:
                await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("巡检对账失败: %s", exc)
    return 标记


_同步引擎 = None


def _取同步引擎():
    """模块级单例同步引擎(psycopg2+小池)。同步 engine 不绑事件循环,建一次复用。

    同步桥(launcher/watchdog 非 async 线程)用它,快连快断从小池拨连接,
    不再每次建引擎/开事件循环/起线程,也彻底避开 async 池的 loop 冲突。
    """
    global _同步引擎
    if _同步引擎 is None:
        from sqlalchemy import create_engine

        from app.config import get_settings
        # asyncpg URL → psycopg2 同步 URL
        url = get_settings().DATABASE_URL.replace("+asyncpg", "+psycopg2")
        _同步引擎 = create_engine(
            url, pool_size=2, max_overflow=3, pool_pre_ping=True, pool_recycle=300,
        )
    return _同步引擎


def 同步登记(
    *, label: str, pid: int | None, kind: str = "other", source: str = "",
    command: str = "", log_path: str = "", ref_id: int | None = None, note: str = "",
    run_token: str = "",
) -> dict | None:
    """同步场景登记桥(watchdog/launcher 等不在 async loop 的线程用)。失败不抛。"""
    import uuid

    from sqlalchemy import text
    token = (run_token or uuid.uuid4().hex)[:64]
    try:
        with _取同步引擎().begin() as conn:
            reg_id = conn.execute(text(
                "INSERT INTO framework_background_processes "
                "(label,pid,kind,source,command,log_path,status,started_at,heartbeat_at,"
                "ref_id,note,run_token,pid_create_time,created_at,updated_at) VALUES "
                "(:label,:pid,:kind,:source,:command,:log_path,'running',now(),now(),"
                ":ref_id,:note,:run_token,:pct,now(),now()) RETURNING id"
            ), {
                "label": label[:128], "pid": pid, "kind": kind[:32], "source": source[:64],
                "command": (command or "")[:4000], "log_path": (log_path or "")[:2000],
                "ref_id": ref_id, "note": (note or "")[:2000],
                "run_token": token, "pct": _采pid创建时间(pid),
            }).scalar()
        return {"reg_id": int(reg_id), "run_token": token}
    except Exception as exc:  # noqa: BLE001
        logger.warning("同步登记失败 label=%s pid=%s: %s", label, pid, exc)
        return None


def 同步注销(*, pid: int | None = None, reg_id: int | None = None,
             status: str = "exited", exit_code: int | None = None) -> None:
    """同步场景注销桥(和 同步登记 配对)。失败不抛。"""
    if pid is None and reg_id is None:
        return

    from sqlalchemy import text
    try:
        with _取同步引擎().begin() as conn:
            if reg_id is not None:
                conn.execute(text(
                    "UPDATE framework_background_processes SET status=:s,exit_code=:e,"
                    "ended_at=now(),updated_at=now() WHERE id=:rid"
                ), {"s": status, "e": exit_code, "rid": reg_id})
            else:
                conn.execute(text(
                    "UPDATE framework_background_processes SET status=:s,exit_code=:e,"
                    "ended_at=now(),updated_at=now() WHERE pid=:pid AND status='running'"
                ), {"s": status, "e": exit_code, "pid": pid})
    except Exception as exc:  # noqa: BLE001
        logger.debug("同步注销失败 pid=%s reg_id=%s: %s", pid, reg_id, exc)


async def 列出活进程(*, 含判活: bool = True) -> list[dict]:
    """列出所有 running 的后台进程(找bug用:谁是谁、日志在哪、是否暴毙)。

    含判活=True 时实时比对 PID+create_time,标出 alive/暴毙,不用等巡检。
    """
    from app.database import AsyncSessionLocal
    psutil = None
    if 含判活:
        import psutil as _p
        psutil = _p
    try:
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(BackgroundProcess).where(BackgroundProcess.status == "running")
                .order_by(BackgroundProcess.started_at.desc())
            )).scalars().all()
            out = []
            for r in rows:
                alive = None
                if 含判活 and psutil is not None:
                    alive = False
                    if r.pid is not None and psutil.pid_exists(int(r.pid)):
                        if r.pid_create_time is None:
                            alive = True
                        else:
                            try:
                                实际 = float(psutil.Process(int(r.pid)).create_time())
                                alive = abs(实际 - float(r.pid_create_time)) <= 1.0
                            except Exception:  # noqa: BLE001
                                alive = False
                out.append({
                    "id": r.id, "run_token": r.run_token, "label": r.label,
                    "pid": r.pid, "kind": r.kind, "source": r.source,
                    "log_path": r.log_path,
                    "started_at": r.started_at.isoformat() if r.started_at else None,
                    "command": r.command[:200],
                    "alive": alive, "暴毙": (alive is False),
                })
            return out
    except Exception as exc:  # noqa: BLE001
        logger.warning("列出活进程失败: %s", exc)
        return []
