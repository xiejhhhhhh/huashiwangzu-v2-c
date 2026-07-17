#!/usr/bin/env python3
"""内容运行时不变量巡检（只读）。

对应方案 §19.8 不变量硬指标。逐条打印 PASS / FAIL / SKIP / WARN + 计数，
任一 FAIL 时进程退出码非零（供 CI / Gate 门禁使用）。全程只读。

约定：
  PASS = 违规计数为 0
  FAIL = 违规计数 > 0（导致退出码非零）
  SKIP = 依赖的表/字段尚不存在，优雅跳过（不算失败）
  WARN = 当前 schema 下字段可空等原因，暂不判定为硬失败

用法：
    backend/.venv/bin/python backend/scripts/content_runtime_invariants.py
    backend/.venv/bin/python backend/scripts/content_runtime_invariants.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
ENV_PATH = BACKEND_ROOT / ".env"

ACTIVE_STATUS_FILTER = "deleted = false AND status <> 'archived'"
READY_STATUSES = ("ready", "degraded", "stale", "parsed")


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _db_config() -> dict[str, object]:
    env = {**_read_env(ENV_PATH), **os.environ}
    return {
        "host": env.get("DB_HOST", "127.0.0.1"),
        "port": int(env.get("DB_PORT", "5432")),
        "user": env.get("DB_USER", "postgres"),
        "password": env.get("DB_PASSWORD", "") or None,
        "database": env.get("DB_NAME", "华世王镞_v2"),
    }


async def _table_exists(conn: asyncpg.Connection, table: str) -> bool:
    return await conn.fetchval("SELECT to_regclass($1)", f"public.{table}") is not None


async def _count(conn: asyncpg.Connection, sql: str) -> int:
    return int(await conn.fetchval(sql) or 0)


def _result(name: str, verdict: str, count: int | None, detail: str) -> dict[str, object]:
    return {"检查项": name, "结论": verdict, "违规计数": count, "说明": detail}


async def check_file_single_current_revision(conn: asyncpg.Connection) -> dict[str, object]:
    name = "每个非删除File的current_revision_id指向属于自己的Revision"
    if not await _table_exists(conn, "framework_file_revisions"):
        return _result(name, "SKIP", None, "framework_file_revisions 表不存在，跳过")
    # 设计（§19.3-C）：current 指针在 framework_file_items.current_revision_id，
    # 不是 revisions 表上的 is_current 标志。回填前 revisions 为空，整体 SKIP。
    total_rev = await _count(conn, "SELECT count(*) FROM framework_file_revisions")
    if total_rev == 0:
        return _result(name, "SKIP", 0, "回填前 framework_file_revisions 为空，跳过（finalize 期再校验必填）")
    # 回填后：current_revision_id 非空的文件，其指针必须指向一条属于该文件的 Revision
    bad = await _count(
        conn,
        """
        SELECT count(*) FROM framework_file_items f
        WHERE f.deleted = false
          AND f.current_revision_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM framework_file_revisions r
              WHERE r.id = f.current_revision_id AND r.file_id = f.id
          )
        """,
    )
    return _result(name, "PASS" if bad == 0 else "FAIL", bad, "current_revision_id 悬空或跨文件的文件数")


async def check_source_file_at_most_one_active_package(conn: asyncpg.Connection) -> dict[str, object]:
    name = "每个非删除source File至多一个active Package"
    bad = await _count(
        conn,
        f"""
        SELECT count(*) FROM (
            SELECT source_file_id
            FROM framework_content_packages
            WHERE source_file_id IS NOT NULL AND {ACTIVE_STATUS_FILTER}
            GROUP BY source_file_id
            HAVING count(*) > 1
        ) t
        """,
    )
    return _result(name, "PASS" if bad == 0 else "FAIL", bad, "存在多个 active Package 的 source_file 数")


async def check_ready_package_has_valid_current_version(conn: asyncpg.Connection) -> dict[str, object]:
    name = "每个ready/degraded/stale Package有合法current Version"
    status_list = ", ".join(f"'{s}'" for s in READY_STATUSES)
    bad = await _count(
        conn,
        f"""
        SELECT count(*)
        FROM framework_content_packages p
        WHERE p.deleted = false
          AND p.status IN ({status_list})
          AND (
              p.current_version_id IS NULL
              OR NOT EXISTS (
                  SELECT 1 FROM framework_content_package_versions v
                  WHERE v.id = p.current_version_id AND v.package_id = p.id
              )
          )
        """,
    )
    return _result(
        name,
        "PASS" if bad == 0 else "FAIL",
        bad,
        f"状态属于 {READY_STATUSES} 但 current_version 缺失/不属于本 package 的 Package 数",
    )


async def check_version_no_unique(conn: asyncpg.Connection) -> dict[str, object]:
    name = "Version的(package_id, version_no)唯一"
    bad = await _count(
        conn,
        """
        SELECT count(*) FROM (
            SELECT package_id, version_no
            FROM framework_content_package_versions
            GROUP BY package_id, version_no
            HAVING count(*) > 1
        ) t
        """,
    )
    return _result(name, "PASS" if bad == 0 else "FAIL", bad, "重复 (package_id, version_no) 组数")


async def check_resource_ref_version_belongs_to_package(conn: asyncpg.Connection) -> dict[str, object]:
    name = "ResourceRef的version_id属于同一package"
    # version_id 可空：可空的先标 WARN，不算 FAIL
    null_version = await _count(
        conn,
        "SELECT count(*) FROM framework_resource_refs WHERE version_id IS NULL",
    )
    # 非空但跨 package 的才是真违规
    cross_pkg = await _count(
        conn,
        """
        SELECT count(*)
        FROM framework_resource_refs rr
        JOIN framework_content_package_versions v ON v.id = rr.version_id
        WHERE rr.version_id IS NOT NULL AND v.package_id <> rr.package_id
        """,
    )
    if cross_pkg > 0:
        return _result(name, "FAIL", cross_pkg, "version_id 指向的 version 不属于本 package 的 ref 数")
    if null_version > 0:
        return _result(
            name,
            "WARN",
            null_version,
            f"当前 version_id 可空，{null_version} 条 ref 未绑定 version（暂不判 FAIL）",
        )
    return _result(name, "PASS", 0, "所有非空 version_id 均属于本 package")


async def check_all_resource_hash_not_null(conn: asyncpg.Connection) -> dict[str, object]:
    name = "所有framework_resources.hash非空"
    bad = await _count(
        conn,
        "SELECT count(*) FROM framework_resources WHERE hash IS NULL OR hash = ''",
    )
    return _result(name, "PASS" if bad == 0 else "FAIL", bad, "hash 为空的 resource 数")


CHECKS = (
    check_file_single_current_revision,
    check_source_file_at_most_one_active_package,
    check_ready_package_has_valid_current_version,
    check_version_no_unique,
    check_resource_ref_version_belongs_to_package,
    check_all_resource_hash_not_null,
)


async def run_all(conn: asyncpg.Connection) -> dict[str, object]:
    results: list[dict[str, object]] = []
    for check in CHECKS:
        results.append(await check(conn))
    verdicts = [r["结论"] for r in results]
    return {
        "生成时间": datetime.now(timezone.utc).isoformat(),
        "数据库名": await conn.fetchval("SELECT current_database()"),
        "检查结果": results,
        "汇总": {
            "PASS": verdicts.count("PASS"),
            "FAIL": verdicts.count("FAIL"),
            "SKIP": verdicts.count("SKIP"),
            "WARN": verdicts.count("WARN"),
        },
        "整体通过": "FAIL" not in verdicts,
    }


def render_human(report: dict[str, object]) -> str:
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("内容运行时不变量巡检（只读，§19.8）")
    lines.append("=" * 72)
    lines.append(f"数据库名 : {report['数据库名']}")
    lines.append(f"生成时间 : {report['生成时间']}")
    lines.append("-" * 72)
    icon = {"PASS": "[ PASS ]", "FAIL": "[ FAIL ]", "SKIP": "[ SKIP ]", "WARN": "[ WARN ]"}
    for r in report["检查结果"]:  # type: ignore[union-attr]
        cnt = r["违规计数"]
        cnt_txt = "-" if cnt is None else str(cnt)
        lines.append(f"{icon.get(str(r['结论']), '[ ???? ]')} {r['检查项']}  (违规={cnt_txt})")
        lines.append(f"          {r['说明']}")
    lines.append("-" * 72)
    s = report["汇总"]  # type: ignore[index]
    lines.append(
        f"汇总: PASS={s['PASS']} FAIL={s['FAIL']} SKIP={s['SKIP']} WARN={s['WARN']}  "  # type: ignore[index]
        f"整体{'通过' if report['整体通过'] else '未通过'}"
    )
    lines.append("=" * 72)
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="内容运行时不变量巡检（只读，任一 FAIL 退出码非零）"
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--output", type=str, default="", help="把报告落盘到指定路径（JSON）")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    cfg = _db_config()
    conn = await asyncpg.connect(**cfg)
    try:
        report = await run_all(conn)
    finally:
        await conn.close()

    if args.output:
        out_path = Path(args.output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[巡检] 报告已落盘: {out_path}")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_human(report))

    return 0 if report["整体通过"] else 1


def main() -> None:
    sys.exit(asyncio.run(_run(parse_args())))


if __name__ == "__main__":
    main()
