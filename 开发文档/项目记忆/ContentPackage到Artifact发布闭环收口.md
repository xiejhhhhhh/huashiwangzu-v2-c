# ContentPackage 到 Artifact 发布闭环收口

## 结果

- ContentPackage publish 已从后台结构化包推进到用户可见/可下载/可追溯的 artifact/file。
- `content:publish` 与 `/api/content/packages/{id}/publish` 返回统一发布契约：
  - `package_id`
  - `artifact_id`
  - `file_id`
  - `download_url`
  - `published_version_id`
  - `status`
  - `publish_status`
- ContentPackage response 增加发布状态派生字段：
  - `publish_status`
  - `published_artifact_id`
  - `published_file_id`
  - `published_version_id`
  - `download_url`
- 状态机口径：
  - 无版本：`draft_package`
  - 有 package version 但未发布：`compiled_preview`
  - 已发布 artifact/file：`published_artifact/file`

## 改动

- `backend/app/services/content/export_service.py`
  - publish 要求真实 authenticated owner。
  - publish 前校验 package owner，避免共享编辑者产生跨 owner 的不可达 artifact/file 引用。
  - publish 前校验 source file 写权限。
  - 无 `source_file_id` 且无 `source_extension` 的 `content:write_ir` 生成包，publish 默认编译为 `txt`，不再错误回退到复制不存在的源文件。
  - no-target publish 创建 file-backed artifact。
  - target publish 替换目标 file，并记录 artifact version。
  - publish 返回顶层 artifact/file/version/download 字段。
- `backend/app/services/content/package_service.py`
  - 新增 `mark_published()`，把发布元数据写回 `manifest.publish`。
  - `_package_to_dict()` 派生发布状态字段。
- `backend/app/routers/content.py`
  - `content:publish` capability 透传 `conflict_policy`。
  - capability 参数声明补 `conflict_policy`。
- `backend/app/schemas/content_package.py`
  - `PackageSummary` 补发布状态字段。
  - 新增 `PublishResponse` 契约模型。
- `backend/tests/test_content_artifact_publish.py`
  - 覆盖 no-target publish 创建 file-backed artifact。
  - 覆盖 `content:write_ir` 生成的无源文件 package 可直接 publish 为 artifact/file。
  - 覆盖 `content:publish` capability envelope 返回 artifact/file/download/version/status 契约。
  - 覆盖 `/api/content/packages/{id}/publish` REST handler 的 `ApiResponse.data` 契约。
  - 覆盖 target publish 的 artifact version / operation / file 替换。
  - 覆盖同一 target 二次 publish 复用 artifact 并追加版本。
  - 覆盖 package response 状态机：`draft_package -> compiled_preview -> published_artifact/file`。

## 验证

- `backend/.venv/bin/ruff check backend/app/routers/content.py backend/app/services/content backend/app/schemas/content_package.py backend/tests/test_content_artifact_publish.py`
  - 通过。
- `backend/.venv/bin/python -m pytest backend/tests/test_content_ir_architecture.py`
  - 55 passed。
- `backend/.venv/bin/python -m pytest backend/tests/test_content_artifact_publish.py`
  - 5 passed。
- 活栈验证：
  - 创建测试文件 `file_id=687`。
  - `content:write_ir` 生成 `package_id=467` / `version_id=405`。
  - `content:publish` 生成 `artifact_id=40` / `file_id=687` / `published_version_id=73` / `download_url=/api/files/download/687`。
  - `framework_artifacts` active 计数从 0 增到 1。
  - `/api/files/download/687` 返回发布后的文本内容。
  - 测试 artifact/package/file/recycle 数据已清理，相关残留计数为 0。
- 续跑完成审计活栈验证：
  - `content:write_ir` 生成 `package_id=512` / `version_id=446`。
  - `content:publish` 生成 `artifact_id=53` / `file_id=724` / `published_version_id=97` / `download_url=/api/files/download/724`。
  - `/api/content/packages/512` 返回 `publish_status=published_artifact/file` 与 published id 字段。
  - `/api/files/download/724` 返回发布后的文本内容。
  - 探针 artifact/package/file/recycle 数据已清理，相关残留计数为 0。
- 最终补修验收：
  - 复现并修复 `content:write_ir` 生成包无 `source_extension/source_file_id` 时 `content:publish` 报 `No source file to copy`。
  - 能力链路：`content:write_ir` 生成 `package_id=535` / `version_id=467`；`content:publish` 生成 `artifact_id=87` / `file_id=818` / `published_version_id=156` / `download_url=/api/files/download/818`；下载返回发布文本；artifact/file 计数从 `0/11` 到 `1/12`。
  - REST 链路：`content:write_ir` 生成 `package_id=627` / `version_id=551`；`POST /api/content/packages/627/publish` 生成 `artifact_id=88` / `file_id=819` / `published_version_id=157` / `download_url=/api/files/download/819`；`GET /api/content/packages/627` 返回 `publish_status=published_artifact/file` 与 published id 字段；下载返回发布文本。
  - 两轮活栈探针均已清理，最终 `framework_artifacts=0`、`framework_file_items=11`，`package_id=535/627`、`artifact_id=87/88`、`file_id=818/819` 残留均为 0。
  - `/api/health` 返回 `status=ok`，worker 运行正常。
- 本轮主会话复验：
  - `backend/.venv/bin/ruff check backend/app/routers/content.py backend/app/services/content` 通过。
  - 从仓库根加载 `backend/.env` 后跑 `backend/.venv/bin/python -m pytest backend/tests/test_content_ir_architecture.py`，55 passed。
  - 从仓库根加载 `backend/.env` 后跑 `backend/.venv/bin/python -m pytest backend/tests/test_content_artifact_publish.py`，7 passed。
  - 按项目 README 的后端工作目录口径单跑：`tests/test_content_ir_architecture.py` 55 passed；`tests/test_content_artifact_publish.py` 5 passed。
  - `/api/health` 返回 `status=ok`、`database=ok`、worker running、task_queue clean。
  - 活栈能力链路：`content:write_ir` 生成 `package_id=674` / `version_id=594`；`content:publish` 返回 `artifact_id=108` / `file_id=863` / `published_version_id=191` / `download_url=/api/files/download/863` / `status=published` / `publish_status=published_artifact/file`。
  - 活栈 REST 链路：`POST /api/content/packages/674/publish` 发布到 `target_file_id=863`，返回同一 `artifact_id=108`、新 `published_version_id=193`、`status=replaced`；`GET /api/content/packages/674` 返回 `published_artifact_id=108`、`published_file_id=863`、`publish_status=published_artifact/file`；`GET /api/files/detail/863` 可查到可见文件；`GET /api/files/download/863` 返回发布文本。
  - 本轮探针已清理，`package_id=674`、`artifact_id=108`、`file_id=863` 和对应物理 storage 均确认无残留。
- 本轮最终收口复验：
  - 只读审计确认主体已实现，补强建议为 capability/REST envelope 自动化测试；已补入 `backend/tests/test_content_artifact_publish.py`。
  - 后端 33000 已重启到当前源码，`/api/health` 返回 `status=ok`、`database=ok`、worker running、task_queue clean。
  - 重启后活栈能力链路：`content:write_ir` 生成 `package_id=761` / `version_id=675`；`content:publish` 返回 `artifact_id=142` / `file_id=933` / `published_version_id=252` / `download_url=/api/files/download/933` / `open_url=/api/files/preview/933` / `desktop_visible=true` / `status=published` / `publish_status=published_artifact/file`。
  - 重启后活栈 REST 链路：`POST /api/content/packages/761/publish` 发布到 `target_file_id=933`，返回同一 `artifact_id=142`、新 `published_version_id=266`、`status=replaced`，且 response 与 nested artifact 均含 `download_url/open_url/desktop_visible`。
  - `GET /api/content/packages/761` 返回 `publish_status=published_artifact/file`、`published_artifact_id=142`、`published_file_id=933`、`published_version_id=266`、`download_url/open_url/desktop_visible`。
  - `GET /api/files/detail/933` 可查到可见文件；`GET /api/files/download/933` 返回发布文本。
  - 本轮探针已清理，`package_id=761`、`artifact_id=142`、`file_id=933` 与物理 storage 均确认残留为 0。
  - 最终命令验收：
    - `backend/.venv/bin/ruff check backend/app/routers/content.py backend/app/services/content`：通过。
    - `set -a; source backend/.env; set +a; backend/.venv/bin/python -m pytest backend/tests/test_content_ir_architecture.py`：55 passed，1 个既有 FastAPI `on_event` deprecation warning。
    - `set -a; source backend/.env; set +a; backend/.venv/bin/python -m pytest backend/tests/test_content_artifact_publish.py`：7 passed。

## 注意

- 本次活栈为了最小验证，把同一个 `file_id` 同时作为 source 和 target；底层 `replace_file_content` 会把该 source 对应 ContentPackage 的解析状态标记为 `stale`。发布态不依赖 parse `status` 字段，使用新增 `publish_status=published_artifact/file` 表达。
- 当前工作区存在其他并发任务留下的脏改动，包含 frontend、modules/agent、dev_toolkit 和若干 backend 任务队列文件；本次实现未回退这些改动。
- 发布状态作为 `publish_status`/`manifest.publish` 与 response 字段表达，未复用 `ContentPackage.status`；后者继续承载解析生命周期（`pending/parsed/failed/stale`）。
- 本轮未接入 `framework_file_assets`，用户可见/可下载/可追溯以 `framework_artifacts + framework_file_items + download_url` 为验收口径。
