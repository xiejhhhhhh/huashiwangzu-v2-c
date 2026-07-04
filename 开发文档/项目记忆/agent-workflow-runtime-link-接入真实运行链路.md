---
name: "Agent workflow runtime link 接入真实运行链路"
type: "task"
tags: [agent, workflow, runtime-link, approval, checkpoint, verification]
agent: "codex-agent-workflow-runtime-link"
created: "2026-07-03T20:32:18.294630+00:00"
---

# 改了什么
在 modules/agent 内完成 Agent workflow 二阶段运行时接入：新增 runtime/workflow_link.py 作为对话/工具循环到 workflow_service 的薄桥接；ConversationRuntime 在真实 /api/agent/chat 和 edit-resubmit 流里携带 workflow context；ToolLoopRuntime 在真实工具解析、无效工具、慢工具、快工具结果、异常、最终持久化处记录 agent_tool_calls、failure、verification、artifact；action_policy 在带 workflow 上下文时通过 workflow_service.request_approval 写 payload_hash/resume_target，避免审批后动作漂移；PostgresCheckpointSaver 持久化 workflow_run_id/workflow_step_id/agent_run_id/checkpoint_type/resume_cursor；子 Agent 结果由工具结果分支记录为 subagent step/artifact/failure。

# 验证了什么
ruff check 通过：workflow_link.py、task_sink.py、checkpointer.py、conversation_runtime.py、tool_loop_runtime.py、action_policy.py、test_workflow_runtime_link.py。pytest 合跑 45 passed：test_workflow_runtime_link.py、test_workflow_service.py、test_workflow_api.py、modules/agent/sandbox/test_module.py。capability_contract_diff(agent, include_parameters=true) 0 drift。/api/health 200 且 backend tail 无新增错误。活系统 capability probe 覆盖 create_workflow、record_workflow_step、record_tool_call、request_workflow_approval、record_verification、resolve_workflow_approval、finalize_workflow，确认 arguments_hash/idempotency_key/payload_hash/resume_target/partial with debt 均正确；探针 run_id=5 已清理，剩余 0。

# 是否还有残留风险
开工时工作区已有 backend/app、frontend/src、dev_toolkit、modules/knowledge 等外部 dirty，本任务未修改这些路径，finish_task 将其作为基线确认 new_outside_allowed_count=0。运行时只 finalize 自己打开或从 checkpoint 恢复的 run；仍有 pending approval 的 run 会停在 needs_confirmation/manual path，不伪装 completed。

# 关联 commit
未提交。
