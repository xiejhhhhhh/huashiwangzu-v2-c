---
name: "Agent 2.0 一次性升级实施"
type: task
tags: ["agent", "v2", "upgrade", "skills", "profiles", "subagent", "scheduler", "trajectory"]
created: 2026-06-27
agent: opencode
---

Agent 模块从 1.0 升级至 2.0，完成六大能力提升：

1. **技能治理** — 实现 agent:skill_manage（list/get/create/update/delete/scan/usage/provenance/approve/reject），文件 markdown 技能兼容，审批门禁
2. **画像 2.0** — 新增用户/岗位/企业/市场四维画像 + 信号池，10个新能力，engine 上下文注入含长度控制
3. **子 Agent V2** — 批量任务、工具白名单、写保护、上下文压缩、执行轨迹、结构化结果
4. **调度增强** — scheduler 定时任务改为真调用 spawn_subagent 执行
5. **轨迹底座** — agent_trajectory_records 表 + 记录/查询能力，用户输入/工具调用/结果/纠错/信号
6. **模型补全** — 14个新 ORM 模型 + 11 个新 DB 表的迁移
