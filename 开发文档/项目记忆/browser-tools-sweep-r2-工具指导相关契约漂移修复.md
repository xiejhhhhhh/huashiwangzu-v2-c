---
name: "browser-tools sweep r2：工具指导相关契约漂移修复"
type: "task"
tags: [browser-tools, module-sweep, tool-guidance, task_id:browser-tools-sweep-20260703-r2]
agent: "codex-browser-tools-sweep-20260703-r2"
created: "2026-07-03T06:55:43.350116+00:00"
---

# browser-tools sweep r2：工具指导相关契约漂移修复

Agent: codex-browser-tools-sweep-20260703-r2
日期: 2026-07-03

## 问题清单

1. `browser-tools._is_blocked_url` 直接透传框架 `validate_safe_url` 的 DNS 判定；当前网络下 `www.google.com` 解析出特殊 IPv6 `2001::1`，导致 agent `test_url_blocklist` 误拦公网 URL。
2. `_get_existing_session` 对测试/兼容场景中缺少 `caller` 字段的会话桩先返回 `session belongs to another caller`，遮蔽了后续 blocked final URL 校验；真实会话仍带 caller。
3. `_download` 在 `session_id` 存在且 `url` 为空时仍先校验空 URL，破坏“浏览器上下文下载或直链下载，二者至少一个”的契约。
4. `open` 的 manifest/handler 声明支持 `session_id`、`width`、`height`，但 HTTP schema 缺 `session_id`，handler 未应用视口尺寸。
5. manifest 与 handler 注册参数漂移：open 缺 width/height，click/type 缺 timeout，wait_for 缺 wait_for_navigation，download 未说明 session_id/url 二选一。
6. sandbox 测试仍验旧契约：screenshot/download 期望 `file_id/path`，click 双参数误判互斥，type 空文本误判非法，wait_for 固定等待/导航等待未覆盖。

## 改了什么

- `modules/browser-tools/backend/handlers/browser.py`
  - 在模块内实现 browser-tools 专用 URL 阻断：显式阻断 localhost、metadata、RFC1918、loopback、link-local、CGNAT、ULA 等内网目标；hostname 解析存在公网地址且无明确内网地址时允许，避免特殊 IPv6 导致公网域名误拦。
  - 缺 caller 的 legacy/test session 首次访问时补 caller，真实跨 caller 仍拒绝。
  - click/wait_for 在动作前检查当前 URL，防止在 blocked final URL 页面上继续交互。
  - download 仅在提供 url 时校验 url，session-only 路径先校验当前页面。
  - open 应用 width/height 到 Playwright viewport。
- `modules/browser-tools/backend/router.py`
  - `OpenRequest` 补 `session_id`。
- `modules/browser-tools/manifest.json`
  - 对齐 public_actions 参数和 background-service `component_key`。
- `modules/browser-tools/sandbox/test_module.py`
  - 更新为当前能力契约与输出形状，覆盖 direct download、navigation wait、fixed wait、empty type text 等。

## 验证

- `ruff`：`modules/browser-tools/backend/router.py`、`modules/browser-tools/backend/handlers/browser.py`、`modules/browser-tools/sandbox/test_module.py` 全通过。
- `PYTHONPATH=backend backend/.venv/bin/python modules/browser-tools/sandbox/test_module.py` 通过。
- `PYTHONPATH=backend backend/.venv/bin/python -m pytest modules/agent/backend/test_tool_guidance.py -q`：32 passed，原 6 个 browser-tools 失败消除。
- `git diff --check -- modules/browser-tools/...` 通过。
- `mcp capabilities(module="browser-tools")` 已读到新 manifest 参数。

## 残留风险

共享工作区开工前已有 backend/frontend/agent/knowledge/memory 等外部脏改动，未触碰未回退。常驻后端未重启时仍运行旧 browser-tools 代码；本次为避免打断并行 agent，未强杀重启活栈。关联 commit: 未提交。
