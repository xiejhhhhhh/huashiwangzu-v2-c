---
name: "模型调用底座统一化：统一契约 + provider adapter"
type: architecture
tags: ["gateway", "model", "contract", "adapter", "provider", "architecture"]
created: 2026-06-27
agent: opencode
---

模型调用底座已重构为"统一契约 + provider adapter"的工业化结构。

内部契约（contract.py）：
- ModelRequest: messages, system_prompt, tools, stream, temperature, top_p, max_tokens, response_format
- ModelResponse: content, thinking, tool_calls (list[ToolCall]), finish_reason, usage (Usage | None), error
- StreamEvent: type (StreamEventType 枚举), content, tool_calls, usage
- ToolCall: id, type, function
- Usage: prompt_tokens, completion_tokens, total_tokens

外部适配：
- 每个 adapter 把厂商原始响应翻译为 ModelResponse/StreamEvent
- DeepSeekAdapter 处理 reasoning_content → thinking
- 流式事件通过 StreamEventType 枚举约束，不再有 "done"/"error" 散落字符串
- 错误分类走 error_classifier → 统一重试策略 → compute_delay

usage/cost 中心化（usage_tracker.py）：
- log_usage() 统一写入 agent_usage_daily
- UsageRecord + log_usage_event() 结构化日志

向后兼容：service.py 公共 API 保持 dict 签名不变，agent 层零改动。
