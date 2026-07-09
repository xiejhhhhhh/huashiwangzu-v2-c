"""Read-only source-folder gap diagnostics for knowledge ingestion."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any


async def source_gap_snapshot(
    repo_root: Path,
    *,
    root_names: list[str],
    root_ids: list[int],
    extensions: list[str],
    sample_limit: int,
) -> dict[str, Any]:
    script = f"""
import asyncio
import json
from sqlalchemy import text
from app.database import AsyncSessionLocal

ROOT_NAMES_JSON = {json.dumps(json.dumps(root_names, ensure_ascii=False))}
ROOT_IDS_JSON = {json.dumps(json.dumps(root_ids, ensure_ascii=False))}
EXTENSIONS_JSON = {json.dumps(json.dumps(extensions, ensure_ascii=False))}
SAMPLE_LIMIT = {int(sample_limit)}
IMAGE_EXTENSIONS_JSON = {json.dumps(json.dumps(image_extensions(), ensure_ascii=False))}

SQL = '''
with recursive
root_name_values as (
  select value::text as name
  from jsonb_array_elements_text(cast(:root_names_json as jsonb))
),
root_id_values as (
  select value::int as id
  from jsonb_array_elements_text(cast(:root_ids_json as jsonb))
),
extension_values as (
  select lower(value::text) as extension
  from jsonb_array_elements_text(cast(:extensions_json as jsonb))
),
image_extension_values as (
  select lower(value::text) as extension
  from jsonb_array_elements_text(cast(:image_extensions_json as jsonb))
),
roots as (
  select f.id, f.name as root_name, f.owner_id
  from framework_file_folders f
  where f.deleted is false
    and (
      f.name in (select name from root_name_values)
      or f.id in (select id from root_id_values)
    )
),
folder_tree as (
  select r.id as root_id, r.root_name, r.owner_id, r.id as folder_id
  from roots r
  union all
  select ft.root_id, ft.root_name, ft.owner_id, child.id as folder_id
  from framework_file_folders child
  join folder_tree ft on child.parent_id = ft.folder_id and child.owner_id = ft.owner_id
  where child.deleted is false
),
source_files as (
  select ft.root_id,
         ft.root_name,
         ft.owner_id,
         fi.id as file_id,
         fi.folder_id,
         fi.name,
         lower(coalesce(fi.extension, '')) as extension,
         fi.size,
         fi.md5_hash,
         fi.storage_path,
         (lower(coalesce(fi.extension, '')) in (select extension from image_extension_values)) as is_image
  from folder_tree ft
  join framework_file_items fi on fi.folder_id = ft.folder_id and fi.owner_id = ft.owner_id
  where fi.deleted is false
    and lower(coalesce(fi.extension, '')) in (select extension from extension_values)
),
doc_status as (
  select d.id as document_id,
         bool_or(q.status in ('pending', 'running')) as active,
         bool_or(q.status = 'failed') as failed,
         bool_or(q.stage_key = 'raw_vision' and q.status = 'completed') as raw_vision_done,
         bool_or(q.stage_key = 'raw_vision' and q.status in ('pending', 'running')) as raw_vision_active,
         count(q.id) filter (where q.status = 'failed') as failed_tasks
  from kb_documents d
  left join framework_system_task_queues q
    on q.task_type = 'kb_pipeline_stage'
   and q.document_id = d.id
  where d.deleted is false
  group by d.id
),
file_facts as (
  select sf.*,
         direct_doc.id as direct_document_id,
         link.id as link_id,
         coalesce(link.canonical_document_id, link.document_id, direct_doc.id) as covered_document_id,
         coalesce(ds.active, false) as active,
         coalesce(ds.failed, false) as failed,
         coalesce(ds.raw_vision_done, false) as raw_vision_done,
         coalesce(ds.raw_vision_active, false) as raw_vision_active,
         coalesce(ds.failed_tasks, 0) as failed_tasks,
         exists (
           select 1
           from kb_documents kd
           where kd.deleted is false
             and kd.owner_id = sf.owner_id
             and kd.file_id <> sf.file_id
             and kd.md5_hash is not null
             and kd.md5_hash <> ''
             and kd.md5_hash = sf.md5_hash
         ) as md5_covered
  from source_files sf
  left join kb_documents direct_doc
    on direct_doc.owner_id = sf.owner_id
   and direct_doc.file_id = sf.file_id
   and direct_doc.deleted is false
  left join kb_file_knowledge_links link
    on link.owner_id = sf.owner_id
   and link.file_id = sf.file_id
   and link.status = 'active'
  left join doc_status ds
    on ds.document_id = coalesce(link.canonical_document_id, link.document_id, direct_doc.id)
),
root_summary as (
  select root_name,
         count(distinct root_id) as root_count,
         count(*) as analyzable_files,
         count(*) filter (where direct_document_id is null) as not_directly_in_kb,
         count(*) filter (where direct_document_id is null and link_id is not null) as linked_to_kb,
         count(*) filter (where direct_document_id is null and link_id is null and md5_covered) as not_direct_but_md5_covered,
         count(*) filter (where covered_document_id is null and not md5_covered) as truly_not_analyzed,
         count(*) filter (where covered_document_id is not null and active) as active,
         count(*) filter (where covered_document_id is not null and failed) as failed,
         count(*) filter (where covered_document_id is not null and not active and not failed) as ok_or_completed,
         count(*) filter (where is_image) as image_files,
         count(*) filter (where is_image and direct_document_id is null) as image_not_directly_in_kb,
         count(*) filter (where is_image and direct_document_id is null and link_id is not null) as image_linked_to_kb,
         count(*) filter (where is_image and covered_document_id is null and not md5_covered) as image_truly_not_analyzed,
         count(*) filter (where is_image and covered_document_id is not null and not raw_vision_done) as image_registered_without_raw_vision_done
  from file_facts
  group by root_name
),
extension_summary as (
  select root_name,
         extension,
         count(*) as analyzable_files,
         count(*) filter (where covered_document_id is null and not md5_covered) as truly_not_analyzed,
         count(*) filter (where direct_document_id is null and link_id is not null) as linked_to_kb,
         count(*) filter (where covered_document_id is not null and failed) as failed,
         count(*) filter (where covered_document_id is not null and active) as active
  from file_facts
  group by root_name, extension
),
sample_rows as (
  select *
  from (
    select root_name,
           file_id,
           name,
           extension,
           size,
           md5_hash,
           storage_path,
           row_number() over (partition by root_name order by size desc, file_id) as rn
    from file_facts
    where covered_document_id is null and not md5_covered
  ) ranked
  where rn <= :sample_limit
),
queue_status as (
  select coalesce(stage_key, '') as stage_key,
         status,
         count(*) as count
  from framework_system_task_queues
  where task_type = 'kb_pipeline_stage'
  group by stage_key, status
)
select jsonb_build_object(
  'root_folders', coalesce((select jsonb_agg(to_jsonb(roots) order by root_name, id) from roots), '[]'::jsonb),
  'summary', coalesce((select jsonb_agg(to_jsonb(root_summary) order by root_name) from root_summary), '[]'::jsonb),
  'extensions', coalesce((select jsonb_agg(to_jsonb(extension_summary) order by root_name, truly_not_analyzed desc, extension) from extension_summary), '[]'::jsonb),
  'samples', coalesce((select jsonb_agg(to_jsonb(sample_rows) order by root_name, rn) from sample_rows), '[]'::jsonb),
  'queue_status', coalesce((select jsonb_agg(to_jsonb(queue_status) order by stage_key, status) from queue_status), '[]'::jsonb)
) as payload
'''

async def main():
    async with AsyncSessionLocal() as db:
        row = (await db.execute(text(SQL), {{
            "root_names_json": ROOT_NAMES_JSON,
            "root_ids_json": ROOT_IDS_JSON,
            "extensions_json": EXTENSIONS_JSON,
            "image_extensions_json": IMAGE_EXTENSIONS_JSON,
            "sample_limit": SAMPLE_LIMIT,
        }})).mappings().one()
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    summary = payload.get("summary") or []
    totals = {{
        "analyzable_files": sum(int(row.get("analyzable_files") or 0) for row in summary),
        "not_directly_in_kb": sum(int(row.get("not_directly_in_kb") or 0) for row in summary),
        "linked_to_kb": sum(int(row.get("linked_to_kb") or 0) for row in summary),
        "not_direct_but_md5_covered": sum(int(row.get("not_direct_but_md5_covered") or 0) for row in summary),
        "truly_not_analyzed": sum(int(row.get("truly_not_analyzed") or 0) for row in summary),
        "active": sum(int(row.get("active") or 0) for row in summary),
        "failed": sum(int(row.get("failed") or 0) for row in summary),
        "ok_or_completed": sum(int(row.get("ok_or_completed") or 0) for row in summary),
        "image_files": sum(int(row.get("image_files") or 0) for row in summary),
        "image_not_directly_in_kb": sum(int(row.get("image_not_directly_in_kb") or 0) for row in summary),
        "image_linked_to_kb": sum(int(row.get("image_linked_to_kb") or 0) for row in summary),
        "image_truly_not_analyzed": sum(int(row.get("image_truly_not_analyzed") or 0) for row in summary),
        "image_registered_without_raw_vision_done": sum(int(row.get("image_registered_without_raw_vision_done") or 0) for row in summary),
    }}
    payload.update({{
        "success": True,
        "totals": totals,
        "input": {{
            "root_names": json.loads(ROOT_NAMES_JSON),
            "root_ids": json.loads(ROOT_IDS_JSON),
            "extensions": json.loads(EXTENSIONS_JSON),
            "sample_limit": SAMPLE_LIMIT,
        }},
    }})
    print(json.dumps(payload, ensure_ascii=False, default=str))

asyncio.run(main())
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = "backend"
    proc = await asyncio.create_subprocess_exec(
        _project_python(repo_root),
        "-c",
        script,
        cwd=repo_root,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        return {
            "success": False,
            "error": stderr.decode("utf-8", errors="replace")[-4000:],
        }
    return json.loads(stdout.decode("utf-8"))


def normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]
    items: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text:
            items.append(text)
    return items


def normalize_int_list(value: Any) -> list[int]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else [value]
    items: list[int] = []
    for item in raw_items:
        try:
            parsed = int(item)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            items.append(parsed)
    return items


def normalize_extensions(value: Any) -> list[str]:
    items = normalize_string_list(value)
    if not items:
        return [
            "pdf",
            "doc",
            "docx",
            "xls",
            "xlsx",
            "ppt",
            "pptx",
            "txt",
            "md",
            "csv",
            "jpg",
            "jpeg",
            "png",
            "webp",
            "bmp",
            "tif",
            "tiff",
            "heic",
        ]
    return sorted({item.lower().lstrip(".") for item in items if item.strip(".")})


def image_extensions() -> list[str]:
    return ["jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff", "heic"]


def _project_python(repo_root: Path) -> str:
    candidate = repo_root / "backend" / ".venv" / "bin" / "python"
    return str(candidate) if candidate.exists() else "python3"
