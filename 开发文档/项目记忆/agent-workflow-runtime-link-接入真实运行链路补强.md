---
name: "Agent workflow runtime link 接入真实运行链路补强"
type: "task"
tags: [agent, workflow, runtime, approval, checkpoint, verification]
agent: "codex-agent-workflow-runtime-link"
created: "2026-07-03T20:37:48.847183+00:00"
---

# 改了什么
在 modules/agent 内补强 Agent workflow 真实运行链路：等待审批时 runtime completion 不再写 tool_execution pass 或把 paused step 盖成 completed；skill_use 包装的 agent__spawn_subagent 结果按 effective_tool_name 归集为 subagent step/artifact/failure；慢工具后台队列参数携带 workflow_run_id/workflow_step_id/tool_call_id/idempotency_key，后台完成/失败会回写 tool_call、artifact、verification、failure 并 finalize；模型调用返回 error 但未抛异常时会写 runtime failure + fail verification，而不是 no_side_effect pass。

# 验证了什么
ruff check 通过：workflow_link.py、tool_loop_runtime.py、handlers/tasks.py、test_workflow_runtime_link.py。合跑指定测试 46 passed：test_workflow_runtime_link.py 10、test_workflow_service.py 10、test_workflow_api.py 6、modules/agent/sandbox/test_module.py 20。capability_contract_diff(agent, include_parameters=true) 0 drift。活系统 capability 验证 create_workflow、record_workflow_step、record_tool_call、request/resolve approval、record_verification、finalize completed/partial 均通过；探针 run 6/7/8 及关联记录已清理，SQL 确认剩余 0。

# 残留风险
开工前工作区已有大量外部 dirty（backend/app、frontend/src、dev_toolkit、modules/knowledge 等）和 modules/agent 一阶段既有改动，finish_task 边界因此失败；本轮未回滚这些改动。审批 approved 后当前主要恢复 ledger 状态并返回 resume_target，完整自动 replay 原 provider tool call 仍依赖后续恢复入口/前端触发链路。

# 关联 commit
未提交。
