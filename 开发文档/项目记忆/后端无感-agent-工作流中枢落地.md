---
name: "后端无感 Agent 工作流中枢落地"
type: "task"
tags: [agent, workflow, capability, verification]
agent: "codex-agent-workflow-center"
created: "2026-07-03T20:10:11.227235+00:00"
---

# 改了什么
在 modules/agent 内落地 Agent 专属 workflow 中枢：新增 agent_workflow_runs/steps/tool_calls/artifacts/verification_results/failure_records 模型与幂等建表/扩列，扩展 approval/checkpoint 字段；新增 workflow_service 统一状态机、终态裁判、approval 恢复关联、tool call 脱敏记录；注册 workflow capabilities 和 /api/agent/workflows HTTP API；补前端 WorkflowList/WorkflowDetail/WorkflowStatusBadge；更新 manifest/README/sandbox/backend tests。

# 验证了什么
ruff check modules/agent 通过；agent sandbox PASS；modules/agent/backend/tests 16 passed；capability drift OK；frontend npm run build 通过；live capability create/get_workflow_status/record_verification/finalize_workflow 通过并清理探针数据。

# 残留风险
当前工作区存在 backend/app、dev_toolkit、modules/knowledge、开发文档/项目记忆 等非本任务并行/外部改动，finish_task 边界检查因此失败；本任务实现文件在 modules/agent/，未修改 framework_workflow_*。未做可视化编排器、多 agent lane、自动 push/publish。

# 关联 commit
未提交。
