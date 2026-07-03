---
name: "Agent 工具循环外部工具失败信号硬化 r2"
type: "task"
tags: [agent, tool-loop, network-tools, failure-semantics, r2]
agent: "codex-agent-tool-failure-hardening-r2"
created: "2026-07-03T09:49:12.270105+00:00"
---

Agent codex-agent-tool-failure-hardening-r2 completed the P1 hardening for modules/agent tool failure semantics on branch codex/sweep-quality-r2. No commit or push was made.

Changed files:
- modules/agent/backend/runtime/tool_loop_runtime.py
- modules/agent/backend/test_tool_loop_failure_normalization.py

What changed:
- Added tool-result normalization in ToolLoopRuntime before fast-tool results are emitted to SSE/timeline, persisted pending events, and appended to the next LLM tool message.
- Preserves structured failure signals for success:false, top-level error, nested data.success:false/data.error, timeout/status failed, and explicit error_class/error_type/code.
- Classifies failures through existing tool_guidance_service when possible, marks network_error/timeout/rate_limited/permission/path/browser/publish classes as hard failures, and treats external tool prefixes web-tools__/browser-tools__/github-search__ as hard unless the class is explicitly recoverable.
- Annotated failed tool outputs with success:false, error_class, failure_kind, hard_failure, effective_tool_name, tool_failure, and a model_instruction so the model does not treat failed network/external calls as normal successful tool output.

Verification:
- ruff check modules/agent/backend/runtime/tool_loop_runtime.py and modules/agent/backend/test_tool_loop_failure_normalization.py: passed.
- pytest modules/agent/backend/test_tool_loop_failure_normalization.py: 4 passed.
- pytest backend/tests/test_agent_tool_loop_runtime.py: 5 passed.
- pytest modules/agent/backend/test_repair09.py::test_check_tool_success: 1 passed.
- pytest modules/agent/sandbox/test_module.py: 6 passed.
- finish_task combined pytest target: 16 passed.
- probe GET /api/health as admin: 200 success:true, status ok, module_errors null.
- tail_log backend 80 lines: empty.

Risk / boundary:
- This task only modified modules/agent files. The worktree already contained unrelated dirty files in backend/app, backend/tests, modules/browser-tools, modules/scheduler, and project memory; they were not touched and caused finish_task boundary_check to report outside_allowed entries.
- No framework/backend app code, other modules, data/uploads, commit, or push was changed by this task.
