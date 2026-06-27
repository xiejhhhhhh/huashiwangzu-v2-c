---
name: "dev_toolkit run_test tool fixed"
type: task
tags: ["dev-toolkit", "mcp", "run-test", "fix"]
created: 2026-06-27
agent: zcode
---

修复 dev_toolkit MCP `run_test` 工具：`dev_toolkit/server.py` 原注册分支调用 `_run_test`，但函数缺失；同一区域还丢了 `_sanity_check` 函数头，导致 lint 报 `_sanity_check` 未定义和悬空 `target/timeout`。已新增 `_run_test(target, timeout)`，复用 `_normalize_pytest_targets()` 与 `_run_command_json()`，并恢复 `_sanity_check()` 函数结构。验证：`dev_toolkit/server.py` ruff 全绿；用独立 Python 进程直接导入新版 `server.py` 调 `_run_test('backend/tests/test_agent_regression.py')` 成功，归一化为 `tests/test_agent_regression.py`，75 passed。注意：当前已启动的 MCP server 进程仍是旧代码，直接通过本会话 MCP 调 `run_test` 仍会报旧的 `name '_run_test' is not defined`，需要重启 MCP server/新会话后生效。
