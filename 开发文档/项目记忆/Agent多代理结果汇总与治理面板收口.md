# Agent 多代理结果汇总与治理面板收口

## 任务

按执行信 `执行信-Agent多代理结果汇总与治理面板.md`，把 Agent workflow 中的 step、tool_call、artifact、failure、verification 账本汇总成前端可见的“子代理/步骤”摘要面板。

## 改动

- 后端新增 `modules/agent/backend/services/workflow_summary_service.py`，只读聚合 `agent_workflow_steps`、`agent_tool_calls`、`agent_workflow_artifacts`、`agent_failure_records`、`agent_verification_results`。
- `GET /api/agent/workflows/{run_id}` 返回 `multi_agent_summary`，详情页无需额外请求也能展示摘要。
- 新增 `GET /api/agent/workflows/{run_id}/multi-agent-summary`，供前端回退和调试。
- 新增 capability `agent:get_multi_agent_summary`，统一通路可读取同一份摘要。
- `modules/agent/manifest.json` 和 `modules/agent/README.md` 已同步声明该能力与端点。
- 前端 `WorkflowDetail.vue` 增加“子代理/步骤”区，展示状态、完成摘要、失败原因、引用/产物 ID、下一步建议；空状态显示自然文案。
- 前端 `WorkflowList.vue` 在列表卡片上显示摘要数量。

## 摘要字段

```text
items[].status              running/completed/failed/blocked
items[].completion_summary  完成摘要
items[].failure_reason      失败原因
items[].reference_ids       从 result_ref/storage_ref/evidence_ref 抽取的已有引用 id
items[].artifact_ids        agent_workflow_artifacts.id
items[].tool_call_ids       agent_tool_calls.id
items[].verification_ids    agent_verification_results.id
items[].failure_ids         agent_failure_records.id
items[].next_action         continue/review_artifacts/manual 等下一步建议
```

## 边界

- 不实现 ContentPackage publish。
- 不读框架 Artifact 表。
- 不跨模块读表，只读取 Agent 自有 `agent_*` workflow 账本。
- 活栈测试数据已按 run_id 清理。

## 验证

- `backend/.venv/bin/ruff check modules/agent/backend`：通过。
- `backend/.venv/bin/python scripts/check-capability-drift.py`：通过。
- `backend/.venv/bin/python -m pytest modules/agent/sandbox/test_module.py modules/agent/backend/tests/test_workflow_service.py modules/agent/backend/tests/test_workflow_api.py modules/agent/backend/tests/test_workflow_runtime_link.py`：50 passed。
- `cd frontend && npm run build`：通过。
- 活栈验证：
  - `GET /api/agent/workflows?limit=5` 空列表正常。
  - 临时 workflow 样本可通过详情接口读到 `multi_agent_summary`。
  - `agent:get_multi_agent_summary` capability 可汇总 step/tool_call/artifact/failure/verification 样本。
  - 临时 run `10`、`11` 已清理。

## 注意

收口时工作区存在其他并行任务留下的 `backend/app`、`frontend/src`、`dev_toolkit` 和若干项目记忆改动；本任务产品改动限定在 `modules/agent/`，另按执行信写入本项目记忆文档。
