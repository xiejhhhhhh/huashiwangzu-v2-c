---
name: "ContentPackage 到 Artifact 发布闭环复验收口"
type: "task"
tags: [content, artifact, publish, backend, verification]
agent: "codex-content-artifact-publish-r1"
created: "2026-07-04T11:51:37.448667+00:00"
---

## 做了什么

接手并复验《ContentPackage 到 Artifact 发布闭环》实现。当前 `content:publish` 与 `POST /api/content/packages/{id}/publish` 已能把 ContentPackage 推进为用户可见、可下载、可追溯的 `framework_artifacts + framework_file_items`：返回 `package_id`、`artifact_id`、`file_id`、`download_url`、`published_version_id`、`status`、`publish_status`，并把 `manifest.publish` 写回 package response。

## 关键实现

- `backend/app/services/content/export_service.py`：publish 要求真实 owner，校验 source file 写权限；无 target 时编译并创建 file-backed artifact；有 target 时替换目标文件并追加 artifact version；统一返回发布契约。
- `backend/app/services/content/package_service.py`：`mark_published()` 写回 `manifest.publish`，`_package_to_dict()` 派生 `draft_package -> compiled_preview -> published_artifact/file` 状态字段。
- `backend/app/routers/content.py`：REST publish 和 `content:publish` capability 走同一 service，并透传 `conflict_policy`。
- `backend/app/schemas/content_package.py`：补发布状态字段和 `PublishResponse` 契约模型。

## 验证

- `/api/health`：ok，database ok，worker running，task_queue clean。
- `backend/.venv/bin/ruff check backend/app/routers/content.py backend/app/services/content`：通过。
- `backend/.venv/bin/python -m pytest backend/tests/test_content_ir_architecture.py backend/tests/test_content_artifact_publish.py`：加载 `backend/.env` 后合跑 60 passed；finish_task 也在 backend cwd 重跑 60 passed。
- 活栈链路：`content:write_ir` 生成 `package_id=674` / `version_id=594`；`content:publish` 生成 `artifact_id=108` / `file_id=863` / `published_version_id=191`；REST publish 到同一 target 后返回 `published_version_id=193` / `status=replaced`；package/detail/download 均可查，download 返回发布文本。
- 探针数据已清理：`package_id=674`、`artifact_id=108`、`file_id=863` 和物理 storage 均无残留。

## 风险

工作区存在大量并行任务既有脏改动，含 frontend、modules/agent、dev_toolkit、其他 backend 文件；本次未回退也未修改那些路径。本轮实际代码 diff 只在 content router/schema/service 允许范围。
