#!/usr/bin/env python3
"""内容运行时 M0 预检基线报告（只读）。

对应方案 §19.7 M0 预检清单：实时生成数据库大小、相关表计数、最大 id、
无 Package 存活文件、无 current_version Package、无 source_file Package、
kb_documents 未绑定、status/origin 分布、source_file 冲突、hash 加盐降级统计。

全程只读，绝不执行 INSERT/UPDATE/DDL。用法：

    backend/.venv/bin/python backend/scripts/content_runtime_preflight.py
    backend/.venv/bin/python backend/scripts/content_runtime_preflight.py --json
    backend/.venv/bin/python backend/scripts/content_runtime_preflight.py --output /tmp/m0_baseline.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
ENV_PATH = BACKEND_ROOT / ".env"

# M0 基线需要计数与取最大 id 的相关表（存在才统计，不存在标 missing）
RELEVANT_TABLES = (
    "framework_file_items",
    "framework_content_packages",
    "framework_content_package_versions",
    "framework_resources",
    "framework_resource_refs",
    "framework_artifacts",
    "framework_artifact_versions",
    "framework_file_revisions",
    "kb_documents",
    "kb_chunks",
    "kb_content_objects",
)

# 视为 active 的 Package：未软删 且 状态非 archived
ACTIVE_STATUS_FILTER = "deleted = false AND status <> 'archived'"


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
    row = await conn.fetchval("SELECT to_regclass($1)", f"public.{table}")
    return row is not None


async def _max_id(conn: asyncpg.Connection, table: str) -> int | None:
    # 所有相关表主键均为 id
    return await conn.fetchval(f'SELECT max(id) FROM "{table}"')


async def _count(conn: asyncpg.Connection, sql: str) -> int:
    val = await conn.fetchval(sql)
    return int(val or 0)


async def collect(conn: asyncpg.Connection) -> dict[str, object]:
    """采集 M0 基线全部只读指标。"""
    report: dict[str, object] = {
        "生成时间": datetime.now(timezone.utc).isoformat(),
        "数据库名": await conn.fetchval("SELECT current_database()"),
    }

    # 数据库大小
    report["数据库大小"] = {
        "字节": int(await conn.fetchval("SELECT pg_database_size(current_database())")),
        "可读": await conn.fetchval(
            "SELECT pg_size_pretty(pg_database_size(current_database()))"
        ),
    }

    # 各相关表 count + 最大 id（表不存在标 missing）
    tables: dict[str, object] = {}
    for tbl in RELEVANT_TABLES:
        if not await _table_exists(conn, tbl):
            tables[tbl] = {"存在": False}
            continue
        tables[tbl] = {
            "存在": True,
            "行数": await _count(conn, f'SELECT count(*) FROM "{tbl}"'),
            "最大id": await _max_id(conn, tbl),
        }
    report["表统计"] = tables

    # 无 ContentPackage 的存活文件数（file 未删，且无任一未删 Package 引用它）
    report["无Package的存活文件数"] = await _count(
        conn,
        """
        SELECT count(*)
        FROM framework_file_items f
        WHERE f.deleted = false
          AND NOT EXISTS (
              SELECT 1 FROM framework_content_packages p
              WHERE p.source_file_id = f.id AND p.deleted = false
          )
        """,
    )

    # 无 current_version 的 Package 数（未删 Package 但 current_version_id 为空）
    report["无current_version的Package数"] = await _count(
        conn,
        """
        SELECT count(*) FROM framework_content_packages
        WHERE deleted = false AND current_version_id IS NULL
        """,
    )

    # 无 source_file 的 Package 数（未删 Package 但 source_file_id 为空）
    report["无source_file的Package数"] = await _count(
        conn,
        """
        SELECT count(*) FROM framework_content_packages
        WHERE deleted = false AND source_file_id IS NULL
        """,
    )

    # kb_documents 无 content_package_id 数（未删文档但未绑定 Package）
    if await _table_exists(conn, "kb_documents"):
        report["kb_documents无content_package_id数"] = await _count(
            conn,
            """
            SELECT count(*) FROM kb_documents
            WHERE deleted = false AND content_package_id IS NULL
            """,
        )
    else:
        report["kb_documents无content_package_id数"] = None

    # status 分布
    report["Package_status分布"] = {
        r["status"]: int(r["c"])
        for r in await conn.fetch(
            "SELECT status, count(*) c FROM framework_content_packages "
            "GROUP BY status ORDER BY c DESC"
        )
    }

    # origin_type 分布
    report["Package_origin_type分布"] = {
        r["origin_type"]: int(r["c"])
        for r in await conn.fetch(
            "SELECT origin_type, count(*) c FROM framework_content_packages "
            "GROUP BY origin_type ORDER BY c DESC"
        )
    }

    # 一个 source_file 对多个 active Package 的冲突数
    report["source_file多active_Package冲突数"] = await _count(
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

    # framework_resources.hash 加盐降级统计
    # 注意 §19.3-C：加盐值实际是 sha256("{owner}:{hash}")，是纯 64 位 hex，
    # 不含字面 "{owner}:" 前缀。此处按任务要求扫字面前缀（预期为 0），
    # 同时给出「非 64 位 hex」的可疑项作为真正需要甄别的信号。
    salted_literal = await _count(
        conn,
        r"""
        SELECT count(*) FROM framework_resources
        WHERE hash LIKE '%:%'
        """,
    )
    pure_hash = await _count(
        conn,
        r"""
        SELECT count(*) FROM framework_resources
        WHERE hash IS NOT NULL AND hash NOT LIKE '%:%'
        """,
    )
    non_sha256_shape = await _count(
        conn,
        r"""
        SELECT count(*) FROM framework_resources
        WHERE hash IS NULL OR hash !~ '^[0-9a-f]{64}$'
        """,
    )
    report["resources_hash统计"] = {
        "带owner冒号前缀条数": salted_literal,
        "纯hash条数": pure_hash,
        "非标准sha256形态条数": non_sha256_shape,
        "说明": (
            "加盐降级实际为 sha256(\"{owner}:hash\") 纯 hex，无字面前缀，"
            "字面前缀数预期为 0；真正加盐降级需跨 owner 比对，无法仅凭 hash 列判定"
        ),
    }

    return report


def render_human(report: dict[str, object]) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("内容运行时 M0 预检基线报告（只读）")
    lines.append("=" * 64)
    lines.append(f"数据库名   : {report['数据库名']}")
    lines.append(f"生成时间   : {report['生成时间']}")
    db = report["数据库大小"]  # type: ignore[index]
    lines.append(f"数据库大小 : {db['可读']} ({db['字节']} 字节)")  # type: ignore[index]
    lines.append("")
    lines.append("[ 表统计 ] 行数 / 最大id")
    lines.append("-" * 64)
    for tbl, info in report["表统计"].items():  # type: ignore[union-attr]
        if not info.get("存在"):  # type: ignore[union-attr]
            lines.append(f"  {tbl:<42} 缺失(表不存在)")
            continue
        lines.append(
            f"  {tbl:<42} {info['行数']:>10}  max_id={info['最大id']}"  # type: ignore[index]
        )
    lines.append("")
    lines.append("[ 迁移基线指标 ]")
    lines.append("-" * 64)
    lines.append(f"  无Package的存活文件数            : {report['无Package的存活文件数']}")
    lines.append(f"  无current_version的Package数     : {report['无current_version的Package数']}")
    lines.append(f"  无source_file的Package数         : {report['无source_file的Package数']}")
    lines.append(f"  kb_documents无content_package_id : {report['kb_documents无content_package_id数']}")
    lines.append(f"  source_file多active_Package冲突数: {report['source_file多active_Package冲突数']}")
    lines.append("")
    lines.append("[ Package status 分布 ]")
    lines.append("-" * 64)
    for k, v in report["Package_status分布"].items():  # type: ignore[union-attr]
        lines.append(f"  {k:<20} {v}")
    lines.append("")
    lines.append("[ Package origin_type 分布 ]")
    lines.append("-" * 64)
    for k, v in report["Package_origin_type分布"].items():  # type: ignore[union-attr]
        lines.append(f"  {k:<20} {v}")
    lines.append("")
    lines.append("[ framework_resources.hash 统计 ]")
    lines.append("-" * 64)
    rh = report["resources_hash统计"]  # type: ignore[index]
    lines.append(f"  带owner冒号前缀条数    : {rh['带owner冒号前缀条数']}")  # type: ignore[index]
    lines.append(f"  纯hash条数             : {rh['纯hash条数']}")  # type: ignore[index]
    lines.append(f"  非标准sha256形态条数   : {rh['非标准sha256形态条数']}")  # type: ignore[index]
    lines.append(f"  说明: {rh['说明']}")  # type: ignore[index]
    lines.append("=" * 64)
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="内容运行时 M0 预检基线报告（只读，不写库）"
    )
    parser.add_argument(
        "--json", action="store_true", help="输出机器可读 JSON（默认人类可读）"
    )
    parser.add_argument(
        "--output", type=str, default="", help="把报告落盘到指定路径（JSON 格式）"
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    cfg = _db_config()
    conn = await asyncpg.connect(**cfg)
    try:
        report = await collect(conn)
    finally:
        await conn.close()

    if args.output:
        out_path = Path(args.output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[预检] 报告已落盘: {out_path}")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_human(report))


def main() -> None:
    asyncio.run(_run(parse_args()))


if __name__ == "__main__":
    main()
