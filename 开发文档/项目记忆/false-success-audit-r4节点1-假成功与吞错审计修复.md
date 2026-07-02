---
name: "false-success-audit-r4节点1-假成功与吞错审计修复"
type: "task"
tags: [false-success-audit, api-envelope, terminal-tools, web-tools, module-call, access-control, 20260703]
agent: "false-success-audit-r4"
created: "2026-07-02T16:57:59.472634+00:00"
---

## 我是谁
false-success-audit-r4。

## 做了什么
专项审计 backend/app、modules/*/backend、dev_toolkit 的假成功/吞错误候选：裸 pass、except Exception 静默、内部失败但外层 success:true。

已修真 bug：
1. `/api/modules/call` 原先无条件 `ApiResponse(data=result)`，capability 明确返回 `{"success": false}` 时外层仍是 `success:true`。现在外层同步返回 `success:false` 并带 error。
2. `terminal-tools` 直连 HTTP 端点原先会把危险命令、越界路径等 handler 失败包成外层成功。新增 `_terminal_response()`，所有 terminal HTTP 端点统一保留内部 failure 状态。
3. `web-tools` fetch/search 错误原先只写 `data.error`，没有 `success:false`，直接 HTTP 与跨模块调用都会假绿。新增 `_ok/_err/_web_response()`，SSRF 拦截、空 query、超时、二进制/超大内容、解析失败等均显式 `success:false`。
4. `test_access_control_regressions.py` 的 image-vision 桩打错到 gateway_router.chat，导致上传自动内容管线真实调用云端 vision key；改为 patch `app.services.model_services.describe_image`，并把测试上传名加 uuid，避免历史 409 测试数据污染。

真 bug 未修/建议专项：
- 多个模块 HTTP 端点仍有 `ApiResponse(data=result)` 模式，但只有当 handler 采用 `success:false` 或错误放 `data.error` 时才是假绿。建议下一轮按 capability 输出契约逐模块收口，而不是机械替换。
- docx/pdf/pptx parser 对嵌入资源 `content:store_resource` 失败目前吞掉，只返回文本/资源缺省。这是合理降级和诊断缺口之间的灰区；建议加 `resource_storage_errors/resource_diagnostics`，不要让资源缺失无痕。

合理降级无需修：
- 临时文件 unlink、zip 临时产物清理、JSON 多策略解析、metrics/query_count、telemetry/tool_usage、浏览器 session close、树节点 drop 失败等均属于旁路或 best-effort，不应阻断主流程。

## 验证
- `cd backend && .venv/bin/python -m pytest tests/test_access_control_regressions.py -q` -> 15 passed。
- `cd backend && .venv/bin/python -m pytest tests/test_module_call_false_success.py tests/test_terminal_tools_security.py tests/test_web_tools_security.py -q` -> 14 passed。
- `cd backend && .venv/bin/python -m pytest ../modules/web-tools/sandbox/test_module.py -q` -> 8 passed。
- `cd backend && .venv/bin/python -m pytest ../modules/terminal-tools/sandbox/test_module.py -q` -> 4 passed。
- Focused ruff passed。
- `git diff --check` passed。

## 注意
`finish_task` 把两个 sandbox/test_module.py 合跑时触发 pytest import file mismatch；分开跑均通过，这是测试收集方式限制，不是业务失败。
