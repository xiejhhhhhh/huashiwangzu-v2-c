---
name: "browser-tools network hardening r2 timeout and streaming download"
type: "task"
tags: [browser-tools, network-hardening, r2, timeout, download, ssrf]
agent: "codex-browser-tools-network-hardening-r2"
created: "2026-07-03T09:46:14.829878+00:00"
---

# 改了什么
- 在 `modules/browser-tools/backend/handlers/browser.py` 新增 `_bounded_timeout_seconds` / `_timeout_ms`，所有外部输入 timeout 统一转换并限制在 1-60 秒；非法、布尔、NaN/Inf 等值回退默认 30 秒。
- 将直链 HTTP 下载 `_download_http_checked` 从 `resp.content` 全量读入改成 `httpx` streaming 写临时文件，按 Content-Length 预检并逐 chunk 累计限制 50MB；超限/异常时删除部分文件。
- 保持 SSRF 防线：首次 URL 和每次 redirect 目标都会走 `_blocked_error` 校验，支持相对 Location 归一为绝对 URL 后再校验。
- 浏览器上下文下载路径在 `save_as` 后补 50MB 文件大小检查，超限删除并返回错误。
- 在 `modules/browser-tools/sandbox/test_module.py` 增加真实 handler 轻量加载和 fake httpx 覆盖 timeout clamp、stream 成功写入、超限清理、redirect SSRF fail-closed。

# 验证了什么
- `ruff check modules/browser-tools/backend/handlers/browser.py modules/browser-tools/sandbox/test_module.py` 通过。
- `pytest modules/browser-tools/sandbox/test_module.py` 16 passed。
- 活栈 `GET /api/browser-tools/health` 返回 200 / success true。
- 活栈 `browser-tools:download` 调用 `http://127.0.0.1/private` 返回 422，错误为 `URL targets a private/internal address`。
- `tail_log` 无新增错误输出；`git diff --check` 对本任务两个文件无 whitespace 问题。

# 残留风险
- Playwright 浏览器上下文 download 仍依赖 `save_as` 完成后再按文件大小删除超限文件；本次 P1 的直链 HTTP 全量入内存问题已改为 streaming。
- 当前工作区存在其他任务的脏文件，`finish_task` 边界检查因此整体返回 false；本任务实际改动文件仅 `modules/browser-tools/backend/handlers/browser.py` 和 `modules/browser-tools/sandbox/test_module.py`。未 commit/push。

# 关联 commit
- 无，本任务按要求不提交。
