---
name: "Agent 回复泄露与空回复底座化治理完成"
type: task
tags: ["agent", "content-gate", "tool-gate", "messagegate", "leak-fix", "validation"]
created: 2026-06-28
agent: zcode
---

完成 Agent 回复泄露/空回复底座化治理。分两次提交：
- 6e8f8af：Batch 1+2，前端 MessageGate + 后端 usage 绑定。前端新增统一 commitAssistantMessage，修复 clean 后空内容仍挂 usage、replace 空内容不清空、content 事件空推送；MessageBubble 空内容不显示 usage。后端 round_usage/references 移到 persist_assistant 成功后下发，失败发 assistant_empty。
- fecdee0：Batch 3+4+5，新增 ContentGate 与 ToolGate。ContentGate 统一 DSML/XML 清洗、inline tool_calls 提取、xml-only/empty/unfinished intent 分类；model_client 只保留兼容导出；stream_emitter/task_sink/tool_loop_runtime 改走 ContentGate。ToolGate 校验模型工具名是否在传入 tools 列表中，不合法则注入 retry message，不再让非法工具消耗执行轮次。新增 cleanup_dirty_messages.py 作为手动历史脏消息隐藏脚本（不自动执行）。
验证：ruff check 相关 Python 文件全绿；pytest `test_stream_emitter_guardrails.py test_content_gate.py test_tool_gate.py` 共 24 passed；frontend `npm run build` 通过（仅 chunk size warning）；后端已重启，/api/health 200 success true。
