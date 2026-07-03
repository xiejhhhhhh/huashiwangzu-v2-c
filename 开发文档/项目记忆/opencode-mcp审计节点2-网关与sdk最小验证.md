---
name: "opencode MCP审计节点2-网关与SDK最小验证"
type: "task"
tags: [opencode, mcp, audit, r2, sdk, gateway, dirty-worktree]
agent: "codex-opencode-mcp-audit-20260703-r2"
created: "2026-07-03T07:18:18.925791+00:00"
---

节点2验证记录：opencode_gateway_status 成功，url=http://127.0.0.1:55891，pid=5166，opencode_version=1.17.13，listening=true。风险：日志提示 OPENCODE_SERVER_PASSWORD is not set; server is unsecured；log_tail 暴露 JSON-RPC/turn metadata 片段。opencode_sdk_smoke 成功，session=ses_0d9292e52ffe3TJUyC0b70JwqQ，model=deepseek-v4-flash，assistant text=OPENCODE_SDK_SMOKE_OK，cost=0.0032613，tokens.total=23261。opencode_sdk_prompt 第一次传自定义 agent=codex-opencode-mcp-audit-20260703-r2 失败：UnknownError ref=err_e355308f；默认 agent 重试成功，返回关于 dirty worktree patch attribution risk 的一句话，cost=0.0032711，tokens.total=23303。默认 prompt 的 assistant parts 含 patch part，指向 /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/modules/desktop-tools/sandbox/test_module.py，即使 prompt 明确要求只读；该文件本来已在脏工作区内，说明 SDK 会把当前工作区 patch/snapshot 纳入会话，脏工作区归因风险高。
