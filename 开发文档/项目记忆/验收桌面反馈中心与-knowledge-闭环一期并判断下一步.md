---
name: "验收桌面反馈中心与 Knowledge 闭环一期并判断下一步"
type: "task"
tags: [verification, next-step, desktop, knowledge, agent, release-gate]
agent: "codex"
created: "2026-07-04T07:42:57.128649+00:00"
---

# 结论

桌面反馈中心与 Knowledge 文件产物闭环一期总体可验收：健康接口、通知、任务审计、Knowledge stats、knowledge:get_pending_count、agent:list_workflows、capability_contract_diff 均成功；release_gate preflight skip-ui 为 PASS_WITH_DEBT，无 BLOCKER。

# 当前状态

当前工作区仍有 3 个 dirty 文件：
- `frontend/src/shared/components/notification-panel.vue`：cancelled/canceled 文案小修。
- 两份项目记忆/反馈 Markdown。

# 下一步建议

先收口提交当前 3 个 dirty 文件并形成干净基线；不要马上开大规模新功能。随后优先做：
1. 反馈中心二期：从状态聚合升级为可点击、可重试、可归档、可跳转的 ActionItem。
2. Knowledge 产物质量二期：导出 format 后端强校验、chunk/fusion 去重、source unavailable 修复路径、graph ready 口径统一。
3. Agent workflow/runtime 真实链路验收与失败样本沉淀：先积累真实工具调用数据，再开工具可靠性大专项。

# 风险

未跑 UI full gate；Knowledge 仍有 158 source_unavailable 历史状态；当前 preflight 因 dirty/skip-ui/preflight 仍是 PASS_WITH_DEBT。
