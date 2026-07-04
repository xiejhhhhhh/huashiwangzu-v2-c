---
name: "Agent 多代理结果汇总与治理面板收口"
type: "task"
tags: [agent, workflow, multi-agent, governance, frontend, backend]
agent: "codex-agent-multi-summary-r1"
created: "2026-07-04T11:16:59.840581+00:00"
---

# 改了什么

- 新增 Agent workflow 多代理摘要聚合：`modules/agent/backend/services/workflow_summary_service.py` 只读汇总 step/tool_call/artifact/failure/verification。
- `GET /api/agent/workflows/{run_id}` 内嵌 `multi_agent_summary`，新增 `GET /api/agent/workflows/{run_id}/multi-agent-summary`，新增 capability `agent:get_multi_agent_summary`。
- Agent 前端工作流详情新增“子代理/步骤”摘要区，展示 status、completion_summary、failure_reason、reference_ids/artifact_ids、next_action，并支持空状态。
- 写入执行信要求文档：`开发文档/项目记忆/Agent多代理结果汇总与治理面板收口.md`。

# 验证了什么

- `backend/.venv/bin/ruff check modules/agent/backend` 通过。
- `backend/.venv/bin/python -m pytest modules/agent/sandbox/test_module.py modules/agent/backend/tests/test_workflow_service.py modules/agent/backend/tests/test_workflow_api.py modules/agent/backend/tests/test_workflow_runtime_link.py`：50 passed。
- `cd frontend && npm run build` 通过。
- 活栈重启后验证：`GET /api/agent/workflows` 空态正常；临时 run 样本可在详情 payload 和 `agent:get_multi_agent_summary` capability 中汇总 step/tool_call/artifact/failure/verification；临时 run 10/11 已清理。

# 是否还有残留风险

- 工作区有其他并行任务留下的 `backend/app`、`backend/tests`、`dev_toolkit`、`frontend/src`、`frontend/tests` 和项目记忆 dirty；本任务没有回滚这些改动。Agent 任务自身改动集中在 `modules/agent/` 和本条项目记忆文档。

# 关联 commit

- 未提交。
