---
name: "ContentPackage 到 Artifact 发布闭环收口"
type: "task"
tags: [content-package, artifact, publish, file, backend, live-stack]
agent: "codex-content-artifact-publish-r1"
created: "2026-07-04T11:19:49.489359+00:00"
---

## 改了什么

- ContentPackage publish 现在返回稳定 artifact/file 契约：`package_id`、`artifact_id`、`file_id`、`download_url`、`published_version_id`、`status`、`publish_status`。
- Package response 派生发布状态：无版本为 `draft_package`，有版本未发布为 `compiled_preview`，已发布为 `published_artifact/file`，并返回 published artifact/file/version/download 字段。
- `content:publish` capability 透传 `conflict_policy`。
- publish 收紧为 package owner 才能执行，避免共享编辑者产生跨 owner 的不可达 artifact/file 引用。
- 新增 `backend/tests/test_content_artifact_publish.py` 覆盖 no-target publish、target publish、二次 publish 版本追加、package response 状态机。

## 验证了什么

- `backend/.venv/bin/ruff check backend/app/routers/content.py backend/app/services/content backend/app/schemas/content_package.py backend/tests/test_content_artifact_publish.py` 通过。
- `backend/.venv/bin/python -m pytest backend/tests/test_content_ir_architecture.py`：55 passed。
- `backend/.venv/bin/python -m pytest backend/tests/test_content_artifact_publish.py`：4 passed。
- finish_task 合跑两组测试：59 passed。
- 活栈验证：`content:write_ir -> content:publish -> /api/files/download/{file_id}` 通过，最终探针 `package_id=467`、`artifact_id=40`、`file_id=687`、`published_version_id=73`，下载返回发布内容；测试 artifact/package/file/recycle 数据均清理为 0。

## 风险与边界

- publish owner-only 是明确安全取舍，后续如果要支持 shared editor 发布，需要先设计 artifact/file 归属和 package manifest 引用规则。
- 当前工作区存在其他并发任务的脏改动（frontend、modules/agent、dev_toolkit、任务队列相关后端文件等），本任务未回退也未纳入交付。
