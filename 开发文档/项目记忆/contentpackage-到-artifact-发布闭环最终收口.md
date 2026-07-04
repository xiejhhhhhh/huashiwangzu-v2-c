---
name: "ContentPackage 到 Artifact 发布闭环最终收口"
type: "task"
tags: [content, artifact, file, publish, backend, verification]
agent: "codex-content-artifact-publish-r1"
created: "2026-07-04T12:02:38.206438+00:00"
---

# 改了什么

执行 `执行信-ContentPackage到Artifact发布闭环.md`，确认并补强 ContentPackage publish 闭环：`content:publish` 与 `/api/content/packages/{id}/publish` 能创建或更新用户可见、可下载、可追溯的 `framework_artifacts + framework_file_items`，返回 `package_id/artifact_id/file_id/download_url/open_url/published_version_id/status/publish_status/desktop_visible`。

本轮在既有未提交实现基础上补强了 `backend/tests/test_content_artifact_publish.py`，新增 capability envelope 与 REST handler envelope 自动化覆盖；收口文档已更新到 `开发文档/项目记忆/ContentPackage到Artifact发布闭环收口.md`。

# 验证了什么

- `backend/.venv/bin/ruff check backend/app/routers/content.py backend/app/services/content` 通过。
- `backend/.venv/bin/python -m pytest backend/tests/test_content_ir_architecture.py`：55 passed，1 个既有 FastAPI `on_event` deprecation warning。
- `backend/.venv/bin/python -m pytest backend/tests/test_content_artifact_publish.py`：7 passed。
- `finish_task` 合跑 `tests/test_content_ir_architecture.py tests/test_content_artifact_publish.py`：62 passed。
- `/api/health`：status ok、database ok、worker running、task_queue clean。
- 后端 33000 已重启到当前源码。
- 活栈验证：`content:write_ir` 生成 `package_id=761`；`content:publish` 生成 `artifact_id=142/file_id=933/published_version_id=252`；REST publish 到同一 target 返回 `published_version_id=266/status=replaced`；包详情返回 `publish_status=published_artifact/file`；文件详情可查，下载返回发布文本。
- 探针 `package_id=749/761`、`artifact_id=130/142`、`file_id=921/933` 与物理 storage 均已清理，残留为 0。

# 残留风险

工作区存在大量并发/既有脏改动，含 frontend、modules/agent、dev_toolkit 和其他后端任务文件；本轮未回退，边界检查以允许路径和基线区分。本轮收口涉及的产品代码边界为 content router/service/schema 与 content artifact publish 测试。

# 关联 commit

未提交。
