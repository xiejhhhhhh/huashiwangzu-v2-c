---
name: "Agent 证据引用点击回源闭环收口"
type: "task"
tags: [agent, workflow, evidence, frontend, backend]
agent: "codex-agent-evidence-clickback-r1"
created: "2026-07-04T11:53:05.827560+00:00"
---

# 改了什么

- 后端 workflow multi_agent_summary 保留并补齐 step/tool/artifact/verification/failure 的证据引用 metadata，其中 step input_ref/output_ref 也纳入 summary reference_ids。
- 前端新增 EvidenceReferenceList 与 evidenceReferences 归一化工具，卡片展示引用类型、id、来源工具、状态。
- file_id/source_file_id 通过 Agent API helper 带 Authorization 拉取 blob 后打开；package_id/artifact_id/document_id/chunk_id/page 显示暂不可直接打开原因。
- WorkflowDetail 的子代理摘要和账本，以及 ToolCallCard 的工具结果引用都接入统一证据卡片；SSE tool_result 的 references/result_ref 不再丢失。
- 写入收口文档：开发文档/项目记忆/Agent证据引用点击回源闭环收口.md。

# 验证了什么

- backend/.venv/bin/ruff check modules/agent/backend：通过。
- backend/.venv/bin/python -m pytest modules/agent/backend/tests/test_workflow_service.py -q：12 passed。
- backend/.venv/bin/python -m pytest modules/agent/sandbox/test_module.py -q：20 passed。
- cd frontend && npm run build：通过，仅既有 chunk size warning。
- project_toolkit call_capability agent:list_workflows：admin 角色返回 200。
- 前端扫描 any/as any/@ts-ignore/@ts-expect-error：无命中。

# 残留风险

活栈当前 list_workflows 为空，没有现成含引用 workflow 做真实 UI 点击截图；引用数据路径由服务层测试覆盖，前端接线由 vue-tsc/vite build 覆盖。

# 关联 commit

未提交。
