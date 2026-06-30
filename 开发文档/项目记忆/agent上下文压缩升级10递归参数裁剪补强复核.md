---
name: "Agent上下文压缩升级10递归参数裁剪补强复核"
type: task
tags: ["agent", "context-compaction", "recursive-args", "review", "tests"]
created: 2026-06-30
agent: codex
---

复核 opencode 对 Agent 上下文压缩升级 10 的递归参数裁剪补强。确认实现支持 dict/list/str 递归裁剪，深度上限 4，长字符串 500 字符、数组前 5 项，短 JSON 字符串保持原格式，dict 参数输出合法 JSON 字符串。验证：pytest 指定三文件 65 passed；ruff lint reducer 与测试通过；直接样本 skill_use 内层 query 3600→511、items 20→6、arguments 类型 str、tool_args_truncated=2。未发现需打回问题。
