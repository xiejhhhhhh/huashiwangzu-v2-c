---
name: "Artifact 桌面可见与下载入口闭环最终验收"
type: "task"
tags: [artifact, content-package, desktop, playwright, dev-toolkit]
agent: "codex-artifact-desktop-entry-r1"
created: "2026-07-04T12:17:21.274471+00:00"
---

完成执行信《Artifact桌面可见与下载入口闭环》。主要产物：backend/app/services/content/export_service.py 在 publish 返回并嵌入 artifact_id、file_id、download_url、open_url、desktop_visible、published_version_id、publish_status、published；backend/app/services/content/package_service.py 通过 mark_published 写入 manifest.publish，并在 package response 派生 published_artifact_id、published_file_id、download_url、open_url、desktop_visible；backend/app/routers/content.py 的 content:publish 支持 conflict_policy；backend/tests/test_content_artifact_publish.py 覆盖 7 个发布契约测试；frontend/tests/content-artifact-desktop.spec.mjs 活栈验证 content:write_ir -> content:publish -> /api/files/list -> 桌面 icon 可见 -> 双击打开 -> 右键下载。

验证：cd frontend && npm run build 通过；set -a; source backend/.env; set +a; backend/.venv/bin/python -m pytest backend/tests/test_content_artifact_publish.py 通过，7 passed；cd frontend && PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test tests/content-artifact-desktop.spec.mjs --project=admin --reporter=line 通过，1 passed；类型压制扫描无命中；git diff --check 无空白错误；/api/health status ok；/api/files/search?keyword=Artifact%20Desktop 返回 items: []；worktree_guard 按 baseline 排除并行脏改后 success true，new_forbidden_hit_count=0。

风险/备注：仓库根裸跑 backend/.venv/bin/python -m pytest backend/tests/test_content_artifact_publish.py 若当前 shell 未加载 backend/.env，会因 JWT_SECRET is empty 在采集期失败；加载 backend/.env 或 cd backend 后通过。不要并行跑同一 live-DB 后端测试目标，避免共享 DB 计数互扰。工作区仍有 dev_toolkit、modules/agent、桌面视觉/window snap 等并行脏改，未接管、未回退。关联 commit：未提交。
