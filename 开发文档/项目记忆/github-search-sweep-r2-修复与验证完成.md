---
name: "github-search sweep r2 修复与验证完成"
type: "task"
tags: [github-search, module-sweep, r2, validation, task_id:github-search-sweep-20260703-r2]
agent: "codex-github-search-sweep-20260703-r2"
created: "2026-07-03T07:17:32.576148+00:00"
---

agent=codex-github-search-sweep-20260703-r2 完成 modules/github-search r2 扫雷。改动仅在 modules/github-search/**：1) github_client.py 将 gh CLI 失败从 None/空列表改为 GitHubClientError，区分 rate limit/auth/query invalid/timeout/CLI missing/JSON invalid；成功结果写入 runtime 目录下的 TTL 磁盘缓存，并保留内存缓存。2) router.py 增加参数校验、持久化本地滑窗限流、GitHubClientError 到框架 AppException/RateLimitError/ValidationError 的映射；真实空结果返回 total=0,error=None，避免 success:true + data.error 假成功。README/框架未改。3) manifest.json 移除 search 里后端不支持的 search_code 参数。4) sandbox/test_module.py 重写为离线 pytest/脚本双入口测试，使用 TemporaryDirectory 和 stubbed gh，不留测试数据，覆盖 manifest 契约、参数范围、缓存、失败/空结果区分、router 错误语义。验证：ruff check router/client/sandbox 全通过；run_test modules/github-search/sandbox/test_module.py 7 passed（仅 FastAPI on_event 既有 deprecation warning）；backend/.venv/bin/python modules/github-search/sandbox/test_module.py 通过；/api/github-search/health probe 200；live call_capability github-search:search 与 search_code 均返回真实 GitHub 结果，说明网络和 gh CLI 可用。注意：常驻后端未为本次模块编辑重启，live invalid-param 探针仍反映旧代码（空 query 返回 data.error），新错误语义由 sandbox 导入新 router 覆盖；后端重启后活栈才会体现新语义。finish_task 因全仓存在其他 worker 的 data/uploads 和其他模块脏改动返回 success:false；本 worker 产品 diff 经 git diff --name-only -- modules/github-search 确认为 4 个 github-search 文件。关联 commit：未提交。
