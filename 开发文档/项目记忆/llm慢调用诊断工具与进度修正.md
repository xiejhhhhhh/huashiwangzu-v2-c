---
name: "LLM慢调用诊断工具与进度修正"
type: task
tags: ["gateway", "diagnostics", "mcp", "knowledge", "performance"]
created: 2026-06-26
agent: opencode
---

审计确认：gateway diagnostics（trace_id/attempts/elapsed_ms/diagnostics field）、MCP工具（llm_probe/gateway_trace/task_trace/log_errors）、progress状态修正已在主分支完整实现。

实际改动：
- dev_toolkit/server.py: 修复_task_trace使用JSONB精确匹配 + 按表类型使用正确关联列名（kb_graph_nodes/edges需JOIN evidence, kb_file_relations需source/target_document_id）
- modules/knowledge/backend/services/pipeline_service.py: import排序修复

慢调用复现：8组测试矩阵覆盖plain/JSON/max_tokens对比
- 基准：小文本6字符，deepseek-v4-flash，opencode.ai
- 范围：3.8s ~ 48.7s，avg ~18s (plain) / ~7s (JSON)
- 全部attempts=1，gateway overhead <50ms，reasoning_chars=0
- 根因在opencode.ai服务端处理慢，非gateway层

遗留问题：上游provider慢需后续用低推理profile或换provider解决。
