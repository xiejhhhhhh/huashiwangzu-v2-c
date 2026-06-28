---
name: "DeepSeek tool_calls 协议适配底座与不可降级错误治理"
type: task
tags: ["gateway", "deepseek", "tool-calls", "protocol", "agent", "fallback"]
created: 2026-06-28
agent: zcode
---

# 改了什么

完成 DeepSeek/OpenAI-compatible tool_calls 协议适配底座，不再把非法历史请求发到云端后靠降级兜底。

- 新增 `backend/app/gateway/protocol.py`：
  - `normalize_openai_messages()`：发送前标准化并校验 OpenAI/DeepSeek messages。
  - 强制 assistant `tool_calls` 后必须紧跟每个 `tool_call_id` 对应的 `tool` 消息。
  - 归一化 tool_call arguments 为 JSON 字符串。
  - 检测 orphan tool message、重复 tool_result、缺失 tool_result。
  - `normalize_openai_tools()` 支持内部 shorthand tool schema 转 OpenAI function schema。
- `backend/app/gateway/openai_provider.py`：所有 OpenAI-compatible payload 在发送前经过协议适配层。
- `backend/app/gateway/error_classifier.py`：400/invalid_request_error/tool_call_id 等协议错误归类为 `protocol`，不可重试。
- `modules/agent/backend/engine/fallback_chain.py`：Agent 层 fallback 遇到协议错误立即停止，不再降级到其他模型。
- 之前配套修复：`event_store.project_to_messages()` 只在所有 tool_call_id 都有结果时才投影 tool_calls；否则降级为普通 assistant 文本，避免污染历史。

# 真实验证

用后端 provider 层真实访问 DeepSeek/OpenCode：

1. plain 文本请求：成功，返回 `ok`。
2. 标准完整多工具历史：assistant 一次 2 个 tool_calls，后面 2 个 tool results，DeepSeek 成功返回总结。
3. 缺失 1 个 tool_result：修复前 DeepSeek 返回 400 且网关重试 3 次；修复后本地协议预检直接拦截，`duration=0ms`，`error_category=protocol`，不再发到 DeepSeek，不再重试。

# 自动化验证

- `ruff check` 覆盖所有改动 Python 文件：通过。
- `pytest backend/tests/test_gateway_protocol.py backend/tests/test_gateway_retry.py ../modules/agent/backend/engine/test_event_store.py ../modules/agent/backend/test_content_gate.py`：32 passed。
- 后端重启成功。
- `/api/gateway/health`：200，opencode=true。
- `/api/agent/health`：200 success。

# 残留风险

这是框架模型网关底座改动，会影响所有 OpenAI-compatible 模型调用；已用真实 DeepSeek 探针和单测覆盖关键协议。工作区仍存在此前已有 `backend/data/agent/*`、`dev_toolkit/memory_embeddings.json`、开发文档记忆/索引等非本任务改动，未处理。
