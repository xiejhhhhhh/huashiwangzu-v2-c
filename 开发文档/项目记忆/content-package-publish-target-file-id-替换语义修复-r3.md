---
name: "Content Package publish target_file_id 替换语义修复 r3"
type: "task"
tags: [content, publish, target_file_id, artifact, verification]
agent: "content-publish-target-fix-r3"
created: "2026-07-03T10:13:34.774443+00:00"
---

# 做了什么
- 修复 `ContentExportService.publish()` 接收 `target_file_id` 后静默忽略的问题。
- 有 `target_file_id` 时先用框架 `check_file_write_access` 预检目标文件写权限；编译 ContentPackage 为 bytes 后，通过 `artifact_service.create_artifact` 建立 artifact 记录并调用 `replace_artifact_content` 写入目标文件。
- 无 `target_file_id` 时保留原 `export -> create_artifact` 新建发布文件行为。
- 未修改 `artifact_service.py`、content router 或其他模块。

# 权限与 owner 边界
- 目标文件不存在或当前用户无写权限会在发布前明确失败，不再静默新建文件。
- 最终写盘仍由 `replace_file_content -> check_file_write_access` 再次守住 owner/edit-share 边界。

# 验证
- `ruff check backend/app/services/content/export_service.py backend/tests/test_content_ir_architecture.py` 通过。
- `pytest tests/test_content_ir_architecture.py::TestContentPublishTarget` 3 passed。
- `pytest tests/test_content_ir_architecture.py` 51 passed。
- `/api/health` probe 返回 200 success。

# 边界说明
- 本任务实际代码 diff 只有 `backend/app/services/content/export_service.py` 和 `backend/tests/test_content_ir_architecture.py`。
- 收尾时工作区存在并行 agent/运行态的范围外 dirty（如 backend-upload-temp-cleanup-r3、modules/knowledge、backend/data），未回退、未接管。

# commit
- 未 commit / 未 push。
