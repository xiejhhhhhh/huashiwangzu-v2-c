---
name: "content pipeline access and get_file_content fail-closed r3"
type: "task"
tags: [content, pipeline, permissions, get_file_content, false-success, r3]
agent: "content-pipeline-access-fix-r3"
created: "2026-07-03T10:17:27.075216+00:00"
---

# 改了什么
- `ContentPipelineService.run_pipeline` 在 `get_or_create` 前改为 `resolve_caller_user_id(caller)` + `check_file_access(db, file_id, caller_user_id)`，不再用 `file_record.owner_id` 作为权限校验用户；package 归属仍沿用现有 owner 语义（`get_or_create` 继续按源文件 owner 建包）。
- `content:get_file_content` lazy parse 改为传原始 caller；仅在拿到可消费且 blocks 非空的 ContentPackage 时返回 `success:true`。
- 对 skipped、parse_failed、not_parsed、非可消费 package、空 blocks 统一返回内层 `success:false` 和状态数据，避免 `/api/modules/call` 假成功。
- 补充回归测试覆盖 caller 越权、skipped fail-closed、pending package fail-closed、empty parsed package fail-closed，同时保留 degraded package 正常可读。

# 验证了什么
- ruff: `backend/app/services/content/pipeline_service.py`, `backend/app/routers/content.py`, `backend/tests/test_content_ir_architecture.py` 全部通过。
- pytest: `backend/tests/test_content_ir_architecture.py::TestContentFailureSemantics` 9 passed。
- probe: `/api/health` 返回 200 / status ok。
- call_capability: `content:get_file_content` 对不存在 file_id 经 `/api/modules/call` 返回 422 + `success:false`。
- `tail_log backend` 无新增输出。

# 残留风险
- 工作区存在并发/既有改动，包含 `backend/app/services/content/export_service.py` 和 modules 下文件；本任务未触碰这些文件，也未 commit/push。

# 关联 commit
- 未提交。
