---
name: "agent 模块 sweep r2：子 Agent 写保护与假成功修复"
type: "task"
tags: [agent, module-sweep, subagent, tool-discovery, boundary]
agent: "codex-agent-module-sweep-20260703-r2"
created: "2026-07-03T06:47:20.686748+00:00"
---

# 改了什么

- 扫描 agent 对话/runtime/tool loop/subagent/checkpoint/trajectory/profile/tool discovery/content IR/timeline 链路。
- 确认 checkpoint 空表是默认关闭、按请求启用，不作为本轮 bug；trajectory、events、messages、timeline 均已有落库链路。
- 修复 `modules/agent/backend/services/subagent_runner.py`：子 Agent 在 `write_enabled=False` 时不再把 `skill_use` 本身视为只读，而是检查其内部目标能力名；读类如 `knowledge__search` 仍可执行，写类如 `agent__update_my_profile` 会被拦截。
- 修复子 Agent 工具错误但无最终结论时仍返回 `completed` 的假成功：现在会返回 `status="error"` 并暴露真实错误。
- 增强 `modules/agent/backend/services/tool_discovery.py`：`agent_skill_usage` 遥测落库失败仍不影响主流程，但会 warning 记录，避免空表/断链完全不可观测。
- 补充 `modules/agent/backend/test_subagent_runner.py` 两个回归测试：写能力被拦截、读能力仍放行。

# 验证了什么

- `ruff check` 通过：`subagent_runner.py`、`tool_discovery.py`、`test_subagent_runner.py`。
- `run_test modules/agent/backend/test_subagent_runner.py`：4 passed。
- `run_test modules/agent/sandbox/test_module.py`：6 passed。
- `run_test backend/tests/test_agent_tool_loop_runtime.py`：5 passed。
- `run_test modules/agent/backend/test_action_policy_runtime_helpers.py`：4 passed。
- `finish_task` 合并测试目标：19 passed。
- 活系统：`GET /api/agent/health` 200 success；`agent:get_my_profile` success；`agent:render_tool_guidance` success；`GET /api/agent/tools` 仍只暴露 `skill_list/skill_describe/skill_use` 三个元工具。
- `modules/agent/backend/test_tool_guidance.py -k 'not browser and not url_blocklist'`：21 passed。

# 残留风险

- 完整 `modules/agent/backend/test_tool_guidance.py` 有 6 个 browser-tools 相关失败（URL blocklist/session owner/error 文案），涉及其他模块，按本任务边界未修。
- 工作区存在并行 agent 的 backend/frontend/knowledge/项目记忆改动，非本任务产生且未触碰；本任务代码改动仅 `modules/agent/**` 三个文件。

# 关联 commit

- 未提交。
