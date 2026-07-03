---
name: "Backend foundation sweep r2 platform false-success and file-access fixes"
type: "task"
tags: [backend, foundation, module-call, content-ir, file-access, task-queue]
agent: "codex-backend-foundation-sweep-20260703-r2"
created: "2026-07-03T06:50:48.733116+00:00"
---

## Agent
codex-backend-foundation-sweep-20260703-r2

## Scope
Only changed backend/app and backend/tests. Other dirty frontend/modules files were pre-existing work from parallel agents and were not touched.

## Scan Findings
- /api/modules/call wrapped capability results with {success:false} in an HTTP 200 ApiResponse, violating the backend rule that business failures should go through the unified exception path.
- Content export adapter accepted a returned file_id from office-gen and resolved the physical path via db.get(File) without check_file_access.
- Content export overwrite branch used Python `not File.deleted` inside a SQLAlchemy where clause instead of `File.deleted.is_(False)`.
- Sent share listing filtered deleted files in the count query but not in the result query, so deleted shared files could still appear.
- DB/task audit found historical task debt: live /api/health reported 905 failed tasks, 1 future scheduled pending, 0 running, and 0 semantic_failed_completed_24h. This is residual data debt, not a code-fix target in this sweep.

## Fixes
- backend/app/routers/modules.py now raises ValidationError when a capability returns success=false, producing HTTP 422 with unified {success:false,data:null,error} instead of HTTP 200 false-success.
- backend/app/services/content/adapter.py checks returned export file_id with check_file_access before resolving its storage path.
- backend/app/services/content/export_service.py checks source file access in fallback copy and fixes overwrite SQL filtering to File.deleted.is_(False).
- backend/app/services/file_share_service.py filters deleted files from sent share results.
- Added backend/tests/test_foundation_sweep_regressions.py and updated backend/tests/test_module_call_false_success.py.

## Verification
- Ruff passed for all changed Python files.
- `cd backend && .venv/bin/python -m pytest tests/test_content_ir_architecture.py tests/test_module_call_false_success.py tests/test_foundation_sweep_regressions.py tests/test_access_control_regressions.py tests/test_framework_health.py tests/test_task_worker_semantics.py tests/test_task_worker_recovery.py` -> 80 passed, 1 warning from unrelated modules/github-search on_event deprecation.
- Restarted backend successfully on 127.0.0.1:33000.
- Live probes: /api/health 200 success; /api/modules/call _self echo 200 success; /api/modules/call content:validate_ir invalid payload now returns HTTP 422 unified failure.

## Commit
No commit created in this task.
