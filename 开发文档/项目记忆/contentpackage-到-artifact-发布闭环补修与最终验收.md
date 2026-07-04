---
name: "ContentPackage 到 Artifact 发布闭环补修与最终验收"
type: "task"
tags: [content, artifact, publish, backend, verification]
agent: "codex-content-artifact-publish-r1"
created: "2026-07-04T11:42:42.917318+00:00"
---

# 改了什么
- 补修 `ContentExportService.export()`：当 `content:write_ir` 生成的 ContentPackage 没有 `source_file_id` 且没有 `source_extension` 时，publish 默认编译为 `txt`，不再回退到复制不存在的源文件导致 `No source file to copy`。
- 保留并验收 ContentPackage -> framework_file_items -> framework_artifacts 主链路：publish 返回 `package_id/artifact_id/file_id/download_url/published_version_id/status/publish_status`，package response 通过 `publish_status` 与 `manifest.publish` 表达 `draft_package -> compiled_preview -> published_artifact/file`。
- 在 `backend/tests/test_content_artifact_publish.py` 新增无源文件 generated package 可直接 publish 的回归测试。
- 更新 `开发文档/项目记忆/ContentPackage到Artifact发布闭环收口.md`，补充最终补修、活栈证据和清理结果。

# 验证了什么
- `backend/.venv/bin/ruff check backend/app/routers/content.py backend/app/services/content backend/app/schemas/content_package.py backend/tests/test_content_artifact_publish.py` 通过。
- `backend/.venv/bin/python -m pytest backend/tests/test_content_ir_architecture.py backend/tests/test_content_artifact_publish.py`：60 passed, 1 warning（github-search FastAPI on_event deprecation）。
- `/api/health`：status=ok，worker 运行正常。
- 能力链路：`content:write_ir` -> `content:publish` 生成 `artifact_id=87/file_id=818/published_version_id=156`，下载内容正确，随后清理。
- REST 链路：`POST /api/content/packages/627/publish` 生成 `artifact_id=88/file_id=819/published_version_id=157`，`GET /api/content/packages/627` 返回 `publish_status=published_artifact/file`，`/api/files/download/819` 返回发布文本，随后清理。
- 最终数据库计数恢复：`framework_artifacts=0`、`framework_file_items=11`，live verification 的 package/file/artifact 残留均为 0。

# 残留风险
- 工作区有大量既有并发脏改动，本轮未回退；边界守卫用 baseline 后无新增越界/forbidden 命中。
- 发布状态使用 `publish_status`/`manifest.publish`，未复用 `ContentPackage.status`，后者继续承载解析生命周期。
- `framework_file_assets` 未接入，本轮验收口径为 `framework_artifacts + framework_file_items + download_url`。
- REST 路由尚未声明精确 `response_model`；真实返回已验收，OpenAPI 契约可后续单独补。

# 关联 commit
- 未提交。
