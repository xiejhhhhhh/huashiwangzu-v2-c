"""Read-only audit for imported knowledge source manifest rows."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CRITICAL_STAGES = [
    "source_validate",
    "parse_index",
    "raw_text",
    "page_render",
    "raw_ocr",
    "raw_vision",
    "fusion",
    "profile",
    "cognitive_index",
    "graph",
    "relations",
]

TERMINAL_STAGE_STATUSES = ["done", "degraded", "skipped"]


def normalize_source_root(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return str(Path(text).expanduser().resolve())


def normalize_stage_list(value: list[str] | None) -> list[str]:
    raw_items = value or DEFAULT_CRITICAL_STAGES
    stages = []
    seen = set()
    for item in raw_items:
        stage = str(item or "").strip()
        if stage and stage not in seen:
            stages.append(stage)
            seen.add(stage)
    return stages or list(DEFAULT_CRITICAL_STAGES)


def _bounded_positive_int(value: int, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


async def source_manifest_import_audit_snapshot(
    repo_root: Path,
    *,
    owner_id: int = 1,
    source_root: str = "",
    limit: int = 1000,
    sample_limit: int = 25,
    critical_stages: list[str] | None = None,
) -> dict[str, Any]:
    cmd = [
        _project_python(repo_root),
        "dev_toolkit/knowledge_source_manifest_audit.py",
        "--owner-id",
        str(int(owner_id)),
        "--limit",
        str(int(limit)),
        "--sample-limit",
        str(int(sample_limit)),
        "--json",
    ]
    if source_root:
        cmd.extend(["--source-root", source_root])
    for stage in normalize_stage_list(critical_stages):
        cmd.extend(["--stage", stage])

    env = os.environ.copy()
    env["PYTHONPATH"] = "backend"
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=repo_root,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return {
            "success": False,
            "read_only": True,
            "error": stderr.decode("utf-8", errors="replace")[-4000:],
        }
    return json.loads(stdout.decode("utf-8"))


async def source_manifest_import_audit(
    *,
    owner_id: int = 1,
    source_root: str = "",
    limit: int = 1000,
    sample_limit: int = 25,
    critical_stages: list[str] | None = None,
) -> dict[str, Any]:
    """Audit imported source manifest rows against framework and knowledge tables."""
    from app.database import AsyncSessionLocal
    from sqlalchemy import text

    normalized_root = normalize_source_root(source_root)
    bounded_limit = _bounded_positive_int(limit, default=1000, maximum=200000)
    bounded_sample_limit = max(0, min(int(sample_limit or 0), 500))
    stages = normalize_stage_list(critical_stages)

    sql = text(
        """
        with
        critical_stages as (
          select value::text as stage
          from jsonb_array_elements_text(cast(:critical_stages_json as jsonb))
        ),
        selected_manifest as (
          select m.*
          from kb_source_file_manifest m
          where m.owner_id = :owner_id
            and m.import_status = 'imported'
            and (:source_root = '' or m.source_root = :source_root)
          order by m.id asc
          limit :audit_limit
        ),
        manifest_total as (
          select count(*) as count
          from kb_source_file_manifest m
          where m.owner_id = :owner_id
            and m.import_status = 'imported'
            and (:source_root = '' or m.source_root = :source_root)
        ),
        file_match as (
          select m.id as manifest_id,
                 direct_file.id as direct_file_id,
                 md5_file.id as md5_file_id,
                 coalesce(direct_file.id, md5_file.id) as covered_file_id,
                 coalesce(direct_file.md5_hash, md5_file.md5_hash, m.md5_hash) as covered_md5_hash
          from selected_manifest m
          left join framework_file_items direct_file
            on direct_file.id = m.file_id
           and direct_file.owner_id = m.owner_id
           and direct_file.deleted is false
          left join lateral (
            select f.id, f.md5_hash
            from framework_file_items f
            where f.owner_id = m.owner_id
              and f.deleted is false
              and m.md5_hash is not null
              and m.md5_hash <> ''
              and f.md5_hash = m.md5_hash
            order by f.id asc
            limit 1
          ) md5_file on true
        ),
        document_candidates as (
          select m.id as manifest_id,
                 d.id as document_id,
                 'manifest_document_id' as match_source,
                 1 as priority
          from selected_manifest m
          join kb_documents d
            on d.id = m.document_id
           and d.owner_id = m.owner_id
           and d.deleted is false
          union all
          select m.id,
                 d.id,
                 'manifest_file_id',
                 2
          from selected_manifest m
          join kb_documents d
            on d.file_id = m.file_id
           and d.owner_id = m.owner_id
           and d.deleted is false
          where m.file_id is not null
          union all
          select m.id,
                 coalesce(l.canonical_document_id, l.document_id),
                 'file_knowledge_link',
                 3
          from selected_manifest m
          join kb_file_knowledge_links l
            on l.file_id = m.file_id
           and l.owner_id = m.owner_id
           and l.status = 'active'
          where m.file_id is not null
            and coalesce(l.canonical_document_id, l.document_id) is not null
          union all
          select m.id,
                 d.id,
                 'framework_md5_document',
                 4
          from selected_manifest m
          join file_match fm on fm.manifest_id = m.id
          join kb_documents d
            on d.file_id = fm.covered_file_id
           and d.owner_id = m.owner_id
           and d.deleted is false
          where fm.covered_file_id is not null
          union all
          select m.id,
                 d.id,
                 'document_md5',
                 5
          from selected_manifest m
          join kb_documents d
            on d.owner_id = m.owner_id
           and d.deleted is false
           and m.md5_hash is not null
           and m.md5_hash <> ''
           and d.md5_hash = m.md5_hash
        ),
        ranked_document_candidates as (
          select dc.*,
                 row_number() over (
                   partition by dc.manifest_id
                   order by dc.priority asc, dc.document_id asc
                 ) as rn
          from document_candidates dc
        ),
        doc_choice as (
          select manifest_id, document_id, match_source
          from ranked_document_candidates
          where rn = 1
        ),
        chunk_counts as (
          select c.document_id, count(*) as chunk_count
          from kb_chunks c
          join doc_choice dc on dc.document_id = c.document_id
          group by c.document_id
        ),
        raw_counts as (
          select r.document_id,
                 count(*) as raw_data_count,
                 count(*) filter (where r.status in ('done', 'degraded')) as raw_terminal_count
          from kb_raw_data r
          join doc_choice dc on dc.document_id = r.document_id
          group by r.document_id
        ),
        pipeline_run_counts as (
          select pr.document_id, count(*) as pipeline_run_count
          from kb_pipeline_runs pr
          join doc_choice dc on dc.document_id = pr.document_id
          group by pr.document_id
        ),
        stage_counts as (
          select sr.document_id,
                 sr.stage,
                 count(*) as run_count,
                 count(*) filter (where sr.status = any(:terminal_statuses)) as terminal_count,
                 count(*) filter (where sr.status = 'failed') as failed_count,
                 max(sr.updated_at) as latest_updated_at
          from kb_pipeline_stage_runs sr
          join doc_choice dc on dc.document_id = sr.document_id
          group by sr.document_id, sr.stage
        ),
        row_audit as (
          select m.id as manifest_id,
                 m.owner_id,
                 m.source_root,
                 m.relative_path,
                 m.source_path,
                 m.extension,
                 m.size,
                 m.md5_hash as manifest_md5_hash,
                 m.file_id as manifest_file_id,
                 m.document_id as manifest_document_id,
                 m.import_task_id,
                 m.updated_at as manifest_updated_at,
                 fm.direct_file_id,
                 fm.md5_file_id,
                 fm.covered_file_id,
                 (fm.covered_file_id is not null) as has_framework_file,
                 dc.document_id,
                 dc.match_source as document_match_source,
                 coalesce(cc.chunk_count, 0) as chunk_count,
                 coalesce(rc.raw_data_count, 0) as raw_data_count,
                 coalesce(rc.raw_terminal_count, 0) as raw_terminal_count,
                 coalesce(prc.pipeline_run_count, 0) as pipeline_run_count,
                 (
                   select coalesce(sum(sc.run_count), 0)::int
                   from stage_counts sc
                   where sc.document_id = dc.document_id
                 ) as stage_run_count,
                 (
                   select count(*)::int
                   from critical_stages cs
                   left join stage_counts sc
                     on sc.document_id = dc.document_id
                    and sc.stage = cs.stage
                   where dc.document_id is not null
                     and coalesce(sc.run_count, 0) = 0
                 ) as missing_critical_stage_count,
                 (
                   select coalesce(
                     jsonb_object_agg(
                       cs.stage,
                       jsonb_build_object(
                         'run_count', coalesce(sc.run_count, 0),
                         'terminal_count', coalesce(sc.terminal_count, 0),
                         'failed_count', coalesce(sc.failed_count, 0),
                         'latest_updated_at', sc.latest_updated_at
                       )
                       order by cs.stage
                     ),
                     '{}'::jsonb
                   )
                   from critical_stages cs
                   left join stage_counts sc
                     on sc.document_id = dc.document_id
                    and sc.stage = cs.stage
                 ) as stage_coverage
          from selected_manifest m
          left join file_match fm on fm.manifest_id = m.id
          left join doc_choice dc on dc.manifest_id = m.id
          left join chunk_counts cc on cc.document_id = dc.document_id
          left join raw_counts rc on rc.document_id = dc.document_id
          left join pipeline_run_counts prc on prc.document_id = dc.document_id
        ),
        summary as (
          select count(*) as audited_imported,
                 count(*) filter (where has_framework_file) as with_framework_file,
                 count(*) filter (where not has_framework_file) as missing_framework_file,
                 count(*) filter (where document_id is not null) as with_document,
                 count(*) filter (where document_id is null) as missing_document,
                 count(*) filter (where document_id is not null and chunk_count > 0) as with_chunks,
                 count(*) filter (where document_id is not null and chunk_count = 0) as missing_chunks,
                 count(*) filter (where document_id is not null and raw_data_count > 0) as with_raw_data,
                 count(*) filter (where document_id is not null and raw_data_count = 0) as missing_raw_data,
                 count(*) filter (where document_id is not null and stage_run_count > 0) as with_stage_runs,
                 count(*) filter (where document_id is not null and stage_run_count = 0) as missing_stage_runs,
                 count(*) filter (where document_id is not null and missing_critical_stage_count > 0) as missing_critical_stage_runs,
                 count(*) filter (
                   where has_framework_file
                     and document_id is not null
                     and chunk_count > 0
                     and raw_data_count > 0
                     and stage_run_count > 0
                 ) as complete_core_data,
                 count(*) filter (
                   where not (
                     has_framework_file
                     and document_id is not null
                     and chunk_count > 0
                     and raw_data_count > 0
                     and stage_run_count > 0
                   )
                 ) as incomplete_core_data
          from row_audit
        ),
        by_source_root as (
          select source_root,
                 count(*) as audited_imported,
                 count(*) filter (where not has_framework_file) as missing_framework_file,
                 count(*) filter (where document_id is null) as missing_document,
                 count(*) filter (where document_id is not null and chunk_count = 0) as missing_chunks,
                 count(*) filter (where document_id is not null and raw_data_count = 0) as missing_raw_data,
                 count(*) filter (where document_id is not null and stage_run_count = 0) as missing_stage_runs,
                 count(*) filter (where document_id is not null and missing_critical_stage_count > 0) as missing_critical_stage_runs,
                 count(*) filter (
                   where not (
                     has_framework_file
                     and document_id is not null
                     and chunk_count > 0
                     and raw_data_count > 0
                     and stage_run_count > 0
                   )
                 ) as incomplete_core_data
          from row_audit
          group by source_root
        ),
        by_extension as (
          select extension,
                 count(*) as audited_imported,
                 count(*) filter (where not has_framework_file) as missing_framework_file,
                 count(*) filter (where document_id is null) as missing_document,
                 count(*) filter (where document_id is not null and chunk_count = 0) as missing_chunks,
                 count(*) filter (where document_id is not null and raw_data_count = 0) as missing_raw_data,
                 count(*) filter (where document_id is not null and stage_run_count = 0) as missing_stage_runs,
                 count(*) filter (where document_id is not null and missing_critical_stage_count > 0) as missing_critical_stage_runs,
                 count(*) filter (
                   where not (
                     has_framework_file
                     and document_id is not null
                     and chunk_count > 0
                     and raw_data_count > 0
                     and stage_run_count > 0
                   )
                 ) as incomplete_core_data
          from row_audit
          group by extension
        ),
        stage_summary as (
          select cs.stage,
                 count(ra.manifest_id) filter (where ra.document_id is not null) as manifest_rows_with_document,
                 count(ra.manifest_id) filter (where coalesce(sc.run_count, 0) > 0) as manifest_rows_with_stage,
                 count(ra.manifest_id) filter (where coalesce(sc.terminal_count, 0) > 0) as manifest_rows_with_terminal_stage,
                 count(ra.manifest_id) filter (where coalesce(sc.failed_count, 0) > 0) as manifest_rows_with_failed_stage
          from critical_stages cs
          cross join row_audit ra
          left join stage_counts sc
            on sc.document_id = ra.document_id
           and sc.stage = cs.stage
          group by cs.stage
        ),
        samples as (
          select *
          from row_audit
          where not (
            has_framework_file
            and document_id is not null
            and chunk_count > 0
            and raw_data_count > 0
            and stage_run_count > 0
          )
          order by
            case
              when not has_framework_file then 1
              when document_id is null then 2
              when chunk_count = 0 then 3
              when raw_data_count = 0 then 4
              when stage_run_count = 0 then 5
              else 6
            end,
            manifest_id asc
          limit :sample_limit
        )
        select jsonb_build_object(
          'success', true,
          'read_only', true,
          'input', jsonb_build_object(
            'owner_id', :owner_id,
            'source_root', :source_root,
            'limit', :audit_limit,
            'sample_limit', :sample_limit,
            'critical_stages', cast(:critical_stages_json as jsonb)
          ),
          'total_matching_imported_rows', (select count from manifest_total),
          'limited', (select count from manifest_total) > :audit_limit,
          'summary', coalesce((select to_jsonb(summary) from summary), '{}'::jsonb),
          'by_source_root', coalesce((select jsonb_agg(to_jsonb(by_source_root) order by source_root) from by_source_root), '[]'::jsonb),
          'by_extension', coalesce((select jsonb_agg(to_jsonb(by_extension) order by incomplete_core_data desc, extension) from by_extension), '[]'::jsonb),
          'stage_summary', coalesce((select jsonb_agg(to_jsonb(stage_summary) order by stage) from stage_summary), '[]'::jsonb),
          'samples', coalesce((select jsonb_agg(to_jsonb(samples) order by manifest_id) from samples), '[]'::jsonb)
        ) as payload
        """
    )

    params = {
        "owner_id": int(owner_id),
        "source_root": normalized_root,
        "audit_limit": bounded_limit,
        "sample_limit": bounded_sample_limit,
        "critical_stages_json": json.dumps(stages, ensure_ascii=False),
        "terminal_statuses": TERMINAL_STAGE_STATUSES,
    }
    async with AsyncSessionLocal() as db:
        row = (await db.execute(sql, params)).mappings().one()
    payload = row["payload"]
    if isinstance(payload, str):
        return json.loads(payload)
    return dict(payload)


def _format_human(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        "Knowledge source manifest imported audit",
        f"read_only: {payload.get('read_only')}",
        f"total_matching_imported_rows: {payload.get('total_matching_imported_rows')}",
        f"audited_imported: {summary.get('audited_imported', 0)}",
        f"complete_core_data: {summary.get('complete_core_data', 0)}",
        f"incomplete_core_data: {summary.get('incomplete_core_data', 0)}",
        f"missing_framework_file: {summary.get('missing_framework_file', 0)}",
        f"missing_document: {summary.get('missing_document', 0)}",
        f"missing_chunks: {summary.get('missing_chunks', 0)}",
        f"missing_raw_data: {summary.get('missing_raw_data', 0)}",
        f"missing_stage_runs: {summary.get('missing_stage_runs', 0)}",
        f"missing_critical_stage_runs: {summary.get('missing_critical_stage_runs', 0)}",
    ]
    samples = payload.get("samples") or []
    if samples:
        lines.append("samples:")
        for item in samples[:10]:
            lines.append(
                "- manifest_id={manifest_id} file_id={manifest_file_id} "
                "document_id={document_id} path={relative_path}".format(**item)
            )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only audit for kb_source_file_manifest rows marked imported. "
            "Checks framework files, knowledge documents, chunks, raw data, and pipeline stage runs."
        )
    )
    parser.add_argument("--source-root", default="", help="Optional source_root filter; normalized with Path.resolve().")
    parser.add_argument("--owner-id", type=int, default=1, help="Owner/user ID. Default: 1.")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum imported manifest rows to audit. Default: 1000.")
    parser.add_argument("--sample-limit", type=int, default=25, help="Maximum incomplete samples to return. Default: 25.")
    parser.add_argument(
        "--stage",
        dest="stages",
        action="append",
        default=None,
        help="Critical pipeline stage to check. May be repeated; defaults to the knowledge DAG stages.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a compact human summary.")
    return parser


def _project_python(repo_root: Path) -> str:
    candidate = repo_root / "backend" / ".venv" / "bin" / "python"
    return str(candidate) if candidate.exists() else "python3"


async def _main_async(args: argparse.Namespace) -> int:
    payload = await source_manifest_import_audit(
        owner_id=args.owner_id,
        source_root=args.source_root,
        limit=args.limit,
        sample_limit=args.sample_limit,
        critical_stages=args.stages,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(_format_human(payload))
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
