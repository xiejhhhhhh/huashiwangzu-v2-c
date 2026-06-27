---
name: "项目工具台 MCP 开发体验优化"
type: task
tags: ["dev-toolkit", "mcp", "run_test", "lint", "finish_task", "agent-efficiency"]
created: 2026-06-27
agent: zcode
---

优化项目工具台 MCP 开发体验：1) run_test 自动兼容 backend/tests、tests、绝对路径，并返回结构化 JSON（command/cwd/returncode/duration/output_tail）；2) lint 支持 diff=true 预览 ruff --diff，返回结构化 JSON；3) brief 增加 Git 工作区摘要，提醒当前分支、dirty 数量、main/master 风险；4) 修复 _snap_diff 缩进 bug，并改为 git status --short 包含未跟踪文件；5) 新增 finish_task 收工辅助，汇总 dirty、可选 lint/test、生成 memory_write 模板，不提交不写记忆；6) 去掉 _ensure_token 重复 resp.json。补 dev_toolkit/test_server_helpers.py，backend venv 无 mcp SDK 时 skip。验证：ruff check dev_toolkit/server.py dev_toolkit/test_server_helpers.py dev_toolkit/test_quick_fix.py 通过；pytest dev_toolkit/test_quick_fix.py dev_toolkit/test_server_helpers.py -> 4 passed, 1 skipped；python3.14 直接调用 _run_test('backend/tests/test_agent_inline_tool_calls.py') 成功归一为 tests/test_agent_inline_tool_calls.py 并通过。
