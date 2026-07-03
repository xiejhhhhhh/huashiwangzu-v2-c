---
name: "OpenCode 官方 SDK 主控制通路接入"
type: "task"
tags: [opencode, sdk, dev-toolkit, dispatch, tracking]
agent: "codex"
created: "2026-07-03T04:07:40.448731+00:00"
---

# 改了什么

把 OpenCode 控制方向从 PTY/CLI 黑盒派发调整为官方 `@opencode-ai/sdk` 主通路。新增 `dev_toolkit/opencode_sdk_client.mjs`，使用 `createOpencodeClient` 连接固定 headless server `127.0.0.1:55891`，支持创建/复用 session、发送 prompt、读取 messages、派发投递箱任务信，并返回 session/message/tokens/cost/parts 等可跟踪信息。

`dev_toolkit/opencode_tools.py` 新增 MCP 工具：`opencode_sdk_smoke`、`opencode_sdk_prompt`、`opencode_sdk_dispatch_letter`、`opencode_sdk_messages`。首次调用若 `.opencode` 下没有官方 SDK，会自动执行 `npm install @opencode-ai/sdk@1.17.13 --prefix .opencode`。SDK helper 支持可选 Basic Auth（显式 username/password 或环境变量 `OPENCODE_SERVER_USERNAME/PASSWORD`）。旧 `opencode_dispatch_letter` 和 `opencode_pty_*` 保留为兜底/人工接管。

# 验证了什么

- SDK 原生调用真实跑通：`session.create -> session.prompt -> session.messages`，返回 `OK`。
- Node helper 真实跑通：返回 `SDK_OK`。
- Python 封装真实跑通：返回 `PY_SDK_OK`、`AUTO_SDK_OK`、`FINAL_SDK_OK`。
- `sdk_messages` 按 session_id 追踪返回最终文本 `FINAL_SDK_OK`。
- `python3.14 -m pytest dev_toolkit/test_opencode_tools.py`：6 passed。
- `backend/.venv/bin/ruff check dev_toolkit/opencode_tools.py dev_toolkit/test_opencode_tools.py`：通过。
- `node --check dev_toolkit/opencode_sdk_client.mjs`：通过。

# 残留风险

当前 MCP 进程需要重启后才会暴露新增 `opencode_sdk_*` 工具；`.opencode/` 被 gitignore，依赖不会提交，但工具已做缺包自动安装。
