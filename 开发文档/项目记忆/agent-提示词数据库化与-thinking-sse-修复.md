---
name: "Agent 提示词数据库化与 thinking/SSE 修复"
type: task
tags: ["agent", "prompt-db", "sse", "thinking", "performance", "verification"]
created: 2026-06-28
agent: zcode
---

本次在 Agent 模块内完成提示词数据库化与前端 thinking/SSE 修复：新增 agent prompt seeds、runtime prompt provider，扩展 agent_prompts 的 key/scope/is_read_only/version 字段，启动 seed 缺失提示词但不覆盖已编辑 content；运行时 context pipeline、compressor、subagent、understanding loop、tool loop final summary/stop decision 均改为从 DB prompt 读取。系统 prompt 通过 service 层强制只读，viewer 验证 PUT /api/agent/prompts/3 返回 403；用户 prompt 可创建/更新/删除且测试后清理。前端 index.vue 增加 SSE block buffer，避免 chunk 截断丢 JSON；MessageBubble 去掉 inline thinking 新路径，thinking 统一走 timeline/ThinkingCard；同时去掉 agent 前端 as any。慢感治理增加非流式决策、工具 batch、最终摘要耗时日志。验证：Python compileall 通过；pytest 29 passed（prompt_service/tool_gate/event_store/gateway protocol/retry）；frontend npm run build 通过；重启 backend 后 /api/agent/prompts 可见只读系统 seed。commit: 未提交。
