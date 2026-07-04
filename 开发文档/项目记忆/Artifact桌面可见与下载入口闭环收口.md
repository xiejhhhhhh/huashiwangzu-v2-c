# Artifact 桌面可见与下载入口闭环收口

## 任务

执行 `执行信-Artifact桌面可见与下载入口闭环.md`：ContentPackage 发布为 Artifact 后，用户不只看到后端记录，还能从桌面/文件入口看到、打开、下载发布产物。

## 改动

- `backend/app/services/content/export_service.py`
  - `publish()` 返回顶层 `artifact_id/file_id/download_url/open_url/desktop_visible/published_version_id/publish_status/published`。
  - nested `artifact` 同步带 `download_url/open_url/desktop_visible`。
  - 无 `target_file_id` 时创建 root 文件和 file-backed artifact；有 `target_file_id` 时替换目标文件并记录 artifact version。
- `backend/app/services/content/package_service.py`
  - 新增 `mark_published()`，把 `manifest.publish` 写回 package。
  - package response 派生 `publish_status/published_artifact_id/published_file_id/download_url/open_url/desktop_visible`。
- `backend/tests/test_content_artifact_publish.py`
  - 覆盖 no-target publish、write_ir 无源文件 publish、target publish、二次 target publish、package 发布状态机。
- `frontend/tests/content-artifact-desktop.spec.mjs`
  - 新增真实 Playwright 闭环：`content:write_ir -> content:publish -> /api/files/list -> 桌面 file icon 可见 -> 双击打开 -> 右键下载`。
  - 测试 finally 清理 artifact、content package、file/recycle item。

## 活栈证据

`frontend/tests/content-artifact-desktop.spec.mjs` 已真打常驻前后端：

1. 通过 `/api/modules/call` 调 `content:write_ir` 创建唯一标题 ContentPackage。
2. 通过 `/api/modules/call` 调 `content:publish`，断言返回：
   - `published === true`
   - `publish_status === "published_artifact/file"`
   - `artifact_id`
   - `file_id`
   - `download_url === /api/files/download/{file_id}`
   - `open_url === /api/files/preview/{file_id}`
   - `desktop_visible === true`
3. `GET /api/artifacts/{artifact_id}` 断言 artifact 绑定同一 `file_id`。
4. `GET /api/files/list?folder_id=0&page=1&page_size=200` 断言发布文件进入用户 root file list。
5. 进入 `/desktop`，等待 `.desktop-file-icon-item[data-selection-key="file:{file_id}"]` 可见。
6. 双击该桌面 icon，断言 window manager 中存在 `payload.fileId === file_id` 的窗口。
7. 右键该 icon 点击 `下载到本地`，断言 `/api/files/download/{file_id}` 返回 200。
8. finally 清理测试 artifact/package/file/recycle item。

测试后污染检查：

- `/api/files/search?keyword=Artifact%20Desktop&page=1&page_size=50` 返回 `items: []`。
- 子代理提到的残留 `file_id=921` 复查为 `File not found`。

## 验证

```bash
cd frontend && npm run build
```

结果：通过。

```bash
set -a; source backend/.env; set +a; backend/.venv/bin/python -m pytest backend/tests/test_content_artifact_publish.py
```

结果：`7 passed`。

```bash
cd backend && .venv/bin/python -m pytest tests/test_content_artifact_publish.py
```

结果：`7 passed`。

```bash
cd frontend && PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test tests/content-artifact-desktop.spec.mjs --project=admin --reporter=line
```

结果：`1 passed`。

```bash
rg -n "\bany\b|as any|@ts-ignore|@ts-expect-error" frontend/tests/content-artifact-desktop.spec.mjs frontend/src/desktop frontend/src/shared/components frontend/src/shared/api
```

结果：无命中。

```bash
git diff --check -- backend/app/routers/content.py backend/app/services/content/export_service.py backend/app/services/content/package_service.py backend/tests/test_content_artifact_publish.py frontend/tests/content-artifact-desktop.spec.mjs
```

结果：无空白错误。

项目工具台：

- `/api/health` 探针返回 `status: ok`。
- `tail_log` 未见新增错误。

2026-07-04 主会话最终复验：

- `cd frontend && npm run build` 通过。
- 仓库根直接执行 `backend/.venv/bin/python -m pytest backend/tests/test_content_artifact_publish.py` 会因当前 shell 未加载 `backend/.env` 失败在 `JWT_SECRET is empty`；加载后端环境后同一测试目标 `7 passed`。
- 后端测试不可并行跑同一真实库目标；一次并行复跑曾因全局 `File` 计数互扰出现 `+2`，顺序重跑后 `7 passed`。
- `cd frontend && PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test tests/content-artifact-desktop.spec.mjs --project=admin --reporter=line` 通过，`1 passed`。
- `/api/files/search?keyword=Artifact%20Desktop&page=1&page_size=50` 返回 `items: []`，未留下本轮 Playwright 测试文件。
- `/api/health` 返回 `status: ok`，`tail_log backend` 无新增错误。

2026-07-04 20:15 主会话复核：

- `cd frontend && npm run build` 通过。
- `set -a; source backend/.env; set +a; backend/.venv/bin/python -m pytest backend/tests/test_content_artifact_publish.py` 通过，`7 passed in 1.09s`。
- `cd frontend && PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test tests/content-artifact-desktop.spec.mjs --project=admin --reporter=line` 通过，`1 passed`。
- 类型压制扫描 `frontend/tests/content-artifact-desktop.spec.mjs frontend/src/desktop frontend/src/shared/components frontend/src/shared/api` 无命中。
- `git diff --check` 覆盖 Artifact 相关后端、前端测试和本收口文档，无空白错误。
- `/api/health` 返回 `status: ok`，任务队列 debt 为 clean。
- `/api/files/search?keyword=Artifact%20Desktop&page=1&page_size=50` 返回 `items: []`，Playwright 清理有效。
- 边界守卫按开工基线排除并行脏改后 `success: true`，`new_outside_allowed_count=0`，`new_forbidden_hit_count=0`。

## 边界说明

本任务允许范围内的 Artifact 产物：

- `backend/app/routers/content.py`
- `backend/app/services/content/export_service.py`
- `backend/app/services/content/package_service.py`
- `backend/tests/test_content_artifact_publish.py`
- `frontend/tests/content-artifact-desktop.spec.mjs`
- `开发文档/项目记忆/Artifact桌面可见与下载入口闭环收口.md`

收口时工作区还有并行任务脏改，包括 `dev_toolkit/release_gate.py`、`modules/agent/`、桌面视觉/窗口 snap、后端语义失败等文件。它们不是本任务产物，未在本轮接管或回退；边界守卫按基线排除后，本任务 `new_forbidden_hits=0`。

## 备注

本轮为了让活栈使用当前 `export_service.py/package_service.py`，按项目常驻夹具规则重启了 33000 后端；重启后 health 正常。
