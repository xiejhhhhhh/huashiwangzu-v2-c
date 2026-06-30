---
name: "Agent上下文压缩升级10验收复核与小修"
type: task
tags: ["agent", "context-compaction", "review", "tool-result-reducer", "tests"]
created: 2026-06-30
agent: codex
---

复核 opencode Agent 上下文压缩升级 10。发现并直接修复两个小问题：1) tool_result_reducer 裁剪 tool_call arguments 后把 function.arguments 从 JSON 字符串变成 dict，违反 event_store._ensure_string_arguments/provider 历史格式要求，已改为 json.dumps 后保留字符串，并更新测试断言；2) reduce(max_json_chars/max_text_chars) 参数保留但未实际传递，已接入 semantic/fallback 裁剪路径。验证：正确路径 pytest 60 passed；ruff lint reducer/test/compressor/tasks 通过；直接断言 reducer 后 arguments 类型为 str 且可 json.loads。残留建议：下一轮可补递归裁剪 skill_use args 内层长字符串。
