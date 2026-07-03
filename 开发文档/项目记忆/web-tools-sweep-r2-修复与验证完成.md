---
name: "web-tools sweep r2 修复与验证完成"
type: "task"
tags: [web-tools, module-sweep, r2, security, ssrf, truncation, validation, task_id:web-tools-sweep-20260703-r2]
agent: "codex-web-tools-sweep-20260703-r2"
created: "2026-07-03T07:14:55.306909+00:00"
---

完成 modules/web-tools r2 扫雷。改动仅限 modules/web-tools/README.md、modules/web-tools/backend/router.py、modules/web-tools/sandbox/test_module.py（另有本 worker 项目记忆）。修复点：1) fetch 改为 GET 流式读取并在真实下载过程中硬限制 5MB，不再只信 HEAD Content-Length；2) redirect 每跳继续走 validate_safe_url，GET 响应也复核 binary content-type；3) direct HTTP endpoint 对内部 success:false 改抛框架 ValidationError，避免 200 假失败；4) top_k/max_chars 越界由静默 clamp 改为拒绝，补 query/url 长度上限；5) search 结果过滤非 http(s)/带凭据 URL，并截断 title/url/snippet；6) sandbox 测试从旧 link/content/char_count 契约改为实际 url/title/text/truncated/error，并覆盖越界拒绝和截断标志。验证：ruff modules/web-tools/backend/router.py 与 sandbox/test_module.py 全绿；run_test modules/web-tools/sandbox/test_module.py 9 passed；重载后端后 /api/health ok；call_capability fetch 127.0.0.1 返回 422 SSRF；probe /api/web-tools/search top_k=21 返回 422；call_capability search top_k=1 成功返回 1 条；fetch https://example.com 成功返回 title/text；fetch max_chars=20 返回 truncated=true；fetch max_chars=8001 返回 422。风险：全仓 worktree 仍有其它 worker 和 data/uploads 改动，finish_task 因 outside_allowed 返回 false；本 worker 未触碰 browser-tools、terminal-tools、backend/app、frontend/src 或其它 modules，未创建需清理测试数据。
